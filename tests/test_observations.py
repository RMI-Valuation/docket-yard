"""Filings/decisions parsing, date-pair assertion, record folding, and document fetching."""

import http.client
import io
import json
import os
import urllib.request

import pytest

from docketyard.capture import documents, records
from docketyard.capture.stb import DECISIONS, DOCKETS, FILINGS
from docketyard.ingest import dockets, observations
from docketyard.ingest.observations import DECISIONS_SPEC, FILINGS_SPEC
from docketyard.store import db, events, projections

S3 = "https://dcms-external.s3.amazonaws.com/DCMS_External_PROD"


def filing_row(
    docket="FD_36873",
    fid="311981",
    row="830599",
    date="8/25/2026",
    filed_for="NRDC",
    ftype="Motion",
    title="UP/NS",
    pdf="311981.pdf",
    docket_link=False,
):
    docket_cell = (
        f'<a href="https://www.stb.gov/proceedings/{docket}">{docket}</a>'
        if docket_link
        else docket
    )
    return (
        f'<tr><td><a class="stb-button-folder" data-stb-id="{docket}|{fid}|{row}"'
        f' data-stb-type="stb_filing" href="#{fid}"><svg></svg></a></td>'
        f"<td>{date}</td><td>{docket_cell}</td><td>{fid}</td><td>{filed_for}</td>"
        f'<td>{ftype}</td><td>{title}</td><td><a href="{S3}/{row}/{pdf}">{pdf}</a></td></tr>'
    )


def decision_row(
    docket="FD_36873",
    did="53210",
    row="830527",
    date="8/21/2026",
    dtype="Decision",
    body="Chief Counsel",
    summary="ORDERED",
    pdf="53210.pdf",
):
    return (
        f'<tr><td><a data-stb-id="{docket}|{did}|{row}" data-stb-type="stb_decision"'
        f' href="#{did}"></a></td>'
        f"<td>{date}</td><td>{did}</td><td>{docket}</td><td>UP TITLE</td>"
        f"<td>{dtype}</td><td>{body}</td><td>{summary}</td>"
        f'<td><a href="{S3}/{row}/{pdf}">{pdf}</a></td></tr>'
    )


def body_of(rows_html: str, total: int) -> bytes:
    return json.dumps({"success": True, "data": {"rows": rows_html, "total": total}}).encode()


@pytest.fixture
def con():
    return db.connect(":memory:")


def save(con, data_dir, body, *, action, asserted=True, mode="forward"):
    cid = records.save_capture(
        con,
        data_dir,
        source_system="stb-ajax",
        endpoint="test",
        table_action=action,
        request_params=[],
        body=body,
        http_status=200,
        ingest_mode=mode,
    )
    if asserted:
        records.set_verdict(con, cid, filter_asserted=True, row_count=0, reported_total=0)
    return cid


def ingest(con, data_dir, rows_html, *, action=FILINGS, total=1):
    return observations.ingest_capture(
        con, data_dir, save(con, data_dir, body_of(rows_html, total), action=action)
    )


# --- parsing -------------------------------------------------------------------------


def test_filing_row_parses():
    parsed = observations.parse_response(FILINGS_SPEC, body_of(filing_row(), 1))
    assert parsed.skipped == 0
    r = parsed.rows[0]
    assert (r.docket_stb_id, r.record_id, r.row_id) == ("FD_36873", "311981", "830599")
    assert r.date_printed == "8/25/2026" and r.date == "2026-08-25"  # quoted + normalised
    assert r.fields["filed_for"] == "NRDC" and r.fields["filing_type"] == "Motion"
    assert r.attachment == (f"{S3}/830599/311981.pdf", "311981.pdf")


def test_decision_row_parses_with_swapped_columns():
    parsed = observations.parse_response(DECISIONS_SPEC, body_of(decision_row(), 1))
    assert parsed.skipped == 0
    r = parsed.rows[0]
    assert (r.docket_stb_id, r.record_id) == ("FD_36873", "53210")
    assert r.fields["deciding_body"] == "Chief Counsel"


def test_links_come_only_from_the_attachment_cell():
    parsed = observations.parse_response(FILINGS_SPEC, body_of(filing_row(docket_link=True), 1))
    assert parsed.skipped == 0
    assert parsed.rows[0].attachment == (f"{S3}/830599/311981.pdf", "311981.pdf")


