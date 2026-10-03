"""Search built out (docs/search-v2.md), the query half: results grouped by proceeding,
filtered by placement, pages reaching proceedings through their documents' records, the page
side bounded and saying so, sorted and paged."""

import pytest

from docketyard.store import db, finder, search
from docketyard.store.finder import Query
from tests.test_documents import (  # noqa: F401 — the fixture registers itself here too
    no_store_in_the_environment,
)
from tests.test_page_search import _with_text
from tests.test_web import build_store


def _numbers(results):
    return [p.number for p in results.proceedings]


@pytest.fixture
def indexed(tmp_path):
    con = db.connect(build_store(tmp_path))
    search.rebuild(con)
    yield con
    con.close()


@pytest.fixture
def texted(tmp_path):
    path, _ = _with_text(tmp_path)
    con = db.connect(path)
    search.rebuild(con, force=True)  # the document's owners, now that it is attached
    yield con
    con.close()


def test_results_are_proceedings_and_a_record_shows_under_each_it_was_entered_in(indexed):
    # 311981 was entered in FD 36873 and its captioned Sub-No. 1: it shows under both
    r = finder.find(indexed, Query("NRDC", kinds=("filings",)))
    assert sorted(_numbers(r)) == ["FD 36873", "FD 36873 (Sub-No. 1)"] and r.total == 2
    for p in r.proceedings:
        assert [h.path for h in p.hits] == ["/filing/311981"] and p.matched == 1
    # a caption match is the proceeding itself, with no evidence line repeating it
    r = finder.find(indexed, Query("control"))
    assert _numbers(r) == ["FD 36873"] and r.proceedings[0].hits == []
    assert r.proceedings[0].path == "/d/FD-36873" and r.proceedings[0].caption == "UP/NS CONTROL"
    assert r.exact


def test_each_filter_reads_the_placement(indexed):
    assert finder.find(indexed, Query("motion", prefixes=("NOR",))).total == 0
    # dates filter dated items only: the caption-only match is left out (decision 6)
    assert finder.find(indexed, Query("control", date_from="2026-01-01")).total == 0
    r = finder.find(indexed, Query("motion", date_from="2026-08-25", date_to="2026-08-25"))
    assert {h.path for p in r.proceedings for h in p.hits} == {"/filing/311981"}
    # the type is keyed by kind: a decision type does not admit a filing
    assert finder.find(indexed, Query("motion", dtypes=("Motion",))).total == 0
    assert finder.find(indexed, Query("motion", ftypes=("Motion",))).total == 2
    # and "N more in this proceeding" is the same search within one
    (sub,) = indexed.execute(
        "SELECT docket_id FROM docket WHERE raw_docket = 'FD_36873_1'"
    ).fetchone()
    r = finder.find(indexed, Query("motion", within=sub))
    assert _numbers(r) == ["FD 36873 (Sub-No. 1)"] and r.proceedings[0].matched == 2


def test_a_browse_is_filters_without_words_and_nothing_at_all_is_not_a_search(indexed):
    r = finder.find(indexed, Query("", ftypes=("Motion",), sort="newest"))
    assert r.total == 2 and all(h.kind == "filing" for p in r.proceedings for h in p.hits)
    assert finder.find(indexed, Query("")).total == 0
    assert finder.find(indexed, Query("***")).total == 0


def test_a_page_reaches_every_proceeding_holding_its_document_with_its_obligations(texted):
    r = finder.find(texted, Query("tazewell"))
    # the file is attached to 311900 (Sub-No. 1) and 311981 (FD 36873 and Sub-No. 1)
    assert sorted(_numbers(r)) == ["FD 36873", "FD 36873 (Sub-No. 1)"]
    for p in r.proceedings:
        assert p.pages == 1  # one page, counted once however many records carry it here
        (hit,) = p.hits
        assert hit.kind == "page" and hit.path.endswith("/text#p3")
        assert search.MARK_OPEN in hit.snippet
        assert hit.label.startswith("The publisher's own text layer")
        assert hit.band and hit.scan.endswith("#file")
    # under FD 36873 the page links the record entered THERE, never the sub-docket's filing
    family = next(p for p in r.proceedings if p.number == "FD 36873")
    assert family.hits[0].record == "/filing/311981"
    # a filter reaches pages through the same placements
    r = finder.find(texted, Query("tazewell", date_to="2026-08-24"))
    assert _numbers(r) == ["FD 36873 (Sub-No. 1)"]
    assert r.proceedings[0].hits[0].record == "/filing/311900"


