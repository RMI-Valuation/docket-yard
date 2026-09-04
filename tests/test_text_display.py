"""What the display rule omits (ADR 0021 D9, addendum 2026-09-04; migration 0020), and the
text page being noindex. The rule is one SQL function used by the view, by the index's
`enter` and by its `leave`, so every test here pins the three agreeing: what a page shows is
what a MATCH can find is what a 'delete' removes.
"""

from fastapi.testclient import TestClient

from docketyard.store import db, display, page_index, search
from docketyard.web.app import create_app
from tests.test_document_text_schema import _reading as _row
from tests.test_document_text_schema import _store
from tests.test_documents import (  # noqa: F401 — the fixture registers itself here too
    _store_with_document,
    no_store_in_the_environment,
)
from tests.test_text_load import _extraction
from tests.test_text_page import _loaded, _paginated

CONTACT = (
    "Served on counsel, Jane Q. Doe, jane.doe@example-law.com, tel. (202) 555-0134, "
    "fax 202-555-0199, and on the Board at 395 E Street SW, Washington, DC 20423-0001."
)


def test_emails_and_separated_phone_numbers_are_replaced_and_nothing_else_is():
    out = display.mask(CONTACT)
    assert out is not None
    assert "jane.doe@example-law.com" not in out and "[email omitted]" in out
    assert "(202) 555-0134" not in out and "202-555-0199" not in out
    assert out.count("[phone omitted]") == 2
    assert "395 E Street SW, Washington, DC 20423-0001" in out  # a postal address stays
    for untouched in (
        "Docket No. FD 36873 (Sub-No. 1), decided 2026-09-03; $1,234,567.89 in fees",
        "49 U.S.C. 10901; 49 CFR 1104.4; case 1:26-cv-01234; EP 711 (Sub-No. 2)",
        "2025450245",  # a bare ten-digit run is left: it is also how identifiers are written
        "STB Finance Docket No. 36500, decision 12345, pages 3-4 of 12",
        # a separated 3-3-4 with no telephone word is how identifiers are written too
        "Tariff 100-200-3000; Section 100.200.1234 applies; pp. 100-200 1234",
    ):
        assert display.mask(untouched) == untouched
    for phone in ("1-800-555-0100", "+1 202.555.0134", "202 555 0134 x12", "(202)555-0134"):
        assert display.mask(f"call {phone} today") == "call [phone omitted] today", phone
    assert display.mask("(202) 555-0134 x 2026 was filed") == "[phone omitted] x 2026 was filed"
    assert display.mask("Telephone No.: 202-555-0134") == "Telephone No.: [phone omitted]"
    assert display.mask("Intel: 202-555-0134") == "Intel: 202-555-0134"  # no cue, no phone
    assert display.mask("") == "" and display.mask(None) is None
    assert display.mask(display.mask(CONTACT)) == display.mask(CONTACT)  # idempotent


def test_the_view_shows_the_omission_and_the_stored_reading_keeps_the_words(tmp_path):
    con = _store(tmp_path)
    text_id = _row(con, text=CONTACT, text_sha256="c" * 64)
    stored = con.execute("SELECT text FROM document_text WHERE text_id = ?", (text_id,))
    assert stored.fetchone()[0] == CONTACT  # ADR 0021 D1: the reading is the document's words
    shown = con.execute("SELECT text FROM document_text_display WHERE text_id = ?", (text_id,))
    assert shown.fetchone()[0] == display.mask(CONTACT)
    assert con.execute("PRAGMA user_version").fetchone()[0] == 21


def test_the_index_holds_the_displayed_bytes_so_a_delete_carries_them_too(tmp_path):
    con = _store(tmp_path)
    text_id = _row(con, text=CONTACT, text_sha256="c" * 64)
    page_index.enter(con, text_id, CONTACT)  # the loader hands it the STORED text

    def hits(q):
        return con.execute("SELECT rowid FROM page_fts WHERE page_fts MATCH ?", (q,))

    assert hits("omitted").fetchall() == [(text_id,)]
    assert hits("counsel").fetchall() == [(text_id,)]
    assert hits('"example-law"').fetchall() == [] and hits("0134").fetchall() == []
    page_index.leave(con, text_id)  # FTS5 requires the text AS INDEXED: no stale tokens
    assert hits("omitted").fetchall() == [] and hits("counsel").fetchall() == []
    # and a whole rebuild from the view agrees with the incremental path
    page_index.enter(con, text_id, CONTACT)
    con.commit()
    assert search.PAGE_INDEX_FORMAT == f"display@0020.{display.VERSION}"
    assert search.rebuild_pages(con, force=True)["pages"] == 1
    assert hits("omitted").fetchall() == [(text_id,)] and hits("0134").fetchall() == []


