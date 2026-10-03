"""`/search` built out (docs/search-v2.md): the filters are parameters in the address, every
value is checked against what the store holds, a filtered search is never a redirect, and the
links on a results page keep the search they came from."""

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from docketyard.store import db, search
from docketyard.web.app import create_app
from tests.test_web import build_store


def _client(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    search.rebuild(con)
    con.close()
    return TestClient(create_app(path))


def test_filters_are_the_address_and_the_form_shows_them_back(tmp_path):
    client = _client(tmp_path)
    r = client.get(
        "/search",
        params=[("q", "motion"), ("prefix", "FD"), ("from", "2026-08-25"), ("ftype", "Motion"),
                ("sort", "newest")],
    )  # fmt: skip
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert "2 proceedings." in r.text and "Newest first" in r.text
    assert '<option value="FD" selected>' in r.text and "<option selected>Motion</option>" in r.text
    assert 'value="2026-08-25"' in r.text and 'value="newest" checked' in r.text
    assert '<details class="filters" open>' in r.text  # a filtered search opens the panel
    assert "Ignored" not in r.text


def test_a_value_the_store_does_not_hold_is_dropped_and_said(tmp_path):
    client = _client(tmp_path)
    r = client.get(
        "/search",
        params=[("q", "motion"), ("prefix", "ZZ"), ("from", "25/08/2026"), ("ftype", "<b>x</b>"),
                ("in", "everything"), ("docket", "FD 99999")],
    )  # fmt: skip
    assert r.status_code == 200
    assert "Ignored, because the record holds no such value:" in r.text
    for label in ("docket type", "date from", "filing type", "what to search", "proceeding"):
        assert label in r.text
    assert "<b>x</b>" not in r.text  # never echoed as markup
    assert "2 proceedings." in r.text  # the search itself still ran, unfiltered


def test_a_filter_turns_a_docket_number_into_a_search_not_a_redirect(tmp_path):
    client = _client(tmp_path)
    plain = client.get("/search", params={"q": "FD 36873"}, follow_redirects=False)
    assert plain.status_code == 303
    filtered = client.get(
        "/search", params={"q": "FD 36873", "from": "2026-01-01"}, follow_redirects=False
    )
    assert filtered.status_code == 200


def test_more_in_this_proceeding_and_paging_keep_the_search(tmp_path, monkeypatch):
    from docketyard.store import finder

    client = _client(tmp_path)
    monkeypatch.setattr(finder, "EVIDENCE", 1)
    html = client.get("/search", params=[("q", "motion"), ("ftype", "Motion")]).text
    assert "1 more match in this proceeding" in html
    href = html.split("1 more match in this proceeding")[0].rsplit('href="', 1)[1].split('"')[0]
    params = parse_qs(urlparse(href.replace("&amp;", "&")).query)
    assert params["q"] == ["motion"] and params["ftype"] == ["Motion"]
    assert params["docket"] == ["FD 36873 (Sub-No. 1)"]
    within = client.get(href.replace("&amp;", "&")).text
    assert "Within FD 36873 (Sub-No. 1)" in within and "1 proceeding." in within
    assert "more match" not in within  # within one proceeding, every match is shown
    monkeypatch.setattr(finder, "PAGE_SIZE", 1)
    first = client.get("/search", params={"q": "motion", "sort": "newest"}).text
    assert "Page 1 of 2" in first and 'rel="next"' in first
    nxt = first.split('rel="next"')[0].rsplit('href="', 1)[1].split('"')[0].replace("&amp;", "&")
    assert parse_qs(urlparse(nxt).query) == {"q": ["motion"], "sort": ["newest"], "page": ["2"]}


def test_the_bare_page_is_a_page_and_offers_the_store_vocabulary(tmp_path):
    client = _client(tmp_path)
    r = client.get("/search")
    assert r.headers["cache-control"].startswith("public") and "noindex" not in r.text
    assert "Filters and order" in r.text and '<details class="filters">' in r.text
    assert '<option value="FD">FD — ' in r.text and "<option>Decision</option>" in r.text
    assert 'class="results"' not in r.text
    # and every page's masthead links to it
    assert '<a href="/search">Search</a>' in client.get("/coverage").text


def test_the_flat_list_shows_each_match_once_and_keeps_the_search(tmp_path):
    client = _client(tmp_path)
    r = client.get("/search", params={"q": "motion", "view": "documents"})
    # 311981 is placed in two proceedings and listed once; 311900 once
    assert "2 matches." in r.text and "<strong>List every match</strong>" in r.text
    assert r.text.count('href="/filing/311981"') == 1 and 'href="/filing/311900"' in r.text
    back = r.text.split(">Group by proceeding</a>")[0].rsplit('href="', 1)[1].split('"')[0]
    assert parse_qs(urlparse(back.replace("&amp;", "&")).query) == {"q": ["motion"]}


def test_the_page_answers_what_it_cannot_list_rather_than_nothing(tmp_path, monkeypatch):
    client = _client(tmp_path)
    # a page number that is not a number is the first page, not a 422
    assert client.get("/search", params={"q": "motion", "page": "x"}).status_code == 200
    assert client.get("/search", params={"q": "motion", "page": "²"}).status_code == 200
    past = client.get("/search", params={"q": "motion", "page": "5"}).text
    assert "is past the last page" in past and "Nothing on record matches" not in past
    only_captions = client.get("/search", params={"q": "control", "view": "documents"}).text
    assert "Only captions or docket numbers matched" in only_captions
    assert "Nothing on record matches" not in only_captions
    many = [("q", "motion")] + [("ftype", f"type {i}") for i in range(25)]
    assert (
        "Only the first 20 values of a filter are used" in client.get("/search", params=many).text
    )


def test_an_index_not_yet_built_says_so(tmp_path):
    path = build_store(tmp_path)  # migrated, never rebuilt: the state migration 0033 leaves
    html = TestClient(create_app(path)).get("/search", params={"q": "motion"}).text
    assert "The search index is being rebuilt" in html
    assert "Nothing on record matches" not in html
