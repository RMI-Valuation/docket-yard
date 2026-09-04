"""The page search path (ADR 0021 D7, ADR 0022 D4): pages of documents reach `/search` and
the MCP search by their own query path, each hit carrying who read the page, the band's
operand or why there is none, and the scan; never `/suggest`; never joined to `search()`.
"""

import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

from docketyard.store import batches, db, page_index, pages, search
from docketyard.text import load
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


def test_a_stale_index_row_is_dropped_and_does_not_take_the_search_down(tmp_path):
    """A human row inserted by hand without `leave(primary)` leaves the primary's id in
    `page_fts` while the view shows the human row. FTS5's snippet over the vanished content
    row raises "database disk image is malformed"; the search must count it, not raise."""
    path, sha = _with_text(tmp_path)
    con = db.connect(path)
    con.execute(
        "INSERT INTO document_text (document_sha256, page_no, method, method_version,"
        " render_profile, reading_channel, reading_role, text, text_sha256, confidence,"
        " confidence_state, asserted_at) VALUES (?, 3, 'human', 'unversioned', 'human',"
        " 'human', 'human', 'a correction with other words', 'h', 0, 'human',"
        " '2026-09-04T12:00:00+00:00')",
        (sha,),
    )
    con.commit()  # no leave(), no rebuild: the primary's row is stale in the index
    found = search.search_pages(con, "tazewell")
    assert found.hits == [] and found.dropped == 1
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
    assert "does not hold the text" not in mcp._NOT_HELD  # the caveat no longer denies it


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


def test_the_batched_rebuild_indexes_exactly_what_fts5s_own_rebuild_would(tmp_path):
    """THE DRIFT GUARD for taking FTS5's `'rebuild'` apart. It reads the content view inside
    ONE transaction, and with migration 0020's masking function running per row that held
    the write lock for 8 m 49 s at 1,104,935 rows, then 27 m 26 s at the v2026.09.3 deploy —
    the poller lost a pass to it (`deferred.md`, 2026-09-04). `rebuild_pages` now pages the
    view outside any transaction and writes each batch in its own, which is only safe while
    the index it leaves is the one FTS5 would have built. This asserts that, batch by batch:
    a batch size of 1 makes every row its own transaction."""
    path, sha = _with_text(tmp_path)
    con = db.connect(path)

    def indexed():
        """Every (rowid, term) pair the index holds, as a search can see them."""
        terms = ("abandonment", "perry", "tazewell", "county", "docket", "example")
        return {
            t: sorted(
                r[0] for r in con.execute("SELECT rowid FROM page_fts WHERE page_fts MATCH ?", (t,))
            )
            for t in terms
        }

    out = search.rebuild_pages(con, force=True, batch=1)
    assert out["pages"] == 3, "the blank page is a row of the view and is indexed as one"
    batched = indexed()
    assert batched["tazewell"], "the fixture matched nothing — this test would prove nothing"
    # the masking is applied by the view, so an address in the page text is in neither index
    assert batched["example"] == [], "the display rule did not reach the batched rebuild"

    con.execute("INSERT INTO page_fts (page_fts) VALUES ('rebuild')")  # FTS5's own, whole
    con.commit()
    assert indexed() == batched

    # one batch and many batches agree, and the count is the view's, not a COUNT(*) over the
    # index — which on an external-content table reads the view a second time
    assert search.rebuild_pages(con, force=True, batch=10_000)["pages"] == 3
    assert indexed() == batched
    con.close()


