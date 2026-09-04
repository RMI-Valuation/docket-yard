"""Environmental-comment capture and ingest (the fourth table).

Markup here mirrors real rows read from the endpoint 2026-08-31, including the two things
that make this table different from filings and decisions: the row prints the middle part
of `data-stb-id` NOWHERE, so identity is the comment number corroborated by its own cell's
anchor; and half the rows print `--` for the comment's words and a quarter for the location.
"""

import json

import pytest

from docketyard.capture import documents, records
from docketyard.capture.stb import ENVIRO_COMMENTS, TABLE_SORT
from docketyard.ingest import observations
from docketyard.ingest.observations import ENVIRO_COMMENTS_SPEC
from docketyard.store import db, events

S3 = "https://dcms-external.s3.amazonaws.com/DCMS_External_PROD"


def comment_row(
    docket="FD_36873",
    number="EI-34280",
    ref="203738",
    row="830758",
    date="8/25/2026",
    submitter="David Gertsch",
    org="Albany County Planning Department",
    text="The Casper Aquifer provides 50% of the water to City of Laramie residents.",
    location="Laramie, WY",
    pdf="EI-34280.pdf",
    anchor=None,  # the id cell's own data-stb-id; defaults to agreeing with the number
):
    return (
        f'<tr><td><a class="stb-button-folder" data-stb-id="{docket}|{ref}|{row}"'
        f' data-stb-record="#{number} | {submitter}" data-stb-type="stb_environmental_comment"'
        f' href="#{number}"><svg></svg></a></td>'
        f"<td>{date}</td>"
        f'<td><a class="stb-table-modal" data-stb-id="{anchor or number}"'
        f' data-stb-nonce="474d2f18a2" href="#{number}">{number}</a></td>'
        f'<td><a href="https://www.stb.gov/proceedings/{docket}">{docket}</a></td>'
        f"<td>{submitter}</td><td>{org}</td><td>{text}</td><td>{location}</td>"
        f'<td><a href="{S3}/{row}/{pdf}">{pdf}</a></td></tr>'
    )


def body_of(rows_html: str, total: int) -> bytes:
    return json.dumps({"success": True, "data": {"rows": rows_html, "total": total}}).encode()


@pytest.fixture
def con():
    return db.connect(":memory:")


def ingest(con, data_dir, rows_html, *, total=1, mode="forward"):
    cid = records.save_capture(
        con,
        data_dir,
        source_system="stb-ajax",
        endpoint="test",
        table_action=ENVIRO_COMMENTS,
        request_params=[],
        body=body_of(rows_html, total),
        http_status=200,
        ingest_mode=mode,
    )
    records.set_verdict(con, cid, filter_asserted=True, row_count=0, reported_total=0)
    return observations.ingest_capture(con, data_dir, cid)


# --- parsing -------------------------------------------------------------------------


def test_the_row_parses_and_the_number_is_the_identity():
    parsed = observations.parse_response(ENVIRO_COMMENTS_SPEC, body_of(comment_row(), 1))
    assert parsed.skipped == 0
    r = parsed.rows[0]
    # the identity is the printed comment number, NOT the middle part of data-stb-id...
    assert r.record_id == "EI-34280"
    assert r.record_ref == "203738"  # ...which is kept beside it, corroborating
    assert r.docket_stb_id == "FD_36873"
    assert r.date_printed == "8/25/2026" and r.date == "2026-08-25"
    assert r.fields["submitter"] == "David Gertsch"
    assert r.fields["location"] == "Laramie, WY"
    assert "Casper Aquifer" in r.fields["comment_text"]
    assert r.attachment == (f"{S3}/830758/EI-34280.pdf", "EI-34280.pdf")


def test_the_id_cell_must_corroborate_itself():
    """The check that replaces "the printed id cell equals the row id" for this table.
    A column reorder, or a number read out of the wrong cell, must not become a record."""
    drifted = comment_row(anchor="EI-99999")
    assert observations.parse_response(ENVIRO_COMMENTS_SPEC, body_of(drifted, 1)).skipped == 1


def test_a_row_with_no_comment_number_is_quarantined_not_keyed():
    """Measured never to happen in 150 rows — but a row that did happen must not be
    stored under a synthesised key, since the key is welded into the event ledger."""
    blank = comment_row().replace(">EI-34280</a>", "></a>")
    assert observations.parse_response(ENVIRO_COMMENTS_SPEC, body_of(blank, 1)).skipped == 1


def test_links_come_only_from_the_attachment_cell():
    """The docket cell carries a link too — it must never become a document."""
    parsed = observations.parse_response(ENVIRO_COMMENTS_SPEC, body_of(comment_row(), 1))
    assert parsed.rows[0].attachment[0].startswith(S3)


