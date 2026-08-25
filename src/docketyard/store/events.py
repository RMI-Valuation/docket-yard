"""Append-only writes to the event ledger.

Events are never updated or deleted. Dedup within a capture is structural (the unique index
on capture/type/source_key); dedup across captures is the caller's change-detection against
the latest observation, so an unchanged row re-observed daily does not flood the ledger.
"""

from sqlite3 import Connection

from docketyard.store.db import dump_json, load_json, utcnow

PAYLOAD_VERSION = 1


def append(
    con: Connection,
    *,
    event_type: str,
    capture_id: int,
    payload: dict,
    source_key: str,
    docket_id: int | None = None,
    occurred_at: str | None = None,
) -> int | None:
    """Append one event; returns its id, or None if this capture already recorded it."""
    cur = con.execute(
        """
        INSERT OR IGNORE INTO event
            (event_type, docket_id, occurred_at, recorded_at, capture_id, source_key,
             payload, payload_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_type,
            docket_id,
            occurred_at,
            utcnow(),
            capture_id,
            source_key,
            dump_json(payload),
            PAYLOAD_VERSION,
        ),
    )
    return cur.lastrowid if cur.rowcount else None


def latest_payload(con: Connection, event_type: str, docket_id: int) -> dict | None:
    row = con.execute(
        """
        SELECT payload FROM event
         WHERE docket_id = ? AND event_type = ?
         ORDER BY event_id DESC LIMIT 1
        """,
        (docket_id, event_type),
    ).fetchone()
    return load_json(row[0]) if row else None
