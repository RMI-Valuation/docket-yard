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
    # the doubted decision month reconciles against its done neighbour: proven empty
    assert summary[DECISIONS]["done"] == 1 and summary[DECISIONS]["empty"] == 1
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
    assert again[FILINGS]["skipped"] == 2 and again[DECISIONS]["skipped"] == 2  # empty skips too
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


def test_a_measured_empty_month_is_declared_not_guessed(tmp_path):
    from datetime import date as d

    from docketyard.capture.stb import FILINGS
    from docketyard.store import home

    slices = walk.month_slices(FILINGS, d(2025, 9, 1), d(2025, 11, 30))
    assert [s.expected_empty for s in slices] == [False, True, False]  # only 2025-10
    assert not any(
        s.expected_empty for s in walk.month_slices(DECISIONS, d(2025, 10, 1), d(2025, 10, 31))
    )
    con = db.connect(tmp_path / "s.sqlite")
    client = FakeStb({})  # everything answers the envelope
    out = walk.walk_observations(
        con, client, FILINGS, d(2025, 10, 1), d(2025, 10, 31), data_dir=tmp_path, log=lambda _: 0
    )
    assert out == {"done": 0, "empty": 1, "capped": 0, "partial": 0, "skipped": 0}
    con.execute(
        "INSERT INTO walk_slice (slice_key, table_action, criteria, status, rows, captures,"
        " completed_at) VALUES (?, ?, '[]', 'done', 2, 1, 't')",
        (f"{DECISIONS}:2025-10", DECISIONS),
    )
    con.commit()
    assert home.covered(con, d(2025, 10, 6), d(2025, 10, 12))  # an empty month still counts


class WindowStb(FakeStb):
    """Keyed by (action, start, end): a month and a window that begins the same day differ."""

    def query_table(self, action, criteria, *, page, per_page, sort_by="", sort_order=""):
        self.requests += 1
        start, end = (v for _, v in criteria)
        body = self.pages.get((action, start, end))
        if page > 1 or body is None:
            return 200, NO_RESULTS, []
        return 200, body, [("search-criteria[0][name]", "x")]


def _month_body(n, month, year=1996, first_id=100):
    rows = "".join(
        filing_row(fid=str(first_id + i), date=f"{month}/{i + 1}/{year}", pdf=f"{first_id + i}.pdf")
        for i in range(n)
    )
    return body_of(rows, n)


def test_a_month_that_answers_the_envelope_is_proven_empty_by_a_neighbour_window(tmp_path):
    """May holds two filings, June answers the envelope, July one filing. Walking May–July:
    June has no done month after it yet, so the proof looks back — a window May 1 → June 30
    that totals exactly May's 2 proves June empty. Both proof requests are captured."""
    from datetime import date as d

    from docketyard.capture.stb import FILINGS

    con = db.connect(tmp_path / "s.sqlite")
    client = WindowStb(
        {
            (FILINGS, "05/01/1996", "05/31/1996"): _month_body(2, 5),
            (FILINGS, "07/01/1996", "07/31/1996"): _month_body(1, 7, first_id=200),
            (FILINGS, "05/01/1996", "06/30/1996"): _month_body(2, 5),  # the window: May alone
        }
    )
    out = walk.walk_observations(
        con, client, FILINGS, d(1996, 5, 1), d(1996, 7, 31), data_dir=tmp_path, log=lambda _: 0
    )
    assert out == {"done": 2, "empty": 1, "capped": 0, "partial": 0, "skipped": 0}
    status = dict(con.execute("SELECT slice_key, status FROM walk_slice").fetchall())
    assert status[f"{FILINGS}:1996-06"] == "empty"
    # the two proof captures are on record, marked backfill and processed (never ingested)
    captures = con.execute(
        "SELECT COUNT(*) FROM capture WHERE ingest_mode = 'backfill' AND table_action = ?",
        (FILINGS,),
    ).fetchone()[0]
    assert captures == 5 and client.requests == 5  # May, June, the two proofs, July