def test_absent_words_and_location_are_kept_as_printed():
    """76 of 150 measured rows print `--` for the words, 37 for the location. That is the
    cell as printed, and the record stores what the source printed."""
    parsed = observations.parse_response(
        ENVIRO_COMMENTS_SPEC, body_of(comment_row(text="--", location="--"), 1)
    )
    assert parsed.rows[0].fields["comment_text"] == "--"


# --- the filter assertion ------------------------------------------------------------


def test_the_date_pair_is_verified_positively():
    parsed = observations.parse_response(ENVIRO_COMMENTS_SPEC, body_of(comment_row(), 1))
    good = [("startDate", "08/01/2026"), ("endDate", "08/31/2026")]
    assert observations.assert_filter(ENVIRO_COMMENTS_SPEC, good, parsed) is True
    outside = [("startDate", "01/01/2026"), ("endDate", "01/31/2026")]
    assert observations.assert_filter(ENVIRO_COMMENTS_SPEC, outside, parsed) is False


def test_the_other_tables_date_pairs_are_unverifiable_here():
    """filingStartDate and serviceStartDate each answer an EMPTY envelope with a 200 on
    this table. A criterion this spec cannot verify quarantines the capture rather than
    letting an unfiltered or empty answer look like a filtered one."""
    parsed = observations.parse_response(ENVIRO_COMMENTS_SPEC, body_of(comment_row(), 1))
    for wrong in ("filingStartDate", "serviceStartDate", "officialFilingStartDate"):
        criteria = [(wrong, "08/01/2026")]
        assert observations.assert_filter(ENVIRO_COMMENTS_SPEC, criteria, parsed) is False


def test_the_sort_is_pinned_to_the_only_value_the_endpoint_accepts():
    """Every non-empty sort_by answers the empty envelope with a 200 (measured). This
    constant is a measurement, and a future 'improvement' that fills it in empties the
    walk silently."""
    assert TABLE_SORT[ENVIRO_COMMENTS] == ("", "desc")


# --- ingest --------------------------------------------------------------------------


def test_a_comment_becomes_a_record_an_event_and_an_attachment(con, tmp_path):
    stats = ingest(con, tmp_path, comment_row())
    assert (stats["records"], stats["new_records"], stats["attachments"]) == (1, 1, 1)
    row = con.execute(
        "SELECT comment_number, stb_row_ref, date_received_or_sent, submitter_raw,"
        " organisation_raw, location_raw, comment_text_printed FROM enviro_comment"
    ).fetchone()
    assert row[0] == "EI-34280" and row[1] == "203738" and row[2] == "2026-08-25"
    assert row[3] == "David Gertsch" and row[5] == "Laramie, WY"
    assert "Casper Aquifer" in row[6]
    # the event key is the docket-qualified number, the same spelling document_source uses
    key = con.execute(
        "SELECT source_key FROM event WHERE event_type = 'enviro_comment_observed'"
    ).fetchone()[0]
    assert key == "FD_36873_0|EI-34280"


def test_one_comment_on_several_rows_folds_into_one_record(con, tmp_path):
    """Measured: FD 36854's EI-34249 occupies four rows, one per attachment."""
    rows = comment_row(pdf="a.pdf", row="1") + comment_row(pdf="b.pdf", row="2")
    stats = ingest(con, tmp_path, rows, total=2)
    assert stats["records"] == 1 and stats["new_records"] == 1
    assert stats["attachments"] == 2
    assert con.execute("SELECT COUNT(*) FROM enviro_comment").fetchone()[0] == 1


def test_the_same_number_under_two_dockets_is_two_records(con, tmp_path):
    rows = comment_row() + comment_row(docket="AB_55_794_X")
    stats = ingest(con, tmp_path, rows, total=2)
    assert stats["records"] == 2
    assert con.execute("SELECT COUNT(*) FROM enviro_comment").fetchone()[0] == 2


def test_every_mirrored_column_reaches_the_event_payload():
    """The rule the schema-critic's D2 turned into an invariant: `_upsert_record` only
    writes a column when the PAYLOAD changed, so a mirrored column missing from the
    payload would be write-once current state — no history, no change detection. Checked
    across every spec, so it retro-covers filings and decisions too."""
    for spec in observations.SPECS.values():
        keys = set(spec.payload_cells) | set(spec.extra_payload) | {"date", "date_printed"}
        missing = set(spec.record_columns.values()) - keys
        assert not missing, f"{spec.record_table} mirrors {missing} with no payload key"


