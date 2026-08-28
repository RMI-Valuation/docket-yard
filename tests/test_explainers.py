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
