"""The trust pages: reachable, measured, and saying nothing the code does not do."""

import pytest
from fastapi.testclient import TestClient

from docketyard.store import coverage, db
from docketyard.web.app import create_app
from tests.test_web import build_store


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(build_store(tmp_path)))


def test_every_trust_page_renders_without_a_cookie(client):
    for path in ("/about", "/coverage", "/corrections", "/methodology", "/privacy"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "not affiliated" in r.text or "Not the Board" in r.text or path != "/about"
        assert "Set-Cookie" not in r.headers


def test_coverage_numbers_are_measured(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    cov = coverage.coverage(con)
    assert cov.dockets == 2 and cov.filings == 3 and cov.decisions == 2
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
    assert "3 filings" in r.text and "2 dockets" in r.text
    assert "Gaps in the record" in r.text and "captures" in r.text and "<td>x</td>" in r.text


def test_corrections_page_links_the_issue_form(client):
    r = client.get("/corrections")
    assert "issues/new?template=data-correction.yml" in r.text
    assert "not a guarantee" in r.text and "does not correct" in r.text
    assert "two business days" not in r.text  # no turnaround is promised
