"""Migration 0011: the environmental-comment record row.

The schema half of the milestone (docs/schema-draft.md § 5). What is pinned here is what
the schema-critic's two reports and the 2026-08-31 row measurement settled:

- the key is the comment number, because it is the only identity the source corroborates;
- the record is published in full, snapshot included, with no name masked — a commenter
  filed on a public docket, and ADR 0011's posture is about this site's readers rather
  than the people who choose to file;
- a document can name a comment as its owner, so an erratum on a comment's file is
  attributable.
"""

import gzip
import sqlite3
from datetime import date

import pytest

from docketyard.store import db, dump, events
from tests.test_web import build_store


def _docket(con) -> int:
    return con.execute("SELECT docket_id FROM docket LIMIT 1").fetchone()[0]


def _capture(con) -> int:
    """One capture per observation, as a page fetch is: the ledger's dedup index is
    (capture_id, event_type, source_key), so sharing one would suppress the second event."""
    cur = con.execute(
        "INSERT INTO capture (source_system, endpoint, request_params, response_sha256,"
        " http_status, filter_asserted, ingest_mode, captured_at, table_action)"
        " VALUES ('stb-ajax', 'https://example.invalid', '[]', 'x', 200, 1, 'forward', ?,"
        " 'stb_hook_table_environmental_comments')",
        (db.utcnow(),),
    )
    return cur.lastrowid


def _comment(con, docket_id, number="EI-34280", **overrides):
    """One comment: the event first, then the row that mirrors it — the order ingest uses."""
    capture_id = _capture(con)
    payload = {
        "date": "2026-08-25",
        "date_printed": "8/25/2026",
        "attachments": ["https://example.invalid/EI-34280.pdf"],
        "submitter": "David Gertsch",
        "organisation": "Albany County Planning Department",
        "location": "Laramie, WY",
        "comment_text": "The Casper Aquifer provides 50% of the water to City of Laramie.",
    }
    event_id = events.append(
        con,
        event_type="enviro_comment_observed",
        capture_id=capture_id,
        docket_id=docket_id,
        occurred_at="2026-08-25",
        payload=payload,
        source_key=f"D{docket_id}|{number}",
    )
    columns = {
        "docket_id": docket_id,
        "comment_number": number,
        "stb_row_ref": "203738",
        "date_received_or_sent": "2026-08-25",
        "submitter_raw": payload["submitter"],
        "organisation_raw": payload["organisation"],
        "location_raw": payload["location"],
        "comment_text_printed": payload["comment_text"],
        "observed_in_event": event_id,
        **overrides,
    }
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    cur = con.execute(
        f"INSERT INTO enviro_comment ({names}) VALUES ({marks})", tuple(columns.values())
    )
    con.commit()
    return cur.lastrowid


def test_the_key_is_the_comment_number_and_is_unique_per_docket(tmp_path):
    con = db.connect(build_store(tmp_path))
    docket_id = _docket(con)
    _comment(con, docket_id)
    with pytest.raises(sqlite3.IntegrityError):
        _comment(con, docket_id)  # the same number, the same docket
    # measured: a comment number never repeats across dockets, but the schema keys on the
    # pair, so the same number under a different docket is a different record, not a clash
    other = con.execute(
        "INSERT INTO docket (raw_docket, prefix, sequence) VALUES ('AB_55', 'AB', 55)"
    ).lastrowid
    assert _comment(con, other) is not None
    con.close()


def test_a_document_source_can_name_a_comment_as_its_owner(tmp_path):
    """Without this column the fetcher writes null into both id columns for every comment
    PDF, the identity index folds them into one anonymous row, and a document_replaced
    alert can only say 'a record it holds (not identified)'."""
    con = db.connect(build_store(tmp_path))
    capture_id = con.execute("SELECT capture_id FROM capture LIMIT 1").fetchone()[0]
    sha, at = "a" * 64, "2026-08-31T00:00:00+00:00"
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, first_seen_at) VALUES (?, 10, ?)",
        (sha, at),
    )
    args = (sha, "https://example.invalid/EI-34280.pdf", capture_id, at)
    con.execute(
        "INSERT INTO document_source (document_sha256, source_url, comment_source_key,"
        " capture_id, observed_at) VALUES (?, ?, 'FD_36873_0|EI-34280', ?, ?)",
        args,
    )
    # the same bytes at the same URL, owned by a filing, is a DIFFERENT association
    con.execute(
        "INSERT INTO document_source (document_sha256, source_url, stb_filing_id,"
        " capture_id, observed_at) VALUES (?, ?, '311981', ?, ?)",
        args,
    )
    with pytest.raises(sqlite3.IntegrityError):  # but the same one twice is not
        con.execute(
            "INSERT INTO document_source (document_sha256, source_url, comment_source_key,"
            " capture_id, observed_at) VALUES (?, ?, 'FD_36873_0|EI-34280', ?, ?)",
            args,
        )
    con.close()


def test_the_snapshot_publishes_the_comment_record_in_full(tmp_path):
    """The record is public and goes out whole: the words, the submitter, the organisation
    and the location. Nothing here is masked or held back, and `enviro_comment` must be on
    the snapshot's table allowlist or `dump` refuses to build at all."""
    path = build_store(tmp_path)
    con = db.connect(path)
    _comment(con, _docket(con))
    con.close()

    m = dump.dump(path, tmp_path / "public", today=date(2026, 9, 1))
    assert m.counts["environmental_comments"] == 1

    plain = tmp_path / "snapshot.sqlite"
    plain.write_bytes(gzip.decompress((tmp_path / "public" / dump.LATEST).read_bytes()))
    out = sqlite3.connect(plain)
    text, submitter, org, location = out.execute(
        "SELECT comment_text_printed, submitter_raw, organisation_raw, location_raw"
        " FROM enviro_comment"
    ).fetchone()
    assert "Casper Aquifer" in text and submitter == "David Gertsch"
    assert org == "Albany County Planning Department" and location == "Laramie, WY"
    # and the ledger the snapshot carries is untouched: no redaction pass exists
    payload = out.execute(
        "SELECT payload FROM event WHERE event_type = 'enviro_comment_observed'"
    ).fetchone()[0]
    assert "Gertsch" in payload
    out.close()