def test_an_interrupted_rebuild_is_refused_rather_than_served_short(tmp_path):
    """The build stopped being atomic when it stopped being one transaction, so a rebuild
    that dies halfway leaves a fraction of the record indexed. `page_built` says `rebuilding`
    from before the first row until after the last, and `web` refuses anything that does not
    begin with `PAGE_INDEX_FORMAT` — so the half-built index is never served."""
    path, sha = _with_text(tmp_path)
    con = db.connect(path)
    search.rebuild_pages(con, force=True)
    good = search.page_built(con)
    assert good[0] and good[0].startswith(search.PAGE_INDEX_FORMAT + ".")
    assert create_app(path) is not None  # a finished build serves

    search._mark_page_build(con, search.PAGE_REBUILDING, good[1])
    con.close()
    with pytest.raises(RuntimeError, match="an interrupted rebuild"):
        create_app(path)

    # and re-running needs no --force: `rebuilding` matches no signature
    con = db.connect(path)
    assert search.rebuild_pages(con)["build"] == good[1] + 1
    assert search.page_built(con)[0] == search.page_signature(con)
    con.close()
    assert create_app(path) is not None


def test_the_rebuild_waits_out_the_write_lock_instead_of_leaving_the_index_empty(tmp_path):
    """The batched rebuild takes the write lock hundreds of times where FTS5's `'rebuild'`
    took it once, and it empties the index BEFORE the first row goes in. A transient
    SQLITE_BUSY that the old shape never met would therefore leave the index empty and
    `page_built` at `rebuilding`, so `web` would refuse to start until a whole rebuild
    landed. It waits the lock out by the passes' own rule (code review, 2026-09-04)."""
    path, sha = _with_text(tmp_path)
    con = db.connect(path)
    con.execute("PRAGMA busy_timeout = 50")
    holder = sqlite3.connect(path, timeout=0)
    holder.execute("BEGIN IMMEDIATE")  # the lock, as Litestream's checkpoint holds it
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        holder.rollback()  # it lets go while the rebuild waits

    monkey = batches.under_lock
    try:
        batches.under_lock = lambda con_, do, **kw: monkey(con_, do, **{**kw, "sleep": sleep})
        out = search.rebuild_pages(con, force=True, batch=1)
    finally:
        batches.under_lock = monkey
    assert out["pages"] == 3 and waits, "the lock was never contended — this proves nothing"
    assert search.page_built(con)[0] == search.page_signature(con)
    assert [r[0] for r in con.execute("SELECT rowid FROM page_fts WHERE page_fts MATCH 'tazewell'")]
    con.close()


def test_the_loader_refuses_to_write_the_index_a_rebuild_owns(tmp_path):
    """Both would write `page_fts` at once and the rebuild's scan would index a row the
    loader had just indexed — external-content FTS5 takes the duplicate rowid in silence,
    and a later `leave` clears one copy and leaves the other's tokens behind."""
    path, sha = _with_text(tmp_path)
    con = db.connect(path)
    assert page_index.REBUILDING == search.PAGE_REBUILDING, "two spellings of one mark"
    search._mark_page_build(con, search.PAGE_REBUILDING, 1)
    assert page_index.owned_by_rebuild(con)
    con.close()
    con = db.connect(path)
    (tmp_path / "readings").mkdir(exist_ok=True)
    with pytest.raises(page_index.Rebuilding, match="rebuild-pages"):
        load.run(con, tmp_path / "readings", tmp_path, log=lambda _: None)
    con.close()
    # and it loads again once the rebuild has finished
    con = db.connect(path)
    search.rebuild_pages(con)
    assert not page_index.owned_by_rebuild(con)
    con.close()
    assert _loaded(path, tmp_path, _ocr(sha, PAGES)) == "loaded"


def test_a_search_during_a_rebuild_says_so_rather_than_answering_short(tmp_path):
    """`web` refuses to START against a half-built index, but a process already running
    would answer a page search out of a fraction of the record with a 200 and no sign —
    a coverage claim the store cannot support. Both surfaces say it instead."""
    path, sha = _with_text(tmp_path)
    client = TestClient(create_app(path))
    assert "Tazewell" in client.get("/search?q=tazewell").text  # it answers normally first

    con = db.connect(path)
    search._mark_page_build(con, search.PAGE_REBUILDING, 1)
    found = search.search_pages(con, "tazewell")
    assert found.rebuilding and found.hits == []
    con.close()

    html = client.get("/search?q=tazewell").text
    assert "The text index is being rebuilt" in html
    assert "page 3" not in html, "a hit was printed out of a half-built index"
    # the record's own search is untouched: only the page path is held back
    assert "FD 36873" in html
    # and an assistant is told, so it does not report an absence that is not one
    answer = mcp._search(db.connect(path), {"query": "tazewell"}, "docketyard.org")
    assert "were NOT searched" in answer


