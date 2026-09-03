"""The page-text render (ADR 0021 D7-D9): `/filing/<id>/text` and `/decision/<id>/text`,
one address per record, a page per anchor, every read page labelled with who read it, the
scan one click away, the band's operand or its absence, and a way to report a misreading.
"""

from fastapi.testclient import TestClient

from docketyard.store import db
from docketyard.text import load
from docketyard.web.app import create_app
from tests.test_documents import (  # noqa: F401 — the fixture registers itself here too
    _store_with_document,
    no_store_in_the_environment,
)
from tests.test_text_load import LATER, STAMP, _extraction, _ocr, _reading

AGAINST_TEXT_LAYER = {"method": "pymupdf", "method_version": "1.24.10", "render_profile": "native"}
AGAINST_OCR = {"method": "dots.mocr", "method_version": "1.5", "render_profile": "150"}


def _loaded(path, data_dir, doc):
    """One reading into the store at `path`, its payload under `data_dir`."""
    con = db.connect(path)
    out = load.load_reading(con, data_dir, _reading(doc))
    con.commit()
    con.close()
    return out


def _paginated(path, sha, count):
    con = db.connect(path)
    con.execute(
        "INSERT INTO document_pagination (document_sha256, outcome, page_count, had_text_layer,"
        " method, method_version, asserted_at, confidence, confidence_state)"
        " VALUES (?, 'paginated', ?, 1, 'pymupdf', '1.24.10', ?, 0, 'unmeasured')",
        (sha, count, STAMP),
    )
    con.commit()
    con.close()


def _second(sha, text, against, distance=0.04, **over):
    doc = _ocr(sha, texts=(text,), role="second", method="ppocrv6", method_version="6", **over)
    doc["pages"][0]["agreement"] = {
        "distance": distance,
        "method": "normalised-edit-distance",
        "method_version": "1",
        "against": against,
    }
    return doc


def test_the_text_page_shows_every_read_page_labelled_with_the_scan_one_click_away(tmp_path):
    path, sha = _store_with_document(tmp_path)
    pages = ("abandonment in Perry County", "", "AB 1242")
    assert _loaded(path, tmp_path, _extraction(sha, pages)) == "loaded"
    _paginated(path, sha, 4)  # four pages, three read
    client = TestClient(create_app(path))
    r = client.get("/filing/311981/text")
    assert r.status_code == 200
    html = r.text
    assert "3 of 4 pages read" in html
    assert 'id="p1"' in html and 'id="p4"' in html and 'id="p5"' not in html
    assert "abandonment in Perry County" in html and "AB 1242" in html
    assert "publisher&#39;s own text layer" in html or "publisher's own text layer" in html
    assert "pymupdf 1.24.10" in html and "Read once" in html
    assert "Read as blank." in html  # page 2: an empty reading is a row, not an absence
    assert "Not yet read." in html  # page 4: in the count, no reading
    assert 'href="/filing/311981/view"' in html and f"/document/{sha}.pdf" in html  # the scan
    assert 'href="/corrections"' in html and "Report a misreading" in html
    assert "docketyard.org/filing/311981/text" in html and "#p4" in html
    assert '<link rel="canonical" href="https://docketyard.org/filing/311981/text">' in html
    assert "FD 36873" in html and "UP/NS CONTROL" in html
    assert "On this sheet" not in html  # the neighbours are not read for this page
    assert client.head("/filing/311981/text").status_code == 200
    # and the page is one click from the record and from the viewer, unconditionally
    assert 'href="/filing/311981/text"' in client.get("/filing/311981").text
    assert 'href="/filing/311981/text"' in client.get("/filing/311981/view").text


