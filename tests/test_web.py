"""The web tier over a small real-shaped store: addresses, redirects, content as printed."""

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from docketyard.capture import records
from docketyard.capture.stb import DECISIONS, DOCKETS, FILINGS
from docketyard.ingest import dockets, observations
from docketyard.ingest.dockets import ParsedDocket
from docketyard.store import db, home, registry, sheet
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
    # The proceeding that moved is the docket the filing was entered in, never its parent:
    # a sub-docket is named and linked as itself (revised 2026-08-30). A filing entered in
    # a docket and its sub is two `filing` rows and one filing, said so on the page.
    assert (
        '2</span><span class="l">filings observed, in 2 proceedings (one entered in two)' in r.text
    )
    assert '<td class="dk"><a href="/d/FD-36873/sub/1">FD 36873 (Sub-No. 1)</a></td>' in r.text
    assert "<table" in r.text and '<th scope="col">Docket</th>' in r.text
    assert "19–25 August 2026" in r.text


def test_a_series_docket_leads_with_its_index(tmp_path):
    """AB 290 is Norfolk Southern's abandonment series: the Board opens a sub-docket per
    line and holds nothing against the number itself (measured 2026-08-30 — every one of
    the fourteen largest families holds zero records of its own). So the page leads with
    the index of proceedings, and lists a proceeding the record holds nothing for: the
    Board opened it, and its number is the answer for a pre-1996 abandonment nobody can
    otherwise find (the operator, 2026-08-30)."""
    db_path = tmp_path / "series.sqlite"
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

    # only sub-dockets are published by the Board; the parent is minted from them
    dockets.ingest_capture(
        con,
        tmp_path,
        save(
            make_body(
                [
                    ("AB_290_1_X", "CAROLINA AND NORTHWESTERN RAILWAY - ABANDONMENT"),
                    ("AB_290_2_X", "SOUTHERN RAILWAY - DISCONTINUANCE"),
                    ("AB_290_3_X", "NORFOLK SOUTHERN - ABANDONMENT - YORK COUNTY"),
                    ("AB_290_4_X", "NORFOLK SOUTHERN - ABANDONMENT - GASTON COUNTY"),
                    ("AB_290_5_X", "NORFOLK SOUTHERN - DISCONTINUANCE - MECKLENBURG"),
                    ("AB_290_6_X", "NORFOLK SOUTHERN - ABANDONMENT - UNION COUNTY"),
                ],
                total=6,
            ),
            DOCKETS,
        ),
    )
    observations.ingest_capture(
        con,
        tmp_path,
        save(
            body_of(
                filing_row(docket="AB_290_1_X", fid="311981", date="8/25/2026", filed_for="NS"), 1
            ),
            FILINGS,
        ),
    )
    con.close()
    sheet = TestClient(create_app(db_path))
    r = sheet.get("/d/AB-290")
    assert r.status_code == 200
    assert "This number is a series" in r.text
    assert "6 proceedings held here are indexed below" in r.text
    assert "All 6 proceedings under AB 290" in r.text
    assert "this record holds nothing against the number itself" in r.text  # never the Board's
    # the ten-row cap is named only when it bites: six active proceedings is not capped
    assert "The ten most recent" not in r.text
    assert "All 6 are" in " ".join(r.text.split())
    assert "Most recently active" in r.text
    # the proceeding with records, and the one without — both listed, the second marked
    assert 'href="/d/AB-290/sub/1X"' in r.text and 'href="/d/AB-290/sub/2X"' in r.text
    assert "CAROLINA AND NORTHWESTERN" in r.text and "SOUTHERN RAILWAY" in r.text
    assert "none held" in r.text and 'class="dormant"' in r.text
    assert "Related proceedings" not in r.text  # the rail is the index's job now
    assert "2026" in r.text  # the index spans the record, so every date carries its year


def test_a_two_member_family_is_a_case_not_a_series(tmp_path):
    """The index leads only where the parent is a series. A docket with one sub-docket
    holding all the records is still one case, and burying its entries under a one-row
    index would lose them (code review, 2026-08-30)."""
    con = db.connect(build_store(tmp_path))
    parent = con.execute("SELECT docket_id FROM docket WHERE raw_docket='FD_36873'").fetchone()[0]
    s = sheet.docket_sheet(con, parent)
    con.close()
    assert s is not None and s.is_index is False and len(s.sub_dockets) == 1


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
        "last_enviro_capture",
        "last_enviro_event",
        "last_document",
        "oldest_pending_alert",
    }
    assert h["last_event"] and h["age_seconds"]["last_event"] >= 0
    assert h["last_document"] is None and h["age_seconds"]["last_document"] is None
    assert "Set-Cookie" not in r.headers