def _long_document(tmp_path, path, mark, n, word="quarterly"):
    """A document every one of whose pages carries the same phrase — the shape that used to
    take the whole section: a 300-page environmental assessment, a tariff, a form."""
    long_sha = mark * 64
    con = db.connect(path)
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'pdf', '2026-08-24T00:00:00+00:00')",
        (long_sha,),
    )
    filing_pk = con.execute("SELECT filing_pk FROM filing ORDER BY filing_pk LIMIT 1").fetchone()[0]
    con.execute(
        "INSERT INTO filing_attachment (filing_pk, label, source_url, document_sha256)"
        f" VALUES (?, 'the long one', 'https://example.org/{mark}.pdf', ?)",
        (filing_pk, long_sha),
    )
    con.commit()
    con.close()
    doc = _extraction(long_sha, tuple(f"{word} report, sheet {i}" for i in range(n)))
    doc["text_sha256"] = mark * 64  # its own run, not a re-load of another document's
    assert _loaded(path, tmp_path, doc) == "loaded"
    _paginated(path, long_sha, n)
    return long_sha


def test_one_document_cannot_take_the_whole_page_section(tmp_path):
    """A phrase printed on every page of one long document ranked twenty of ITS pages and
    buried every other document that matched — and the reader saw a full section with no
    sign anything was missing. The record path cannot fail this way (one row per docket);
    this one's grain is one row per page (`deferred.md`, 2026-09-04)."""
    path, sha = _with_text(tmp_path)
    _long_document(tmp_path, path, "d", n=40)
    _long_document(tmp_path, path, "e", n=12)  # a second, ranked below it
    con = db.connect(path)
    search.rebuild_pages(con, force=True)

    found = search.search_pages(con, "quarterly")
    per_document = Counter(h.path.split("#")[0] for h in found.hits)
    assert max(per_document.values()) <= search.PAGE_PER_DOCUMENT, per_document
    assert found.folded, "nothing was folded — the fixture did not reproduce the shape"
    assert found.truncated, "the record holds more pages than are shown, and must say so"
    # the second document is REACHABLE, which is the whole point: before the fold, the long
    # one's pages 1-20 filled the section and this was invisible
    assert len(per_document) > 1, "the long document still took the section"
    con.close()

    html = TestClient(create_app(path)).get("/search?q=quarterly").text
    assert f"at most {search.PAGE_PER_DOCUMENT} from any one document" in html
    assert "the record holds more" in html
    # the clauses in an order that reads: what was counted, then where it came from, then
    # what is missing. The first spelling put "the record holds more" between "20 pages" and
    # "as read by machine", which left the sentence attaching to the wrong thing
    sentence = html.split("In the text of documents")[1].split("</p>")[0]
    assert sentence.index("from any one document") < sentence.index("as read by machine")
    assert sentence.index("as read by machine") < sentence.index("the record holds more")
    answer = mcp._search(db.connect(path), {"query": "quarterly"}, "docketyard.org")
    assert f"At most {search.PAGE_PER_DOCUMENT} pages of any one document" in answer