def test_an_ocr_page_names_its_engine_route_and_band_operand_or_says_it_has_none(tmp_path):
    path, sha = _store_with_document(tmp_path)
    _loaded(path, tmp_path, _ocr(sha))
    client = TestClient(create_app(path))
    html = client.get("/filing/311981/text").text
    assert "Machine-read by dots.mocr 1.5 at render 150, routed as degraded" in html
    assert "No second reading yet, so no band." in html
    _loaded(path, tmp_path, _second(sha, "abandonment in Perry Country", AGAINST_OCR, ran_at=LATER))
    html = client.get("/filing/311981/text").text
    assert (
        "Distance from the second reading (ppocrv6 6): 0.040 by normalised-edit-distance 1" in html
    )
    assert "Perry Country" not in html  # the second reading never reaches the display
    assert "page count is not yet recorded" in html


def test_a_band_measured_against_an_earlier_primary_is_not_this_pages_band(tmp_path):
    """The primary is superseded routinely and the second is not re-measured with it; a
    distance against text no longer shown is a false number on a page (ADR 0021 D8)."""
    path, sha = _store_with_document(tmp_path)
    _loaded(path, tmp_path, _ocr(sha))
    _loaded(path, tmp_path, _second(sha, "abandonment in Perry Country", AGAINST_OCR, ran_at=LATER))
    client = TestClient(create_app(path))
    assert "0.040" in client.get("/filing/311981/text").text
    newer = _ocr(
        sha,
        texts=("abandonment in Perry County.",),
        method_version="1.6",
        ran_at="2026-09-04T00:00:00+00:00",
    )
    _loaded(path, tmp_path, newer)
    html = client.get("/filing/311981/text").text
    assert "dots.mocr 1.6" in html and "0.040" not in html
    assert "measured against an earlier reading of this page, so no band" in html


def test_a_text_layer_page_with_a_second_reading_shows_the_distance(tmp_path):
    """The label is data-driven: a born-digital page that is also OCR'd has a band."""
    path, sha = _store_with_document(tmp_path)
    _loaded(path, tmp_path, _extraction(sha, ("abandonment in Perry County",)))
    _loaded(path, tmp_path, _second(sha, "abandonment in Perry Country", AGAINST_TEXT_LAYER))
    html = TestClient(create_app(path)).get("/filing/311981/text").text
    assert "publisher&#39;s own text layer" in html or "publisher's own text layer" in html
    assert "Read once" not in html and "0.040" in html


def test_a_human_correction_wins_the_display_and_says_so(tmp_path):
    path, sha = _store_with_document(tmp_path)
    _loaded(path, tmp_path, _extraction(sha, ("abandonment in Perry County",)))
    con = db.connect(path)
    con.execute(
        "INSERT INTO document_text (document_sha256, page_no, method, method_version,"
        " render_profile, reading_channel, reading_role, text, text_sha256, confidence,"
        " confidence_state, asserted_at) VALUES (?, 1, 'human', 'unversioned', 'human',"
        " 'human', 'human', 'abandonment in Ferry County', 'x', 1, 'human', ?)",
        (sha, STAMP),
    )
    con.commit()
    con.close()
    html = TestClient(create_app(path)).get("/filing/311981/text").text
    assert "abandonment in Ferry County" in html and "Perry County" not in html
    assert "Corrected by a person (2026-09-03)" in html
    assert "no band" not in html  # a human row carries no band sentence at all


def test_machine_read_text_is_external_content_and_is_escaped(tmp_path):
    """A PDF's text layer is whatever the filer's software put there; it reaches the page
    as text, never as markup."""
    path, sha = _store_with_document(tmp_path)
    hostile = '<script>alert(1)</script> <a href="x">y</a> & "quoted"'
    _loaded(path, tmp_path, _extraction(sha, (hostile,)))
    html = TestClient(create_app(path)).get("/filing/311981/text").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert '<a href="x">' not in html and "&amp; &#34;quoted&#34;" in html


