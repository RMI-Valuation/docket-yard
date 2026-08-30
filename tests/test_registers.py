"""Registers are projections of a type the Board printed, and the citation resolver never
guesses."""

from fastapi.testclient import TestClient

from docketyard.capture.stb import DECISIONS
from docketyard.parties import resolve
from docketyard.store import db, registers
from docketyard.web import cite
from docketyard.web.app import create_app
from tests.test_observations import decision_row, filing_row, ingest
from tests.test_web import build_store


def _store(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    ingest(
        con,
        tmp_path,
        filing_row(
            fid="400001", date="8/26/2026", filed_for="NRDC", ftype="Motion For Protective Order"
        )
        + filing_row(
            docket="EP_711", fid="400002", date="8/26/2026", filed_for="NRDC", ftype="Reply"
        ),
    )
    ingest(
        con,
        tmp_path,
        decision_row(docket="EP_711", did="60001", date="8/26/2026", dtype="Notice Of Court Action")
        + decision_row(docket="EP_711", did="60002", date="8/20/2026", dtype="Decision")
        + decision_row(docket="EP_711", did="60003", date="8/20/2026", dtype="Decision"),
        action=DECISIONS,
    )
    resolve.run(con, log=lambda _: 0)
    return path, con


def test_registers_list_what_the_board_typed_and_nothing_else(tmp_path):
    path, con = _store(tmp_path)
    court = registers.court_actions(con).groups
    assert [g.raw_docket for g in court] == ["EP_711"]
    assert (
        court[0].entries[0].record_id == "60001"
        and court[0].entries[0].type == "Notice Of Court Action"
    )
    reg = registers.protective_orders(con)
    prot = reg.groups
    assert reg.names  # the party names the page prints, from the one components build
    assert prot[0].raw_docket == "FD_36873" and prot[0].entries[0].record_id == "400001"
    assert prot[0].entries[0].parties  # filed for NRDC, resolved
    client = TestClient(create_app(path))
    page = client.get("/court").text
    assert "1 notice in 1 docket" in page and 'href="/decision/60001"' in page and "EP 711" in page
    assert "listed under each" not in page
    page = client.get("/protective").text
    assert (
        "1 motion in 1 docket" in page and 'href="/filing/400001"' in page and 'href="/p/' in page
    )
    assert "in the protective-order register" in client.get("/d/FD-36873").text
    assert "/court<" in client.get("/sitemap-pages-1.xml").text


def test_the_resolver_reads_every_printed_form_and_never_guesses(tmp_path):
    path, con = _store(tmp_path)
    r = lambda q: cite.resolve(con, q)  # noqa: E731
    assert r("STB Finance Docket No. 36873").path == "/d/FD-36873"
    assert r("Docket No. FD 36873 (Sub-No. 1)").path == "/d/FD-36873/sub/1"
    assert r("Ex Parte No. 711").path == "/d/EP-711" and r("STB Ex Parte 711").kind == "docket"
    assert r("Surface Transportation Board Docket No. EP 711").path == "/d/EP-711"
    assert r("Decision 60001").path == "/decision/60001" and r("filing 400001").kind == "filing"
    assert r("Decision 99999") is None and r("FD 99999") is None and r("lorem ipsum") is None
    assert r("Decision No. 12") is None and r("decision 2019") is None  # never a guess
    # a decision is the docket plus its service date, in any printed form
    for q in (
        "EP 711 (STB served Aug. 26, 2026)",
        "Ex Parte No. 711, served August 26, 2026",
        "EP 711 service date: 2026-08-26",
    ):
        assert r(q).path == "/decision/60001", q
    # A decision is decided some days before it is served and the record holds the service
    # date alone (they differ in 34 of the sixty benchmark decisions), so a decided date is
    # never matched against it: a "match" would likelier be a sibling served that day than
    # the decision named, and a citation resolving to the wrong document is worse than one
    # resolving to nothing (ADR 0017 decision 3, taken for the resolver 2026-08-30). Both
    # the date that would have matched and one that would not answer the same way.
    for q in ("EP 711 decided 8/26/2026", "EP 711 decided 3/25/2026"):
        miss = r(q)
        assert miss.kind == "sheet" and miss.path == "/d/EP-711", q
        assert "not the date it was decided" in miss.note, q
        assert "no decision served" not in miss.note, q
    # two decisions on one day: the sheet, and why
    # one decision entered under a docket and its sub-docket is one decision, not two
    ingest(
        con,
        tmp_path,
        decision_row(
            docket="EP_711_1", did="60001", date="8/26/2026", dtype="Notice Of Court Action"
        ),
        action=DECISIONS,
    )
    assert r("EP 711 (STB served Aug. 26, 2026)").path == "/decision/60001"
    assert registers.court_actions(con).groups and (
        len({e.record_id for g in registers.court_actions(con).groups for e in g.entries}) == 1
    )
    two = r("EP 711 (STB served Aug. 20, 2026)")
    assert two.kind == "sheet" and two.path == "/d/EP-711" and "2 decisions" in two.note
    none = r("EP 711 (served Aug. 21, 2026)")
    assert none.kind == "sheet" and "no decision served 2026-08-21" in none.note
    assert r("EP 711 (served Augtember 1, 2026)").note.startswith("the date")
    assert (
        cite.parse_date("Aug. 25, 2026") == "2026-08-25" and cite.parse_date("Feb 30, 2026") is None
    )
    # the link service and the search box
    client = TestClient(create_app(path))
    assert (
        client.get(
            "/d",
            params={"q": "Ex Parte No. 711 (STB served Aug. 26, 2026)"},
            follow_redirects=False,
        ).headers["location"]
        == "/decision/60001"
    )
    assert (
        client.get("/d", params={"q": "FD 99999"}, follow_redirects=False).headers["location"]
        == "/d/FD-99999"
    )
    assert (
        client.get("/d", params={"q": "lorem"}, follow_redirects=False)
        .headers["location"]
        .startswith("/search?q=lorem")
    )
    assert (
        client.get("/search", params={"q": "Decision 60001"}, follow_redirects=False).headers[
            "location"
        ]
        == "/decision/60001"
    )
    j = client.get("/cite", params={"q": "STB Finance Docket No. 36873"}).json()
    assert (
        j["resolved"]["url"] == "https://docketyard.org/d/FD-36873"
        and j["resolved"]["kind"] == "docket"
    )
    assert client.get("/cite", params={"q": "nothing"}).json()["resolved"] is None