def test_the_text_page_shows_the_omission_and_is_noindex_while_the_record_page_is_not(tmp_path):
    path, sha = _store_with_document(tmp_path)
    assert _loaded(path, tmp_path, _extraction(sha, (CONTACT, "AB 1242"))) == "loaded"
    _paginated(path, sha, 2)
    client = TestClient(create_app(path))
    r = client.get("/filing/311981/text")
    assert r.status_code == 200
    assert r.headers["X-Robots-Tag"] == "noindex"
    assert '<meta name="robots" content="noindex">' in r.text
    assert "jane.doe@example-law.com" not in r.text and "(202) 555-0134" not in r.text
    assert "[email omitted]" in r.text and "[phone omitted]" in r.text and "AB 1242" in r.text
    assert "Email addresses and telephone numbers are omitted" in r.text
    assert 'type="application/atom+xml"' in r.text  # the head block still carries the feed
    record = client.get("/filing/311981")
    assert "noindex" not in record.text and "X-Robots-Tag" not in record.headers
    # ordinary crawlers may still fetch the page, or they never see the noindex
    robots = client.get("/robots.txt").text.split("User-agent: ")[1]
    assert robots.startswith("*") and "/text" not in robots
    assert "Text pages are marked not to be indexed" in client.get("/methodology").text


def test_a_connection_without_the_function_cannot_read_the_view(tmp_path):
    """The intended failure for a copy queried raw: nothing shown rather than the unmasked
    text under this project's display rule. Every table reads as before."""
    import sqlite3

    con = _store(tmp_path)
    _row(con, text=CONTACT, text_sha256="c" * 64)
    con.commit()
    con.close()
    raw = sqlite3.connect(tmp_path / "s.sqlite")
    assert raw.execute("SELECT count(*) FROM document_text").fetchone()[0] == 1
    try:
        raw.execute("SELECT text FROM document_text_display").fetchall()
    except sqlite3.OperationalError as e:
        assert "no such function" in str(e)
    else:
        raise AssertionError("the view read without the display function")


def test_the_stored_text_cannot_be_updated_only_superseded(tmp_path):
    """ADR 0021 D1 as a trigger: `leave` and the view both rest on `text` never changing."""
    import sqlite3

    import pytest

    con = _store(tmp_path)
    text_id = _row(con, text=CONTACT, text_sha256="c" * 64)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("UPDATE document_text SET text = 'edited' WHERE text_id = ?", (text_id,))
    later = _row(con, text=CONTACT, text_sha256="c" * 64, page_no=2)
    con.execute(  # a supersession is the one write a reading takes, and it is not a text edit
        "UPDATE document_text SET superseded_by = ?, superseded_at = ? WHERE text_id = ?",
        (later, "2026-09-04T00:00:00+00:00", text_id),
    )


def test_the_house_rename_idiom_survives_a_view_that_calls_the_function(tmp_path):
    """SQLite re-parses every view on a RENAME, so a view calling an unregistered function
    would fail the next rebuild migration; `db.connect` registers it before `migrate`."""
    con = _store(tmp_path)
    con.execute("ALTER TABLE walk_slice RENAME TO walk_slice_rebuilt")
    con.execute("ALTER TABLE walk_slice_rebuilt RENAME TO walk_slice")
    assert con.execute("SELECT count(*) FROM document_text_display").fetchone()[0] == 0


def test_only_the_view_names_the_function(tmp_path):
    """No index, generated column or trigger may persist the rule's output: `deterministic`
    would then let a raw connection fail to INSERT a reading at all."""
    con = _store(tmp_path)
    rows = con.execute(
        "SELECT type, name FROM sqlite_master WHERE sql LIKE '%dy_display_text%'"
    ).fetchall()
    assert rows == [("view", "document_text_display")]


def test_web_refuses_an_index_built_under_an_older_view(tmp_path):
    """Between the migration and the rebuild the index holds the old view's bytes; the
    runbook rebuilds behind the wall, and this is what makes forgetting loud."""
    import pytest

    path, sha = _store_with_document(tmp_path)
    assert _loaded(path, tmp_path, _extraction(sha, (CONTACT,))) == "loaded"
    con = db.connect(path)
    search.rebuild_pages(con)  # a current build serves
    create_app(path)
    con.execute("UPDATE search_meta SET signature = 'display@0018.1.0.0' WHERE key = 'page_built'")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="rebuild-pages"):
        create_app(path)
