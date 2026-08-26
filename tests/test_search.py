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
    assert counts["docket"] == 1 and counts["party"] >= 2  # the sub-docket folds into FD 36873
    con = db.connect(path)
    hits = search.search(con, "peoria")  # the sub-docket's caption finds the family
    assert [h.address for h in hits] == ["/d/FD-36873"] and hits[0].title == "FD 36873"
    assert search.search(con, "nrdc")[0].kind == "party"
    assert search.search(con, "control")[0].address == "/d/FD-36873"
    # every token is quoted: FTS syntax typed by a reader is words, never operators
    assert search.search(con, 'peoria OR "x') == search.search(con, "peoria or x") == []
    assert search.search(con, "peor", prefix=True)[0].address == "/d/FD-36873"
    assert search.search(con, "   ") == [] and search.search(con, "*") == []
    # rebuilding twice is the same index
    assert search.rebuild(con) == counts
    con.close()


def test_search_page_and_suggest(tmp_path):
    path, _ = _indexed(tmp_path)
    client = TestClient(create_app(path))
    r = client.get("/search", params={"q": "fd 36873"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/d/FD-36873"  # never a search
    r = client.get("/search", params={"q": "FD 99999"})  # a number the record does not hold
    assert r.status_code == 200 and "Nothing on record" in r.text
    r = client.get("/search", params={"q": "peoria"})
    assert r.status_code == 200 and 'href="/d/FD-36873"' in r.text and "1 result" in r.text
    assert "Set-Cookie" not in r.headers
    assert "Nothing you search for is kept" in client.get("/search").text
    s = client.get("/suggest", params={"q": "peor"})
    assert s.status_code == 200 and s.headers["cache-control"] == "no-store"
    assert s.json()["hits"][0]["address"] == "/d/FD-36873"
    s = client.get("/suggest", params={"q": "FD 36873"}).json()
    assert s["hits"][0] == {
        "kind": "docket",
        "address": "/d/FD-36873",
        "title": "FD 36873",
        "fact": "the docket sheet",
    }
    assert client.get("/suggest").json() == {"hits": []}
    # the old lookup box's non-number falls through to search
    r = client.get("/d", params={"q": "peoria"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/search?q=peoria"
    assert 'action="/search"' in client.get("/").text
