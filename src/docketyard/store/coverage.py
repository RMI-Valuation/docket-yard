"""What the record covers, measured from the store — never typed by hand (coverage.md).

Every number on the public coverage page comes from here, so the page cannot claim more
than the ledger holds. Forward and backfill are reported separately because they mean
different things: forward is the promise (watched continuously since a date); backfill is
whatever has been walked so far.
"""

from dataclasses import dataclass
from sqlite3 import Connection

from docketyard.capture.stb import DECISIONS, DOCKETS, EXPECTED_EMPTY_PREFIXES, FILINGS


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
    documents: int
    attachments_unfetched: int
    earliest_filed: str | None  # among forward-observed filings
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
        documents=one("SELECT COUNT(*) FROM document"),
        attachments_unfetched=one(
            "SELECT (SELECT COUNT(*) FROM filing_attachment WHERE document_sha256 IS NULL)"
            " + (SELECT COUNT(*) FROM decision_attachment WHERE document_sha256 IS NULL)"
        ),
        earliest_filed=one(
            "SELECT MIN(f.filed_date) FROM filing f"
            " JOIN event e ON e.event_id = f.observed_in_event"
            " JOIN capture c ON c.capture_id = e.capture_id WHERE c.ingest_mode = 'forward'"
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
                    for r in q(
                        "SELECT slice_key FROM walk_slice WHERE table_action IN (?, ?)"
                        " AND status NOT IN ('done', 'empty')",
                        (FILINGS, DECISIONS),
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