def test_a_stale_index_row_is_counted_where_the_operator_can_see_it(tmp_path, monkeypatch):
    """`PageResults.dropped` was computed and read by nobody, and it is the ONE signal that
    `page_fts` has drifted from the display view — a human row inserted without `leave`, a
    store restored from a replica (`deferred.md`, 2026-09-04). There is no cheap store query
    for it (the masking function over 1.1M rows), so it is what searches have MET."""
    path, sha = _with_text(tmp_path)
    con = db.connect(path)
    before = search.stale_page_rows()
    assert search.search_pages(con, "tazewell").dropped == 0
    assert search.stale_page_rows() == before  # a clean index moves nothing

    # the drift `page_index`'s docstring names: a human row lands on the page and the
    # primary leaves the view, with no `leave` to take it out of the index
    text_id = con.execute("SELECT rowid FROM page_fts WHERE page_fts MATCH 'tazewell'").fetchone()[
        0
    ]
    row = con.execute(
        "SELECT document_sha256, page_no FROM document_text WHERE text_id = ?", (text_id,)
    ).fetchone()
    con.execute(
        "INSERT INTO document_text (document_sha256, page_no, reading_channel, reading_role,"
        " method, method_version, render_profile, text, text_sha256, confidence,"
        " confidence_state, asserted_at) VALUES (?,?,'human','human','human','unversioned',"
        " 'human', 'read by a person', ?, 1.0, 'human', '2026-09-04T00:00:00+00:00')",
        (row[0], row[1], "e" * 64),
    )
    con.commit()
    found = search.search_pages(con, "tazewell")
    assert found.dropped == 1 and found.hits == []
    assert search.stale_page_rows() == before + 1
    con.close()

    monkeypatch.setenv("DY_METRICS_TOKEN", "t")
    client = TestClient(create_app(path))
    client.get("/search?q=tazewell")  # a reader meets the stale row
    body = client.get("/metrics", headers={"Authorization": "Bearer t"}).text
    assert "docket_yard_page_index_stale_rows_total" in body
    shown = int(
        next(
            line for line in body.splitlines() if line.startswith("docket_yard_page_index_stale")
        ).split()[1]
    )
    assert shown >= 1


def test_a_document_with_no_text_address_is_dropped_without_moving_the_drift_counter(tmp_path):
    """`dropped` and the metric are not the same number. A comment's attachment has text and
    no address to show it at, so its pages are dropped from every search of a HEALTHY store;
    counting those as drift would move the one signal in proportion to traffic and bury it
    (review, 2026-09-04)."""
    path, sha = _with_text(tmp_path)
    con = db.connect(path)
    orphan = "f" * 64  # held, read, and carried by no filing or decision
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'pdf', '2026-08-24T00:00:00+00:00')",
        (orphan,),
    )
    con.commit()
    con.close()
    doc = _extraction(orphan, ("marmoset husbandry in Perry County",))
    doc["text_sha256"] = orphan
    assert _loaded(path, tmp_path, doc) == "loaded"
    con = db.connect(path)
    search.rebuild_pages(con, force=True)

    before = search.stale_page_rows()
    found = search.search_pages(con, "marmoset")
    assert found.hits == [] and found.dropped == 1, "it is in the index and has no address"
    assert search.stale_page_rows() == before, "an expected drop moved the drift counter"
    con.close()


def test_the_machine_answer_never_offers_more_pages_than_the_none_it_showed(tmp_path):
    """`truncated` is set from the index, before a single row is looked up, so every matched
    row dropping leaves it true with nothing shown — and the assistant was told "…and more
    pages than the 0 shown" after a list of nothing (review, 2026-09-04)."""
    path, sha = _with_text(tmp_path)
    con = db.connect(path)
    orphan = "b" * 64  # held and read, carried by no filing or decision: no text address
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'pdf', '2026-08-24T00:00:00+00:00')",
        (orphan,),
    )
    con.commit()
    con.close()
    # more than the deepest window a caller can open (PAGE_LIMIT * PAGE_OVERFETCH), so the
    # index truthfully says "more matched" while every one of them drops
    doc = _extraction(orphan, tuple(f"pangolin sighting {i}" for i in range(220)))
    doc["text_sha256"] = orphan
    assert _loaded(path, tmp_path, doc) == "loaded"
    con = db.connect(path)
    search.rebuild_pages(con, force=True)
    found = search.search_pages(con, "pangolin")
    assert found.hits == [] and found.truncated, "the fixture did not reproduce the shape"
    con.close()

    answer = mcp._search(db.connect(path), {"query": "pangolin"}, "docketyard.org")
    assert "0 shown" not in answer
    assert "more pages than" not in answer