def test_cells_must_corroborate_the_triple_id():
    drifted = filing_row().replace("<td>311981</td>", "<td>999999</td>")
    assert observations.parse_response(FILINGS_SPEC, body_of(drifted, 1)).skipped == 1


def test_malformed_triple_id_is_skipped():
    bad = filing_row().replace("FD_36873|311981|830599", "FD_36873|311981")
    assert observations.parse_response(FILINGS_SPEC, body_of(bad, 1)).skipped == 1


# --- the filter assertion, date-pair edition -----------------------------------------


def crit(*pairs):
    return list(pairs)


def test_date_range_positively_verified():
    parsed = observations.parse_response(FILINGS_SPEC, body_of(filing_row(date="8/25/2026"), 1))
    inside = crit(("filingStartDate", "08/01/2026"), ("filingEndDate", "08/31/2026"))
    outside = crit(("filingStartDate", "09/01/2026"), ("filingEndDate", "09/30/2026"))
    assert observations.assert_filter(FILINGS_SPEC, inside, parsed) is True
    assert observations.assert_filter(FILINGS_SPEC, outside, parsed) is False


def test_wrong_date_pair_is_unverifiable_and_quarantined():
    # THE trap: officialFilingStartDate returns zero rows with no error; it is not in the
    # verifiable set, so even a plausible-looking response cannot be asserted
    parsed = observations.parse_response(FILINGS_SPEC, body_of(filing_row(), 1))
    bad_pair = crit(("officialFilingStartDate", "08/01/2026"))
    assert observations.assert_filter(FILINGS_SPEC, bad_pair, parsed) is False


def test_unreadable_date_value_quarantines_instead_of_skipping_the_check():
    parsed = observations.parse_response(FILINGS_SPEC, body_of(filing_row(), 1))
    iso_typed = crit(("filingStartDate", "2026-08-01"))
    assert observations.assert_filter(FILINGS_SPEC, iso_typed, parsed) is False


def test_docket_criteria_verified_against_triple():
    parsed = observations.parse_response(FILINGS_SPEC, body_of(filing_row(), 1))
    assert observations.assert_filter(FILINGS_SPEC, crit(("docketNum_one", "FD")), parsed)
    assert not observations.assert_filter(FILINGS_SPEC, crit(("docketNum_one", "AB")), parsed)


# --- ingest --------------------------------------------------------------------------


def test_attachment_rows_fold_into_one_filing_with_their_own_labels(con, tmp_path):
    two_rows = filing_row(pdf="main.pdf") + filing_row(row="830600", pdf="exhibit.xlsx")
    stats = ingest(con, tmp_path, two_rows, total=2)
    assert stats["records"] == 1 and stats["new_records"] == 1 and stats["events"] == 1
    assert stats["attachments"] == 2
    rows = dict(con.execute("SELECT source_url, label FROM filing_attachment").fetchall())
    assert rows == {
        f"{S3}/830599/main.pdf": "main.pdf",
        f"{S3}/830600/exhibit.xlsx": "exhibit.xlsx",
    }


def test_rows_straddling_a_page_boundary_converge_not_oscillate(con, tmp_path):
    # the filing's two attachment rows arrive in two captures (page 1, page 2)
    page1 = filing_row(pdf="main.pdf")
    page2 = filing_row(row="830600", pdf="exhibit.xlsx")
    ingest(con, tmp_path, page1)
    ingest(con, tmp_path, page2)
    # a second identical run must be silent — the folded set is the union, not the page
    again1 = ingest(con, tmp_path, page1)
    again2 = ingest(con, tmp_path, page2)
    assert again1["events"] == 0 and again2["events"] == 0
    latest = events.latest_payload_by_key(con, "filing_observed", "FD_36873_0|311981")
    assert latest["attachments"] == sorted([f"{S3}/830599/main.pdf", f"{S3}/830600/exhibit.xlsx"])