def test_a_backfill_capture_alerts_nobody(con, tmp_path):
    """Break B6: a wave's captures are labelled before it starts. The comment event type
    is not on the alerting allowlist either, so this is belt and braces."""
    from docketyard.alerts import build

    ingest(con, tmp_path, comment_row(), mode="backfill")
    assert "enviro_comment_observed" not in build.ALERTING_EVENT_TYPES
    mode = con.execute(
        "SELECT c.ingest_mode FROM event e JOIN capture c ON c.capture_id = e.capture_id"
        " WHERE e.event_type = 'enviro_comment_observed'"
    ).fetchone()[0]
    assert mode == "backfill"


def test_an_unchanged_re_observation_appends_no_second_event(con, tmp_path):
    ingest(con, tmp_path, comment_row())
    ingest(con, tmp_path, comment_row())
    assert (
        con.execute(
            "SELECT COUNT(*) FROM event WHERE event_type = 'enviro_comment_observed'"
        ).fetchone()[0]
        == 1
    )
    assert events.latest_payload_by_key(con, "enviro_comment_observed", "FD_36873_0|EI-34280")


def test_the_fetcher_names_the_comment_as_the_documents_owner(con, tmp_path):
    """`document_source`'s two id columns are null for a comment, so without the third one
    every comment PDF folds into one anonymous association and a `document_replaced` alert
    could only say "a record it holds (not identified)". The value is docket-qualified: a
    comment number is identity only within a docket."""
    ingest(con, tmp_path, comment_row())
    url = f"{S3}/830758/EI-34280.pdf"
    stats = documents.fetch_attachments(con, tmp_path, lambda u: (200, b"%PDF-fake"))
    assert stats["fetched"] == 1 and stats["new_documents"] == 1
    filing_id, decision_id, comment_key = con.execute(
        "SELECT stb_filing_id, stb_decision_id, comment_source_key FROM document_source"
    ).fetchone()
    assert (filing_id, decision_id) == (None, None)
    assert comment_key == "FD_36873_0|EI-34280"
    sha = con.execute("SELECT document_sha256 FROM document").fetchone()[0]
    held = con.execute("SELECT document_sha256 FROM enviro_comment_attachment").fetchone()[0]
    assert held == sha and url  # the attachment row now holds the bytes it cited


def test_a_comment_attachment_joins_the_errata_recheck(con, tmp_path):
    """ADR 0002's replacement chain, and the PUBLISHED re-check cycle, are both computed
    from the held-URL union — a table left out of it silently has neither."""
    ingest(con, tmp_path, comment_row())
    documents.fetch_attachments(con, tmp_path, lambda u: (200, b"%PDF-fake"))
    assert observations.held_url_count(con) == 1
    assert observations.recheck_urls(con, limit=None) == [f"{S3}/830758/EI-34280.pdf"]


# --- the sheet (F1's third row) --------------------------------------------------------


def _sheet_with(con, tmp_path, rows, total=1):
    from docketyard.store import sheet

    ingest(con, tmp_path, rows, total=total)
    docket_id = con.execute("SELECT docket_id FROM enviro_comment LIMIT 1").fetchone()[0]
    return sheet.docket_sheet(con, docket_id)


def test_a_comment_appears_on_the_docket_sheet(con, tmp_path):
    """F1 defines the sheet as filings, decisions AND environmental comments. This is the
    row that was missing."""
    s = _sheet_with(con, tmp_path, comment_row())
    assert s.comments == 1 and s.filings == 0 and s.decisions == 0
    e = s.entries[0]
    assert e.kind == "comment" and e.record_id == "EI-34280"
    assert e.date == "2026-08-25" and e.date_printed == "8/25/2026"
    assert e.submitter == "David Gertsch"
    assert e.organisation == "Albany County Planning Department"
    assert e.location == "Laramie, WY"
    assert "Casper Aquifer" in e.comment_text
    assert e.attachments and e.attachments[0].url.startswith(S3)
    # a commenter is not a filer: the submitter must never arrive as filed_for_raw
    assert e.filed_for_raw is None


def test_the_boards_placeholder_is_an_absence_not_a_name(con, tmp_path):
    """The Board prints `--` for a cell it has nothing for — measured on half the rows for
    the words and a quarter for the location. Rendering it would state something the record
    does not ("Pamela Underwood, --")."""
    s = _sheet_with(con, tmp_path, comment_row(text="--", location="--", org="--"))
    e = s.entries[0]
    assert e.comment_text is None and e.location is None and e.organisation is None
    assert e.submitter == "David Gertsch"  # what WAS printed is untouched
    # and the store still holds the cell exactly as the Board printed it
    assert con.execute("SELECT location_raw FROM enviro_comment").fetchone()[0] == "--"


def test_a_comment_counts_as_activity_in_the_family_index(con, tmp_path):
    """A proceeding whose only held record is a comment is still active; the index must
    not show it as holding nothing."""
    s = _sheet_with(con, tmp_path, comment_row())
    own = [m for m in [*s.sub_dockets, None] if m and m.comments]
    assert s.comments == 1 or own  # the docket itself, or a sub-docket, carries the count


