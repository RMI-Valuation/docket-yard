"""M8: Atom feeds are the alert stream as a page; webhooks are subscriptions whose
recipient is a URL, confirmed by a ping and delivered signed. Both render the same
EventSummary the email does."""

import json
import xml.dom.minidom

from fastapi.testclient import TestClient

from docketyard.alerts import build, subscriptions, webhooks
from docketyard.alerts.summary import event_summary
from docketyard.web.app import create_app
from tests.test_alerts import T0, FakeSender, observe
from tests.test_alerts import store as store  # noqa: F401 — fixture re-export
from tests.test_observations import filing_row


def _forward_filing(con, tmp_path, fid="312000", docket="FD_36873_1"):
    observe(con, tmp_path, filing_row(docket=docket, fid=fid, date="8/26/2026"), 1)
    return con.execute("SELECT MAX(event_id) FROM event").fetchone()[0]


def test_summary_is_the_one_source(store):
    con, _, _, tmp_path = store
    eid = _forward_filing(con, tmp_path)
    s = event_summary(con, eid, "docketyard.org")
    assert s.kind == "filing" and s.docket == "FD 36873 (Sub-No. 1)" and s.record_id == "312000"
    assert s.first and s.url == "https://docketyard.org/filing/312000"
    assert s.lines()[0] == "FD 36873 (Sub-No. 1) — new filing 312000, 8/26/2026"
    assert s.as_dict()["date"] == "8/26/2026"  # the Board's date, as printed


def test_feeds_render_forward_events_only(store):
    con, path, _, tmp_path = store
    observe(con, tmp_path, filing_row(fid="300000", date="8/1/2026"), 1, mode="backfill")
    _forward_filing(con, tmp_path)
    con.close()
    client = TestClient(create_app(path))
    for url in ("/feed", "/d/FD-36873/feed", "/d/FD-36873/sub/1/feed"):
        r = client.get(url)
        if url.endswith("/sub/1/feed"):
            assert r.status_code == 404  # a family is addressed by its parent
            continue
        assert r.status_code == 200, url
        assert r.headers["content-type"].startswith("application/atom+xml")
        assert r.headers["cache-control"] == "public, max-age=1800"
        assert "Set-Cookie" not in r.headers
        doc = xml.dom.minidom.parseString(r.text)  # well-formed
        titles = [
            e.getElementsByTagName("title")[0].firstChild.data
            for e in doc.getElementsByTagName("entry")
        ]
        assert titles[0] == "FD 36873 (Sub-No. 1) — new filing 312000, 8/26/2026"  # newest first
        assert not any("300000" in t for t in titles)  # the backfill filing is not there
        assert "tag:docketyard.org,2026:event/" in r.text
    assert client.get("/d/FD-99999/feed").status_code == 404
    assert client.get("/feed/party/999999").status_code == 404
    sheet = client.get("/d/FD-36873").text
    assert 'type="application/atom+xml"' in sheet and 'href="/d/FD-36873/feed"' in sheet


