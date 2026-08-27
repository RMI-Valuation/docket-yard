"""M9: the bulk snapshot omits every reader table, its manifest is measured, the page is
generated from the manifest, and JSON twins answer at the permanent addresses."""

import gzip
import json
import sqlite3
from datetime import date

from fastapi.testclient import TestClient

from docketyard.alerts import subscriptions
from docketyard.store import db, dump
from docketyard.web.app import create_app
from tests.test_web import build_store


def test_api_page_and_llms_txt_say_what_the_surface_is(tmp_path):
    client = TestClient(create_app(build_store(tmp_path)))
    r = client.get("/api")
    assert r.status_code == 200
    for needle in (
        "/openapi.json",
        "/llms.txt",
        "CC0 1.0",
        '"shape_version": 1',
        "ADR 0013",
        "User-Agent",
        "/document/&lt;sha256&gt;.pdf",
        "position",
    ):
        assert needle in r.text, needle
    assert "v20" in r.text or "0.0.0" in r.text  # the release this answer came from
    r = client.get("/llms.txt")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert r.text.startswith("# Docket Yard\n\n> ")
    for needle in (
        "## Read the record",
        "## Data",
        "## Trust",
        "does not say what any party argued",
        "https://docketyard.org/api",
        "https://docketyard.org/coverage",
        "2 filings, 1 decision and",
        "CC0 1.0",
    ):
        assert needle in r.text, needle
    assert "Cache-Control" in r.headers and "&#" not in r.text and "&amp;" not in r.text
    assert (
        "pages are good for 5 minutes, JSON for 30, a document for 365 days"
        in client.get("/api").text
    )
    assert '"description"' in client.get("/openapi.json").text
    assert "/api<" in client.get("/sitemap-pages-1.xml").text


