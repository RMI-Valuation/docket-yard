"""The forward poller: window arithmetic, the pass over a fake endpoint, the loop's
tolerance of a failing pass."""

from datetime import date

import pytest

from docketyard import cli
from docketyard.capture import poll, walk
from docketyard.capture.stb import DECISIONS, DOCKETS, FILINGS
from docketyard.store import db, projections
from tests.test_dockets_parse import make_body
from tests.test_observations import body_of, decision_row, filing_row
from tests.test_walk import NO_RESULTS


class FakeStb:
    """One page per table (or the same full page forever); records every criteria list
    sent; serves a PDF for any URL; can fail one table's transport."""

    def __init__(self, bodies, *, endless=False, dead=()):
        self.bodies = bodies
        self.endless = endless
        self.dead = dead
        self.criteria_sent = []
        self.fetched = []
        self.refreshes = 0

    def refresh_nonces(self):
        self.refreshes += 1

    def query_table(self, action, criteria, *, page, per_page, sort_by, sort_order):
        self.criteria_sent.append(list(criteria))
        if action in self.dead:
            raise RuntimeError("HTTP 503 after retries")
        fields = [  # as stb.build_fields does: name AND value, so the ledger reads the same
            pair
            for i, (n, v) in enumerate(criteria)
            for pair in (
                (f"search-criteria[{i}][name]", n),
                (f"search-criteria[{i}][value]", v),
            )
        ]
        # a table this fake was not given, or a page past the end: the no-results envelope,
        # which is what the endpoint sends — with the fields it was asked with, as the real
        # client returns them
        if action not in self.bodies or (page > 1 and not self.endless):
            return 200, NO_RESULTS, fields
        return 200, self.bodies[action], fields

    def get(self, url):
        self.fetched.append(url)
        return 200, b"%PDF-1.4 fake"

    def fetcher(self, data_dir):
        return lambda url: self.download(url, data_dir)

    def download(self, url, into):  # the production fetcher: a file on the blob filesystem
        from pathlib import Path

        status, body = self.get(url)
        tmp = Path(into) / "blobs" / ".tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        path = tmp / f"dl-{len(self.fetched)}"
        path.write_bytes(body)
        return status, path


def test_window_is_inclusive_and_spelled_like_the_endpoint():
    assert poll.window(date(2026, 8, 25)) == ("08/19/2026", "08/25/2026")
    assert poll.window(date(2026, 1, 2), days=3) == ("12/31/2025", "01/02/2026")


