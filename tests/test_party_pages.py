"""ADR 0015: a party has a permanent address. The id is the address; every member of a
same_as component resolves; a non-representative answers 301 to the representative;
superseding a join changes only the redirect target; an id is never reused."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from docketyard.cli import main
from docketyard.parties import resolve
from docketyard.store import db, directory
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
    assert client.get("/p/\u00b2").status_code == 404  # superscript two: isdigit, not int
    assert client.get("/p/\u0663").status_code == 404  # Arabic-Indic three: not a second spelling
    r = client.get(f"/p/00{nrdc}", follow_redirects=False)  # one spelling of the address
    assert r.status_code == 301 and r.headers["location"] == f"/p/{nrdc}"
    r = client.get(f"/p/{nrdc}/feed/", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/p/{nrdc}/feed"
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

    before_etag = TestClient(create_app(path)).get(f"/p/{lo}").headers["ETag"]

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
    # the join moved the store's version: a validator from before it must not answer 304
    assert r.headers.get("ETag") is None  # a 301 carries no validator
    assert client.get(f"/p/{lo}").headers["ETag"] != before_etag
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
    assert cli("unjoin", hi, 999999, "--note", "x") == 1  # no such party
    # the seed's own pass never re-makes a retired join, and neither does a plain re-join
    con = db.connect(path)
    resolve.run(con, log=lambda _: 0)
    assert (
        con.execute(
            "SELECT COUNT(*) FROM party_relationship WHERE rel_type = 'same_as'"
            " AND from_party = ? AND to_party = ? AND superseded_by IS NULL",
            (lo, hi),
        ).fetchone()[0]
        == 0
    )
    con.close()
    assert cli("join", lo, hi, "--note", "again") == 1
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
    with pytest.raises(sqlite3.IntegrityError, match="renumber"):
        con.execute("UPDATE party SET party_id = 999 WHERE party_id = ?", (nrdc,))
    con.close()


def test_unjoin_reports_what_still_holds_a_component_together(tmp_path):
    path, nrdc, ppu = _resolved_store(tmp_path)
    con = db.connect(path)
    third = con.execute(
        "INSERT INTO party (founding_key, created_at) VALUES ('third', 't')"
    ).lastrowid
    resolve.join(con, nrdc, third, "a")
    resolve.join(con, third, ppu, "b")
    assert resolve.component_of(con, ppu) == min(nrdc, ppu, third)
    with pytest.raises(ValueError, match="through other edges"):
        resolve.unjoin(con, nrdc, ppu, "no direct edge")
    # join() refuses a redundant edge; the seed can still assert one, so make it that way
    assert resolve._join(con, nrdc, ppu, "t", {"note": "c"}) is not None
    con.commit()
    # a triangle splits one edge at a time: the retirement stands and the rest is named
    edge, still = resolve.unjoin(con, nrdc, ppu, "wrong")
    assert len(still) == 2 and resolve.component_of(con, ppu) == min(nrdc, ppu, third)
    row = con.execute(
        # 0014 renamed the column and made it TEXT (it must address a natural-keyed
        # citation row); an integer pk is rendered as digits
        "SELECT method_version, source_location FROM correction WHERE target_key = ?",
        (str(edge),),
    ).fetchone()
    assert row[0] == resolve.JOIN_VERSION and "unjoin" in row[1]
    _, still = resolve.unjoin(con, third, ppu, "wrong too")
    assert still == [] and resolve.component_of(con, ppu) == ppu
    con.close()


def test_parties_is_a_page_before_it_is_a_search(tmp_path):
    """`/parties` is one of the three things in the masthead and was a heading, a sentence
    and an empty box over 10,108 parties, none of them named — no way in for a reader who
    did not already know a name (navigation-review.md § C)."""
    path = build_store(tmp_path)
    con = db.connect(path)
    resolve.run(con, log=lambda _: 0)
    rows = directory.rows(con)
    con.close()
    assert rows and all(r.name for r in rows)
    assert rows == sorted(rows, key=lambda r: (r.name.casefold(), r.party_id))  # by name
    d = directory.directory(rows)
    assert d.parties == len(rows)
    assert d.busiest[0].filings >= d.busiest[-1].filings  # busiest first
    # A–Z first and the digit bucket last, which is NOT plain `sorted()` — that puts '0'
    # in front, and this assertion passed only because the fixture has no digit-initial
    # name (code review, 2026-09-01)
    keys = [le.key for le in d.letters]
    assert keys == sorted(keys, key=lambda k: (k == directory.OTHER, k))
    assert set(keys) == {directory._bucket(r.name) for r in rows}

    client = TestClient(create_app(path))
    r = client.get("/parties")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=1800"
    assert "parties on record" in r.text
    for row in d.busiest:
        assert f'href="/p/{row.party_id}"' in r.text  # every one of them named and linked
    # the alphabet, and a page behind each entry
    for le in d.letters:
        assert f'href="/parties/{le.key}"' in r.text
        page = client.get(f"/parties/{le.key}")
        assert page.status_code == 200
        assert page.text.count('href="/p/') >= le.parties
    # a search still answers, and does not carry the directory with it
    hit = client.get("/parties", params={"name": "nrdc"})
    assert hit.status_code == 200 and "parties on record" not in hit.text
    assert hit.headers["cache-control"] != "public, max-age=1800"  # a query is not cached


def test_a_party_letter_has_one_address_and_no_others(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    resolve.run(con, log=lambda _: 0)
    con.close()
    client = TestClient(create_app(path))
    con = db.connect(path)
    try:
        live = directory.directory(directory.rows(con)).letters[0].key
    finally:
        con.close()
    r = client.get(f"/parties/{live.lower()}", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/parties/{live}"
    assert client.get("/parties/9").status_code == 404  # no parties file under it
    assert client.get("/parties/ZZ").status_code == 404
