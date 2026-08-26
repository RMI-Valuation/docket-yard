"""Subscriptions and alerts end to end over the small real-shaped store: confirm, the
join above the high-water mark, the family fold, the daily digest, late marking,
delivery through a fake session, and unsubscribe-as-deletion."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from docketyard.alerts import build, mail, subscriptions, vault
from docketyard.capture import records
from docketyard.capture.stb import FILINGS
from docketyard.ingest import observations
from docketyard.store import db
from docketyard.web.app import create_app
from tests.test_observations import body_of, filing_row
from tests.test_web import build_store

T0 = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


class FakeSender(mail.Sender):
    """Records instead of sending; `session()` yields a recorder with the same shape."""

    def __new__(cls):
        self = super().__new__(cls)
        object.__setattr__(self, "from_address", "Docket Yard <alerts@docketyard.org>")
        object.__setattr__(self, "region", "us-east-2")
        object.__setattr__(self, "username", "u")
        object.__setattr__(self, "password", "p")
        object.__setattr__(self, "sent", [])
        object.__setattr__(self, "fail_with", None)
        return self

    def __init__(self):
        pass

    def send(self, out):
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append(out)
        return "id-1"

    def session(self):
        sender = self

        class S:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def send(self_inner, out):
                return sender.send(out)

        return S()


def observe(con, tmp_path, rows_html, total, mode="forward"):
    cid = records.save_capture(
        con,
        tmp_path,
        source_system="stb-ajax",
        endpoint="test",
        table_action=FILINGS,
        request_params=[],
        body=body_of(rows_html, total),
        http_status=200,
        ingest_mode=mode,
    )
    records.set_verdict(con, cid, filter_asserted=True, row_count=total, reported_total=total)
    return observations.ingest_capture(con, tmp_path, cid)


@pytest.fixture
def store(tmp_path):
    path = build_store(tmp_path)  # FD 36873 + Sub-No. 1, three filings, one decision
    con = db.connect(path)
    docket_id = con.execute(
        "SELECT docket_id FROM docket WHERE raw_docket = 'FD_36873'"
    ).fetchone()[0]
    return con, path, docket_id, tmp_path


def test_subscribe_confirm_sets_the_mark_at_the_ledger_head(store):
    con, _, d, _ = store
    token = subscriptions.subscribe(con, " A@Example.org ", d, "pass", now=T0)
    assert token and len(token) >= 40
    assert subscriptions.subscribe(con, "a@example.org", d, "daily", now=T0) != token  # resend
    assert subscriptions.confirm(con, "not-a-token", now=T0) is None
    sub = subscriptions.confirm(con, token, now=T0)  # the first link still works
    assert sub.status == "active" and sub.cadence == "daily" and sub.email == "a@example.org"
    head = con.execute("SELECT MAX(event_id) FROM event").fetchone()[0]
    mark = con.execute("SELECT high_water_event_id FROM subscription").fetchone()[0]
    assert mark == head  # nothing already in the ledger will ever be sent
    assert subscriptions.subscribe(con, "a@example.org", d, "pass", now=T0) is None  # active
    assert build.pending_events(con, "daily") == []


def test_confirmation_mail_is_rate_limited_and_links_expire(store):
    con, _, d, _ = store
    tokens = [subscriptions.subscribe(con, "b@example.org", d, "pass", now=T0) for _ in range(4)]
    assert all(tokens[:3]) and tokens[3] is None
    late = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    assert subscriptions.confirm(con, tokens[2], now=late) is None
    assert subscriptions.sweep(con, now=late) == 1  # the stranger's address is gone
    assert con.execute("SELECT COUNT(*) FROM subscription").fetchone()[0] == 0


def test_alert_join_family_fold_forward_only_and_delivery(store):
    con, _, d, tmp_path = store
    token = subscriptions.subscribe(con, "c@example.org", d, "pass", now=T0)
    subscriptions.confirm(con, token, now=T0)
    # a backfill capture after confirmation never alerts; a forward one on the sub-docket does
    observe(con, tmp_path, filing_row(fid="300000", date="8/1/2026"), 1, mode="backfill")
    observe(con, tmp_path, filing_row(docket="FD_36873_1", fid="312000", date="8/26/2026"), 1)
    pending = build.pending_events(con, "pass")
    assert [p.docket_raw for p in pending] == ["FD_36873_1"]
    ids = build.build(con, "pass", now=T0)
    assert len(ids) == 1 and build.pending_events(con, "pass") == []  # the mark advanced
    sender = FakeSender()
    stats = build.deliver(con, sender, "docketyard.org", log=lambda _: None)
    assert stats == {"sent": 1, "failed": 0, "suppressed": 0}
    out = sender.sent[0]
    assert out.to == "c@example.org" and out.subject == "FD 36873 (Sub-No. 1): 1 new entry"
    assert "new filing 312000" in out.text and "https://docketyard.org/filing/312000" in out.text
    assert out.unsubscribe_url.startswith("https://docketyard.org/s/unsubscribe/")
    assert "delivered late" not in out.text
    status, message_id = con.execute("SELECT status, message_id FROM alert").fetchone()
    assert status == "sent" and message_id == "id-1"
    # a second delivery pass sends nothing
    assert build.deliver(con, sender, "docketyard.org")["sent"] == 0 and len(sender.sent) == 1


def test_daily_digest_is_one_email_across_dockets(store):
    con, _, d, tmp_path = store
    sub_id = con.execute("SELECT docket_id FROM docket WHERE raw_docket = 'FD_36873_1'").fetchone()[
        0
    ]
    for docket_id in (d, sub_id):  # parent AND sub-docket: overlapping subscriptions
        subscriptions.confirm(
            con, subscriptions.subscribe(con, "e@example.org", docket_id, "daily", now=T0), now=T0
        )
    observe(con, tmp_path, filing_row(docket="FD_36873_1", fid="312001", date="8/26/2026"), 1)
    early = datetime(2026, 8, 26, 20, 0, tzinfo=UTC)  # 16:00 Eastern: not yet
    assert not build.daily_due(con, early)
    due = datetime(2026, 8, 27, 3, 30, tzinfo=UTC)  # 23:30 Eastern on the 26th
    assert build.daily_due(con, due)
    ids = build.build(con, "daily", now=due)
    assert len(ids) == 1  # one message, both subscriptions, the shared event once each
    assert con.execute("SELECT COUNT(*) FROM alert_event").fetchone()[0] == 2
    assert not build.daily_due(con, due)  # built for today
    # a pass that misses the 23:00 hour still owes the digest until the next boundary
    after_midnight = datetime(2026, 8, 27, 5, 0, tzinfo=UTC)  # 01:00 Eastern
    assert not build.daily_due(con, after_midnight)  # today's was built
    con.execute("UPDATE alert SET created_at = '2026-08-25T03:30:00+00:00'")  # two nights ago
    con.commit()
    assert build.daily_due(con, after_midnight)  # nothing since yesterday's 23:00: owed
    # the digest's unsubscribe link stops every daily docket, not just one
    observe(con, tmp_path, filing_row(docket="FD_36873_1", fid="312009", date="8/27/2026"), 1)
    build.build(con, "daily", now=due)
    sender = FakeSender()
    build.deliver(con, sender, "docketyard.org")
    token = sender.sent[0].unsubscribe_url.rsplit("/", 1)[1]
    assert subscriptions.unsubscribe(con, token)
    assert con.execute("SELECT COUNT(*) FROM subscription").fetchone()[0] == 0


def test_late_events_are_marked_from_capture_spacing(store):
    con, _, d, tmp_path = store
    subscriptions.confirm(con, subscriptions.subscribe(con, "f@example.org", d, "pass"), now=T0)
    con.execute("UPDATE capture SET captured_at = '2026-08-26T00:00:00+00:00'")
    con.commit()
    # the recovery pass: two table captures seconds apart, nine hours after the last one
    observe(con, tmp_path, filing_row(fid="312002", date="8/26/2026"), 1)
    con.execute(
        "UPDATE capture SET captured_at = '2026-08-26T09:00:00+00:00'"
        " WHERE capture_id = (SELECT MAX(capture_id) FROM capture)"
    )
    observe(con, tmp_path, filing_row(fid="312003", date="8/26/2026"), 1)
    con.execute(
        "UPDATE capture SET captured_at = '2026-08-26T09:00:04+00:00'"
        " WHERE capture_id = (SELECT MAX(capture_id) FROM capture)"
    )
    con.execute(
        "INSERT INTO coverage_gap (started_at, failure) VALUES ('2026-08-26T00:30', 'captures')"
    )
    con.execute(  # an unrelated old documents gap must not be the one cited
        "INSERT INTO coverage_gap (started_at, ended_at, failure)"
        " VALUES ('2026-07-10', '2026-07-12', 'documents')"
    )
    con.commit()
    pending = build.pending_events(con, "pass")
    assert [p.late for p in pending] == [True, True]  # both captures of the pass are late
    build.build(con, "pass")
    sender = FakeSender()
    build.deliver(con, sender, "docketyard.org")
    assert "delivered late" in sender.sent[0].text and "2026-08-26T00:30" in sender.sent[0].text
    assert "2026-07-10" not in sender.sent[0].text


def test_delivery_claims_the_attempt_before_sending_and_survives_a_dropped_line(store):
    import smtplib

    con, _, d, tmp_path = store
    subscriptions.confirm(con, subscriptions.subscribe(con, "h@example.org", d, "pass"), now=T0)
    observe(con, tmp_path, filing_row(fid="312004", date="8/26/2026"), 1)
    build.build(con, "pass")
    sender = FakeSender()
    sender.fail_with = smtplib.SMTPServerDisconnected("gone")
    stats = build.deliver(con, sender, "docketyard.org", log=lambda _: None)
    assert stats["sent"] == 0 and stats["failed"] == 0
    status, attempts = con.execute("SELECT status, attempts FROM alert").fetchone()
    assert (status, attempts) == ("pending", 0)  # a transport failure is not this message's
    sender.fail_with = smtplib.SMTPDataError(554, b"rejected")
    for _ in range(build.MAX_ATTEMPTS):
        build.deliver(con, sender, "docketyard.org", log=lambda _: None)
    status, attempts = con.execute("SELECT status, attempts FROM alert").fetchone()
    assert (status, attempts) == ("failed", build.MAX_ATTEMPTS)  # a refusal is, and it caps
    assert build.deliver(con, sender, "docketyard.org")["sent"] == 0


def test_no_sender_builds_nothing_so_the_backlog_folds(store):
    con, _, d, tmp_path = store
    subscriptions.confirm(con, subscriptions.subscribe(con, "i@example.org", d, "pass"), now=T0)
    observe(con, tmp_path, filing_row(fid="312005", date="8/26/2026"), 1)
    assert build.run_after_pass(con, None, "docketyard.org")["built"] == 0
    assert con.execute("SELECT COUNT(*) FROM alert").fetchone()[0] == 0
    assert len(build.pending_events(con, "pass")) == 1  # still waiting, mark untouched
    # a webhook subscription does not wait for mail: it is built and delivered regardless
    from unittest import mock

    from docketyard.alerts import webhooks

    subscriptions.confirm(
        con,
        subscriptions.subscribe(con, "https://h.example/x", d, "pass", channel="webhook"),
        now=T0,
    )
    observe(con, tmp_path, filing_row(fid="312006", date="8/26/2026"), 1)
    with mock.patch.object(webhooks, "post", return_value=webhooks.Result(200)):
        out = build.run_after_pass(con, None, "docketyard.org")
    assert out["built"] == 1 and out["webhooks_sent"] == 1 and out["skipped"] == "no sender"
    assert len(build.pending_events(con, "pass", "email")) == 2  # email still folding


def test_web_flow_subscribe_confirm_unsubscribe(store):
    con, path, d, _ = store
    con.close()
    sender = FakeSender()
    client = TestClient(create_app(path, sender=sender))
    r = client.post("/subscribe", data={"email": "G@Example.org", "docket": "FD 36873 (Sub-No. 1)"})
    assert r.status_code == 200 and "Check your inbox" in r.text
    assert "Set-Cookie" not in r.headers
    assert len(sender.sent) == 1 and sender.sent[0].to == "g@example.org"
    link = next(w for w in sender.sent[0].text.split() if "/s/confirm/" in w)
    token = link.rsplit("/", 1)[1]
    # a fetch is not consent: a mail-security gateway following the link changes nothing
    r = client.get(f"/s/confirm/{token}")
    assert r.status_code == 200 and "Confirm" in r.text
    con = db.connect(path)
    assert con.execute("SELECT status FROM subscription").fetchone()[0] == "pending"
    con.close()
    # the family's parent is what was subscribed, whatever docket the form named
    r = client.post(f"/s/confirm/{token}")
    assert r.status_code == 200 and "following FD 36873" in r.text
    assert client.post(f"/s/confirm/{token}").status_code == 404  # single use
    # the same page whatever the address's state (no enumeration)
    again = client.post("/subscribe", data={"email": "g@example.org", "docket": "FD 36873"})
    assert again.status_code == 200 and "Check your inbox" in again.text
    assert len(sender.sent) == 1  # already active: nothing more is mailed
    assert (
        client.post("/subscribe", data={"email": "nope", "docket": "FD 36873"}).status_code == 400
    )
    # a mail failure shows the same page and gives the rate-limit slot back
    sender.fail_with = RuntimeError("smtp down")
    r = client.post("/subscribe", data={"email": "h@example.org", "docket": "FD 36873"})
    assert r.status_code == 200 and "Check your inbox" in r.text
    con = db.connect(path)
    confirms = "SELECT COUNT(*) FROM subscription_token WHERE purpose = 'confirm'"
    assert con.execute(confirms).fetchone()[0] == 0
    con.close()
    sender.fail_with = None
    con = db.connect(path)
    sid = con.execute("SELECT subscription_id FROM subscription").fetchone()[0]
    unsub = subscriptions.unsubscribe_token(con, sid)
    con.commit()
    con.close()
    assert "Unsubscribe" in client.get(f"/s/unsubscribe/{unsub}").text  # a page, not an action
    assert client.post(f"/s/unsubscribe/{unsub}").status_code == 200
    con = db.connect(path)
    gone = "SELECT COUNT(*) FROM subscription WHERE email_hash = ?"
    assert con.execute(gone, (vault.current().hash("g@example.org"),)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM subscription_token").fetchone()[0] == 0
    assert client.post(f"/s/unsubscribe/{unsub}").status_code == 200  # idempotent, same answer


def test_sheet_offers_the_follow_form(store):
    _, path, _, _ = store
    client = TestClient(create_app(path))
    r = client.get("/d/FD-36873")
    assert 'action="/subscribe"' in r.text and 'name="cadence" value="daily"' in r.text
    # without a configured sender the form must not claim a mail is on its way
    r = client.post("/subscribe", data={"email": "x@example.org", "docket": "FD 36873"})
    assert r.status_code == 503 and "not available" in r.text
    con = db.connect(path)
    assert con.execute("SELECT COUNT(*) FROM subscription").fetchone()[0] == 0


def test_subscribe_by_party_alerts_filings_across_dockets_and_never_decisions(store):
    from docketyard.parties import resolve

    con, path, d, tmp_path = store
    resolve.run(con, log=lambda _: 0)  # NRDC and PPU become parties
    nrdc = con.execute("SELECT party_id FROM party WHERE founding_key = 'nrdc'").fetchone()[0]
    with pytest.raises(ValueError):
        subscriptions.subscribe(con, "p@example.org", d, "pass", party_id=nrdc)
    token = subscriptions.subscribe(con, "p@example.org", None, "pass", party_id=nrdc)
    sub = subscriptions.confirm(con, token, now=T0)
    assert sub.party_id == nrdc and sub.docket_id is None
    # a new filing for NRDC in another docket, a decision, and a filing for someone else
    observe(
        con,
        tmp_path,
        filing_row(docket="AB_55", fid="400001", date="8/26/2026", filed_for="NRDC", pdf="a.pdf"),
        1,
    )
    observe(
        con,
        tmp_path,
        filing_row(docket="AB_55", fid="400002", date="8/26/2026", filed_for="PPU", pdf="b.pdf"),
        1,
    )
    resolve.run(con, log=lambda _: 0)
    pending = build.pending_events(con, "pass")
    assert [p.docket_raw for p in pending] == ["AB_55"]
    assert build.build(con, "pass", now=T0) and build.pending_events(con, "pass") == []
    sender = FakeSender()
    build.deliver(con, sender, "docketyard.org", log=lambda _: None)
    out = sender.sent[0]
    assert out.subject == "NRDC: 1 new filing" and "400001" in out.text and "400002" not in out.text
    # the web form: a party predicate, the confirmation names the party
    client = TestClient(create_app(path, sender=sender))
    r = client.post("/subscribe", data={"email": "q@example.org", "party": str(nrdc)})
    assert r.status_code == 200 and "filings for NRDC" in r.text
    link = next(w for w in sender.sent[-1].text.split() if "/s/confirm/" in w)
    r = client.post(f"/s/confirm/{link.rsplit('/', 1)[1]}")
    assert r.status_code == 200 and "following filings for NRDC" in r.text
    assert (
        client.post("/subscribe", data={"email": "q@example.org", "party": "999999"}).status_code
        == 404
    )
    assert 'name="party" value="' in client.get("/parties", params={"name": "nrdc"}).text