def test_forward_pass_captures_ingests_and_fetches(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    client = FakeStb(
        {
            FILINGS: body_of(filing_row(fid="311981", date="8/25/2026"), 1),
            DECISIONS: body_of(decision_row(did="53210", date="8/24/2026"), 1),
        }
    )
    lines = []
    summary = poll.forward_pass(con, client, tmp_path, today=date(2026, 8, 25), log=lines.append)
    assert summary["window"] == ("08/19/2026", "08/25/2026")
    assert summary["captured"] == {FILINGS: "done", DECISIONS: "done"}
    assert summary["problems"] == []
    status = projections.status(con)
    assert status["filings"] == 1 and status["decisions"] == 1
    assert status["attachments_unfetched"] == 0 and len(client.fetched) == 2
    assert lines[-1].startswith("poll 08/19/2026..08/25/2026")
    # the criteria went through the pair that filters, never officialFilingStartDate
    sent = {name for criteria in client.criteria_sent for name, _ in criteria}
    assert {"filingStartDate", "filingEndDate", "serviceStartDate", "serviceEndDate"} <= sent
    assert "officialFilingStartDate" not in sent
    assert client.refreshes == 1  # fresh nonces every pass, never one for the container's life

    # the overlapping window on the next pass: requests, but no new records, events or fetches
    before = projections.status(con)
    again = poll.forward_pass(con, client, tmp_path, today=date(2026, 8, 25), log=lambda _: 0)
    after = projections.status(con)
    assert again["problems"] == [] and again["fetched"]["fetched"] == 0
    # one page per table, and NO second caption ask: FD 36873's caption was asked about on
    # the first pass and the ledger holds that ask, so the second pass inside the retry
    # window does not repeat it (stb-ingest-specialist, 2026-08-31 — an uncaptioned docket
    # that keeps receiving records must not be asked about every half hour for 45 days)
    assert after["captures"] == before["captures"] + 2
    assert again["captions"]["asked"] == 0 and again["captions"]["captioned"] == 0
    for key in ("filings", "decisions", "documents", "events"):
        assert after[key] == before[key], key
    assert again["rechecked"]["fetched"] == 0  # nothing held is 30 days unchecked yet
    # a month on, the held files are due: the pass re-fetches them, oldest-checked first,
    # under its own limit, and a replaced file is an erratum event that alerts
    con.execute("UPDATE capture SET captured_at = '2026-07-01T00:00:00+00:00'")
    con.commit()
    client.get = lambda url: (client.fetched.append(url), (200, b"%PDF-1.4 replaced"))[1]
    passes = lambda: poll.forward_pass(  # noqa: E731
        con, client, tmp_path, today=date(2026, 8, 25), log=lambda _: 0, recheck_limit=1
    )
    third = passes()
    assert third["rechecked"]["fetched"] == 1 and third["rechecked"]["replaced"] == 1
    replaced = "SELECT COUNT(*) FROM event WHERE event_type = 'document_replaced'"
    assert con.execute(replaced).fetchone()[0] == 1
    assert passes()["rechecked"]["fetched"] == 1  # the other one; the first is checked now
    assert passes()["rechecked"]["fetched"] == 0  # both checked within the month


def test_a_pass_over_a_dead_endpoint_reports_rather_than_raises(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    client = FakeStb({FILINGS: NO_RESULTS, DECISIONS: NO_RESULTS})
    summary = poll.forward_pass(con, client, tmp_path, today=date(2026, 8, 25), log=lambda _: 0)
    assert len(summary["problems"]) == 2  # both slices quarantined, nothing ingested
    assert all("TRAP: no-results envelope on page 1" in p for p in summary["problems"])
    assert projections.status(con)["captures_quarantined"] == 2


def test_one_table_down_does_not_cost_the_other(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    client = FakeStb(
        {FILINGS: b"", DECISIONS: body_of(decision_row(did="53210", date="8/24/2026"), 1)},
        dead=(FILINGS,),
    )
    summary = poll.forward_pass(con, client, tmp_path, today=date(2026, 8, 25), log=lambda _: 0)
    assert summary["captured"] == {FILINGS: "failed", DECISIONS: "done"}
    assert summary["problems"] == [
        f"{FILINGS}: capture failed (RuntimeError: HTTP 503 after retries)"
    ]
    assert projections.status(con)["decisions"] == 1 and len(client.fetched) == 1


def test_the_page_ceiling_is_loud(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    full_page = "".join(filing_row(fid=str(311000 + i)) for i in range(50))
    client = FakeStb(
        {FILINGS: body_of(full_page, 5000), DECISIONS: body_of(decision_row(), 1)}, endless=True
    )
    summary = poll.forward_pass(con, client, tmp_path, today=date(2026, 8, 25), log=lambda _: 0)
    assert summary["captured"][FILINGS] == "partial"
    assert any(f"page limit {poll.PAGES} reached" in p for p in summary["problems"])


def test_window_floor():
    with pytest.raises(ValueError, match="at least"):
        poll.forward_pass(None, None, None, days=1)
    with pytest.raises(SystemExit):  # and the CLI refuses before any loop could swallow it
        cli.main(["poll", "--days", "2", "--every", "1"])


def test_search_page_down_still_ingests_what_is_pending(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    client = FakeStb({FILINGS: body_of(filing_row(), 1), DECISIONS: body_of(decision_row(), 1)})
    # a pass that captured but was interrupted before ingest: simulate by ingesting nothing
    walk.capture_slice(
        con,
        client,
        FILINGS,
        [("filingStartDate", "08/19/2026"), ("filingEndDate", "08/25/2026")],
        data_dir=tmp_path,
        mode="forward",
        log=lambda *_: None,
    )
    assert projections.status(con)["captures_unprocessed"] >= 1

    def down():
        raise RuntimeError("search page unreachable")

    client.refresh_nonces = down
    summary = poll.forward_pass(con, client, tmp_path, today=date(2026, 8, 25), log=lambda _: 0)
    assert summary["captured"] == {FILINGS: "skipped", DECISIONS: "skipped"}
    assert summary["problems"][0].startswith("nonce refresh failed")
    assert projections.status(con)["filings"] == 1  # the pending capture was still consumed


def test_run_forever_survives_a_failing_pass(monkeypatch):
    calls = []
    sleeps = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("endpoint down")
        if len(calls) == 3:
            raise KeyboardInterrupt  # our way out of forever; not an Exception, so not caught

    monkeypatch.setattr(poll.time, "sleep", sleeps.append)
    try:
        poll.run_forever(flaky, every=0, log=lambda _: None)
    except KeyboardInterrupt:
        pass
    assert len(calls) == 3 and len(sleeps) == 2


def test_a_new_proceeding_gains_its_caption_from_the_dockets_table(tmp_path):
    """A proceeding reaches the filings table before the dockets table, so its docket row
    is minted from the filing and has no caption — three such dockets were reading
    "(caption not yet observed)" on the live home page (the operator, 2026-08-31). The
    pass asks the dockets table about each one, by prefix and number, and the caption
    arrives on the next pass rather than waiting for a re-walk of the whole registry."""
    con = db.connect(tmp_path / "s.sqlite")
    client = FakeStb(
        {
            FILINGS: body_of(filing_row(docket="AB_290_423_X", fid="311981", date="8/25/2026"), 1),
            DECISIONS: body_of(
                decision_row(docket="AB_290_423_X", did="53210", date="8/24/2026"), 1
            ),
            DOCKETS: make_body([("AB_290_423_X", "NORFOLK SOUTHERN — ABANDONMENT — POLK CO.")], 1),
        }
    )
    summary = poll.forward_pass(con, client, tmp_path, today=date(2026, 8, 25), log=lambda _: 0)
    assert summary["problems"] == []
    assert summary["captions"]["asked"] == 1 and summary["captions"]["captioned"] == 1
    title = con.execute(
        "SELECT json_extract(latest_payload, '$.title') FROM docket_current"
        " WHERE raw_docket = 'AB_290_423_X'"
    ).fetchone()[0]
    assert title == "NORFOLK SOUTHERN — ABANDONMENT — POLK CO."
    # the question was asked as the endpoint requires: the family, by prefix and number
    # the question names the DOCKET, not its family: `docketNum_three` is the
    # sub-sequence (measured against the live endpoint 2026-08-31 — asking AB 290 by
    # family answers 392 rows, asking AB 290 (Sub-No. 423) answers one), so the ask
    # costs one request and cannot be truncated by a thousand-member family
    assert ["docketNum_one", "docketNum_two", "docketNum_three"] in [
        [n for n, _ in c] for c in client.criteria_sent
    ]
    assert ("docketNum_three", "423") in [pair for c in client.criteria_sent for pair in c]
    # and it is not asked again once answered
    again = poll.forward_pass(con, client, tmp_path, today=date(2026, 8, 25), log=lambda _: 0)
    assert again["captions"]["asked"] == 0


def test_a_caption_the_board_does_not_publish_stops_being_asked_about(tmp_path):
    """The ~2,400 parents minted for sub-dockets (`AB_1_0`, implied by `AB_1_6`) hold no
    records of their own and must never be asked about, or every pass would ask for ever."""
    con = db.connect(tmp_path / "s.sqlite")
    client = FakeStb(
        {
            FILINGS: body_of(filing_row(docket="AB_290_423_X", fid="311981", date="8/25/2026"), 1),
            DECISIONS: body_of(
                decision_row(docket="AB_290_423_X", did="53210", date="8/24/2026"), 1
            ),
        }
    )
    poll.forward_pass(con, client, tmp_path, today=date(2026, 8, 25), log=lambda _: 0)
    # the minted parent exists and has no caption, and is not one of the questions asked
    assert (
        con.execute("SELECT COUNT(*) FROM docket WHERE raw_docket = 'AB_290_0'").fetchone()[0] == 1
    )
    asked = [(p, q, sub) for _, p, q, sub in poll._uncaptioned(con, date(2026, 8, 25))]
    assert asked == [("AB", 290, 423)]  # the sub-docket itself, never the bare parent
    # and a record too old to be new stops the question
    assert poll._uncaptioned(con, date(2027, 1, 1)) == []


def test_a_docket_the_board_never_publishes_is_asked_about_a_bounded_number_of_times(tmp_path):
    """The first draft asked by FAMILY and forever: `AB 55` would have cost 20 requests
    every half hour for 45 days — ~43,000 asks to learn one caption — and its thousand-row
    family would not even have reached the docket in question (stb-ingest-specialist,
    2026-08-31). It now asks about the docket itself, once per retry window, and stops
    after CAPTION_ATTEMPTS with a problem naming what it gave up on."""
    con = db.connect(tmp_path / "s.sqlite")
    client = FakeStb(
        {  # no dockets body: the Board has not published this proceeding's row, ever
            FILINGS: body_of(filing_row(docket="AB_55_827_X", fid="311981", date="8/25/2026"), 1),
            DECISIONS: body_of(
                decision_row(docket="AB_55_827_X", did="53210", date="8/24/2026"), 1
            ),
        }
    )
    retry = poll.CAPTION_RETRY_HOURS
    poll.CAPTION_RETRY_HOURS = 0  # a burst of passes in one second still exercises the cap
    try:
        summaries = [
            poll.forward_pass(con, client, tmp_path, today=date(2026, 8, 25), log=lambda _: 0)
            for _ in range(poll.CAPTION_ATTEMPTS + 2)
        ]
    finally:
        poll.CAPTION_RETRY_HOURS = retry
    asks = [c for c in client.criteria_sent if any(n == "docketNum_one" for n, _ in c)]
    assert len(asks) == poll.CAPTION_ATTEMPTS  # bounded, and never once per family page
    assert all(len(c) == 3 for c in asks)  # prefix, sequence, sub-sequence: one docket
    assert summaries[-1]["captions"]["asked"] == 0
    assert any("asked about" in p and "no longer asked" in p for p in summaries[-1]["problems"])
