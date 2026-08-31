"""What the record covers, measured from the store — never typed by hand (coverage.md).

Every number on the public coverage page comes from here, so the page cannot claim more
than the ledger holds. Forward and backfill are reported separately because they mean
different things: forward is the promise (watched continuously since a date); backfill is
whatever has been walked so far.
"""

from dataclasses import dataclass
from sqlite3 import Connection

from docketyard.capture.stb import (
    DECISIONS,
    DOCKETS,
    ENVIRO_COMMENTS,
    EXPECTED_EMPTY_PREFIXES,
    FILINGS,
)
from docketyard.ingest import observations


@dataclass(frozen=True)
class Gap:
    started_at: str
    ended_at: str | None
    failure: str
    note: str | None


@dataclass(frozen=True)
class Coverage:
    dockets: int
    registry_walked_at: str | None  # the dockets-table backfill: when it completed
    forward_since: str | None  # first forward filings/decisions capture
    last_checked: str | None  # newest forward table capture
    filings: int
    decisions: int
    comments: int
    documents: int
    attachments_unfetched: int
    earliest_filed: str | None  # among forward-observed filings
    record_from: str | None  # earliest Board date in the whole record, any wave
    record_to: str | None  # latest
    earliest_served: str | None
    backfill_from: str | None  # earliest filed/served date observed by a backfill wave
    backfill_filings: int  # records first observed by a wave
    backfill_decisions: int
    backfill_incomplete: tuple[str, ...]  # month slices a wave has not finished
    empty_prefixes: tuple[str, ...]
    gaps: list[Gap]


def coverage(con: Connection) -> Coverage:
    q = con.execute
    one = lambda sql, *p: q(sql, p).fetchone()[0]  # noqa: E731
    return Coverage(
        dockets=one("SELECT COUNT(*) FROM docket"),
        registry_walked_at=one(
            "SELECT MAX(captured_at) FROM capture WHERE ingest_mode = 'backfill'"
            " AND table_action = ?",
            DOCKETS,
        ),
        forward_since=one(
            "SELECT MIN(captured_at) FROM capture WHERE ingest_mode = 'forward'"
            " AND filter_asserted = 1 AND table_action IN (?, ?)",
            FILINGS,
            DECISIONS,
        ),
        last_checked=one(
            "SELECT MAX(captured_at) FROM capture WHERE ingest_mode = 'forward'"
            " AND filter_asserted = 1 AND table_action IN (?, ?)",
            FILINGS,
            DECISIONS,
        ),
        filings=one("SELECT COUNT(DISTINCT stb_filing_id) FROM filing"),
        decisions=one("SELECT COUNT(DISTINCT stb_decision_id) FROM decision_record"),
        # by (number, row ref), NOT the number alone: the row ref folds one comment
        # entered in a docket and its sub-docket, while keeping the two numbers the Board
        # gave to two DIFFERENT comments apart (measured, the archive wave)
        comments=one(
            "SELECT COUNT(*) FROM (SELECT 1 FROM enviro_comment"
            " GROUP BY comment_number, COALESCE(stb_row_ref, ''))"
        ),
        documents=one("SELECT COUNT(*) FROM document"),
        # derived from SPECS, like the held-URL union: this is the PUBLISHED backlog, so
        # a table left out of it hides its own backlog on the page that exists to show it
        attachments_unfetched=one(
            "SELECT "
            + " + ".join(
                f"(SELECT COUNT(*) FROM {spec.attachment_table} WHERE document_sha256 IS NULL)"
                for spec in observations.SPECS.values()
            )
        ),
        earliest_filed=one(
            "SELECT MIN(f.filed_date) FROM filing f"
            " JOIN event e ON e.event_id = f.observed_in_event"
            " JOIN capture c ON c.capture_id = e.capture_id WHERE c.ingest_mode = 'forward'"
        ),
        # over every record table: after a comments wave the span reaches back decades
        # further than filings and decisions do, and a published span that omitted it
        # would understate what the record actually holds
        record_from=one(
            "SELECT MIN(d) FROM (SELECT MIN(NULLIF(filed_date, '')) AS d FROM filing"
            " UNION ALL SELECT MIN(NULLIF(service_date, '')) FROM decision_record"
            " UNION ALL SELECT MIN(NULLIF(date_received_or_sent, '')) FROM enviro_comment)"
        ),
        record_to=one(
            "SELECT MAX(d) FROM (SELECT MAX(NULLIF(filed_date, '')) AS d FROM filing"
            " UNION ALL SELECT MAX(NULLIF(service_date, '')) FROM decision_record"
            " UNION ALL SELECT MAX(NULLIF(date_received_or_sent, '')) FROM enviro_comment)"
        ),
        earliest_served=one(
            "SELECT MIN(r.service_date) FROM decision_record r"
            " JOIN event e ON e.event_id = r.observed_in_event"
            " JOIN capture c ON c.capture_id = e.capture_id WHERE c.ingest_mode = 'forward'"
        ),
        backfill_from=one(
            "SELECT MIN(d) FROM (SELECT f.filed_date AS d FROM filing f"
            " JOIN event e ON e.event_id = f.observed_in_event"
            " JOIN capture c ON c.capture_id = e.capture_id WHERE c.ingest_mode = 'backfill'"
            " UNION ALL SELECT r.service_date FROM decision_record r"
            " JOIN event e ON e.event_id = r.observed_in_event"
            " JOIN capture c ON c.capture_id = e.capture_id WHERE c.ingest_mode = 'backfill')"
        ),
        backfill_filings=one(
            "SELECT COUNT(*) FROM filing f JOIN event e ON e.event_id = f.observed_in_event"
            " JOIN capture c ON c.capture_id = e.capture_id WHERE c.ingest_mode = 'backfill'"
        ),
        backfill_decisions=one(
            "SELECT COUNT(*) FROM decision_record r"
            " JOIN event e ON e.event_id = r.observed_in_event"
            " JOIN capture c ON c.capture_id = e.capture_id WHERE c.ingest_mode = 'backfill'"
        ),
        backfill_incomplete=tuple(
            sorted(
                {
                    r[0].split(":", 1)[1][:7]
                    # every walked record table: a comment month a wave has not finished
                    # is as unfinished as a filings month, and the page exists to say so
                    for r in q(
                        "SELECT slice_key FROM walk_slice WHERE table_action IN (?, ?, ?)"
                        " AND status NOT IN ('done', 'empty')",
                        (FILINGS, DECISIONS, ENVIRO_COMMENTS),
                    )
                }
            )
        ),
        empty_prefixes=tuple(sorted(EXPECTED_EMPTY_PREFIXES)),
        gaps=[
            Gap(*row)
            for row in q(
                "SELECT started_at, ended_at, failure, note FROM coverage_gap"
                " ORDER BY started_at DESC"
            )
        ],
    )
