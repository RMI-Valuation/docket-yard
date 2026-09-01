"""Past weeks: Monday–Sunday at a permanent address, coverage-aware."""

from dataclasses import replace
from datetime import date, timedelta

from fastapi.testclient import TestClient

from docketyard.capture.stb import DECISIONS, FILINGS
from docketyard.store import db, home
from docketyard.web import urls
from docketyard.web.app import create_app
from tests.test_web import build_store


def test_monday_of_and_path():
    assert home.monday_of(date(2026, 8, 26)) == date(2026, 8, 24)  # a Wednesday
    assert home.monday_of(date(2026, 8, 24)) == date(2026, 8, 24)
    assert home.monday_of(date(2026, 8, 30)) == date(2026, 8, 24)  # Sunday belongs to it
    assert urls.week_path(date(2026, 8, 17)) == "/week/2026-08-17"


def test_week_pages(tmp_path):
    path = build_store(tmp_path)  # entries dated 2026-08-24/25, one decision 2026-08-21
    client = TestClient(create_app(path))
    r = client.get("/week/2026-08-26", follow_redirects=False)  # a Wednesday
    assert r.status_code == 301 and r.headers["location"] == "/week/2026-08-24"
    r = client.get("/week/2026-08-24")
    assert r.status_code == 200 and "Week of 24 Aug 2026" in r.text
    assert "311981" in r.text or "filings observed" in r.text
    assert 'href="/week/2026-08-17"' in r.text  # previous
    assert "next week" not in r.text  # nothing after the latest activity
    assert client.get("/week/not-a-date").status_code == 404
    r = client.get("/week", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/week/2026-08-17"
    # the home page links the INDEX, not one week: "past weeks" used to land the reader on
    # a single week and leave them clicking backwards (navigation-review.md § C)
    assert 'href="/weeks"' in client.get("/").text


def test_uncovered_week_says_so_and_fills_in_after_a_wave(tmp_path):
    path = build_store(tmp_path)
    client = TestClient(create_app(path))
    r = client.get("/week/2024-08-05")
    assert r.status_code == 200 and "does not yet cover this week" in r.text
    assert "decisions served" not in r.text
    con = db.connect(path)
    assert not home.covered(con, date(2024, 8, 5), date(2024, 8, 11))
    for action in (FILINGS, DECISIONS):
        con.execute(
            "INSERT INTO walk_slice (slice_key, table_action, criteria, status, rows, captures,"
            " completed_at) VALUES (?, ?, '[]', 'done', 0, 1, 't')",
            (f"{action}:2024-08", action),
        )
    con.commit()
    assert home.covered(con, date(2024, 8, 5), date(2024, 8, 11))
    assert not home.covered(con, date(2024, 8, 26), date(2024, 9, 1))  # September not walked
    con.close()
    assert "does not yet cover" not in client.get("/week/2024-08-05").text


def _slice(con, action, key, status="done"):
    con.execute(
        "INSERT INTO walk_slice (slice_key, table_action, criteria, status, rows, captures,"
        " completed_at) VALUES (?, ?, '[]', ?, 0, 1, 't')",
        (key, action, status),
    )


def test_a_partly_walked_month_is_read_at_the_days_it_names(tmp_path):
    """`walk.py` appends `:{lo}..{hi}` to the slice key whenever a wave walked part of a
    month, and `covered()` matched the unsuffixed key exactly — so the one month that had
    ever happened to read as never walked, and because it sat between the reader and
    everything older it walled off the whole archive (navigation-review.md A1). No test
    carried a suffixed key before this one."""
    path = build_store(tmp_path)
    con = db.connect(path)
    for action in (FILINGS, DECISIONS):
        _slice(con, action, f"{action}:2024-08:2024-08-01..2024-08-20")
    con.commit()
    # inside the range the wave actually walked
    assert home.covered(con, date(2024, 8, 5), date(2024, 8, 11))
    # the days the suffix excludes are NOT claimed: the fix stops hiding what was walked,
    # it does not start claiming what was not
    assert not home.covered(con, date(2024, 8, 19), date(2024, 8, 25))
    assert not home.covered(con, date(2024, 8, 26), date(2024, 9, 1))
    assert home.walked_through(con, date(2024, 8, 19), date(2024, 8, 25)) == date(2024, 8, 20)
    # one table walked and the other not is not a walked week
    con.execute("DELETE FROM walk_slice WHERE table_action = ?", (DECISIONS,))
    con.commit()
    assert not home.covered(con, date(2024, 8, 5), date(2024, 8, 11))
    con.close()


def test_the_not_covered_sentence_never_prints_over_records_the_page_holds(tmp_path):
    """A2's invariant. The sentence asserts the record does not reach here; it may only
    render when the window is empty, whatever the ledger says."""
    path = build_store(tmp_path)
    con = db.connect(path)
    con.execute("DELETE FROM walk_slice")
    con.commit()
    # a week the ledger does not reach and the watch began after: the sentence's own case
    start, end = date(2024, 8, 5), date(2024, 8, 11)
    assert not home.covered(con, start, end)
    empty = home.calendar_week(con, start)
    assert not empty.filings and not empty.decision_entries
    assert home.coverage_state(con, empty, start, end, date(2026, 8, 31)) == home.UNCOVERED
    # the same uncovered week, holding records. The ledger has not moved; the page has
    # something to show, so the sentence claiming it has nothing must not render.
    held = replace(empty, filings=91, filing_entries=91)
    assert home.coverage_state(con, held, start, end, date(2026, 8, 31)) == home.PARTIAL
    # a decision alone is enough — the sentence speaks for both tables
    served = replace(empty, decision_entries=16)
    assert home.coverage_state(con, served, start, end, date(2026, 8, 31)) == home.PARTIAL
    con.close()


def test_the_week_corridor_is_bounded_at_both_ends(tmp_path):
    """A4: year 1 and year 9999 were 500s from date arithmetic in the prev/next links, and
    1900 answered 200 with a link one week further back, for ever."""
    path = build_store(tmp_path)
    client = TestClient(create_app(path))
    assert client.get("/week/0001-01-01").status_code == 404
    assert client.get("/week/9999-12-27").status_code == 404
    assert client.get("/week/1900-01-01", follow_redirects=False).status_code == 404
    floor = home.monday_of(home.WEEK_FLOOR + timedelta(days=6))
    r = client.get(urls.week_path(floor))
    assert r.status_code == 200 and "previous week" not in r.text  # the corridor ends here


def test_a_week_that_has_not_happened_says_so(tmp_path):
    """A4: the record affirmatively asserted an empty week four years out, because
    `covered()`'s watch-start test had no upper bound."""
    path = build_store(tmp_path)
    client = TestClient(create_app(path))
    ahead = home.monday_of(date.today() + timedelta(days=120))
    r = client.get(urls.week_path(ahead))
    assert r.status_code == 200
    assert "has not happened yet" in r.text
    # no counts, in either direction: the record has nothing to be silent about here
    assert "decisions served" not in r.text and "filings observed" not in r.text
    assert "does not yet cover" not in r.text
    assert 'name="robots" content="noindex"' in r.text


def test_the_archive_week_heading_names_its_own_week(tmp_path):
    """A5: `_week_body.html` is shared by the home page and ~1,590 archive pages, and its
    heading was the constant "this week"."""
    path = build_store(tmp_path)
    client = TestClient(create_app(path))
    week_page = client.get("/week/2026-08-24").text
    assert "Proceedings that moved in the week of 24 Aug 2026" in week_page
    assert "moved this week" not in week_page
    home_page = client.get("/").text
    assert "The latest seven days at the Board" in home_page
    assert "Proceedings that moved in these seven days" in home_page
    assert "This week at the Board" not in home_page


def test_the_weeks_index_is_the_way_into_the_archive(tmp_path):
    """~1,590 week pages rendered correctly and were reachable only by clicking "previous
    week" sixteen hundred times (navigation-review.md § C). One aggregate, not a query per
    week."""
    path = build_store(tmp_path)
    con = db.connect(path)
    years = home.weeks_index(con, today=date(2026, 8, 31))
    con.close()
    assert [y.year for y in years] == [2026]
    mondays = [w.monday for w in years[0].weeks]
    assert mondays == ["2026-08-24", "2026-08-17"]  # newest first; Monday-anchored
    # the fixture's two filings fall in one week and its decision in the week before
    first, second = years[0].weeks
    assert first.end == "2026-08-30" and (first.filings, first.decisions) == (2, 0)
    assert (second.filings, second.decisions) == (0, 1)
    assert years[0].filings == 2 and years[0].decisions == 1  # the year's own totals
    client = TestClient(create_app(path))
    r = client.get("/weeks")
    assert r.status_code == 200
    assert 'href="/week/2026-08-24"' in r.text and 'href="/week/2026-08-17"' in r.text
    assert '<span class="n serif">2</span><span class="l">weeks with something' in r.text
    # a week with nothing on record is not listed, and the page says why that is not a
    # claim about the Board
    assert "/week/2026-08-10" not in r.text
    assert "not about the Board" in r.text
    # and the crawler is told about them too, where it was told about none
    assert "/week/2026-08-24" in client.get("/sitemap-weeks-1.xml").text
    assert "/weeks" in client.get("/sitemap-pages-1.xml").text
    assert "/weeks" in client.get("/llms.txt").text


def test_the_weeks_index_ignores_dates_outside_the_corridor(tmp_path):
    """Dates are shape-checked at ingest, not range-checked. A Board-side typo must not
    stretch this page to 2062 or invent a week before the record."""
    path = build_store(tmp_path)
    con = db.connect(path)
    con.execute("UPDATE filing SET filed_date = '2062-01-05' WHERE rowid = 1")
    con.execute("UPDATE filing SET filed_date = '1301-04-02' WHERE rowid = 2")
    con.commit()
    years = home.weeks_index(con, today=date(2026, 8, 31))
    con.close()
    assert all(int(w.monday[:4]) <= 2026 for y in years for w in y.weeks)
    assert all(date.fromisoformat(w.monday) >= home.WEEK_FLOOR for y in years for w in y.weeks)


def test_the_weeks_index_holds_its_address_on_an_empty_record(tmp_path):
    """The footer links `/weeks` from every page and the sitemap publishes it, so it must
    not 404 on a record with nothing dated in it (code review, 2026-09-01)."""
    path = tmp_path / "empty.sqlite"
    db.connect(path).close()
    client = TestClient(create_app(path))
    r = client.get("/weeks")
    assert r.status_code == 200
    assert "no week to list" in r.text
    assert r.headers["cache-control"] == "public, max-age=1800"
    assert client.get("/sitemap-weeks-1.xml").status_code == 200


def test_the_weeks_index_is_computed_once_per_store_stamp(tmp_path):
    """Two full aggregates over `filing` and `decision_record`, on a page the footer links
    from every one of ~130,000 addresses."""
    path = build_store(tmp_path)
    client = TestClient(create_app(path))
    assert client.get("/weeks").headers["cache-control"] == "public, max-age=1800"
    con = db.connect(path)
    calls = {"n": 0}
    real = home.weeks_index

    def counted(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    con.close()
    import docketyard.store.home as home_mod

    home_mod.weeks_index = counted
    try:
        client2 = TestClient(create_app(path))
        for _ in range(3):
            assert client2.get("/weeks").status_code == 200
        assert calls["n"] == 1  # memoised on the store stamp
    finally:
        home_mod.weeks_index = real


def test_an_outage_longer_than_the_poll_window_is_not_covered_by_the_watch(tmp_path):
    """The poller asks for a trailing seven days each pass, so a short outage costs
    nothing — the next pass re-asks what the missed ones covered. A LONGER one is never
    caught up: when the poller resumes it asks for the last seven days and the days before
    them are never asked again. `covered()` was answering yes for them on the watch alone
    (stb-ingest-specialist, 2026-08-31)."""
    path = build_store(tmp_path)
    con = db.connect(path)
    # the watch began before the week under test, so the watch branch is what answers here
    con.execute(
        "UPDATE capture SET captured_at = '2026-08-20T00:00:00+00:00' WHERE ingest_mode = 'forward'"
    )
    con.commit()
    today = date(2026, 8, 31)
    week = (date(2026, 8, 24), date(2026, 8, 30))
    assert home.covered(con, *week, today)  # the watch answers for it
    con.execute(
        "INSERT INTO coverage_gap (started_at, ended_at, failure, note)"
        " VALUES ('2026-08-01T00:00:00+00:00', '2026-08-30T00:00:00+00:00', 'captures', NULL)"
    )
    con.commit()
    # a month down: everything up to six days before it ended was never asked for
    assert home.gap_shadows(con, today) == [(date(2026, 8, 1), date(2026, 8, 24))]
    assert not home.covered(con, *week, today)
    assert not home.covered(con, date(2026, 8, 10), date(2026, 8, 16), today)
    # the days the resuming pass re-asked are still covered
    assert home.covered(con, date(2026, 8, 25), date(2026, 8, 31), today)

    # a SHORT outage shadows nothing: the next pass's own window covers it
    con.execute("DELETE FROM coverage_gap")
    con.execute(
        "INSERT INTO coverage_gap (started_at, ended_at, failure, note)"
        " VALUES ('2026-08-25T00:00:00+00:00', '2026-08-27T00:00:00+00:00', 'captures', NULL)"
    )
    con.commit()
    assert home.gap_shadows(con, today) == []
    assert home.covered(con, *week, today)

    # and a failure downstream of the capture ledger shadows nothing either
    con.execute("DELETE FROM coverage_gap")
    con.execute(
        "INSERT INTO coverage_gap (started_at, ended_at, failure, note)"
        " VALUES ('2026-08-01T00:00:00+00:00', '2026-08-30T00:00:00+00:00', 'delivery', NULL)"
    )
    con.commit()
    assert home.gap_shadows(con, today) == [] and home.covered(con, *week, today)
    con.close()


def test_a_shadowed_week_still_renders_what_it_holds(tmp_path):
    """The invariant A2 built: the "not covered" sentence is only ever printed over an
    empty window, whatever put the window in doubt."""
    path = build_store(tmp_path)
    con = db.connect(path)
    con.execute(
        "INSERT INTO coverage_gap (started_at, ended_at, failure, note)"
        " VALUES ('2026-08-01T00:00:00+00:00', '2026-08-30T00:00:00+00:00', 'captures', NULL)"
    )
    con.commit()
    today = date(2026, 8, 31)
    w = home.calendar_week(con, date(2026, 8, 24))
    assert w.filings, "fixture precondition: this week holds filings"
    assert home.coverage_state(con, w, date(2026, 8, 24), date(2026, 8, 30), today) == home.PARTIAL
    con.close()
    page = TestClient(create_app(path)).get("/week/2026-08-24").text
    assert "does not yet cover" not in page  # the sentence never prints over held records
    assert "filings observed" in page and "FD 36873" in page  # what it holds, rendered
    assert "A wave has not finished this week" in page  # and the caveat beside them
