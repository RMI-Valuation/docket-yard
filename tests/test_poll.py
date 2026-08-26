"""The forward poller: window arithmetic, the pass over a fake endpoint, the loop's
tolerance of a failing pass."""

from datetime import date

import pytest

from docketyard import cli
from docketyard.capture import poll, walk
from docketyard.capture.stb import DECISIONS, FILINGS
from docketyard.store import db, projections
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
        if page > 1 and not self.endless:
            return 200, NO_RESULTS, []
        return (
            200,
            self.bodies[action],
            [(f"search-criteria[{i}][name]", n) for i, (n, _) in enumerate(criteria)],
        )

    def get(self, url):
        self.fetched.append(url)
        return 200, b"%PDF-1.4 fake"

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
    assert after["captures"] == before["captures"] + 2  # one page per table; no fetch captures
    for key in ("filings", "decisions", "documents", "events"):
        assert after[key] == before[key], key


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
