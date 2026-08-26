"""ADR 0015: a party has a permanent address. The id is the address; every member of a
same_as component resolves; a non-representative answers 301 to the representative;
superseding a join changes only the redirect target; an id is never reused."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from docketyard.cli import main
from docketyard.parties import resolve
from docketyard.store import db
from docketyard.web import sitemaps
from docketyard.web.app import create_app
from tests.test_web import build_store


def _resolved_store(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    resolve.run(con, log=lambda _: 0)
    nrdc = con.execute("SELECT party_id FROM party WHERE founding_key = 'nrdc'").fetchone()[0]
    ppu = con.execute("SELECT party_id FROM party WHERE founding_key = 'ppu'").fetchone()[0]
    con.close()
    return path, nrdc, ppu


def test_party_page_names_provenance_and_dockets_with_captions(tmp_path):
    path, nrdc, _ = _resolved_store(tmp_path)
    client = TestClient(create_app(path))
    r = client.get(f"/p/{nrdc}")
    assert r.status_code == 200
    assert f'<link rel="canonical" href="https://docketyard.org/p/{nrdc}">' in r.text
    assert "FD 36873" in r.text and "UP/NS CONTROL" in r.text  # number and caption
    assert "25 Aug 2026" in r.text  # last filing date, quoted from the record
    assert "resolve-exact 1" in r.text and "from filing" in r.text  # provenance on the name
    assert f'href="/p/{nrdc}/feed"' in r.text and f'name="party" value="{nrdc}"' in r.text
    assert "Nothing here says what anyone argued" in r.text
    assert r.headers["ETag"] and "Set-Cookie" not in r.headers
    # the family fold: the sub-docket's filing counts under the parent, once
    assert r.text.count('href="/d/FD-36873"') == 1
    # /parties carries the same caption treatment and links to the page
    s = client.get("/parties", params={"name": "nrdc"})
    assert "UP/NS CONTROL" in s.text and f'href="/p/{nrdc}"' in s.text
    assert "25 Aug 2026" in s.text
    # the sheet's Parties block links to the page
    assert f'href="/p/{nrdc}"' in client.get("/d/FD-36873").text


def test_addresses_never_422_and_unknown_ids_are_404(tmp_path):
    path, nrdc, _ = _resolved_store(tmp_path)
    client = TestClient(create_app(path))
    assert client.get("/p/999999").status_code == 404
    assert client.get("/p/abc").status_code == 404
    assert client.get("/p/abc/feed").status_code == 404
    assert client.get("/p/999999/feed").status_code == 404
    r = client.get(f"/p/{nrdc}/union-pacific-railroad", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/p/{nrdc}"
    r = client.get(f"/feed/party/{nrdc}", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/p/{nrdc}/feed"
    assert client.get("/feed/party/abc", follow_redirects=False).status_code == 404
    f = client.get(f"/p/{nrdc}/feed")
    assert f.status_code == 200 and f.headers["content-type"].startswith("application/atom+xml")
    assert f"https://docketyard.org/p/{nrdc}/feed" in f.text


def test_join_folds_the_id_and_unjoin_moves_only_the_redirect(tmp_path, capsys):
    path, nrdc, ppu = _resolved_store(tmp_path)
    lo, hi = min(nrdc, ppu), max(nrdc, ppu)

    def cli(*args):
        return main(["--db", str(path), "parties", *[str(a) for a in args]])

    # a join needs a note, and two parties that exist
    assert cli("join", lo, hi, "--note", " ") == 1
    assert cli("join", lo, 999999, "--note", "x") == 1
    assert cli("join", lo, hi, "--note", "one entity", "--cite", "311981") == 0
    assert f"{hi} to /p/{lo}" in capsys.readouterr().out
    # joining again is refused: already one component
    assert cli("join", hi, lo, "--note", "again") == 1
    client = TestClient(create_app(path))
    r = client.get(f"/p/{hi}", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/p/{lo}"
    r = client.get(f"/p/{hi}/feed", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/p/{lo}/feed"
    page = client.get(f"/p/{lo}").text
    assert "Also known here as" in page and "one entity" in page and "see 311981" in page
    assert f'href="/p/{hi}"' in page and "human cli-join/1" in page
    assert "2 records held to be one entity" in page
    # the sub-docket filing folds to the family: one docket row, two filings, one caption
    assert "UP/NS CONTROL" in page and "PEORIA SUB" not in page
    assert "2 filings resolved to this party in 1 docket" in page
    con = db.connect(path)
    edge = con.execute(
        "SELECT source_location, method FROM party_relationship WHERE rel_type = 'same_as'"
        " AND from_party = ? AND to_party = ?",
        (lo, hi),
    ).fetchone()
    con.close()
    assert edge[1] == "human" and '"note": "one entity"' in edge[0] and '"cite"' in edge[0]
    # the sitemap lists the representative only
    con = db.connect(path)
    body = sitemaps.section(con, "docketyard.org", "parties", 1, "t1")
    con.close()
    assert body and f"https://docketyard.org/p/{lo}<" in body and f"/p/{hi}<" not in body
    assert "sitemap-parties-1.xml" in client.get("/sitemap.xml").text
    # unjoin: the edge is retired by itself, a correction row carries the note, and
    # only the redirect target changes — both ids answer 200 again
    assert cli("unjoin", hi, lo, "--note", "wrong") == 0
    assert cli("unjoin", hi, lo, "--note", "wrong") == 1  # nothing live to retire
    con = db.connect(path)
    assert (
        con.execute(
            "SELECT COUNT(*) FROM party_relationship WHERE superseded_by = edge_id"
        ).fetchone()[0]
        == 1
    )
    assert con.execute(
        "SELECT note FROM correction WHERE target_table = 'party_relationship'"
    ).fetchone() == ("wrong",)
    con.close()
    client = TestClient(create_app(path))
    assert client.get(f"/p/{hi}", follow_redirects=False).status_code == 200
    assert client.get(f"/p/{lo}", follow_redirects=False).status_code == 200
    assert "Also known here as" not in client.get(f"/p/{lo}").text


def test_a_party_is_never_deleted_so_an_id_is_never_reused(tmp_path):
    path, nrdc, _ = _resolved_store(tmp_path)
    con = db.connect(path)
    with pytest.raises(sqlite3.IntegrityError, match="permanent"):
        con.execute("DELETE FROM party WHERE party_id = ?", (nrdc,))
    con.close()