def test_a_window_that_does_not_reconcile_leaves_the_month_partial(tmp_path):
    """The same shape, but the window returns more than May alone (June is not empty; the
    month's own request answered the envelope for some other reason): partial, with the
    walker saying the criterion may be wrong rather than guessing empty."""
    from datetime import date as d

    from docketyard.capture.stb import FILINGS

    con = db.connect(tmp_path / "s.sqlite")
    notes = []
    client = WindowStb(
        {
            (FILINGS, "05/01/1996", "05/31/1996"): _month_body(2, 5),
            (FILINGS, "05/01/1996", "06/30/1996"): _month_body(3, 5),  # one more than May
        }
    )
    out = walk.walk_observations(
        con, client, FILINGS, d(1996, 5, 1), d(1996, 6, 30), data_dir=tmp_path, log=notes.append
    )
    assert out["empty"] == 0 and out["partial"] == 1
    assert any("did not reconcile" in n for n in notes)
    assert any("criterion may be wrong" in n for n in notes)
    # both proof requests answering the envelope (a dead criterion) with a done neighbour
    # present: two requests, no proof, partial
    con3 = db.connect(tmp_path / "u.sqlite")
    client3 = WindowStb({(FILINGS, "05/01/1996", "05/31/1996"): _month_body(2, 5)})
    out3 = walk.walk_observations(
        con3, client3, FILINGS, d(1996, 5, 1), d(1996, 6, 30), data_dir=tmp_path, log=lambda _: 0
    )
    assert out3["partial"] == 1 and client3.requests == 4
    # a proof whose responses parse but do not pass the filter assertion (rows outside the
    # window) proves nothing
    con4 = db.connect(tmp_path / "v.sqlite")
    client4 = WindowStb(
        {
            (FILINGS, "05/01/1996", "05/31/1996"): _month_body(2, 5),
            (FILINGS, "05/01/1996", "06/30/1996"): _month_body(2, 9),  # September rows
        }
    )
    out4 = walk.walk_observations(
        con4, client4, FILINGS, d(1996, 5, 1), d(1996, 6, 30), data_dir=tmp_path, log=lambda _: 0
    )
    assert out4["partial"] == 1
    # and with no done neighbour at all, nothing is asked and the month stays partial
    con2 = db.connect(tmp_path / "t.sqlite")
    client2 = WindowStb({})
    out2 = walk.walk_observations(
        con2, client2, FILINGS, d(1996, 6, 1), d(1996, 6, 30), data_dir=tmp_path, log=lambda _: 0
    )
    assert out2["partial"] == 1 and client2.requests == 1


def _days_body(days, month=5, year=1996, first_id=300):
    rows = "".join(
        filing_row(fid=str(first_id + i), date=f"{month}/{d}/{year}", pdf=f"{first_id + i}.pdf")
        for i, d in enumerate(days)
    )
    return body_of(rows, len(days))


def test_a_neighbour_walked_in_two_halves_can_still_prove_a_month_empty(tmp_path):
    """The proof needs a neighbour month walked WHOLE, and `reconcile_empty_month` decided
    that with its own `len(rest) == 7` test on the slice key — a fourth hand-rolled reading
    of the grammar, and the only one blind to a month finished as two complementary range
    slices. It failed safe, recording `partial` where `empty` was provable
    (stb-ingest-specialist, 2026-08-31); the grammar now lives beside it."""
    from datetime import date as d

    from docketyard.capture.stb import FILINGS

    con = db.connect(tmp_path / "s.sqlite")
    client = WindowStb(
        {
            (FILINGS, "05/01/1996", "05/15/1996"): _days_body([1, 2]),
            (FILINGS, "05/16/1996", "05/31/1996"): _days_body([20], first_id=400),
            (FILINGS, "05/01/1996", "05/31/1996"): _days_body([1, 2, 20], first_id=500),
            # the window across May and June returns May's own total: June holds nothing
            (FILINGS, "05/01/1996", "06/30/1996"): _days_body([1, 2, 20], first_id=600),
        }
    )
    # May walked as two ranges, neither of them a whole-month key
    for lo, hi in ((d(1996, 5, 1), d(1996, 5, 15)), (d(1996, 5, 16), d(1996, 5, 31))):
        walk.walk_observations(con, client, FILINGS, lo, hi, data_dir=tmp_path, log=lambda _: 0)
    keys = [k for (k,) in con.execute("SELECT slice_key FROM walk_slice")]
    assert all(".." in k for k in keys), keys  # every May key carries a range suffix

    notes = []
    out = walk.walk_observations(
        con, client, FILINGS, d(1996, 6, 1), d(1996, 6, 30), data_dir=tmp_path, log=notes.append
    )
    assert out["empty"] == 1 and out["partial"] == 0
    assert any("reconciles" in n or "empty" in n for n in notes), notes