def test_the_footer_names_the_release_that_served_the_page(tmp_path, monkeypatch):
    path = build_store(tmp_path)
    assert "Development build." in TestClient(create_app(path)).get("/").text  # off a release
    monkeypatch.setattr("docketyard.web.app.__version__", "v2026.09.26")
    html = TestClient(create_app(path)).get("/coverage").text
    assert (
        '<a href="https://github.com/RMI-Valuation/docket-yard/releases/tag/v2026.09.26"'
        ' rel="noopener">Release v2026.09.26</a>.' in html
    )


def test_record_pages_and_404s(client):
    assert client.get("/filing/311981").status_code == 200
    assert client.get("/filing/1").status_code == 404
    assert client.get("/d/FD-1").status_code == 404
    assert client.get("/d/nonsense").status_code == 404


def test_every_freshness_signal_is_actually_watched():
    """A canary nobody reads is not a canary. `/health` reports the timestamps and the
    heartbeat workflow judges them, so the two must name the same set: a signal added here
    and forgotten there is exactly the silent gap the third record table opened."""
    import re
    from pathlib import Path

    from docketyard.store import db, projections

    con = db.connect(":memory:")
    reported = set(projections.freshness(con))
    con.close()
    workflow = Path(".github/workflows/heartbeat.yml").read_text(encoding="utf-8")
    limits = set(re.findall(r'"(last_\w+|oldest_\w+)":\s*\d', workflow))
    assert reported == limits, f"unwatched: {reported - limits}; unknown: {limits - reported}"


def test_a_head_override_adds_to_the_shared_head_or_deliberately_replaces_it(tmp_path):
    """`base.html`'s head block carries the site feed. A page that only wants to ADD a tag
    must call `super()` — copying the link instead drifts the moment base gains one
    (Copilot, PR #13). A page with a feed of its OWN replaces the block on purpose, and
    must not end up advertising two."""
    client = TestClient(create_app(build_store(tmp_path)))
    # the head link itself, not the footer's plain link to the same address
    site_feed = '<link rel="alternate" type="application/atom+xml" title="Every new filing'
    for path in ("/", "/week/2026-08-24", "/search?q=peoria", "/coverage"):
        text = client.get(path).text
        assert text.count(site_feed) == 1, path  # inherited via super(), exactly once
    # a page with a feed of its own swaps the site's out rather than advertising both
    sheet = client.get("/d/FD-36873").text
    assert sheet.count('type="application/atom+xml"') == 1 and site_feed not in sheet


def con_count(path, sql: str) -> int:
    con = db.connect(path)
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


def test_the_docket_index_lists_the_registry_by_number(tmp_path):
    """`/coverage` said the record holds 32,623 dockets and offered no way to look at one
    (navigation-review.md § C). By NUMBER, not by year: a docket row carries a caption and
    no date, and 16,805 of 21,807 families hold no entry to infer one from."""
    path = build_store(tmp_path)
    con = db.connect(path)
    rows = registry.rows(con)
    con.close()
    assert [r.raw_docket for r in rows] == ["FD_36873"]  # families only; the sub is on its sheet
    assert rows[0].filings == 2 and rows[0].decisions == 1 and rows[0].held
    con = db.connect(path)
    summary = registry.prefixes(rows, registry.sub_counts(con))
    con.close()
    # the sub-docket is counted, not listed: /coverage counts every docket and this page
    # counts the ones opened directly, and a page publishing only its own total would
    # contradict it (code review, 2026-09-01)
    assert [(p.prefix, p.dockets, p.subs, p.held, p.banded) for p in summary] == [
        ("FD", 1, 1, 1, False)
    ]

    client = TestClient(create_app(path))
    r = client.get("/dockets")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=1800"
    assert 'href="/dockets/FD"' in r.text
    # both totals on the page, and they reconcile with the one /coverage publishes
    assert "listed here" in r.text and "dockets in all" in r.text
    held = int(
        re.search(r'([\d,]+)</span><span class="l">dockets in all', r.text)
        .group(1)
        .replace(",", "")
    )
    assert held == con_count(path, "SELECT COUNT(*) FROM docket")
    prefix = client.get("/dockets/FD")
    assert prefix.status_code == 200
    assert 'href="/d/FD-36873"' in prefix.text and "UP/NS CONTROL" in prefix.text
    # a small prefix is listed without bands, and its band addresses do not exist
    assert client.get("/dockets/FD/36000").status_code == 404
    assert client.get("/dockets/ZZ").status_code == 404
    assert client.get("/dockets/FD/notanumber").status_code == 404
    # one canonical address, as everywhere else
    lower = client.get("/dockets/fd", follow_redirects=False)
    assert lower.status_code == 301 and lower.headers["location"] == "/dockets/FD"
    # and the surfaces that make it reachable
    assert 'href="/dockets"' in client.get("/").text  # the footer, on every page
    assert "/dockets" in client.get("/sitemap-pages-1.xml").text
    assert "/dockets" in client.get("/llms.txt").text


