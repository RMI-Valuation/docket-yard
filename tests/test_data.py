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


def test_snapshot_omits_readers_and_measures_itself(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    subscriptions.subscribe(con, "secret@example.org", 1, "pass")
    con.close()
    out = tmp_path / "public"
    m = dump.dump(path, out, today=date(2026, 9, 1), now="2026-09-01T04:10:00+00:00")
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
    assert {"docket", "filing", "decision_record", "event", "capture", "party"} <= tables
    assert s.execute("SELECT COUNT(DISTINCT stb_filing_id) FROM filing").fetchone()[0] == 2
    s.close()
    idx = json.loads((out / "index.json").read_text())
    assert idx["latest"]["sha256"] == m.latest.sha256 and len(idx["latest"]["sha256"]) == 64
    assert (
        "CC0" in (out / "LICENSE.txt").read_text()
        and "CREATE TABLE" in (out / "schema.sql").read_text()
    )
    # a mid-month cut replaces latest and drops nothing kept
    m2 = dump.dump(path, out, today=date(2026, 9, 2), now="2026-09-02T04:10:00+00:00")
    assert [f.name for f in m2.dated] == ["docketyard-2026-09-01.sqlite.gz"]
    assert not (out / "docketyard-2026-09-02.sqlite.gz").exists()
    assert dump.read_manifest(out).built_at == "2026-09-02T04:10:00+00:00"


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
    assert client.get("/d/fd-36873.json").status_code == 200  # any case resolves