def test_docket_and_parent_minted_from_filing_get_provenance(con, tmp_path):
    stats = ingest(con, tmp_path, filing_row(docket="FD_36500_1"))
    assert stats["new_dockets"] == 2  # the sub-docket AND its parent
    ids = dict(con.execute("SELECT raw_docket, docket_id FROM docket").fetchall())
    assert events.latest_payload(con, "docket_inferred", ids["FD_36500_1"]) == {
        "inferred_from": "filing:311981"
    }
    assert events.latest_payload(con, "docket_inferred", ids["FD_36500_0"]) == {
        "inferred_from": "filing:311981"
    }


def test_reobservation_without_change_is_quiet(con, tmp_path):
    ingest(con, tmp_path, filing_row())
    stats = ingest(con, tmp_path, filing_row())
    assert stats["events"] == 0 and stats["new_records"] == 0 and stats["attachments"] == 0


def test_changed_filing_appends_event_and_updates_record(con, tmp_path):
    ingest(con, tmp_path, filing_row(ftype="Motion"))
    before = con.execute("SELECT observed_in_event FROM filing").fetchone()[0]
    ingest(con, tmp_path, filing_row(ftype="Errata"))
    ftype, after = con.execute("SELECT filing_type, observed_in_event FROM filing").fetchone()
    assert ftype == "Errata" and after != before
    assert (
        con.execute("SELECT COUNT(*) FROM event WHERE event_type='filing_observed'").fetchone()[0]
        == 2
    )


def test_decisions_ingest(con, tmp_path):
    stats = ingest(con, tmp_path, decision_row(), action=DECISIONS)
    assert stats["new_records"] == 1
    dtype, body_, date = con.execute(
        "SELECT decision_type, deciding_body, service_date FROM decision_record"
    ).fetchone()
    assert (dtype, body_, date) == ("Decision", "Chief Counsel", "2026-08-21")


def test_wrong_parser_refuses_the_capture_and_leaves_it_pending(con, tmp_path):
    cid = save(con, tmp_path, body_of(filing_row(), 1), action=FILINGS)
    with pytest.raises(ValueError, match="not"):
        dockets.ingest_capture(con, tmp_path, cid)
    assert projections.pending_capture_ids(con, FILINGS) == [cid]  # still consumable


def test_pre_migration_captures_are_labelled_as_dockets():
    import sqlite3

    raw = sqlite3.connect(":memory:")
    from importlib import resources

    raw.executescript(resources.files("docketyard.store").joinpath("schema.sql").read_text())
    raw.execute(
        "INSERT INTO capture (source_system, endpoint, request_params, response_sha256,"
        " http_status, filter_asserted, ingest_mode, captured_at)"
        " VALUES ('stb-ajax', 'x', '[]', 'abc', 200, 1, 'forward', 'now')"
    )
    raw.commit()
    db.migrate(raw)
    assert projections.pending_capture_ids(raw, DOCKETS) == [1]


# --- document fetching ---------------------------------------------------------------


def fake_fetch(payload: dict[str, bytes]):
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, bytes]:
        calls.append(url)
        return 200, payload[url]

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


def test_fetch_hashes_documents_and_links_provenance(con, tmp_path):
    ingest(con, tmp_path, filing_row())
    url = f"{S3}/830599/311981.pdf"
    stats = documents.fetch_attachments(con, tmp_path, fake_fetch({url: b"%PDF-fake"}))
    assert stats == {"fetched": 1, "unchanged": 0, "new_documents": 1, "replaced": 0, "failed": 0}
    sha, media = con.execute("SELECT document_sha256, media_type FROM document").fetchone()
    assert media == "pdf"  # sniffed from the bytes, not trusted from the URL
    assert con.execute("SELECT document_sha256 FROM filing_attachment").fetchone()[0] == sha
    assert con.execute("SELECT stb_filing_id FROM document_source").fetchone()[0] == "311981"
    assert records.load_blob(tmp_path, sha) == b"%PDF-fake"
    again = documents.fetch_attachments(con, tmp_path, fake_fetch({}))
    assert again["fetched"] == 0
    # fetch captures are consumed by definition — they never appear as pending work,
    # and their verdict counts are "not applicable", not zero
    assert projections.pending_capture_ids(con) == []
    row_count = con.execute(
        "SELECT row_count FROM capture WHERE table_action = ?", (documents.FETCH_ACTION,)
    ).fetchone()[0]
    assert row_count is None


