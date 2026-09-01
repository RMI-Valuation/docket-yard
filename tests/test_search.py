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
        # the caption `docs/search.md` has promised as-you-type since M4; the fast path was
        # the one row that answered with a bare number
        "caption": "UP/NS CONTROL",
    }
    # the marked-up snippet is for one template and never for a JSON answer
    assert "snippet" not in s["hits"][0]
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


def test_a_result_row_says_what_the_proceeding_is_and_why_it_matched(tmp_path):
    """§ B: the index yields (kind, ref, path, title, body, fact) and the template rendered
    three of them, so 86,069 of 96,225 rows published an identifier and nothing else while
    the Board's caption sat one field away in the same tuple."""
    path, _ = _indexed(tmp_path)
    con = db.connect(path)
    family = search.search(con, "control")[0]
    assert family.title == "FD 36873" and family.caption == "UP/NS CONTROL"
    sub = search.search(con, "peoria")[0]
    assert sub.title == "FD 36873 (Sub-No. 1)" and sub.caption == "PEORIA SUB"
    # a party's title is already its name, so it needs no caption beside it
    assert search.search(con, "nrdc")[0].caption == ""
    con.close()
    r = TestClient(create_app(path)).get("/search", params={"q": "peoria"})
    assert r.status_code == 200
    assert ">PEORIA SUB</a>" in r.text  # the caption is the link, the number sits beside it
    assert "FD 36873 (Sub-No. 1)</span>" in r.text


def test_the_snippet_says_why_a_row_matched_and_never_repeats_the_caption(tmp_path):
    path, _ = _indexed(tmp_path)
    con = db.connect(path)
    # the family row matched on a SUB-docket's caption: the snippet is the only thing on
    # the row that can say which one
    family = [h for h in search.search(con, "peoria") if h.path == "/d/FD-36873"][0]
    assert search.MARK_OPEN in family.snippet and "PEORIA" in family.snippet
    # the sub-docket's own row matched its own caption, which is already printed as its
    # title: a second marked copy of the same string is not a reason, it is noise
    sub = [h for h in search.search(con, "peoria") if h.path == "/d/FD-36873/sub/1"][0]
    assert sub.snippet == ""
    con.close()
    r = TestClient(create_app(path)).get("/search", params={"q": "peoria"})
    assert "<mark>PEORIA</mark>" in r.text
    assert search.MARK_OPEN not in r.text  # the markers never reach the page as themselves


def test_a_snippet_cannot_carry_markup_out_of_the_record(tmp_path):
    """The body holds the Board's printed text and the words environmental commenters
    wrote — external input. The snippet is marked with control characters and the web tier
    escapes before it substitutes tags, so the only markup that can reach the page is the
    markup search.py put there."""
    path, _ = _indexed(tmp_path)
    con = db.connect(path)
    con.execute(
        "UPDATE search_doc SET body = ? WHERE kind = 'docket' AND title = 'FD 36873'",
        ("<script>alert(1)</script> tainted \"'&<> caption words",),
    )
    con.execute("INSERT INTO search_fts (search_fts) VALUES ('rebuild')")
    con.commit()
    hit = search.search(con, "tainted")[0]
    assert "<script>" in hit.snippet  # the store keeps the record's own text verbatim
    con.close()
    r = TestClient(create_app(path)).get("/search", params={"q": "tainted"})
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    assert "<mark>tainted</mark>" in r.text


def test_highlight_escapes_before_it_marks():
    from docketyard.web.app import highlight

    marked = f"a {search.MARK_OPEN}<b>{search.MARK_CLOSE} c"
    assert str(highlight(marked)) == "a <mark>&lt;b&gt;</mark> c"
    assert str(highlight('" onerror=x')) == "&#34; onerror=x"


