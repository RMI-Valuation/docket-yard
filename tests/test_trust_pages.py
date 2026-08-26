"""The trust pages: reachable, measured, and saying nothing the code does not do."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from docketyard.store import coverage, db, stats
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
