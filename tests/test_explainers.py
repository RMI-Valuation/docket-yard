"""The docket-type explainers: every figure measured, every prefix reachable, the unconfirmed
rows marked, and the sheet and stats pages pointing at them."""

from fastapi.testclient import TestClient

from docketyard.store import db, explainers
from docketyard.web import urls
from docketyard.web.app import create_app
from tests.test_web import build_store


def test_explainers_measure_the_record_and_publish_every_prefix(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    f = explainers.measure(con)
    con.close()
    fd = f.prefix("FD")
    assert fd.dockets == 2 and fd.subs == 1 and fd.seq_min == fd.seq_max == 36873
    assert fd.filings == 2 and fd.top_filing_types[0][0] == "Motion"
    assert f.prefix("ZZ").dockets == 0 and f.dockets_in(explainers.PAGES) == 2
    client = TestClient(create_app(path))
    index = client.get("/about/prefixes").text
    assert "2 of the registry’s 2 dockets" in index and "[?]" in index and "unconfirmed" in index
    assert 'id="ISM"' in index and 'id="empty"' in index and "Not the Board" in index
    for p in explainers.PAGES:
        page = client.get(f"/about/{p}")
        assert page.status_code == 200 and "not legal advice" in page.text, p
    fd_page = client.get("/about/FD").text
    assert "36,873 to 36,873" in fd_page and "1 of them sub-numbers" in fd_page  # live figures
    assert "(0 in the record)" in fd_page and "hold 1 decision," in fd_page
    # every spelling resolves; a prefix without its own page lands on its row
    r = client.get("/about/fd", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/about/FD"
    r = client.get("/about/ISM", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/about/prefixes#ISM"
    assert client.get("/about/ZZZ").status_code == 404
    assert (
        urls.explainer_path("ab") == "/about/AB"
        and urls.explainer_path("WB") == "/about/prefixes#WB"
    )
    # the sheet and the stats table point at the explainer
    assert 'href="/about/FD">What an FD proceeding is</a>' in client.get("/d/FD-36873").text
    assert 'href="/about/FD">FD</a>' in client.get("/stats").text
    assert "/about/FD<" in client.get("/sitemap-pages-1.xml").text


def test_every_explainer_leads_to_the_dockets_it_counts(tmp_path):
    """Each explainer quoted "the registry holds N X dockets" and stopped, with no way to
    see one of them (navigation-review.md § C). The link carries no count of its own: a
    number repeated in two places is how two pages come to disagree."""
    client = TestClient(create_app(build_store(tmp_path)))
    for prefix in explainers.PAGES:
        page = client.get(f"/about/{prefix}")
        assert page.status_code == 200, prefix
        assert f'href="/dockets/{prefix}">Every {prefix} proceeding on record</a>' in page.text
        # follow it: grepping the markup and never fetching the target is why the shared
        # layout could render `<a href="/dockets/">` and still pass (code review)
        target = client.get(f"/dockets/{prefix}")
        assert target.status_code in (200, 404), prefix
        if prefix == "FD":  # the one the fixture holds
            assert target.status_code == 200 and 'href="/d/FD-36873"' in target.text
    index = client.get("/about/prefixes")
    assert index.status_code == 200
    assert 'href="/dockets/FD">list</a>' in index.text
    # the shared layout is also this page's, and this page is about no single prefix
    assert 'href="/dockets/"' not in index.text
    assert "Every  proceeding" not in index.text