def test_the_page_side_says_when_it_was_bounded(texted, monkeypatch):
    monkeypatch.setattr(finder, "PAGE_WINDOW", 0)
    r = finder.find(texted, Query("tazewell"))
    assert r.pages_cut == "window" and not r.exact
    monkeypatch.setattr(finder, "PAGE_WINDOW", 5000)
    monkeypatch.setattr(finder, "PAGE_BUDGET", -1.0)  # already over
    monkeypatch.setattr(finder, "PROGRESS_STEPS", 1)
    r = finder.find(texted, Query("tazewell", prefixes=("FD",)))
    assert r.pages_cut == "budget" and all(p.pages == 0 for p in r.proceedings)
    # the connection is left without a handler, so the next query is not interrupted
    assert texted.execute("SELECT COUNT(*) FROM search_place").fetchone()[0] > 0


def test_filtering_by_intersection_answers_what_filtering_the_matches_does(texted, monkeypatch):
    q = Query("tazewell", prefixes=("FD",))
    direct = finder.find(texted, q)
    monkeypatch.setattr(finder, "DIRECT_MATCHES", 0)
    crossed = finder.find(texted, q)
    assert _numbers(direct) == _numbers(crossed) and direct.pages_matched == 1
    assert [h.path for p in direct.proceedings for h in p.hits] == [
        h.path for p in crossed.proceedings for h in p.hits
    ]


def test_a_rebuilding_page_index_is_said_not_answered_short(texted):
    texted.execute(
        "UPDATE search_meta SET signature = ? WHERE key = 'page_built'", (search.PAGE_REBUILDING,)
    )
    texted.commit()
    r = finder.find(texted, Query("tazewell"))
    assert r.pages_cut == "rebuilding" and r.total == 0


def test_newest_first_and_paging(indexed, monkeypatch):
    r = finder.find(indexed, Query("motion", sort="newest"))
    # 311981 (Aug 25) is in both; the sub-docket also holds 311900 (Aug 24): both lead with Aug 25
    assert r.total == 2
    assert all(p.hits[0].path == "/filing/311981" for p in r.proceedings)
    monkeypatch.setattr(finder, "PAGE_SIZE", 1)
    first = finder.find(indexed, Query("motion"))
    second = finder.find(indexed, Query("motion", page=2))
    assert first.page_count == 2 and len(first.proceedings) == len(second.proceedings) == 1
    assert _numbers(first) != _numbers(second)


def test_parties_are_a_strip_and_a_filter_drops_it(tmp_path):
    from docketyard.parties import resolve

    con = db.connect(build_store(tmp_path))
    resolve.run(con, log=lambda _: 0)
    search.rebuild(con)
    assert [h.kind for h in finder.find(con, Query("nrdc")).parties] == ["party"]
    assert finder.find(con, Query("nrdc", prefixes=("FD",))).parties == []
    con.close()


def test_within_one_proceeding_every_page_is_seen(texted, monkeypatch):
    (fd,) = texted.execute("SELECT docket_id FROM docket WHERE raw_docket = 'FD_36873'").fetchone()
    monkeypatch.setattr(finder, "PAGE_WINDOW", 0)  # the record-wide window would drop it
    r = finder.find(texted, Query("tazewell", within=fd))
    assert r.pages_cut == "" and r.proceedings[0].pages == 1


def test_a_page_links_the_file_on_the_copy_that_carries_it(texted):
    # the headline copy of 311981 loses the attachment; the sub-docket's copy keeps it
    texted.execute(
        "DELETE FROM filing_attachment WHERE filing_pk = (SELECT MIN(filing_pk) FROM filing"
        " WHERE stb_filing_id = '311981')"
    )
    texted.commit()
    search.rebuild(texted, force=True)
    hits = [h for p in finder.find(texted, Query("tazewell")).proceedings for h in p.hits]
    assert hits and all(h.path.endswith("/text#p3") for h in hits)
