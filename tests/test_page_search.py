"""The page search path (ADR 0021 D7, ADR 0022 D4): pages of documents reach `/search` and
the MCP search by their own query path, each hit carrying who read the page, the band's
operand or why there is none, and the scan; never `/suggest`; never joined to `search()`.
"""

from fastapi.testclient import TestClient
from markupsafe import escape

from docketyard.store import db, pages, search
from docketyard.web import mcp
from docketyard.web.app import create_app
from tests.test_documents import (  # noqa: F401 — the fixture registers itself here too
    _store_with_document,
    no_store_in_the_environment,
)
from tests.test_text_load import _extraction, _ocr
from tests.test_text_page import _loaded, _paginated, _second

PAGES = (
    "abandonment in Perry County, counsel jane.doe@example-law.com",
    "",
    "Docket No. AB 1242, Tazewell County",
)


def _with_text(tmp_path):
    path, sha = _store_with_document(tmp_path)
    assert _loaded(path, tmp_path, _extraction(sha, PAGES)) == "loaded"
    _paginated(path, sha, 3)
    con = db.connect(path)
    search.rebuild(con)  # the record index, for the hits the page hits sit under
    con.close()
    return path, sha


def test_a_page_hit_carries_the_label_the_band_and_the_scan(tmp_path):
    path, _ = _with_text(tmp_path)
    con = db.connect(path)
    found = search.search_pages(con, "tazewell")
    assert len(found.hits) == 1 and not found.truncated and found.dropped == 0
    h = found.hits[0]
    # the EARLIEST-FILED record that carries the document: 311900 (8/24) before 311981 (8/25)
    assert h.kind == "page" and h.path == "/filing/311900/text#p3"
    assert h.title == "Filing 311900, page 3" and h.fact == "in FD 36873 (Sub-No. 1)"
    assert h.caption  # the docket's caption as the Board printed it
    assert search.MARK_OPEN in h.snippet and "Tazewell" in h.snippet
    assert h.label == "The publisher's own text layer, read by pymupdf 1.24.10."
    assert h.band == "Read once; no second reading to compare it with, so no band."
    assert h.scan == "/filing/311900#file"
    # a record hit leaves the three empty: they are a page hit's obligation
    record = search.search(con, "control")[0]
    assert (record.label, record.band, record.scan) == ("", "", "")
    # the index holds the displayed bytes: an omitted email is not findable
    assert search.search_pages(con, "example-law").hits == []
    assert search.search_pages(con, "jane").hits == []
    assert search.search_pages(con, "omitted").hits[0].path.endswith("#p1")
    # every token is quoted, as in search(); an empty query is nothing
    assert search.search_pages(con, 'tazewell OR "x').hits == []
    assert search.search_pages(con, "  ").hits == []
    # the limit is a published promise: clamped for every caller, and truncation is reported
    both = search.search_pages(con, "county", limit=1)
    assert len(both.hits) == 1 and both.truncated
    exact = search.search_pages(con, "county", limit=2)
    assert len(exact.hits) == 2 and not exact.truncated  # exactly the limit is not "more"
    assert len(search.search_pages(con, "county", limit=500).hits) == 2
    con.close()


def test_the_wording_is_the_text_pages_own(tmp_path):
    """One home for the label and the band (`store.pages`): the hit and the page agree."""
    path, sha = _with_text(tmp_path)
    con = db.connect(path)
    shown = pages.readings(con, sha)
    h = search.search_pages(con, "tazewell").hits[0]
    assert h.label == pages.label(shown[2]) and h.band == pages.band(shown[2])
    con.close()
    html = TestClient(create_app(path)).get("/filing/311981/text").text
    assert str(escape(h.label)) in html and str(escape(h.band)) in html  # as the template escapes


def test_an_ocr_page_names_its_engine_and_its_band(tmp_path):
    path, sha = _store_with_document(tmp_path)
    ocr = _ocr(sha, texts=("faint fax page about Peoria",), method_version="1.5")
    assert _loaded(path, tmp_path, ocr) == "loaded"
    con = db.connect(path)
    h = search.search_pages(con, "peoria").hits[0]
    assert h.label == "Machine-read by dots.mocr 1.5 at render 150, routed as degraded."
    assert h.band == "No second reading yet, so no band."
    con.close()
    against = {"method": "dots.mocr", "method_version": "1.5", "render_profile": "150"}
    assert _loaded(path, tmp_path, _second(sha, "faint fax page about Peoria", against)) == "loaded"
    con = db.connect(path)
    h = search.search_pages(con, "peoria").hits[0]
    assert h.band.startswith("Distance from the second reading (ppocrv6 6): 0.040 by")
    assert h.band.endswith("— 0 is agreement.")
    con.close()


