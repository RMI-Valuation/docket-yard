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
    assert head.headers["content-length"] == get.headers["content-length"]
    assert head.headers["content-type"] == get.headers["content-type"]
    assert client.head("/d/FD-99999").status_code == 404
    assert client.head("/health").status_code == 200


def test_reader_pages_carry_validators_and_a_short_cache_life(tmp_path):
    client = TestClient(create_app(build_store(tmp_path)))
    r = client.get("/d/FD-36873")
    assert r.headers["cache-control"] == "public, max-age=300"
    assert r.headers["etag"].startswith('W/"')
    assert "Set-Cookie" not in r.headers
    again = client.get("/d/FD-36873", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    listed = client.get("/d/FD-36873", headers={"If-None-Match": 'W/"x", ' + r.headers["etag"]})
    assert listed.status_code == 304  # a list of validators, as browsers send
    # the validator is the store's version: every page shares it, and it moves with the store
    assert client.get("/stats").headers["etag"] == r.headers["etag"]
    # a page that already chose its own life keeps it
    assert client.get("/stats").headers["cache-control"] == "public, max-age=1800"
    # consent, token and telemetry paths are marked no-store
    assert client.get("/s/confirm/nope").headers["cache-control"] == "no-store"
    assert client.get("/health").headers["cache-control"] == "no-store"
    assert "etag" not in client.get("/health").headers
    # mounted files keep StaticFiles' own validators and streaming
    css = client.get("/static/site.css")
    assert css.headers["etag"] != r.headers["etag"] and "last-modified" in css.headers


def test_canonical_and_open_graph_on_a_docket_page(tmp_path):
    client = TestClient(create_app(build_store(tmp_path)))
    r = client.get("/d/FD-36873?order=oldest&kind=reply")
    assert '<link rel="canonical" href="https://docketyard.org/d/FD-36873">' in r.text
    assert '<meta property="og:title" content="FD 36873 — Docket Yard">' in r.text
    assert 'property="og:description"' in r.text and 'property="og:url"' in r.text
    home = client.get("/").text
    assert '<link rel="canonical" href="https://docketyard.org/">' in home
    assert 'rel="canonical"' not in client.get("/d/FD-99999").text  # a 404 has no address


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
    assert "sitemap-dockets-1.xml" in idx.text and "sitemap-filings-1.xml" in idx.text
    dockets = client.get("/sitemap-dockets-1.xml")
    xml.dom.minidom.parseString(dockets.text)
    assert "<loc>https://docketyard.org/d/FD-36873</loc>" in dockets.text
    assert "/sub/" not in dockets.text  # a family is addressed by its parent
    assert "<lastmod>20" in dockets.text
    # a token page carries no canonical or og:url: a scanner must not learn the address
    assert 'rel="canonical"' not in client.get("/s/confirm/nope").text
    filings = client.get("/sitemap-filings-1.xml")
    assert "<loc>https://docketyard.org/filing/" in filings.text
    assert client.get("/sitemap-nope-1.xml").status_code == 404
    assert client.get("/sitemap-filings-2.xml").status_code == 404  # no such page
    assert "/privacy" in client.get("/sitemap-pages-1.xml").text
    assert idx.headers["cache-control"] == "public, max-age=86400"


def test_coverage_says_when_the_watch_began_and_what_the_record_spans(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    cov = coverage.coverage(con)
    con.close()
    assert cov.record_from and cov.record_to and cov.record_from <= cov.record_to
    page = TestClient(create_app(path)).get("/coverage").text
    assert "The record spans" in page and "within the hour" in page  # the hedge stays
    assert "every new entry is caught" not in page  # no guarantee was made
    assert "Outages" in page and "No outage has been recorded" in page
    assert "Gaps in the record" not in page