def test_the_text_page_has_its_own_validator_per_document_and_is_held(tmp_path):
    """A corrected page, a new reading or a page count moves this page's ETag and no
    other's (ocr-migration.md item 11); every term is per document, none a table scan; the
    held text inherits the party module's robots rule (item 25)."""
    path, sha = _store_with_document(tmp_path)
    _loaded(path, tmp_path, _extraction(sha, ("abandonment in Perry County",)))
    client = TestClient(create_app(path))
    text_etag = client.get("/filing/311981/text").headers["etag"]
    site_etag = client.get("/filing/311981").headers["etag"]
    assert text_etag != site_etag
    assert (
        client.get("/filing/311981/text", headers={"if-none-match": text_etag}).status_code == 304
    )
    con = db.connect(path)
    con.execute(
        "INSERT INTO correction (target_table, target_key, note, asserted_at)"
        " VALUES ('document_text', ?, 'Ferry, not Perry', ?)",
        (f"{sha}/1/pymupdf/1.24.10/native", STAMP),
    )
    con.commit()
    con.close()
    after_correction = client.get("/filing/311981/text").headers["etag"]
    assert after_correction != text_etag
    assert client.get("/filing/311981").headers["etag"] == site_etag
    _paginated(path, sha, 3)  # a page count lands: the render changes, so must the validator
    after_count = client.get("/filing/311981/text").headers["etag"]
    assert after_count != after_correction
    # a page count corrected by its surrogate id moves it too
    con = db.connect(path)
    pid = con.execute("SELECT pagination_id FROM document_pagination").fetchone()[0]
    con.execute(
        "INSERT INTO correction (target_table, target_key, note, asserted_at)"
        " VALUES ('document_pagination', ?, 'four pages, not three', ?)",
        (str(pid), STAMP),
    )
    con.commit()
    con.close()
    assert client.get("/filing/311981/text").headers["etag"] != after_count
    robots = client.get("/robots.txt").text
    assert "Disallow: /filing/*/text" in robots and "Disallow: /decision/*/text" in robots
    assert robots.index("Disallow: /filing/*/text") > robots.index("User-agent: GPTBot")
    assert "/filing/311981/text" not in client.get("/sitemap.xml").text
    # and the held layer's prose moved with the rule
    assert "machine-read text" in client.get("/data").text
    assert "machine-read text" in client.get("/api").text
    assert "machine-read page text" in client.get("/llms.txt").text


def test_only_a_pdf_is_a_text_pages_file_and_the_viewer_agrees_on_which(tmp_path):
    """One attachment rule for the viewer and the text page (`documents.pick`): the scan
    link on the text page lands on the file whose text is shown, and a held file that is
    not a PDF is offered as a download, never as a text page."""
    path, sha = _store_with_document(tmp_path)
    con = db.connect(path)
    con.execute("UPDATE document SET media_type = 'xlsx' WHERE document_sha256 = ?", (sha,))
    con.commit()
    con.close()
    client = TestClient(create_app(path))
    html = client.get("/filing/311981/text").text
    assert "not a kind whose text is read" in html and "no text is read from it" in html
    assert 'href="/filing/311981/view"' not in html  # no scan of a spreadsheet


def test_a_record_with_no_file_or_no_reading_still_has_a_page(tmp_path):
    path, sha = _store_with_document(tmp_path)
    client = TestClient(create_app(path))
    r = client.get("/filing/311981/text")  # held, nothing read
    assert r.status_code == 200 and "Nothing has been read" in r.text
    r = client.get("/decision/53210/text")  # its file was refused (404), never held
    assert r.status_code == 200 and "not been fetched" in r.text
    assert client.get("/filing/999999/text").status_code == 404
    r = client.get("/filing/311981/text?file=9")  # falls back to the first, as the viewer does
    assert r.status_code == 200
    assert '<link rel="canonical" href="https://docketyard.org/filing/311981/text">' in r.text


def test_pages_beyond_the_count_are_said_plainly(tmp_path):
    path, sha = _store_with_document(tmp_path)
    _loaded(path, tmp_path, _extraction(sha, ("a", "b", "c")))
    _paginated(path, sha, 2)
    html = TestClient(create_app(path)).get("/filing/311981/text").text
    assert "3 pages read; the file was counted at 2" in html
    assert 'id="p3"' in html