def test_migration_0013_alters_a_populated_index_without_disturbing_it(tmp_path):
    """The path production takes. 0012 empties `search_doc` before recreating it, so a test
    starting there proves nothing about an ALTER on a *populated* external-content FTS5
    table — which is what 0013 is, and what its central claim rests on (schema-critic,
    2026-08-31): a content column the FTS table does not name is invisible to it."""
    path = tmp_path / "s.sqlite"
    con = db.connect(path, upto=12)
    assert con.execute("PRAGMA user_version").fetchone()[0] == 12
    for ref, title, body in (
        (1, "FD 36873", "UP/NS CONTROL · FD 36873"),
        (2, "AB 55 (Sub-No. 794X)", "ABANDONMENT IN CARBON COUNTY · AB 55"),
    ):
        con.execute(
            "INSERT INTO search_doc (kind, ref, path, title, body, fact)"
            " VALUES ('docket', ?, ?, ?, ?, 'x')",
            (ref, f"/d/{ref}", title, body),
        )
    con.execute("INSERT INTO search_fts (search_fts) VALUES ('rebuild')")
    con.execute(
        "INSERT INTO search_meta (key, signature, build, built_at)"
        " VALUES ('built', '2.1.1.1.1.0.0.0.0', 7, '2026-08-30T00:00:00+00:00')"
    )
    con.commit()
    con.close()

    con = db.connect(path)  # the migration production will run
    assert con.execute("PRAGMA user_version").fetchone()[0] == 13
    # every row survives, un-rebuilt, with the column's default
    assert con.execute("SELECT COUNT(*) FROM search_doc").fetchone()[0] == 2
    assert {c for (c,) in con.execute("SELECT caption FROM search_doc")} == {""}
    # and the index still answers, still ranks, and still snippets — no rebuild yet
    hits = search.search(con, "carbon")
    assert [h.title for h in hits] == ["AB 55 (Sub-No. 794X)"]
    assert search.MARK_OPEN in hits[0].snippet and "CARBON" in hits[0].snippet
    assert hits[0].caption == ""  # nothing has filled it in
    # the ETag's build counter is not restarted, and the format bump is what rebuilds
    signature, build = search.built(con)
    assert build == 7 and signature.startswith("2.")
    assert search.signature(con).startswith(f"{search.INDEX_FORMAT}.")
    assert search.rebuild(con).get("unchanged") is not True
    assert search.built(con)[1] == 8
    con.close()


def test_a_snippet_shows_the_seam_between_two_fields(tmp_path):
    """`body` is a concatenation, `snippet()` windows across it with no field boundary, and
    the page renders the result in the Board's-words styling — so a plain space let one
    window print two captions, or a number and a caption, as one apparently-quoted run
    (schema-critic, 2026-08-31)."""
    path, _ = _indexed(tmp_path)
    con = db.connect(path)
    body = con.execute(
        "SELECT body FROM search_doc WHERE kind = 'docket' AND title = 'FD 36873'"
    ).fetchone()[0]
    # the caption leads, the sub-caption follows, the number spellings come last, and every
    # seam between them is visible
    assert body == "UP/NS CONTROL · PEORIA SUB · FD 36873 FD36873"
    family = [h for h in search.search(con, "peoria") if h.path == "/d/FD-36873"][0]
    assert "·" in family.snippet  # the reader can see where one quotation ends
    con.close()


def test_the_index_carries_no_control_characters(tmp_path):
    """The snippet's markers ARE control characters and `escape()` passes them through, so
    a record carrying one would put a stray tag on the page. Made a property of the index
    rather than an assumption about the Board."""
    path = build_store(tmp_path)
    con = db.connect(path)
    # planted as JSON escapes, not as raw bytes: a literal control character inside a JSON
    # string is malformed JSON, which `json_extract` rejects outright on some SQLite builds
    # (and silently tolerated on others — this test passed on Windows and failed on CI).
    # The record decodes these to the real characters, which is the case under test.
    changed = con.execute(
        r"UPDATE event SET payload = replace(payload, 'UP/NS CONTROL', 'UPNSCONTROL')"
        " WHERE payload LIKE '%UP/NS CONTROL%'"
    ).rowcount
    con.commit()
    assert changed, "fixture precondition: a caption the markers were planted in"
    captions = [
        c
        for (c,) in con.execute(
            "SELECT json_extract(latest_payload, '$.title') FROM docket_current"
        )
    ]
    assert any(search.MARK_OPEN in (c or "") for c in captions), (
        "precondition: the record itself now carries a marker"
    )
    search.rebuild(con, force=True)
    indexed = [v for row in con.execute("SELECT title, body FROM search_doc") for v in row]
    assert any("CONTROL" in v for v in indexed)  # the caption is still indexed...
    assert not any(search.MARK_OPEN in v or search.MARK_CLOSE in v for v in indexed)  # ...clean
    con.close()
