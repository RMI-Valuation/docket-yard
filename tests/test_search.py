"""One search box (docs/search.md): a docket number is a redirect, not a search; captions,
party names and decision summaries are found by word; nothing about the reader is kept."""

from fastapi.testclient import TestClient

from docketyard.parties import resolve
from docketyard.store import db, search
from docketyard.web.app import create_app
from tests.test_web import build_store


def _indexed(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    resolve.run(con, log=lambda _: 0)
    counts = search.rebuild(con)
    con.close()
    return path, counts


def test_rebuild_indexes_families_parties_and_summaries(tmp_path):
    path, counts = _indexed(tmp_path)
    # the family, and the sub-docket as its own hit because its caption differs
    assert counts["docket"] == 2 and counts["party"] >= 2 and counts["build"] == 1
    con = db.connect(path)
    hits = search.search(con, "peoria")
    assert [h.path for h in hits] == ["/d/FD-36873/sub/1", "/d/FD-36873"]
    assert hits[0].fact == "in FD 36873" and hits[1].title == "FD 36873"
    assert search.search(con, "nrdc")[0].kind == "party"
    assert search.search(con, "control")[0].path == "/d/FD-36873"
    assert "2 filings" in search.search(con, "control")[0].fact  # the sheet's count: 311981 once
    # every token is quoted: FTS syntax typed by a reader is words, never operators
    assert search.search(con, 'peoria OR "x') == search.search(con, "peoria or x") == []
    assert search.search(con, "peor", prefix=True)[0].path == "/d/FD-36873/sub/1"
    assert search.search(con, "p", prefix=True) == []  # too short to be a lookup
    assert search.search(con, "   ") == [] and search.search(con, "*") == []
    # an unchanged record is not rebuilt; a changed one is, and the build number moves
    assert search.rebuild(con) == {"unchanged": True, "build": 1}
    con.execute(
        "INSERT INTO correction (target_table, target_id, note, asserted_at)"
        " VALUES ('x', 1, 'n', 't')"
    )
    con.commit()
    assert search.rebuild(con)["build"] == 2
    # the fast path: the exact identity when held, else the family, else nothing
    assert search.held_docket(con, "fd 36873 (sub-no. 1)").path == "/d/FD-36873/sub/1"
    assert search.held_docket(con, "FD 36873 (Sub-No. 9)").path == "/d/FD-36873"
    assert search.held_docket(con, "FD 99999") is None and search.held_docket(con, "x") is None
    # a number plus a word is a search, not a redirect with the word dropped
    assert search.held_docket(con, "FD 36873 peoria") is None
    assert search.search(con, "FD 36873 peoria")[0].path == "/d/FD-36873/sub/1"
    # a retirement without an insert moves the signature
    before = search.signature(con)
    con.execute(
        "UPDATE party_name SET superseded_by = name_id"
        " WHERE name_id = (SELECT MIN(name_id) FROM party_name)"
    )
    con.commit()
    assert search.signature(con) != before
    con.close()


def test_search_page_and_suggest(tmp_path):
    path, _ = _indexed(tmp_path)
    client = TestClient(create_app(path))
    r = client.get("/search", params={"q": "fd 36873"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/d/FD-36873"  # never a search
    r = client.get("/search", params={"q": "FD 99999"})  # a number the record does not hold
    assert r.status_code == 200 and "Nothing on record" in r.text
    r = client.get("/search", params={"q": "FD 36873 (Sub-No. 9)"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/d/FD-36873"  # the family holds it
    r = client.get("/search", params={"q": "peoria"})
    assert r.status_code == 200 and 'href="/d/FD-36873"' in r.text and "2 results" in r.text
    assert r.headers["cache-control"] == "no-store" and 'content="noindex"' in r.text
    assert "ETag" not in r.headers and 'rel="canonical"' not in r.text
    # a stale validator never short-circuits a result page
    etag = client.get("/").headers["ETag"]
    stale = client.get("/search", params={"q": "peoria"}, headers={"If-None-Match": etag})
    assert stale.status_code == 200
    assert "Set-Cookie" not in r.headers
    empty = client.get("/search")
    assert "Nothing you search for is kept" in empty.text and "noindex" not in empty.text
    assert empty.headers["cache-control"].startswith("public")  # the bare page is a page
    s = client.get("/suggest", params={"q": "peor"})
    assert s.status_code == 200 and s.headers["cache-control"] == "no-store"
    assert s.json()["hits"][0]["path"] == "/d/FD-36873/sub/1"
    s = client.get("/suggest", params={"q": "FD 36873"}).json()
    assert s["hits"][0] == {
        "kind": "docket",
        "path": "/d/FD-36873",
        "title": "FD 36873",
        "fact": "the docket sheet",
    }
    assert [h["path"] for h in s["hits"]].count("/d/FD-36873") == 1  # led once, not twice
    assert client.get("/suggest").json() == {"hits": []}
    assert client.get("/suggest", params={"q": "p"}).json() == {"hits": []}
    # a rebuild moves the version stamp, so a cached result page is not answered 304
    etag = client.get("/").headers["ETag"]
    con = db.connect(path)
    search.rebuild(con, force=True)
    con.close()
    assert client.get("/", headers={"If-None-Match": etag}).status_code == 200
    # the old lookup box's non-number falls through to search
    r = client.get("/d", params={"q": "peoria"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/search?q=peoria"
    assert 'action="/search"' in client.get("/").text