def test_a_human_row_has_no_band_and_says_who_corrected_it(tmp_path):
    path, sha = _with_text(tmp_path)
    con = db.connect(path)
    con.execute(
        "INSERT INTO document_text (document_sha256, page_no, method, method_version,"
        " render_profile, reading_channel, reading_role, text, text_sha256, confidence,"
        " confidence_state, asserted_at) VALUES (?, 3, 'human', 'unversioned', 'human',"
        " 'human', 'human', 'Docket No. AB 1242, Tazewell County (corrected)', 'h', 0,"
        " 'human', '2026-09-04T12:00:00+00:00')",
        (sha,),
    )
    con.commit()
    search.rebuild_pages(con, force=True)  # the human writer's half is by hand (page_index)
    h = search.search_pages(con, "corrected").hits[0]
    assert h.label == "Corrected by a person (2026-09-04)." and h.band == ""
    con.close()


def test_the_search_page_shows_pages_in_their_own_section_and_suggest_does_not(tmp_path):
    path, _ = _with_text(tmp_path)
    client = TestClient(create_app(path))
    html = client.get("/search?q=tazewell").text
    assert "In the text of documents" in html
    assert 'href="/filing/311900/text#p3"' in html and "Filing 311900, page 3" in html
    assert "<mark>Tazewell</mark>" in html
    assert "publisher&#39;s own text layer" in html or "publisher's own text layer" in html
    assert "so no band" in html and 'href="/filing/311900#file">Scan</a>' in html
    assert "Nothing on record matches" not in html  # a page hit is a result
    assert "narrow the words" not in html  # two pages matched, none were cut
    # a query that matches only a record shows no page section
    assert "In the text of documents" not in client.get("/search?q=control").text
    # and one matching nothing still says so
    assert "Nothing on record matches" in client.get("/search?q=zzzz").text
    assert client.get("/suggest?q=tazewell").json() == {"hits": []}


def test_the_mcp_search_hands_over_the_page_with_its_label_band_and_scan(tmp_path):
    path, _ = _with_text(tmp_path)
    con = db.connect(path)
    out = mcp._search(con, {"query": "tazewell"}, "docketyard.org")
    con.close()
    assert "(Filing 311900, page 3) — in FD 36873 (Sub-No. 1)" in out
    assert "https://docketyard.org/filing/311900/text#p3" in out
    assert "publisher's own text layer" in out and "so no band" in out
    assert "The scan: https://docketyard.org/filing/311900#file" in out
    assert "check it against the scan" in out and "narrow the words" not in out


def test_a_document_no_record_carries_is_not_a_hit_and_is_counted(tmp_path):
    path, _ = _with_text(tmp_path)
    con = db.connect(path)
    sha = "9" * 64
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'pdf', '2026-09-04T00:00:00+00:00')",
        (sha,),
    )
    con.commit()
    con.close()
    assert _loaded(path, tmp_path, _extraction(sha, ("orphan words here",))) == "loaded"
    con = db.connect(path)
    found = search.search_pages(con, "orphan")
    assert found.hits == [] and found.dropped == 1
    con.close()


def test_the_file_index_is_the_sheets_so_the_anchor_lands_on_the_right_file(tmp_path):
    """A record carrying a non-PDF whose URL sorts first: the text is file 1 on the sheet,
    the hit says `?file=1`, and the text page at `?file=1` shows it."""
    path, sha = _with_text(tmp_path)
    con = db.connect(path)
    other = "8" * 64
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'jpg', '2026-09-04T00:00:00+00:00')",
        (other,),
    )
    con.execute(
        "INSERT INTO filing_attachment (filing_pk, source_url, label, document_sha256)"
        " SELECT filing_pk, 'https://a.example/first.jpg', 'Map', ? FROM filing"
        " WHERE stb_filing_id = '311900'",
        (other,),
    )
    con.commit()
    h = search.search_pages(con, "tazewell").hits[0]
    assert h.path == "/filing/311900/text?file=1#p3" and h.scan == "/filing/311900?file=1#file"
    con.close()
    html = TestClient(create_app(path)).get("/filing/311900/text?file=1").text
    assert "Tazewell County" in html


def test_a_marker_the_record_itself_carries_never_becomes_a_mark(tmp_path):
    path, sha = _store_with_document(tmp_path)
    text = "Docket No. AB 1242 " + search.MARK_OPEN + "Tazewell" + search.MARK_CLOSE + " County"
    assert _loaded(path, tmp_path, _extraction(sha, (text,))) == "loaded"
    con = db.connect(path)
    h = search.search_pages(con, "tazewell").hits[0]
    assert h.snippet == ""  # shown without a snippet rather than with the record's mark
    con.close()