def test_snapshot_omits_readers_and_measures_itself(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    subscriptions.subscribe(con, "secret@example.org", 1, "pass")
    con.execute("CREATE TABLE _litestream_seq (id INTEGER PRIMARY KEY, seq INTEGER)")  # as live
    con.commit()
    con.close()
    out = tmp_path / "public"
    m = dump.dump(path, out, today=date(2026, 9, 1), now="2026-09-01T04:10:00+00:00")
    schema = (out / "schema.sql").read_text()
    assert "subscription" not in schema and "PRAGMA user_version" in schema  # its own DDL
    assert not list(out.glob(".*"))  # nothing half-built is left where it is served
    assert not (out.parent / ".dump-work" / "snapshot.sqlite").exists()
    assert m.licence == "CC0-1.0" and m.schema_version == db.MIGRATIONS[-1][0]
    assert m.counts["filings"] == 2 and m.omitted_tables == list(dump.PRIVATE_TABLES)
    assert (out / "docketyard-2026-09-01.sqlite.gz").exists()  # first of the month: kept
    raw = gzip.decompress((out / m.latest.name).read_bytes())
    assert b"secret@example.org" not in raw and b"email_enc" not in raw
    snap = tmp_path / "snap.sqlite"
    snap.write_bytes(raw)
    s = sqlite3.connect(snap)
    tables = {r[0] for r in s.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not tables & set(dump.PRIVATE_TABLES)
    assert {"docket", "filing", "decision_record", "event", "capture"} <= tables
    assert not tables & set(dump.HELD_TABLES)  # the enriched layer waits for its licence
    assert not tables & set(dump.TOOL_TABLES)  # replication bookkeeping is not record
    # the search index ships empty: the held party names never reach the snapshot; the
    # tables stay so the file is at schema 10 like any store
    assert {"search_doc", "search_fts", "search_meta"} <= tables
    assert s.execute("SELECT COUNT(*) FROM search_doc").fetchone()[0] == 0
    empty = "SELECT COUNT(*) FROM search_fts WHERE search_fts MATCH 'a*'"
    assert s.execute(empty).fetchone()[0] == 0
    assert "parties" not in m.counts and m.held_tables == list(dump.HELD_TABLES)
    assert s.execute("SELECT COUNT(DISTINCT stb_filing_id) FROM filing").fetchone()[0] == 2
    s.close()
    idx = json.loads((out / "index.json").read_text())
    assert idx["latest"]["sha256"] == m.latest.sha256 and len(idx["latest"]["sha256"]) == 64
    assert (
        "CC0" in (out / "LICENSE.txt").read_text()
        and "CREATE TABLE" in (out / "schema.sql").read_text()
    )
    # a later cut in the month replaces latest and keeps the month's one archive
    m2 = dump.dump(path, out, today=date(2026, 9, 2), now="2026-09-02T04:10:00+00:00")
    assert [f.name for f in m2.dated] == ["docketyard-2026-09-01.sqlite.gz"]
    assert not (out / "docketyard-2026-09-02.sqlite.gz").exists()
    assert dump.read_manifest(out).built_at == "2026-09-02T04:10:00+00:00"
    assert m2.dated[0].sha256 == m.dated[0].sha256  # an archive keeps last night's hash
    # a month whose first was missed still gets its archive on the first run that happens
    m3 = dump.dump(path, out, today=date(2026, 10, 3))
    assert [f.name for f in m3.dated][0] == "docketyard-2026-10-03.sqlite.gz"


def test_scrub_refuses_a_table_it_does_not_know(tmp_path):
    import pytest

    path = build_store(tmp_path)
    con = db.connect(path)
    con.execute("CREATE TABLE subscription_digest (email_hash TEXT, last_sent TEXT)")
    con.commit()
    con.close()
    with pytest.raises(dump.Unsafe):
        dump.dump(path, tmp_path / "public")
    assert not (tmp_path / "public" / dump.LATEST).exists()  # nothing was offered


def test_data_page_and_files_follow_the_manifest(tmp_path):
    path = build_store(tmp_path)
    out = tmp_path / "public"
    client = TestClient(create_app(path, public_dir=out))
    r = client.get("/data")
    assert r.status_code == 200 and "has not been cut yet" in r.text
    dump.dump(path, out, today=date(2026, 9, 1))
    r = client.get("/data")
    assert "docketyard-latest.sqlite.gz" in r.text and "CC0" in r.text
    assert "docketyard-2026-09-01.sqlite.gz" in r.text
    f = client.get("/data/files/docketyard-latest.sqlite.gz")
    assert f.status_code == 200 and f.content[:2] == b"\x1f\x8b"
    assert client.get("/data/files/index.json").json()["licence"] == "CC0-1.0"
    assert client.get("/data/files/../docketyard.sqlite").status_code in (400, 404)


def test_json_twins_at_the_permanent_addresses(tmp_path):
    path = build_store(tmp_path)
    client = TestClient(create_app(path))
    r = client.get("/d/FD-36873.json")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=1800"
    d = r.json()
    assert d["licence"] == "CC0-1.0" and d["source"] == "https://docketyard.org/"
    assert "enriched" in d["held"] and "parties" not in d["docket"]
    doc = d["docket"]
    assert doc["printed"] == "FD 36873" and doc["url"] == "https://docketyard.org/d/FD-36873"
    assert len(doc["entries"]) == 3 and doc["sub_dockets"][0]["raw_docket"].startswith("FD_36873")
    e = doc["entries"][0]
    assert e["url"].startswith("https://docketyard.org/") and "date_printed" in e
    fid = next(x["record_id"] for x in doc["entries"] if x["kind"] == "filing")
    one = client.get(f"/filing/{fid}.json").json()["filing"]
    assert one["record_id"] == fid and one["docket"]["printed"].startswith("FD 36873")
    assert client.get("/filing/nope.json").status_code == 404
    assert client.get("/d/FD-99999.json").status_code == 404
    r = client.get("/d/fd-36873.json", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/d/FD-36873.json"
    sub = client.get("/d/FD-36873/sub/1.json").json()
    assert (
        sub["requested"]["printed"] == "FD 36873 (Sub-No. 1)"
        and sub["docket"]["printed"] == "FD 36873"
    )
    assert d["shape_version"] == 1
    # the key set is the public contract: a rename must be a deliberate shape bump
    assert set(e) == {
        "kind",
        "date",
        "date_printed",
        "docket_raw",
        "record_id",
        "type",
        "filed_for_raw",
        "deciding_body",
        "summary",
        "attachments",
        "also_in",
        "url",
    }


def test_every_template_is_packaged():
    """The wheel ships only the globs in pyproject's package-data: a template the app can
    render locally but the image cannot is a 500 in production (llms.txt, 2026-08-27)."""
    import fnmatch
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    globs = re.search(r'"docketyard.web" = \[(.*?)\]', (root / "pyproject.toml").read_text()).group(
        1
    )
    patterns = re.findall(r'"([^"]+)"', globs)
    web = root / "src" / "docketyard" / "web"
    for f in (web / "templates").iterdir():
        rel = f.relative_to(web).as_posix()
        assert any(fnmatch.fnmatch(rel, p) for p in patterns), f"{rel} is not in package-data"