def test_shared_url_is_fetched_once_and_associated_to_every_owner(con, tmp_path):
    # the same document under a docket and its sub-docket (measured)
    ingest(
        con,
        tmp_path,
        filing_row(docket="FD_36873", fid="1") + filing_row(docket="FD_36873_1", fid="2"),
        total=2,
    )
    url = f"{S3}/830599/311981.pdf"
    fetch = fake_fetch({url: b"%PDF-shared"})
    stats = documents.fetch_attachments(con, tmp_path, fetch)
    assert fetch.calls == [url] and stats["fetched"] == 1
    owners = {r[0] for r in con.execute("SELECT stb_filing_id FROM document_source")}
    assert owners == {"1", "2"}
    shas = {r[0] for r in con.execute("SELECT document_sha256 FROM filing_attachment")}
    assert len(shas) == 1 and None not in shas


def test_refresh_detects_errata_and_keeps_the_chain_on_revert(con, tmp_path):
    ingest(con, tmp_path, filing_row())
    url = f"{S3}/830599/311981.pdf"
    fetch = documents.fetch_attachments
    fetch(con, tmp_path, fake_fetch({url: b"original"}))
    assert fetch(con, tmp_path, fake_fetch({url: b"original"}), refresh=True)["unchanged"] == 1
    assert fetch(con, tmp_path, fake_fetch({url: b"replaced"}), refresh=True)["replaced"] == 1
    assert fetch(con, tmp_path, fake_fetch({url: b"original"}), refresh=True)["replaced"] == 1
    chains = con.execute(
        "SELECT COUNT(*) FROM document_source WHERE supersedes_sha256 IS NOT NULL"
    ).fetchone()[0]
    assert chains == 2  # replaced-supersedes-original AND original-supersedes-replaced
    replaced_events = con.execute(
        "SELECT COUNT(*) FROM event WHERE event_type='document_replaced'"
        " AND document_sha256 IS NOT NULL"
    ).fetchone()[0]
    assert replaced_events == 2
    payload = events.latest_payload_by_key(con, "document_replaced", url)
    assert payload["method"] == documents.DETECTION_METHOD


class _FakeResponse(io.BytesIO):
    """An http.client response for tests: status, chunked reads, a context manager, and
    optionally a failure part-way through the body."""

    status = 200

    def __init__(self, body: bytes, fail_after: int | None = None):
        super().__init__(body)
        self.fail_after = fail_after

    def read(self, n=-1):
        if self.fail_after is not None and self.tell() >= self.fail_after:
            raise http.client.IncompleteRead(b"")
        return super().read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_download_streams_to_disk_and_a_streamed_file_is_hashed_in_place(
    con, tmp_path, monkeypatch
):
    """A document never sits in memory whole: the client copies the response to a temp
    file on the blob filesystem by chunks, and the fetcher hashes and moves that file."""
    import tracemalloc

    from docketyard.capture import stb

    body = b"%PDF-big " + bytes(range(256)) * (24 << 10)  # ~6 MB, well above one chunk
    monkeypatch.setattr(stb, "CHUNK", 64 << 10)
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _FakeResponse(body))
    client = stb.StbClient(min_interval=0)
    tracemalloc.start()
    status, path = client.download("https://x/1.pdf", tmp_path)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert status == 200 and path.parent == records.staging_dir(tmp_path)
    assert path.stat().st_size == len(body) and peak < (1 << 20)  # never the whole body
    # the fetcher takes the file: hashed by chunks, moved into the blob store, media sniffed
    ingest(con, tmp_path, filing_row())  # its attachment is {S3}/830599/311981.pdf
    stats = documents.fetch_attachments(con, tmp_path, lambda u: (200, path))
    assert stats == {"fetched": 1, "unchanged": 0, "new_documents": 1, "replaced": 0, "failed": 0}
    sha, size, media = con.execute(
        "SELECT document_sha256, size_bytes, media_type FROM document"
    ).fetchone()
    assert size == len(body) and media == "pdf" and not path.exists()
    assert records.blob_path(tmp_path, sha).stat().st_size == len(body)
    # the same bytes give the same address whichever way they arrive (ADR 0002), and a
    # second download of bytes already held is discarded, not duplicated
    assert records.save_blob(tmp_path, body) == sha
    _, again = client.download("https://x/1.pdf", tmp_path)
    assert records.save_blob(tmp_path, again) == sha and not again.exists()
    # the blob itself is never a victim of its own save
    assert records.save_blob(tmp_path, records.blob_path(tmp_path, sha)) == sha
    assert records.blob_path(tmp_path, sha).exists()


