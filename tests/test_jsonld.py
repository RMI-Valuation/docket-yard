"""schema.org JSON-LD, site level only (docs/machine-surface.md, decided 2026-09-10): each
block is built from its page's own reads, points only at addresses that answer, and cannot
end the script element it sits in."""

import json
import re

from fastapi.testclient import TestClient

from docketyard.ingest.dockets import ParsedDocket
from docketyard.store import dump
from docketyard.web import jsonld
from docketyard.web.app import create_app
from tests.test_web import build_store

_BLOCK = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
SITE = "https://docketyard.org"


def blocks(html: str) -> list[dict]:
    return [json.loads(b) for b in _BLOCK.findall(html)]


def test_the_home_page_names_the_site_and_a_search_that_answers(tmp_path):
    client = TestClient(create_app(build_store(tmp_path)))
    [site] = blocks(client.get("/").text)
    assert site["@type"] == "WebSite" and site["url"] == f"{SITE}/"
    template = site["potentialAction"]["target"]["urlTemplate"]
    assert template == f"{SITE}/search?q={{search_term_string}}"
    assert site["potentialAction"]["query-input"] == "required name=search_term_string"
    path = template.removeprefix(SITE).replace("{search_term_string}", "CONTROL")
    assert client.get(path).status_code == 200


def test_a_sub_docket_sheet_carries_its_way_up_and_every_step_answers(tmp_path):
    client = TestClient(create_app(build_store(tmp_path)))
    html = client.get("/d/FD-36873/sub/1").text
    [trail] = blocks(html)
    assert trail["@type"] == "BreadcrumbList"
    items = trail["itemListElement"]
    assert [i["name"] for i in items] == ["Dockets", "FD", "FD 36873", "FD 36873 (Sub-No. 1)"]
    assert [i["position"] for i in items] == [1, 2, 3, 4]
    for item in items:
        path = item["item"].removeprefix(SITE)
        assert client.get(path).status_code == 200, path
    # the number above is a way up the page itself offers, not one the block invents
    assert 'href="/d/FD-36873"' in html


def test_a_parent_sheet_ends_at_itself(tmp_path):
    client = TestClient(create_app(build_store(tmp_path)))
    [trail] = blocks(client.get("/d/FD-36873").text)
    assert [i["name"] for i in trail["itemListElement"]] == ["Dockets", "FD", "FD 36873"]


def test_a_prefix_the_registry_does_not_list_is_not_a_step():
    """A sheet can exist for a docket the dockets table never showed, and `/dockets/<P>`
    answers 404 for a prefix the registry does not hold."""
    trail = jsonld.sheet_trail(
        ParsedDocket("ZZ", 7, None, None), in_series=False, prefix_listed=False
    )
    assert trail == [("Dockets", "/dockets"), ("ZZ 7", "/d/ZZ-7")]


def _manifest(public, held_reason):
    public.mkdir()
    manifest = {
        "built_at": "2026-09-10T04:10:00+00:00",
        "licence": dump.LICENCE,
        "licence_url": dump.LICENCE_URL,
        "schema_version": 25,
        "counts": {
            "dockets": 1234,
            "filings": 5678,
            "decisions": 90,
            "events": 12345,
            "documents": 7,
        },
        "omitted_tables": ["subscription"],
        "held_tables": ["party"],
        "held_reason": held_reason,
        "latest": {"name": "docketyard-latest.sqlite.gz", "bytes": 12_300_000, "sha256": "ab" * 32},
        "dated": [],
    }
    (public / "index.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def test_the_data_page_describes_the_snapshot_it_links(tmp_path):
    public = tmp_path / "public"
    manifest = _manifest(public, "Held </script><b>pending</b> a licence review.")
    client = TestClient(create_app(build_store(tmp_path), public_dir=public))
    html = client.get("/data").text
    [ds] = blocks(html)
    assert ds["@type"] == "Dataset" and ds["license"] == dump.LICENCE_URL
    assert ds["url"] == f"{SITE}/data" and ds["dateModified"] == manifest["built_at"]
    [download] = ds["distribution"]
    assert download["contentUrl"] == f"{SITE}/data/files/docketyard-latest.sqlite.gz"
    assert download["sha256"] == manifest["latest"]["sha256"]
    # the file the block names is the file the page links, and the counts are the manifest's
    assert 'href="/data/files/docketyard-latest.sqlite.gz"' in html
    assert "1,234 dockets" in ds["description"] and "12,345 ledger events" in ds["description"]
    assert manifest["held_reason"] in ds["description"]
    # the manifest's prose reaches a script element and cannot end it
    assert "</script><b>" not in html


def test_no_snapshot_no_dataset(tmp_path):
    client = TestClient(create_app(build_store(tmp_path), public_dir=tmp_path / "absent"))
    assert blocks(client.get("/data").text) == []


def test_no_record_or_party_page_carries_a_type(tmp_path):
    """Site level only: schema.org has no type for a proceeding, a filing or a decision, and
    a party type would publish a classification nobody has measured."""
    client = TestClient(create_app(build_store(tmp_path)))
    for path in ("/filing/311981", "/parties", "/about", "/coverage", "/dockets"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "application/ld+json" not in r.text, path
