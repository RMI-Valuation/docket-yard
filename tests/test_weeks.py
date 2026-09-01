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
    assert 'href="/week"' in client.get("/").text  # the home page links past weeks


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
