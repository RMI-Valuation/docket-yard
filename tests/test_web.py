"""The web tier over a small real-shaped store: addresses, redirects, content as printed."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from docketyard.capture import records
from docketyard.capture.stb import DECISIONS, DOCKETS, FILINGS
from docketyard.ingest import dockets, observations
from docketyard.ingest.dockets import ParsedDocket
from docketyard.store import db, home
from docketyard.web import urls
from docketyard.web.app import create_app
from tests.test_dockets_parse import make_body
from tests.test_observations import body_of, decision_row, filing_row


def build_store(tmp_path):
    db_path = tmp_path / "store.sqlite"
    con = db.connect(db_path)

    def save(body, action):
        cid = records.save_capture(
            con,
            tmp_path,
            source_system="stb-ajax",
            endpoint="test",
            table_action=action,
            request_params=[],
            body=body,
            http_status=200,
            ingest_mode="forward",
        )
        records.set_verdict(con, cid, filter_asserted=True, row_count=0, reported_total=0)
        return cid

    dockets.ingest_capture(
        con,
        tmp_path,
        save(
            make_body([("FD_36873", "UP/NS CONTROL"), ("FD_36873_1", "PEORIA SUB")], total=2),
            DOCKETS,
        ),
    )
    observations.ingest_capture(
        con,
        tmp_path,
        save(
            body_of(
                filing_row(fid="311981", date="8/25/2026", filed_for="NRDC", ftype="Motion")
                + filing_row(docket="FD_36873_1", fid="311900", date="8/24/2026", filed_for="PPU")
                # the same filing entered in both the docket and its sub-docket (measured)
                + filing_row(docket="FD_36873_1", fid="311981", date="8/25/2026", filed_for="NRDC"),
                3,
            ),
            FILINGS,
        ),
    )
    # a decision entered in both dockets of the family
    observations.ingest_capture(
        con,
        tmp_path,
        save(
            body_of(
                decision_row(did="53210", summary="ORDERED REPLIES DUE")
                + decision_row(docket="FD_36873_1", did="53210", summary="ORDERED REPLIES DUE"),
                2,
            ),
            DECISIONS,
        ),
    )
    con.close()
    return db_path


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(build_store(tmp_path)))


# --- addresses (ADR 0013) ------------------------------------------------------------


def test_docket_paths_round_trip():
    cases = {
        "/d/FD-36873": ParsedDocket("FD", 36873, None, None),
        "/d/FD-36873/sub/1": ParsedDocket("FD", 36873, 1, None),
        "/d/S5M-1-A": ParsedDocket("S5M", 1, None, "A"),
        "/d/AB-55/sub/785X": ParsedDocket("AB", 55, 785, "X"),
    }
    for path, identity in cases.items():
        assert urls.docket_path(identity) == path
        parts = path.removeprefix("/d/").split("/sub/")
        assert urls.parse_docket_path(parts[0], parts[1] if len(parts) > 1 else None) == identity


def test_bad_paths_do_not_parse():
    assert urls.parse_docket_path("FD_36873") is None  # the source's spelling is not an address
    assert urls.parse_docket_path("FD-36873-1") is None  # a digit third part is not a suffix
    assert urls.parse_docket_path("FD-36873-A", "1") is None  # a suffix belongs to one level
    assert urls.parse_docket_path("FD-36873", "0") is None  # sub 0 is the parent


def test_lookup_accepts_every_spelling_a_person_might_paste():
    sub = ParsedDocket("FD", 36873, 1, None)
    parent = ParsedDocket("FD", 36873, None, None)
    for text in ("FD_36873_1", "FD 36873 (Sub-No. 1)", "fd 36873 sub-no 1", "FD-36873-1"):
        assert urls.lookup(text) == sub, text
    for text in ("FD_36873", "FD_36873_0", "fd 36873", " FD  36873 "):
        assert urls.lookup(text) == parent, text
    assert urls.lookup("AB 55 (Sub-No. 785X)") == ParsedDocket("AB", 55, 785, "X")
    assert urls.lookup("S5M-1-A") == ParsedDocket("S5M", 1, None, "A")
    assert urls.lookup("hello") is None


def test_printed_and_cited_forms():
    assert urls.printed_docket(ParsedDocket("FD", 36873, None, None)) == "FD 36873"
    assert urls.printed_docket(ParsedDocket("AB", 55, 785, "X")) == "AB 55 (Sub-No. 785X)"
    assert (
        urls.cite_docket(ParsedDocket("FD", 36873, 1, None))
        == "STB Finance Docket No. 36873 (Sub-No. 1)"
    )
    assert urls.cite_docket(ParsedDocket("EP", 789, None, None)) == "STB Ex Parte No. 789"
    assert (
        urls.cite_docket(ParsedDocket("AB", 55, 785, "X")) == "STB Docket No. AB 55 (Sub-No. 785X)"
    )
    assert urls.cite_docket(ParsedDocket("S5M", 1, None, "A")) == "STB Docket No. S5M 1-A"


# --- the server is a reader ----------------------------------------------------------


def test_server_refuses_a_missing_store(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_app(tmp_path / "nope.sqlite")
    assert not (tmp_path / "nope.sqlite").exists()  # and never creates one


def test_server_refuses_a_foreign_schema_version(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    con.execute("PRAGMA user_version = 99")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="schema version"):
        create_app(path)


# --- pages ---------------------------------------------------------------------------


def test_home_lists_the_week_once_per_record(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "not affiliated" in r.text
    assert r.text.count("ORDERED REPLIES DUE") == 1  # entered in two dockets, shown once
    assert "also entered in" in r.text and 'href="/d/FD-36873/sub/1"' in r.text
    assert "(one entered in two dockets)" in r.text
    assert '2</span><span class="l">filings observed, in 1 proceeding<' in r.text  # by family
    assert "<table" in r.text and '<th scope="col">Docket</th>' in r.text
    assert "19–25 August 2026" in r.text


def test_this_week_is_seven_days_and_never_in_the_future(tmp_path):
    con = db.connect(build_store(tmp_path))
    w = home.this_week(con, today=date(2026, 8, 25))
    assert (w.start, w.end) == ("2026-08-19", "2026-08-25")
    # an anchor after "today" is ignored: the window ends today
    w2 = home.this_week(con, today=date(2026, 8, 20))
    assert w2.end == "2026-08-20"


def test_sheet_at_its_permanent_address(client):
    r = client.get("/d/FD-36873")
    assert r.status_code == 200
    assert "UP/NS CONTROL" in r.text
    assert "311900" in r.text  # the sub-docket's own entry is included
    for link in ('href="/filing/311981"', 'href="/filing/311900"', 'href="/decision/53210"'):
        assert r.text.count(link) == 1, link  # each record once, its title the permalink
    assert "Sub-No. 1" in r.text
    assert "Related proceedings" in r.text and "Finance Docket" in r.text
    assert "STB Finance Docket No. 36873" in r.text
    assert "docketyard.org/d/FD-36873" in r.text  # cite-this emits the canonical address
    assert "Set-Cookie" not in r.headers  # reading leaves no trace (ADR 0011)


def test_lookup_box_redirects_to_canonical(client):
    r = client.get("/d", params={"q": "FD 36873 (Sub-No. 1)"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/d/FD-36873/sub/1"
    r = client.get("/d", params={"q": "nonsense"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/search?q=nonsense"


def test_lower_case_redirects_to_canonical(client):
    r = client.get("/d/fd-36873", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/d/FD-36873"


def test_query_string_is_not_a_second_address(client):
    assert client.get("/d/FD-36873?sub=1").status_code == 200  # ignored, the parent is served


def test_record_page_headlines_the_parent(client):
    r = client.get("/decision/53210")
    assert r.status_code == 200
    assert "UP/NS CONTROL" in r.text and "PEORIA SUB" not in r.text.split("<h1")[0]


def test_kind_labels_are_short_and_never_from_the_filer():
    from docketyard.web import labels

    assert (
        labels.kind_label("filing", "Notice Of Intent To Participate (Without Comment)") == "Notice"
    )
    assert labels.kind_label("filing", "Motion/Petition/Request") == "Motion"
    assert (
        labels.kind_label("filing", "Modify/Supplement Prior Filing Or The Record") == "Supplement"
    )
    assert labels.kind_label("filing", "Miscellaneous") == "Misc."
    assert labels.kind_label("decision", None) == "Decision"
    assert labels.kind_label("filing", None) == "Filing"
    assert labels.filter_key("filing", "Miscellaneous") == "misc"


def test_sheet_toolbar_filters_and_order(client):
    r = client.get("/d/FD-36873")
    assert 'data-filter="decision"' in r.text and 'data-filter="motion"' in r.text
    # the preference strip is site-wide and above the masthead, on every page
    for page in (r.text, client.get("/").text):
        assert page.index('class="prefs') < page.index('class="masthead')
        assert 'data-pref="density" data-value="compact" aria-pressed="false"' in page
    assert 'datetime="2026-08-25">25 Aug 2026</time>' in r.text
    assert "(printed as 8/25/2026)" in r.text  # the quoted form is real text, not a tooltip
    assert 'aria-pressed="true">All entries' in r.text


def test_display_helpers():
    from docketyard.web import labels
    from docketyard.web.app import fmt_range

    thrice = ", ".join(["Grand Trunk Corporation, on behalf of itself and its subsidiaries"] * 3)
    assert labels.display_filed_for(thrice) == (
        "Grand Trunk Corporation, on behalf of itself and its subsidiaries"
    )
    two_parties = "Norfolk Southern Corporation, Union Pacific Corporation"
    assert labels.display_filed_for(two_parties) == two_parties  # different parties stay
    assert labels.plural(1, "filing") == "1 filing" and labels.plural(2, "filing") == "2 filings"
    assert labels.plural(53130, "filing") == "53,130 filings"
    assert labels.kind_label("filing", "Support Statem") == "Statement"
    assert labels.prefix_name("FD") == "Finance Docket" and labels.prefix_name("ZZ") == "ZZ docket"
    assert fmt_range("2026-08-18", "2026-08-25") == "18–25 August 2026"
    assert fmt_range("2026-07-28", "2026-08-03") == "28 July – 3 August 2026"


def test_sheet_order(client):
    newest = client.get("/d/FD-36873").text
    oldest = client.get("/d/FD-36873?order=oldest").text
    assert newest.index("311981") < newest.index("311900")
    assert oldest.index("311900") < oldest.index("311981")


def test_health_reports_freshness_without_judging_it(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    h = r.json()
    assert h["schema"] == db.MIGRATIONS[-1][0] and set(h["age_seconds"]) == {
        "last_forward_capture",
        "last_event",
        "last_document",
        "oldest_pending_alert",
    }
    assert h["last_event"] and h["age_seconds"]["last_event"] >= 0
    assert h["last_document"] is None and h["age_seconds"]["last_document"] is None
    assert "Set-Cookie" not in r.headers


def test_record_pages_and_404s(client):
    assert client.get("/filing/311981").status_code == 200
    assert client.get("/filing/1").status_code == 404
    assert client.get("/d/FD-1").status_code == 404
    assert client.get("/d/nonsense").status_code == 404
