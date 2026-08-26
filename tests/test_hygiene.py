"""HTTP hygiene the outside review asked for (2026-08-26): HEAD, validators and cache
life on reader pages, canonical and Open Graph, robots and sitemaps, and the coverage page
saying two things that reconcile."""

import xml.dom.minidom

from fastapi.testclient import TestClient

from docketyard.store import coverage, db
from docketyard.web.app import create_app
from tests.test_web import build_store


def test_head_mirrors_get_without_a_body(tmp_path):
    client = TestClient(create_app(build_store(tmp_path)))
    get = client.get("/d/FD-36873")
    head = client.head("/d/FD-36873")
    assert head.status_code == 200 and head.content == b""
    assert head.headers["etag"] == get.headers["etag"]
    assert head.headers["content-type"] == get.headers["content-type"]
    assert client.head("/d/FD-99999").status_code == 404
    assert client.head("/health").status_code == 200


def test_reader_pages_carry_validators_and_a_short_cache_life(tmp_path):
    client = TestClient(create_app(build_store(tmp_path)))
    r = client.get("/d/FD-36873")
    assert r.headers["cache-control"] == "public, max-age=300"
    assert r.headers["etag"].startswith('W/"') and r.headers["vary"] == "Accept-Encoding"
    assert "Set-Cookie" not in r.headers
    again = client.get("/d/FD-36873", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    # a page that already chose its own life keeps it
    assert client.get("/stats").headers["cache-control"] == "public, max-age=1800"
    # consent and token paths are never cached
    assert "cache-control" not in client.get("/s/confirm/nope").headers or "max-age" not in (
        client.get("/s/confirm/nope").headers.get("cache-control", "")
    )
    assert "etag" not in client.get("/health").headers


def test_canonical_and_open_graph_on_a_docket_page(tmp_path):
    client = TestClient(create_app(build_store(tmp_path)))
    r = client.get("/d/FD-36873?order=oldest&kind=reply")
    assert '<link rel="canonical" href="https://docketyard.org/d/FD-36873">' in r.text
    assert '<meta property="og:title" content="FD 36873 — Docket Yard">' in r.text
    assert 'property="og:description"' in r.text and 'property="og:url"' in r.text
    home = client.get("/").text
    assert '<link rel="canonical" href="https://docketyard.org/">' in home


def test_robots_and_sitemaps(tmp_path):
    client = TestClient(create_app(build_store(tmp_path)))
    robots = client.get("/robots.txt")
    assert (
        robots.status_code == 200 and "Sitemap: https://docketyard.org/sitemap.xml" in robots.text
    )
    assert "Disallow: /s/" in robots.text
    idx = client.get("/sitemap.xml")
    assert idx.status_code == 200 and idx.headers["content-type"].startswith("application/xml")
    xml.dom.minidom.parseString(idx.text)
    assert "sitemap-dockets.xml" in idx.text and "sitemap-filings.xml" in idx.text
    dockets = client.get("/sitemap-dockets.xml")
    xml.dom.minidom.parseString(dockets.text)
    assert "<loc>https://docketyard.org/d/FD-36873</loc>" in dockets.text
    assert "/sub/" not in dockets.text  # a family is addressed by its parent
    assert "<lastmod>20" in dockets.text
    filings = client.get("/sitemap-filings.xml")
    assert "<loc>https://docketyard.org/filing/" in filings.text
    assert client.get("/sitemap-nope.xml").status_code == 404
    assert idx.headers["cache-control"] == "public, max-age=86400"


def test_coverage_says_when_the_watch_began_and_what_the_record_spans(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    cov = coverage.coverage(con)
    con.close()
    assert cov.record_from and cov.record_to and cov.record_from <= cov.record_to
    r = client_text = TestClient(create_app(path)).get("/coverage").text
    assert "The watch began" in r and "The record spans" in r
    assert "Outages" in client_text and "No outage has been recorded" in client_text
    assert "Known gaps" not in client_text