def test_webhook_subscribe_ping_confirm_deliver_signed(store, monkeypatch):
    con, path, d, tmp_path = store
    posted = []

    def fake_post(url, payload, secret, *, delivery_id, timeout=10):
        posted.append((url, payload, secret, delivery_id))
        return webhooks.Result(200)

    monkeypatch.setattr(webhooks, "post", fake_post)
    con.close()
    app = create_app(path, sender=FakeSender())
    client = TestClient(app)
    # a plain http URL, or one with credentials, is refused before anything is stored
    r = client.post(
        "/subscribe", data={"webhook_url": "http://example.org/h", "docket": "FD 36873"}
    )
    assert r.status_code == 400
    r = client.post(
        "/subscribe",
        data={"webhook_url": "https://hooks.example.org/stb", "docket": "FD 36873"},
    )
    assert r.status_code == 200 and "hooks.example.org" in r.text
    assert "https://hooks.example.org/stb" not in r.text  # the page never echoes the URL
    url, ping, secret, delivery_id = posted[0]
    assert url == "https://hooks.example.org/stb" and delivery_id == "confirm"
    assert ping["type"] == "subscription.confirm" and ping["secret"] == secret and secret
    confirm_url = ping["confirm_url"]
    assert confirm_url.startswith("https://docketyard.org/s/confirm/")
    # stored like an address: no readable URL anywhere in the store
    from docketyard.store import db

    con = db.connect(path)
    row = con.execute(
        "SELECT email_hash, email_enc, channel, secret_enc FROM subscription"
    ).fetchone()
    assert row[2] == "webhook" and "hooks.example.org" not in (row[0] + row[1] + row[3])
    con.close()
    # confirm by pressing the button
    token = confirm_url.rsplit("/", 1)[1]
    r = client.post(f"/s/confirm/{token}")
    assert r.status_code == 200 and "POSTed to hooks.example.org" in r.text
    # a forward filing arrives; the alert goes out as a signed POST
    con = db.connect(path)
    _forward_filing(con, tmp_path)
    ids = build.build(con, "pass", now=T0)
    assert len(ids) == 1
    assert con.execute("SELECT channel FROM alert").fetchone()[0] == "webhook"
    stats = build.deliver_webhooks(con, "docketyard.org", log=lambda _: None)
    assert stats == {"sent": 1, "failed": 0}
    url, payload, secret2, delivery_id = posted[1]
    assert secret2 == secret and delivery_id == str(ids[0])
    assert payload["events"][0]["record_id"] == "312000" and payload["events"][0]["late"] is False
    assert payload["unsubscribe_url"].startswith("https://docketyard.org/s/unsubscribe/")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    assert webhooks.verify(secret, body, webhooks.sign(secret, body))
    assert not webhooks.verify(secret, body + b" ", webhooks.sign(secret, body))
    status, message_id = con.execute("SELECT status, message_id FROM alert").fetchone()
    assert status == "sent" and message_id == "http-200"
    # email delivery never touches a webhook alert, and vice versa
    assert build.deliver(con, FakeSender(), "docketyard.org")["sent"] == 0
    # unsubscribe deletes everything, from the link the delivery carried
    unsub = payload["unsubscribe_url"].rsplit("/", 1)[1]
    con.close()
    assert client.post(f"/s/unsubscribe/{unsub}").status_code == 200
    con = db.connect(path)
    assert con.execute("SELECT COUNT(*) FROM subscription").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM alert").fetchone()[0] == 0
    con.close()


def test_webhook_failures_are_retried_then_failed(store, monkeypatch):
    con, path, d, tmp_path = store
    monkeypatch.setattr(webhooks, "post", lambda *a, **k: webhooks.Result(503, "HTTP 503"))
    token = subscriptions.subscribe(
        con, "https://hooks.example.org/x", d, "pass", now=T0, channel="webhook"
    )
    sub = subscriptions.for_confirm_token(con, token)
    assert sub.channel == "webhook" and sub.secret and sub.email == "https://hooks.example.org/x"
    subscriptions.confirm(con, token, now=T0)
    _forward_filing(con, tmp_path)
    build.build(con, "pass", now=T0)
    for attempt in (1, 2, 3):
        assert build.deliver_webhooks(con, "docketyard.org", log=lambda _: None)["failed"] == 1
        status, attempts = con.execute("SELECT status, attempts FROM alert").fetchone()
        assert attempts == attempt and status == ("failed" if attempt == 3 else "pending")
    assert build.deliver_webhooks(con, "docketyard.org")["failed"] == 0  # given up, logged


def test_webhook_refuses_private_destinations(store, monkeypatch):
    con, path, d, tmp_path = store
    monkeypatch.setattr(
        webhooks.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("10.0.0.5", 443))],
    )
    try:
        webhooks.post("https://internal.example/x", {}, "s", delivery_id="t")
        raise AssertionError("connected to a private address")
    except webhooks.RefusedDestination:
        pass
    monkeypatch.setattr(
        webhooks.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("169.254.169.254", 80))],
    )
    try:
        webhooks.public_addresses("metadata.example")
        raise AssertionError("allowed the metadata address")
    except webhooks.RefusedDestination:
        pass
    assert webhooks.plausible_url("https://a.example/h")
    for bad in ("https://user:pw@a.example/h", "https://a.example/h#f", "ftp://a.example/", ""):
        assert not webhooks.plausible_url(bad), bad


def test_pass_delivers_both_channels(store, monkeypatch):
    con, path, d, tmp_path = store
    monkeypatch.setattr(webhooks, "post", lambda *a, **k: webhooks.Result(204))
    t1 = subscriptions.subscribe(con, "a@example.org", d, "pass", now=T0)
    t2 = subscriptions.subscribe(
        con, "https://hooks.example.org/y", d, "pass", now=T0, channel="webhook"
    )
    subscriptions.confirm(con, t1, now=T0)
    subscriptions.confirm(con, t2, now=T0)
    _forward_filing(con, tmp_path)
    sender = FakeSender()
    out = build.run_after_pass(con, sender, "docketyard.org", now=T0, log=lambda _: None)
    assert out["built"] == 2 and out["sent"] == 1 and out["webhooks_sent"] == 1
    assert len(sender.sent) == 1