def test_a_banded_prefix_splits_by_number_and_the_bands_are_permanent(tmp_path):
    """A band is a range of the Board's own numbers, so `/dockets/FD/36000` means
    FD 36000–36999 for ever, whatever is opened in it later — which a page number would
    not."""
    path = build_store(tmp_path)
    con = db.connect(path)
    for seq in range(1, registry.DIRECT + 2):  # one more than fits on a single page
        if seq != 36873:
            con.execute(
                "INSERT OR IGNORE INTO docket (raw_docket, prefix, sequence) VALUES (?, 'FD', ?)",
                (f"FD_{seq}", seq),
            )
    con.commit()
    rows = registry.rows(con)
    con.close()
    info = next(p for p in registry.prefixes(rows) if p.prefix == "FD")
    assert info.banded and {b.start for b in info.bands} == {0, 1000, 36000}
    assert sum(b.dockets for b in info.bands) == info.dockets
    client = TestClient(create_app(path))
    listing = client.get("/dockets/FD")
    assert listing.status_code == 200
    assert 'href="/dockets/FD/36000"' in listing.text  # bands, not 1,002 rows
    assert 'href="/d/FD-36873"' not in listing.text
    band = client.get("/dockets/FD/36000")
    assert band.status_code == 200 and 'href="/d/FD-36873"' in band.text
    assert client.get("/dockets/FD/2000").status_code == 404  # a range holding nothing


def test_a_decisions_date_says_it_is_the_served_date_everywhere(tmp_path):
    """The operator, 2026-09-16, on the independent graders' finding: a decision's date is the
    day the Board served it, not the day it was decided, and nothing said so. Labelled, so a
    quoted decided date can arrive beside it later without renaming anything."""
    from docketyard.web import labels, mcp

    path = build_store(tmp_path)
    client = TestClient(create_app(path))
    page = client.get("/decision/53210").text
    assert "Served <time" in page
    assert "(STB served Aug. 21, 2026)</p>" in page  # the Board's own citation form
    assert "(filed Aug. 25, 2026)</p>" in client.get("/filing/311981").text
    assert '<span class="small">served </span>' in client.get("/d/FD-36873").text
    d = client.get("/decision/53210.json").json()["decision"]
    assert d["date_kind"] == "served" and d["date"] == "2026-08-21"
    assert client.get("/filing/311981.json").json()["filing"]["date_kind"] == "filed"
    con = db.connect(path)
    out = mcp._docket(con, {"docket": "FD 36873"}, "docketyard.org")
    con.close()
    assert "- served 2026-08-21 [decision] 53210" in out
    assert "- filed 2026-08-25 [filing] 311981" in out
    assert labels.cite_date("decision", "2026-09-03") == "(STB served Sept. 3, 2026)"
    assert labels.cite_date("filing", "2026-06-01") == "(filed June 1, 2026)"
    assert labels.cite_date("decision", None) == ""


def test_last_checked_is_the_last_poll_and_the_last_entry_is_said_apart(tmp_path):
    """Two independent graders, 2026-09-16: `last checked` was the latest capture that brought
    the docket an entry, so a quiet docket polled every thirty minutes read weeks stale. Shape 3
    (the operator's decision): the poll and the entry are two fields, and the page shows both."""
    from docketyard.web import mcp

    path = build_store(tmp_path)
    con = db.connect(path)
    (entry_time,) = con.execute("SELECT MAX(captured_at) FROM capture").fetchone()
    # a later pass that found nothing new for any docket: every table asked, no events
    for action in (FILINGS, DECISIONS):
        cid = records.save_capture(
            con,
            tmp_path,
            source_system="stb-ajax",
            endpoint="test",
            table_action=action,
            request_params=[],
            body=b'{"success": true, "data": {"rows": "", "total": 0}}',
            http_status=200,
            ingest_mode="forward",
        )
        records.set_verdict(con, cid, filter_asserted=True, row_count=0, reported_total=0)
        con.execute(
            "UPDATE capture SET captured_at = '2099-01-01T00:00:00+00:00' WHERE capture_id = ?",
            (cid,),
        )
    con.commit()
    s = sheet.docket_sheet(con, 1)
    assert s.last_checked == "2099-01-01T00:00:00+00:00"
    assert s.last_new_entry == entry_time
    out = mcp._docket(con, {"docket": "FD 36873"}, "docketyard.org")
    con.close()
    assert "Last checked against the Board: 2099-01-01" in out
    assert f"Last new entry observed: {entry_time}" in out
    client = TestClient(create_app(path))
    d = client.get("/d/FD-36873.json").json()
    assert d["shape_version"] == 3
    assert d["docket"]["last_checked"].startswith("2099") and d["docket"]["last_new_entry"]
    assert "last new entry" in client.get("/d/FD-36873").text


