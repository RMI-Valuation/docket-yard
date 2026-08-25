"""Read-side queries derived from the ledger. Nothing here is a source of truth."""

from sqlite3 import Connection

from docketyard.capture.stb import DISPLAY_CAP
from docketyard.store.db import load_json


def docket_count(con: Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM docket").fetchone()[0]


def pending_capture_ids(con: Connection, table_action: str | None = None) -> list[int]:
    """The one definition of 'pending': asserted and not yet consumed by ingest."""
    sql = "SELECT capture_id FROM capture WHERE processed_at IS NULL AND filter_asserted = 1"
    params: tuple = ()
    if table_action is not None:
        sql += " AND table_action = ?"
        params = (table_action,)
    return [row[0] for row in con.execute(sql + " ORDER BY capture_id", params)]


def docket_titles(con: Connection, limit: int = 20) -> list[tuple[str, str | None]]:
    rows = con.execute(
        "SELECT raw_docket, latest_payload FROM docket_current ORDER BY prefix, sequence,"
        " COALESCE(sub_sequence, -1) LIMIT ?",
        (limit,),
    ).fetchall()
    return [(raw, load_json(p)["title"] if p else None) for raw, p in rows]


def status(con: Connection) -> dict:
    q = con.execute
    return {
        "captures": q("SELECT COUNT(*) FROM capture").fetchone()[0],
        "captures_unprocessed": len(pending_capture_ids(con)),
        "captures_quarantined": q(
            "SELECT COUNT(*) FROM capture WHERE filter_asserted = 0"
        ).fetchone()[0],
        "captures_capped": q(
            "SELECT COUNT(*) FROM capture WHERE reported_total >= ?", (DISPLAY_CAP,)
        ).fetchone()[0],
        "dockets": docket_count(con),
        "filings": q("SELECT COUNT(*) FROM filing").fetchone()[0],
        "decisions": q("SELECT COUNT(*) FROM decision_record").fetchone()[0],
        "documents": q("SELECT COUNT(*) FROM document").fetchone()[0],
        "attachments_unfetched": q(
            "SELECT (SELECT COUNT(*) FROM filing_attachment WHERE document_sha256 IS NULL)"
            " + (SELECT COUNT(*) FROM decision_attachment WHERE document_sha256 IS NULL)"
        ).fetchone()[0],
        "events": q("SELECT COUNT(*) FROM event").fetchone()[0],
    }