def test_a_body_cut_short_is_retried_and_leaves_no_staging_file(tmp_path, monkeypatch):
    from docketyard.capture import stb

    body = b"%PDF-" + b"x" * (300 << 10)
    attempts = []

    def urlopen(req, timeout=None):
        attempts.append(1)
        # the first two attempts die mid-body; the third completes
        return _FakeResponse(body, fail_after=(100 << 10) if len(attempts) < 3 else None)

    monkeypatch.setattr(stb, "CHUNK", 64 << 10)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    client = stb.StbClient(min_interval=0)
    status, path = client.download("https://x/2.pdf", tmp_path)
    assert status == 200 and len(attempts) == 3 and path.stat().st_size == len(body)
    assert sorted(records.staging_dir(tmp_path).glob("dl-*")) == [path]  # nothing else left
    # a vanished file costs one URL, not the batch; a stale orphan is swept at the start
    orphan = records.staging_dir(tmp_path) / "dl-orphan"
    orphan.write_bytes(b"half")
    os.utime(orphan, (1, 1))
    con = db.connect(":memory:")
    ingest(con, tmp_path, filing_row())
    gone = records.staging_dir(tmp_path) / "dl-gone"
    stats = documents.fetch_attachments(con, tmp_path, lambda u: (200, gone))
    assert stats["failed"] == 1 and stats["fetched"] == 0 and not orphan.exists()


def test_a_refused_answer_is_recorded_not_stored_and_rested_a_week(con, tmp_path):
    """Capture-first still: the refusal is a capture with its status. But it is not a
    document, the attachment stays unfetched, and the host is not asked again for a week
    (the Board's bucket refuses one legacy /MPD/ path forever, measured 2026-08-27)."""
    from docketyard.ingest import observations

    ingest(con, tmp_path, filing_row())
    asked = []

    def refuse(u):
        asked.append(u)
        return (404, b"<html>gone</html>")

    stats = documents.fetch_attachments(con, tmp_path, refuse)
    assert stats["failed"] == 1 and stats["fetched"] == 0 and len(asked) == 1
    assert con.execute("SELECT COUNT(*) FROM document").fetchone()[0] == 0
    status, processed = con.execute(
        "SELECT http_status, processed_at FROM capture WHERE table_action = ?",
        (documents.FETCH_ACTION,),
    ).fetchone()
    assert status == 404 and processed  # on record, and never pending work
    assert observations.attachments(con, unfetched_only=True) == []  # resting
    assert documents.fetch_attachments(con, tmp_path, refuse)["failed"] == 0 and len(asked) == 1
    assert len(observations.attachments(con, unfetched_only=False)) == 1  # a refresh may
    con.execute("UPDATE capture SET captured_at = '2026-01-01T00:00:00+00:00'")
    assert len(observations.attachments(con, unfetched_only=True)) == 1  # a week on: again
    # a 200 with nothing in it is a refusal by another door
    stats = documents.fetch_attachments(con, tmp_path, lambda u: (200, b""))
    assert stats["failed"] == 1
    assert con.execute("SELECT COUNT(*) FROM document").fetchone()[0] == 0


def test_the_client_hands_a_document_hosts_refusal_back_as_the_answer(tmp_path, monkeypatch):
    """A 404/403 from the Board's bucket for one object is an answer to record, not a
    stop; the same code from stb.gov itself is still the WAF diagnosis."""
    import io
    import urllib.error
    import urllib.request

    from docketyard.capture import stb

    def refuse(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 404, "Not Found", {}, io.BytesIO(b"<Error>NoSuchKey</Error>")
        )

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    client = stb.StbClient(min_interval=0)
    status, path = client.download("https://dcms-external.s3.amazonaws.com/x/1.pdf", tmp_path)
    assert status == 404 and path.read_bytes() == b"<Error>NoSuchKey</Error>"
    with pytest.raises(urllib.error.HTTPError):  # the agency's own host: still an error
        client.get("https://www.stb.gov/x")