def test_a_cite_block_carries_the_day_it_was_read_and_the_snapshot(tmp_path):
    """The researcher grader, 2026-09-16: a paper citing a sheet could not say what it showed
    that day. The operator's decision: an access date and the bulk snapshot, now."""
    from docketyard.store import dump

    path = build_store(tmp_path)
    client = TestClient(create_app(path))
    from datetime import UTC, datetime

    today = datetime.now(UTC)  # the page's clock is UTC
    assert f"Accessed {today.day} {today.strftime('%b %Y')}." in client.get("/d/FD-36873").text
    dump.dump(path, tmp_path / "public")  # a snapshot exists: the cite names it
    page = TestClient(create_app(path)).get("/decision/53210").text
    kept = dump.read_manifest(tmp_path / "public").dated[0].name
    assert f"; bulk archive {kept}." in page and "latest" not in kept  # a file that stays


def test_the_thin_early_years_are_said_to_be_the_boards_and_an_early_sheet_warns(
    tmp_path, monkeypatch
):
    """The operator's decision 1 on the independent graders' findings: the early years' small
    numbers read as months still to come, and a sheet that may be the later part of an older
    proceeding gave no hint. Measured years on /coverage; one line on such a sheet."""
    from docketyard.store import coverage

    path = build_store(tmp_path)
    con = db.connect(path)
    (event,) = con.execute("SELECT MIN(observed_in_event) FROM filing").fetchone()
    for i, filed in enumerate(["1996-03-01", "1997-05-01", "1999-01-01", "1999-02-01"]):
        con.execute(
            "INSERT INTO filing (docket_id, stb_filing_id, filing_type, filed_date,"
            " observed_in_event) VALUES (1, ?, 'Letter', ?, ?)",
            (str(800000 + i), filed, event),
        )
    con.commit()
    monkeypatch.setattr(coverage, "DENSE_YEAR", 1)
    years = coverage.early_filing_years(con, this_year="2026")
    # 1999 holds two (> 1) and so does no later full year: the thin run ends at 1999
    assert years == [("1996", 1), ("1997", 1), ("1999", 2)]
    con.close()
    client = TestClient(create_app(path))
    page = client.get("/d/FD-36873").text
    assert "The record begins with the Board’s own search, on 25 Jan 1996." in page
    # a sheet whose record starts later carries no such line
    assert "The record begins with" not in client.get("/d/FD-36873/sub/1").text


def test_the_licence_dedicates_what_is_ours_and_reproduces_what_was_filed():
    """The operator's decision 5: comments and filings are public record and stay published as
    filed; the label says CC0 covers the compilation and the Board's own fields."""
    from importlib import resources

    text = resources.files("docketyard").joinpath("LICENSE-DATA.txt").read_text(encoding="utf-8")
    assert "WHAT IS DEDICATED" in text and "WHAT IS REPRODUCED AS FILED" in text
    assert "does not purport" in text and "machine-read text of documents" in text
    assert "as works of the United States Government they are in the public domain" not in text


def test_walked_back_to_refuses_a_gap_no_wave_began_and_takes_the_later_table(tmp_path):
    """Code review, 2026-09-16: `/stats` and `/coverage` said "every month back to 1996-01 has
    been walked" while a month between waves had no slice, or one table was walked less far
    back than the other."""
    from docketyard.store import coverage

    con = db.connect(build_store(tmp_path))
    start = coverage._watch_starts(con.execute, (FILINGS, DECISIONS))[FILINGS]

    def months(first: str):
        y, m = int(first[:4]), int(first[5:7])
        while (y, m) <= (start.year, start.month):
            yield f"{y:04d}-{m:02d}"
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    def slice_(action, month):
        con.execute(
            "INSERT OR REPLACE INTO walk_slice (slice_key, table_action, criteria, status, rows,"
            " captures, completed_at) VALUES (?, ?, '[]', 'done', 0, 1, '2026-09-01')",
            (f"{action}:{month}", action),
        )

    for m in months("2025-11"):
        slice_(FILINGS, m)
    for m in months("2026-01"):
        slice_(DECISIONS, m)
    con.commit()
    assert coverage.walked_back_to(con) == "2026-01"  # decisions reach back less far
    con.execute("DELETE FROM walk_slice WHERE slice_key = ?", (f"{FILINGS}:2025-12",))
    con.commit()
    assert coverage.walked_back_to(con) is None  # a month no slice names is outstanding
    con.close()
