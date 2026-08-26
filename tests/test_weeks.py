"""Past weeks: Monday–Sunday at a permanent address, coverage-aware."""

from datetime import date

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