def test_a_shared_url_keeps_its_chain_and_fills_its_new_owner(con, tmp_path):
    """The same file under a docket and a later sub-docket row: a forward fetch of the new
    row must not restart the errata chain, and an unchanged re-check must still give the
    new row its hash."""
    url = f"{S3}/830599/311981.pdf"
    ingest(con, tmp_path, filing_row())
    assert documents.fetch_attachments(con, tmp_path, fake_fetch({url: b"%PDF-A"}))["fetched"] == 1
    # a second record citing the held file (as a sub-docket entry does)
    ingest(con, tmp_path, filing_row(docket="FD_36873_1", fid="311999"))
    assert (
        con.execute(
            "SELECT COUNT(*) FROM filing_attachment WHERE document_sha256 IS NULL"
        ).fetchone()[0]
        == 1
    )
    # ... the Board replaced the file meanwhile: the forward fetch sees the chain
    stats = documents.fetch_attachments(con, tmp_path, fake_fetch({url: b"%PDF-B"}))
    assert stats["replaced"] == 1
    assert (
        con.execute(
            "SELECT COUNT(*) FROM document_source WHERE supersedes_sha256 IS NOT NULL"
        ).fetchone()[0]
        == 2
    )  # both rows chained from A
    # a third record citing it, unchanged on re-check: it still gets the hash
    ingest(con, tmp_path, filing_row(docket="FD_36873_2", fid="312000"))
    stats = documents.fetch_attachments(con, tmp_path, fake_fetch({url: b"%PDF-B"}), refresh=True)
    assert stats["unchanged"] == 1
    assert (
        con.execute(
            "SELECT COUNT(*) FROM filing_attachment WHERE document_sha256 IS NULL"
        ).fetchone()[0]
        == 0
    )


def test_the_recheck_walks_the_longest_unchecked_first_within_its_bounds(con, tmp_path):
    from docketyard.ingest import observations

    url = f"{S3}/830599/311981.pdf"
    ingest(con, tmp_path, filing_row())
    documents.fetch_attachments(con, tmp_path, fake_fetch({url: b"%PDF-1"}))
    assert observations.recheck_urls(con, limit=10) == [url]  # the operator: any age
    assert observations.recheck_urls(con, limit=10, after_days=30) == []  # the watch: not yet
    con.execute("UPDATE capture SET captured_at = '2026-01-01T00:00:00+00:00'")
    assert observations.recheck_urls(con, limit=10, after_days=30) == [url]
    assert observations.recheck_urls(con, limit=10, after_days=30, max_bytes=3) == []  # too big
    assert observations.held_url_count(con, 3) == 0 and observations.held_url_count(con) == 1

    # a re-check that raises is an attempt on record: the URL goes to the back of the line
    def boom(u):
        raise ConnectionError("reset")

    stats = documents.fetch_attachments(con, tmp_path, boom, refresh=True)
    assert stats["failed"] == 1
    assert (
        con.execute("SELECT http_status FROM capture ORDER BY capture_id DESC LIMIT 1").fetchone()[
            0
        ]
        == 0
    )
    assert observations.recheck_urls(con, limit=10, after_days=30) == []
    assert con.execute("SELECT document_sha256 FROM filing_attachment").fetchone()[0]  # kept
    with pytest.raises(ValueError):
        documents.fetch_attachments(con, tmp_path, boom, refresh=True, observed_in="forward")


def test_limit_zero_fetches_nothing(con, tmp_path):
    ingest(con, tmp_path, filing_row())
    fetch = fake_fetch({})
    stats = documents.fetch_attachments(con, tmp_path, fetch, limit=0)
    assert stats["fetched"] == 0 and fetch.calls == []


def test_media_type_sniffing():
    assert documents.media_type_for(f"{S3}/1/lies.pdf", b"PK\x03\x04zip") == "zip"
    assert documents.media_type_for(f"{S3}/1/a.xlsx", b"PK\x03\x04") == "xlsx"
    assert documents.media_type_for(f"{S3}/1/noext", b"%PDF-1.7") == "pdf"
    assert documents.media_type_for(f"{S3}/1/mystery", b"???") is None
