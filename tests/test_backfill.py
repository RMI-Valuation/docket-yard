"""Backfill waves: month slicing in the endpoint's spelling, the wave over a fake endpoint,
resumability, and the guarantee that nothing a wave observes can alert."""

from datetime import date

from docketyard.alerts import build, subscriptions
from docketyard.capture import backfill, walk
from docketyard.capture.stb import DECISIONS, FILINGS
from docketyard.store import coverage, db
from tests.test_observations import body_of, decision_row, filing_row
from tests.test_walk import NO_RESULTS


def test_month_slices_cover_the_range_inclusively_with_the_filtering_pair():
    slices = walk.month_slices(FILINGS, date(2024, 8, 15), date(2024, 10, 3))
    assert [s.key for s in slices] == [
        "2024-08:2024-08-15..2024-08-31",  # a partial month carries its day range
        "2024-09",
        "2024-10:2024-10-01..2024-10-03",
    ]
    assert slices[0].criteria == [
        ("filingStartDate", "08/15/2024"),
        ("filingEndDate", "08/31/2024"),
    ]
    assert slices[-1].criteria == [
        ("filingStartDate", "10/01/2024"),
        ("filingEndDate", "10/03/2024"),
    ]
    assert walk.month_slices(DECISIONS, date(2026, 2, 1), date(2026, 2, 28))[0].criteria[0] == (
        "serviceStartDate",
        "02/01/2026",
    )
    assert all("officialFilingStartDate" not in dict(s.criteria) for s in slices)


class FakeStb:
    """Answers one page per month slice from a table keyed by the start criterion."""

    def __init__(self, pages):
        self.pages = pages
        self.requests = 0
        self.fetched = []

    def refresh_nonces(self):
        pass

    def query_table(self, action, criteria, *, page, per_page, sort_by, sort_order):
        self.requests += 1
        start = dict(criteria)[list(dict(criteria))[0]]
        body = self.pages.get((action, start))
        if page > 1 or body is None:
            return 200, NO_RESULTS, []
        return 200, body, [("search-criteria[0][name]", "x")]

    def get(self, url):
        self.fetched.append(url)
        return 200, b"%PDF-1.4 old"


def test_wave_walks_ingests_fetches_and_never_alerts(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    client = FakeStb(
        {
            (FILINGS, "08/01/2024"): body_of(
                filing_row(fid="200001", date="8/12/2024", pdf="200001.pdf"), 1
            ),
            (FILINGS, "09/01/2024"): body_of(
                filing_row(fid="200002", date="9/3/2024", pdf="200002.pdf"), 1
            ),
            (DECISIONS, "08/01/2024"): body_of(decision_row(did="40001", date="8/20/2024"), 1),
        }
    )
    summary = backfill.wave(
        con, client, tmp_path, date(2024, 8, 1), date(2024, 9, 30), log=lambda _: 0
    )
    docket_id = con.execute(
        "SELECT docket_id FROM docket WHERE raw_docket = 'FD_36873'"
    ).fetchone()[0]
    assert summary[FILINGS]["done"] == 2
    # September decisions: the no-results envelope on page 1 is the trap, never "empty"
    assert summary[DECISIONS]["done"] == 1 and summary[DECISIONS]["partial"] == 1
    assert summary[f"{FILINGS}:ingest"]["captures"] >= 1
    assert summary["documents"]["fetched"] == 3
    status = con.execute("SELECT COUNT(*) FROM filing").fetchone()[0]
    assert status == 2
    # everything the wave observed is stamped backfill
    modes = {r[0] for r in con.execute("SELECT DISTINCT ingest_mode FROM capture")}
    assert modes == {"backfill"}
    # a subscriber confirmed now has a mark at the head; but even a mark of 0 would not
    # alert on backfill events — the join filters on the capture's mode
    subscriptions.confirm(
        con, subscriptions.subscribe(con, "w@example.org", docket_id, "pass"), now=None
    )
    con.execute("UPDATE subscription SET high_water_event_id = 0")
    con.commit()
    assert build.pending_events(con, "pass") == []
    # coverage reports the wave
    cov = coverage.coverage(con)
    assert cov.backfill_from == "2024-08-12" and cov.backfill_filings == 2
    assert cov.backfill_decisions == 1
    # a second run is a no-op plus requests for the slice that ended partial
    before = client.requests
    again = backfill.wave(
        con, client, tmp_path, date(2024, 8, 1), date(2024, 9, 30), log=lambda _: 0
    )
    assert again[FILINGS]["skipped"] == 2 and again[DECISIONS]["skipped"] == 1
    assert client.requests - before <= 2 and again["documents"]["fetched"] == 0


def test_wave_ends_where_the_watch_began(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    assert backfill.forward_since(con) is None
    con.execute(
        "INSERT INTO capture (source_system, endpoint, request_params, response_sha256,"
        " http_status, filter_asserted, ingest_mode, captured_at, table_action)"
        " VALUES ('s', 'e', '[]', 'x', 200, 1, 'forward', '2026-08-26T01:21:09+00:00', ?)",
        (FILINGS,),
    )
    con.commit()
    assert backfill.forward_since(con) == date(2026, 8, 26)


def test_a_wider_rerun_does_not_skip_a_partly_walked_month():
    narrow = walk.month_slices(FILINGS, date(2024, 8, 15), date(2024, 8, 31))
    wide = walk.month_slices(FILINGS, date(2024, 8, 1), date(2024, 8, 31))
    assert narrow[0].key == "2024-08:2024-08-15..2024-08-31" and wide[0].key == "2024-08"
    import pytest

    with pytest.raises(ValueError, match="empty"):
        walk.walk_observations(
            None, None, FILINGS, date(2024, 9, 1), date(2024, 8, 1), data_dir=None
        )


def test_poller_fetches_the_watch_own_files_before_a_wave_backlog(tmp_path):
    from docketyard.ingest import observations

    con = db.connect(tmp_path / "s.sqlite")
    client = FakeStb(
        {(FILINGS, "08/01/2024"): body_of(filing_row(fid="1", date="8/12/2024", pdf="1.pdf"), 1)}
    )
    backfill.wave(
        con, client, tmp_path, date(2024, 8, 1), date(2024, 8, 31), fetch_limit=0, log=lambda _: 0
    )
    assert observations.attachments(con, unfetched_only=True, observed_in="forward") == []
    assert len(observations.attachments(con, unfetched_only=True)) == 1
    assert len(observations.attachments(con, unfetched_only=True, observed_in="backfill")) == 1
