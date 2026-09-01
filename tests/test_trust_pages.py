"""The trust pages: reachable, measured, and saying nothing the code does not do."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from docketyard.capture import poll
from docketyard.capture.stb import DECISIONS, DOCKETS, ENVIRO_COMMENTS, FILINGS
from docketyard.store import coverage, db, home, stats
from docketyard.web.app import create_app
from tests.test_web import build_store


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(build_store(tmp_path)))


def test_every_trust_page_renders_without_a_cookie(client):
    for path in (
        "/about",
        "/contribute",
        "/coverage",
        "/corrections",
        "/methodology",
        "/privacy",
        "/stats",
    ):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "not affiliated" in r.text or "Not the Board" in r.text or path != "/about"
        assert "Set-Cookie" not in r.headers
        assert 'href="/static/site.css?v=' in r.text  # cache-busted by content hash


def test_coverage_numbers_are_measured(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    cov = coverage.coverage(con)
    assert cov.dockets == 2 and cov.filings == 2 and cov.decisions == 1  # by Board id
    assert cov.comments == 0  # the third record row, counted the same way
    assert cov.forward_since and cov.earliest_filed == "2026-08-24"
    assert cov.empty_prefixes == ("ARB", "ASC", "DSO", "RER", "S5A", "SUS")
    assert cov.gaps == []
    con.execute(
        "INSERT INTO coverage_gap (started_at, ended_at, failure, note)"
        " VALUES ('2026-08-26T00:00:00+00:00', '2026-08-26T09:00:00+00:00', 'captures', 'x')"
    )
    con.commit()
    con.close()
    r = TestClient(create_app(path)).get("/coverage")
    assert "2 filings" in r.text and "2 dockets" in r.text
    # the page no longer says environmental comments are absent: the watch asks for them
    assert "Environmental comments and rail recordations" not in r.text
    # the watch line names comments without backdating the watch to before they joined it
    assert "Environmental comments joined that watch later" in r.text
    assert "Outages" in r.text and "captures" in r.text and "<td>x</td>" in r.text


def test_corrections_page_links_the_issue_form(client):
    r = client.get("/corrections")
    assert "issues/new?template=data-correction.yml" in r.text
    assert "not a guarantee" in r.text and "does not correct" in r.text
    assert "two business days" not in r.text  # no turnaround is promised


def test_stats_page_is_measured(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    s = stats.stats(con, today=date(2026, 10, 15))
    assert s.filings == 2  # the same unit as coverage: by the Board's own identifier
    assert s.decisions == 1
    assert [m.month for m in s.months] == ["2026-08", "2026-09", "2026-10"]  # to today, no gaps
    assert (s.months[0].filings, s.months[0].decisions) == (2, 1)
    assert (s.busiest[0].docket.prefix, s.busiest[0].docket.sequence) == ("FD", 36873)
    assert s.busiest[0].filings == 2  # folded by family
    assert s.by_prefix[0][:2] == ("FD", 2)
    assert s.year == 2026
    assert [(y.year, y.filings, y.decisions, y.partial) for y in s.years] == [(2026, 2, 1, True)]
    con.close()
    r = TestClient(create_app(path)).get("/stats")
    assert r.status_code == 200
    assert "2026-08" in r.text and "Nothing on this page is about who" in r.text
    assert r.text.count("<svg") == 1 and "2 filings, 1 decisions" in r.text  # drawn from the data
    assert r.headers["cache-control"] == "public, max-age=1800"


def test_stats_page_survives_odd_dates(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    # A Board-side typo neither stretches the table to 2062 nor hangs the month walk.
    con.execute("UPDATE filing SET filed_date = '2062-01-05' WHERE rowid = 1")
    con.execute("UPDATE filing SET filed_date = '2026-99-05' WHERE rowid = 2")
    con.commit()
    s = stats.stats(con, today=date(2026, 8, 26))
    assert [m.month for m in s.months] == ["2026-08"]
    assert s.filings == 2  # still counted in the headline; only the month table is bounded
    # No dated filings at all: the chart's denominator must not be zero.
    con.execute("UPDATE filing SET filed_date = NULL")
    con.commit()
    s = stats.stats(con, today=date(2026, 8, 26))
    assert s.months and all(m.filings == 0 for m in s.months)
    con.close()
    assert TestClient(create_app(path)).get("/stats").status_code == 200


def test_coverage_reports_unfinished_months_by_table_and_never_unioned(tmp_path):
    """A3: one list under a sentence whose subject is filings and decisions told readers
    that 56 months were incomplete for them, when every one of those months belonged to the
    comment walk, whose table does not begin where theirs does."""
    path = build_store(tmp_path)
    con = db.connect(path)
    for key, action in (
        ("stb_hook_table_filings:2026-08", FILINGS),
        ("stb_hook_table_decisions:2026-08", DECISIONS),
        ("stb_hook_table_environmental_comments:1996-01", ENVIRO_COMMENTS),
        ("stb_hook_table_environmental_comments:1996-02", ENVIRO_COMMENTS),
        ("stb_hook_table_environmental_comments:1996-03", ENVIRO_COMMENTS),
        ("stb_hook_table_environmental_comments:2026-08", ENVIRO_COMMENTS),
    ):
        con.execute(
            "INSERT INTO walk_slice (slice_key, table_action, criteria, status, rows, captures,"
            " completed_at)"
            " VALUES (?, ?, '[]', 'partial', 0, 1, 't')",
            (key, action),
        )
    # a wave has run, so the page prints the sentence the month list hangs off
    con.execute("UPDATE capture SET ingest_mode = 'backfill' WHERE table_action = ?", (FILINGS,))
    con.commit()
    cov = coverage.coverage(con)
    con.close()
    assert cov.backfill_from, "fixture precondition: a wave has observed something"
    assert cov.records_incomplete == ("2026-08",)
    assert cov.comments_incomplete == ("1996-01", "1996-02", "1996-03", "2026-08")
    # consecutive months print as a range, not as 56 comma-separated strings
    assert coverage.month_runs(cov.comments_incomplete) == ("1996-01 to 1996-03", "2026-08")
    r = TestClient(create_app(path)).get("/coverage")
    assert "months not yet complete for filings and decisions: 2026-08" in r.text
    assert "months not yet complete for comments: 1996-01 to 1996-03, 2026-08" in r.text.lower()
    # the comment walk's gaps are not attributed to the tables above it
    assert "for filings and decisions: 1996" not in r.text


def test_month_runs_collapses_only_consecutive_months():
    assert coverage.month_runs(()) == ()
    assert coverage.month_runs(("2000-01",)) == ("2000-01",)
    assert coverage.month_runs(("1999-11", "1999-12", "2000-01")) == ("1999-11 to 2000-01",)
    assert coverage.month_runs(("2000-01", "2000-03")) == ("2000-01", "2000-03")


def test_coverage_says_the_registry_is_topped_up_after_its_one_walk(tmp_path):
    """The published page described a walk that happens once and never mentioned the
    caption refresh that has been running against the registry ever since (deferred, the
    caption-refresh review). Every bound is read from the constants that enforce it."""
    r = TestClient(create_app(build_store(tmp_path))).get("/coverage")
    assert "That walk is not repeated" in r.text
    assert f"at most {poll.CAPTION_LOOKUPS} a pass" in r.text
    assert f"last {poll.CAPTION_WINDOW_DAYS} days" in r.text
    assert f"no more than {poll.CAPTION_ATTEMPTS} times each" in r.text


def test_stats_counts_the_third_record_table(tmp_path):
    """A8: 34,257 environmental comments, a third of the search index, and `store/stats.py`
    did not mention them anywhere."""
    path = build_store(tmp_path)
    con = db.connect(path)
    s = stats.stats(con, today=date(2026, 10, 15))
    cov = coverage.coverage(con)
    assert s.comments == cov.comments  # one number, folded one way, on both pages
    con.close()
    r = TestClient(create_app(path)).get("/stats")
    assert "environmental comments" in r.text
    assert "The chart below is filings and decisions only" in r.text


def test_the_404_points_at_the_corrections_page_that_shipped(client):
    """A8: the page still said a corrections page "is being written". It shipped, and is in
    the footer of every page including this one."""
    r = client.get("/d/FD-99999999")
    assert r.status_code == 404
    assert "is being written" not in r.text
    assert 'href="/corrections"' in r.text.split("<main")[1].split("</main>")[0]


def test_a_partly_walked_month_is_unfinished_on_the_coverage_page_too(tmp_path):
    """`/week` reads the ledger by day and `/coverage` read it by status, so a wave that
    walked 15–31 July recorded `done` and the page asserted by omission that July was
    finished — the same defect as A1, pointing the other way (code review, 2026-08-31)."""
    path = build_store(tmp_path)
    con = db.connect(path)
    for key, action, status in (
        (f"{FILINGS}:1999-07:1999-07-15..1999-07-31", FILINGS, "done"),
        (f"{DECISIONS}:1999-07", DECISIONS, "done"),
        # the dockets walk keys by prefix, not by month: it must not reach this list, and
        # must not raise on the way past
        (f"{DOCKETS}:AB", DOCKETS, "done"),
    ):
        con.execute(
            "INSERT INTO walk_slice (slice_key, table_action, criteria, status, rows, captures,"
            " completed_at) VALUES (?, ?, '[]', ?, 0, 1, 't')",
            (key, action, status),
        )
    con.commit()
    cov = coverage.coverage(con)
    con.close()
    assert cov.records_incomplete == ("1999-07",)  # 14 days were never asked for
    assert coverage.month_runs(cov.records_incomplete) == ("1999-07",)
    # and the two modules now agree about it, off one shared grammar
    con = db.connect(path)
    # the fortnight the filings wave never asked for is not covered...
    assert not home.covered(con, date(1999, 7, 5), date(1999, 7, 11))
    # ...and the days it did ask for are, on both tables
    assert home.covered(con, date(1999, 7, 19), date(1999, 7, 25))
    con.close()


def test_a_wholly_walked_month_is_finished_however_it_was_sliced(tmp_path):
    """Two complementary range slices finish a month between them; neither does alone."""
    path = build_store(tmp_path)
    con = db.connect(path)

    def add(action, suffix):
        con.execute(
            "INSERT INTO walk_slice (slice_key, table_action, criteria, status, rows, captures,"
            " completed_at) VALUES (?, ?, '[]', 'done', 0, 1, 't')",
            (f"{action}:1999-07:{suffix}", action),
        )

    for action in (FILINGS, DECISIONS):
        add(action, "1999-07-01..1999-07-14")
    assert coverage.coverage(con).records_incomplete == ("1999-07",)
    for action in (FILINGS, DECISIONS):
        add(action, "1999-07-15..1999-07-31")
    con.commit()
    assert coverage.coverage(con).records_incomplete == ()
    assert home.covered(con, date(1999, 7, 12), date(1999, 7, 18))  # across the seam
    con.close()