def test_the_sheet_page_renders_a_comment_without_dressing_it_as_a_filing(con, tmp_path):
    from fastapi.testclient import TestClient

    from docketyard.web.app import create_app

    path = tmp_path / "s.sqlite"
    live = db.connect(path)
    ingest(live, tmp_path, comment_row())
    live.close()
    client = TestClient(create_app(path))
    r = client.get("/d/FD-36873")
    assert r.status_code == 200
    assert "EI-34280" in r.text and "Casper Aquifer" in r.text
    assert "Albany County Planning Department" in r.text and "Laramie, WY" in r.text
    assert ">Comment<" in r.text  # labelled as what it is
    # addressed as a comment, never dressed as a filing or a decision
    assert "/comment/EI-34280" in r.text
    assert "/filing/EI-34280" not in r.text and "/decision/EI-34280" not in r.text


# --- the permanent address (ADR 0013) --------------------------------------------------


def test_a_comment_answers_at_its_own_address(con, tmp_path):
    """A comment's address names the docket that holds it, because the Board's numbers are
    NOT unique: two of the 34,255 in the archive name two different people's comments."""
    from fastapi.testclient import TestClient

    from docketyard.ingest.dockets import parse_docket_id
    from docketyard.web.app import create_app
    from docketyard.web.urls import comment_path, comment_short_path

    assert comment_path(parse_docket_id("FD_36873"), "EI-34280") == ("/d/FD-36873/comment/EI-34280")
    assert comment_short_path("EI-34280") == "/comment/EI-34280"
    path = tmp_path / "s.sqlite"
    live = db.connect(path)
    ingest(live, tmp_path, comment_row())
    live.close()
    client = TestClient(create_app(path))

    r = client.get("/d/FD-36873/comment/EI-34280")
    assert r.status_code == 200
    assert "EI-34280" in r.text and "Casper Aquifer" in r.text
    assert "David Gertsch" in r.text and "Laramie, WY" in r.text
    assert "/d/FD-36873/comment/EI-34280" in r.text  # it states its own address
    # A comment has no frame (`documents.VIEWABLE_KINDS`), so it has no rail: the files,
    # the neighbours and the cite line the record page's rail carries are the framed
    # kinds'. Its caption keeps the file addresses those pages moved into Cite, and the
    # page must not reach for `parties`/`prev`/`next`, which its route does not pass.
    assert 'class="rail viewer-rail"' not in r.text
    assert "Permanent address" in r.text

    j = client.get("/d/FD-36873/comment/EI-34280.json")
    body = j.json()["comment"]
    assert body["record_id"] == "EI-34280" and body["kind"] == "comment"
    assert body["url"].endswith("/d/FD-36873/comment/EI-34280")

    # the bare number stays citable: it redirects when it names one comment
    r = client.get("/comment/EI-34280", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/d/FD-36873/comment/EI-34280"
    r = client.get("/comment/EI-34280.json", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"].endswith(
        "/d/FD-36873/comment/EI-34280.json"
    )
    # and casing still canonicalises
    r = client.get("/d/FD-36873/comment/ei-34280", follow_redirects=False)
    assert r.status_code == 301

    assert "/d/FD-36873/comment/EI-34280" in client.get("/d/FD-36873").text
    assert "/d/FD-36873/comment/EI-34280" in client.get("/sitemap-comments-1.xml").text
    assert client.get("/d/FD-36873/comment/EI-99999").status_code == 404
    assert client.get("/comment/EI-99999").status_code == 404


def test_a_number_two_different_comments_share_names_both(con, tmp_path):
    """Measured in the archive wave: EI-25366 and EI-25367 each name TWO different
    people's comments in two dockets. The bare number must not pick one silently."""
    from fastapi.testclient import TestClient

    from docketyard.web.app import create_app

    path = tmp_path / "s.sqlite"
    live = db.connect(path)
    ingest(live, tmp_path, comment_row(number="EI-25366", ref="190089", submitter="Helen"))
    ingest(
        live,
        tmp_path,
        comment_row(docket="FD_36095", number="EI-25366", ref="190749", submitter="Elizabeth"),
    )
    from docketyard.store import search

    search.rebuild(live)
    live.close()
    client = TestClient(create_app(path))

    r = client.get("/comment/EI-25366", follow_redirects=False)
    assert r.status_code == 200  # named, not redirected to whichever sorts first
    assert "/d/FD-36873/comment/EI-25366" in r.text
    assert "/d/FD-36095/comment/EI-25366" in r.text
    # and each answers its own comment
    assert "Helen" in client.get("/d/FD-36873/comment/EI-25366").text
    assert "Elizabeth" in client.get("/d/FD-36095/comment/EI-25366").text
    # both are searchable: folding by number alone would have dropped one
    sitemap = client.get("/sitemap-comments-1.xml").text
    assert sitemap.count("/comment/EI-25366") == 2


def test_a_number_held_under_another_docket_is_reported_not_minted(con, tmp_path):
    """The number is a permanent public address, and its global uniqueness is measured
    (2,385 comments, no collision) rather than structural. A second docket claiming one
    must surface loudly in the wave that finds it."""
    ingest(con, tmp_path, comment_row())
    stats = ingest(con, tmp_path, comment_row(docket="AB_55_794_X"))
    assert stats["id_collisions"] == 1
    # both rows still exist — the store keys on (docket, number), so no data is lost;
    # what is refused is silence about the ambiguity
    assert con.execute("SELECT COUNT(*) FROM enviro_comment").fetchone()[0] == 2


def test_an_ordinary_comment_reports_no_collision(con, tmp_path):
    assert ingest(con, tmp_path, comment_row())["id_collisions"] == 0
    assert ingest(con, tmp_path, comment_row(number="EI-34281"))["id_collisions"] == 0


# --- the canary ------------------------------------------------------------------------


def test_the_comment_canary_separates_a_quiet_week_from_a_broken_one(tmp_path):
    """The two signals answer different questions. A quiet week must leave the CAPTURE
    canary fresh — otherwise a table that legitimately goes 14 days without a comment pages
    every time — while a poll that never asserts must leave it stale."""
    from datetime import date

    from docketyard.capture import poll
    from docketyard.capture.stb import DECISIONS, FILINGS
    from docketyard.store import projections
    from tests.test_observations import decision_row, filing_row
    from tests.test_poll import FakeStb
    from tests.test_walk import NO_RESULTS

    def pass_over(client, path):
        con = db.connect(path)
        poll.forward_pass(con, client, path.parent, today=date(2026, 8, 25), log=lambda _: 0)
        fresh = projections.freshness(con)
        con.close()
        return fresh

    healthy = {
        FILINGS: body_of(filing_row(fid="311981", date="8/25/2026"), 1),
        DECISIONS: body_of(decision_row(did="53210", date="8/24/2026"), 1),
    }

    # a quiet week: the weekly slice is empty, the wider proof window is not
    class Quiet(FakeStb):
        def query_table(self, action, criteria, *, page, per_page, sort_by, sort_order):
            if action == ENVIRO_COMMENTS:
                if dict(criteria).get("startDate") == "08/19/2026":
                    return 200, NO_RESULTS, []
                return 200, body_of(comment_row(date="7/2/2026"), 1), []
            return super().query_table(
                action,
                criteria,
                page=page,
                per_page=per_page,
                sort_by=sort_by,
                sort_order=sort_order,
            )

    quiet = pass_over(Quiet(dict(healthy)), tmp_path / "quiet.sqlite")
    assert quiet["last_enviro_capture"] is not None  # the proof asserted: the poll is alive
    assert quiet["last_enviro_event"] is not None  # and the proof's own row was ingested

    # broken: the table never answers anything that asserts
    class Broken(FakeStb):
        def query_table(self, action, criteria, *, page, per_page, sort_by, sort_order):
            if action == ENVIRO_COMMENTS:
                return 200, NO_RESULTS, []
            return super().query_table(
                action,
                criteria,
                page=page,
                per_page=per_page,
                sort_by=sort_by,
                sort_order=sort_order,
            )

    broken = pass_over(Broken(dict(healthy)), tmp_path / "broken.sqlite")
    assert broken["last_enviro_capture"] is None  # nothing asserted: the canary goes stale
    # and the other tables are unaffected, which is why they are separate signals
    assert broken["last_forward_capture"] is not None and broken["last_event"] is not None


# --- search ------------------------------------------------------------------------------


def test_a_comment_is_findable_by_its_words_and_its_submitter(con, tmp_path):
    """Migration 0012: `search_doc.kind` was a closed CHECK, so a comment could be
    addressed and shown while being unfindable. Its words are the richest free text the
    record holds."""
    from docketyard.store import search

    ingest(con, tmp_path, comment_row())
    counts = search.rebuild(con)
    assert counts["comment"] == 1

    for query in ("Casper Aquifer", "Gertsch", "Albany County Planning", "Laramie", "EI-34280"):
        hits = search.search(con, query)
        assert any(h.kind == "comment" for h in hits), query
    hit = next(h for h in search.search(con, "Casper Aquifer") if h.kind == "comment")
    # the title is the number AS PRINTED, with no noun: EO rows are the Board's own
    # environmental documents, and migration 0011 declines to type the row
    assert hit.path == "/d/FD-36873/comment/EI-34280" and hit.title == "EI-34280"
    # the fact line says "dated", never "received": the Board's own column declines to say
    assert "dated" in hit.fact and "FD 36873" in hit.fact


def test_a_comment_with_no_words_is_still_findable_by_who_sent_it(con, tmp_path):
    """Half the rows print `--` for the text (measured). Their submitter and organisation
    are terms nothing else in the index carries, so they are indexed anyway — and the
    placeholder itself is never a search term."""
    from docketyard.store import search

    ingest(con, tmp_path, comment_row(text="--", location="--"))
    assert search.rebuild(con)["comment"] == 1
    assert any(h.kind == "comment" for h in search.search(con, "Gertsch"))
    body = con.execute("SELECT body FROM search_doc WHERE kind = 'comment'").fetchone()[0]
    assert "--" not in body


def test_a_new_comment_moves_the_index_signature(con, tmp_path):
    """The index rebuilds only when its signature changes. Comments write to the event
    ledger, which the signature already keys on — checked rather than assumed, because an
    index that never notices the third table is worse than no index."""
    from docketyard.store import search

    ingest(con, tmp_path, comment_row())
    first = search.signature(con)
    search.rebuild(con)
    assert search.rebuild(con)["unchanged"] is True
    ingest(con, tmp_path, comment_row(number="EI-34281"))
    assert search.signature(con) != first
    assert search.rebuild(con).get("unchanged") is not True


def test_migrating_a_populated_index_leaves_it_empty_and_knowing_it(tmp_path):
    """The path production takes: a live store at schema 10 with a built index, migrated
    to 12. Migration 0012 drops and recreates `search_doc` AND its FTS5 virtual table, so
    what must hold afterwards is that the tables are there, empty, that the index knows it
    is stale, that the ETag's build counter did not restart, and that no orphaned shadow
    table survives to fail the snapshot's allowlist."""
    from docketyard.store import dump, search

    path = tmp_path / "s.sqlite"
    con = db.connect(path, upto=10)
    assert con.execute("PRAGMA user_version").fetchone()[0] == 10
    con.execute(
        "INSERT INTO search_doc (kind, ref, path, title, body, fact)"
        " VALUES ('docket', 1, '/d/FD-36873', 'FD 36873', 'UP NS merger', 'x')"
    )
    con.execute("INSERT INTO search_fts (search_fts) VALUES ('rebuild')")
    con.execute(
        "INSERT INTO search_meta (key, signature, build, built_at)"
        " VALUES ('built', 'old-signature', 7, '2026-08-30T00:00:00+00:00')"
    )
    con.commit()
    con.close()

    con = db.connect(path)  # the migration production will run
    assert con.execute("PRAGMA user_version").fetchone()[0] == db.MIGRATIONS[-1][0]
    assert con.execute("SELECT COUNT(*) FROM search_doc").fetchone()[0] == 0
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []

    signature, build = search.built(con)
    assert signature == "" and build == 7  # stale on purpose; the ETag counter carries on
    assert search.rebuild(con).get("unchanged") is not True  # so the next pass rebuilds

    # Every FTS5 index owns its shadows, and nothing is orphaned beside them. Migration 0018
    # added the second index, so this is two prefixes now rather than one — and `dump.py`
    # exempts only `search_fts_`, which is safe because `page_fts` is HELD and dropping the
    # virtual table takes its shadows with it before the allowlist is computed.
    shadows = {name for _, name, kind, *_ in con.execute("PRAGMA table_list") if kind == "shadow"}
    assert shadows and all(s.startswith(("search_fts_", "page_fts_")) for s in shadows), sorted(
        shadows
    )
    con.close()
    dump.dump(path, tmp_path / "public")  # the allowlist still passes over the new tables


# --- the wave and the sheet, after /code-review -------------------------------------------


def test_a_comments_only_wave_walks_and_judges_only_that_table(tmp_path):
    """`backfill --tables comments` is the flag's headline use, and the exit code judged a
    fixed pair of tables — so it raised KeyError on the one table it had walked."""
    from datetime import date

    from docketyard.capture import backfill
    from docketyard.capture.stb import DECISIONS, FILINGS
    from tests.test_backfill import FakeStb

    con = db.connect(tmp_path / "s.sqlite")
    client = FakeStb({(ENVIRO_COMMENTS, "06/01/2026"): body_of(comment_row(date="6/2/2026"), 1)})
    summary = backfill.wave(
        con,
        client,
        tmp_path,
        date(2026, 6, 1),
        date(2026, 6, 30),
        tables=(ENVIRO_COMMENTS,),
        fetch_limit=0,
        log=lambda _: None,
    )
    assert ENVIRO_COMMENTS in summary
    assert FILINGS not in summary and DECISIONS not in summary  # not walked, not reported
    # the exit-code rule reads only what was walked
    walked = (ENVIRO_COMMENTS,)
    assert not any(summary[a]["partial"] or summary[a]["capped"] for a in walked)
    assert con.execute("SELECT COUNT(*) FROM enviro_comment").fetchone()[0] == 1
    con.close()


def test_same_day_comments_have_a_defined_order(con, tmp_path):
    """A comment id is `EI-34280`, not bare digits, so the sheet's sort key read 0 for
    every one of them and same-day comments fell back to whatever the SELECT yielded."""
    from docketyard.store import sheet

    rows = "".join(
        comment_row(number=n, row=str(i)) for i, n in enumerate(("EI-1", "EI-30", "EI-7"))
    )
    ingest(con, tmp_path, rows, total=3)
    docket_id = con.execute("SELECT docket_id FROM enviro_comment LIMIT 1").fetchone()[0]
    ids = [e.record_id for e in sheet.docket_sheet(con, docket_id).entries]
    assert ids == ["EI-30", "EI-7", "EI-1"]  # newest first, by the number's own sequence


def test_a_comment_only_sub_docket_reads_as_active(con, tmp_path):
    """The family index totalled filings + decisions, so a sub-docket holding only comments
    showed as '0 held' — the very thing counting comments in last_activity was meant to
    prevent."""
    from fastapi.testclient import TestClient

    from docketyard.web.app import create_app

    path = tmp_path / "s.sqlite"
    live = db.connect(path)
    ingest(live, tmp_path, comment_row(docket="AB_55_794_X"))
    live.close()
    con2 = db.connect(path)
    from docketyard.store import sheet

    parent = con2.execute(
        "SELECT parent_docket_id FROM docket WHERE parent_docket_id IS NOT NULL LIMIT 1"
    ).fetchone()[0]
    s = sheet.docket_sheet(con2, parent)
    sub = next(m for m in s.sub_dockets if m.comments)
    assert sub.comments == 1 and sub.last_activity == "2026-08-25"
    con2.close()
    body = TestClient(create_app(path)).get("/d/AB-55").text
    assert "0 held" not in body


def test_a_filings_backlog_cannot_starve_comment_attachments(con, tmp_path):
    """`attachments()` concatenates the specs in order, so taking the first `limit` of that
    list would give every slot on every pass to whichever table is listed first — and a
    comment's file would never be fetched at all, silently, for as long as the backlog
    lasted. The budget is shared round-robin instead."""
    from tests.test_observations import filing_row
    from tests.test_observations import ingest as ingest_filings

    for i in range(6):
        ingest_filings(con, tmp_path, filing_row(fid=f"31198{i}", row=f"8305{i}"))
    ingest(con, tmp_path, comment_row())

    refs = observations.attachments(con, unfetched_only=True, limit=2)
    assert len(refs) == 2
    assert {r.spec.record_table for r in refs} == {"filing", "enviro_comment"}
    # and with no limit every one of them is still offered, in table order
    assert len(observations.attachments(con, unfetched_only=True)) == 7
    assert observations.attachments(con, unfetched_only=True, limit=0) == []


def test_the_empty_envelope_is_recognised_for_every_table_the_record_walks():
    r"""The message below is verbatim from the live endpoint, 2026-08-31.

    `_NO_RESULTS_RE` was `There are no \w+ available`, and `\w+` cannot span a space, so it
    silently failed on the ONE table whose name is two words — the same table whose empty
    weeks are ordinary. Every quiet week would have quarantined and cried wolf, the
    quiet-week proof would never have run, and a slice whose last page was exactly full
    would have quarantined instead of finishing. Every test passed anyway, because the
    fixture named a one-word table. So these are the real strings.
    """
    from docketyard.ingest.dockets import is_no_results_envelope

    def envelope(error: str) -> bytes:
        return json.dumps({"success": False, "data": {"error": error}}).encode()

    for table in ("filings", "decisions", "environmental comments", "dockets"):
        body = envelope(f"<p>There are no {table} available at this time.</p>\n")
        assert is_no_results_envelope(body), table
    # and it still refuses to read a genuine failure as an empty result
    assert not is_no_results_envelope(envelope("Security check failed"))
    assert not is_no_results_envelope(b'{"success":true,"data":{"rows":"","total":0}}')


def test_a_cross_posted_comment_is_one_comment_at_one_address(con, tmp_path):
    """108 of the 110 repeated numbers are ONE comment entered in a docket and its
    sub-docket — one row ref. It must have one address, and the bare number must redirect
    rather than announce "two different people", which review found it doing."""
    from fastapi.testclient import TestClient

    from docketyard.web.app import create_app

    path = tmp_path / "s.sqlite"
    live = db.connect(path)
    rows = comment_row(docket="AB_55") + comment_row(docket="AB_55_794_X")
    ingest(live, tmp_path, rows, total=2)
    live.close()
    client = TestClient(create_app(path))

    # the bare number resolves to ONE comment and redirects to the parent's copy
    r = client.get("/comment/EI-34280", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/d/AB-55/comment/EI-34280"
    # and the sub-docket's address is not a second live page for the same comment
    r = client.get("/d/AB-55/sub/794X/comment/EI-34280", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/d/AB-55/comment/EI-34280"
    assert client.get("/d/AB-55/comment/EI-34280").status_code == 200
    # one comment, one sitemap entry
    assert client.get("/sitemap-comments-1.xml").text.count("comment/EI-34280") == 1


def test_the_docket_half_of_the_address_canonicalises_too(con, tmp_path):
    """`/d/fd-36873` 301s, so `/d/fd-36873/comment/...` must not answer 200."""
    from fastapi.testclient import TestClient

    from docketyard.web.app import create_app

    path = tmp_path / "s.sqlite"
    live = db.connect(path)
    ingest(live, tmp_path, comment_row())
    live.close()
    client = TestClient(create_app(path))
    for url in ("/d/fd-36873/comment/EI-34280", "/d/FD-36873/comment/ei-34280"):
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 301, url
        assert r.headers["location"] == "/d/FD-36873/comment/EI-34280"
    r = client.get("/d/fd-36873/comment/EI-34280.json", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"].endswith(
        "/d/FD-36873/comment/EI-34280.json"
    )


def test_record_path_refuses_a_comment_rather_than_inventing_a_filing():
    """It used to fall through to `/filing/<comment number>` — a live 404 — and
    `viewer.html`'s prev/next calls it with whatever kind the neighbour happens to be."""
    import pytest as _pytest

    from docketyard.web import urls

    with _pytest.raises(ValueError, match="addressed under its docket"):
        urls.record_path("comment", "EI-34280")
    assert urls.record_path("filing", "311981") == "/filing/311981"


def test_a_sheet_entry_is_addressed_by_its_kind_in_one_place():
    """The guard above was only half the fix: it made a comment reaching `record_path`
    loud instead of wrong, and left `viewer.html` calling it, which answered 500 on every
    viewer page whose neighbour was a comment. `entry_path` is where that branch lives."""
    from docketyard.web import urls

    assert urls.entry_path("filing", "311981", "FD_36873") == "/filing/311981"
    assert urls.entry_path("decision", "53210", "FD_36873") == "/decision/53210"
    assert urls.entry_path("comment", "EI-34280", "FD_36873") == "/d/FD-36873/comment/EI-34280"
    # the entry's own docket, not the family's: a comment entered in a sub-docket is
    # addressed there, which is the copy the sheet folded to
    assert urls.entry_path("comment", "EI-1", "AB_290_324_X") == "/d/AB-290/sub/324X/comment/EI-1"
    # a docket that will not parse is not a reason to raise inside a link
    assert urls.entry_path("comment", "EI-34280", "not a docket") == "/comment/EI-34280"
    # and the neighbour link: the file when there is one, the record when there is not
    assert urls.entry_viewer_path("filing", "311981", "FD_36873", 0) == "/filing/311981#file"
    assert urls.entry_viewer_path("filing", "311981", "FD_36873", 2) == "/filing/311981?file=2#file"
    assert urls.entry_viewer_path("filing", "311981", "FD_36873", None) == "/filing/311981"
    # `viewable_index` answers None for every comment (it has no viewer page), so a
    # comment always leaves through `entry_path` — never `/comment/EI-34280/view`
    assert (
        urls.entry_viewer_path("comment", "EI-34280", "FD_36873", None)
        == "/d/FD-36873/comment/EI-34280"
    )


def test_the_index_rebuilds_when_its_shape_changes_not_only_its_rows(con, tmp_path):
    """`signature()` read store row ids only, so a deploy that changed the index's PATHS
    short-circuited and served the old ones until unrelated data moved."""
    from docketyard.store import search

    ingest(con, tmp_path, comment_row())
    first = search.signature(con)
    assert first.startswith(f"{search.INDEX_FORMAT}.")
    search.rebuild(con)
    assert search.rebuild(con)["unchanged"] is True
    bumped = search.INDEX_FORMAT + 1
    try:
        search.INDEX_FORMAT = bumped
        assert search.signature(con) != first
        assert search.rebuild(con).get("unchanged") is not True
    finally:
        search.INDEX_FORMAT = bumped - 1
