"""A backfill wave: the record tables over a date range, then their documents.

Everything a wave does is stamped `backfill`, so nothing it observes can ever alert
(schema-draft.md § 6, break B6). Every step is resumable from the store alone: month slices
already `done` are skipped (walk_slice), captures already ingested are not re-read
(processed_at), documents already held are not re-fetched (content hash). Running a wave
twice is a no-op plus a few requests. It is meant to run on the instance beside the poller,
politely — the record it builds is the one the poller keeps.

The wave stops at the day the forward watch began: from there on the poller has been
keeping the record, and re-walking that window would only spend requests.
"""

from datetime import date
from sqlite3 import Connection

from docketyard.capture import documents, walk
from docketyard.capture.stb import DECISIONS, FILINGS
from docketyard.ingest import observations
from docketyard.parties import resolve
from docketyard.store import projections


def forward_since(con: Connection) -> date | None:
    """The first day the poller's window covered, from the earliest forward table capture."""
    row = con.execute(
        "SELECT MIN(captured_at) FROM capture WHERE ingest_mode = 'forward'"
        " AND filter_asserted = 1 AND table_action IN (?, ?)",
        (FILINGS, DECISIONS),
    ).fetchone()
    return date.fromisoformat(row[0][:10]) if row and row[0] else None


def ingest_pending(con: Connection, data_dir, action: str, log=print) -> dict:
    counts: dict = {"captures": 0, "failed": 0}
    for capture_id in projections.pending_capture_ids(con, action):
        try:
            observations.ingest_capture(con, data_dir, capture_id)
            counts["captures"] += 1
        except Exception as e:  # noqa: BLE001 — one bad capture must not strand the wave
            con.rollback()
            counts["failed"] += 1
            log(f"capture {capture_id}: FAILED ({type(e).__name__}: {e})")
    return counts


def wave(
    con: Connection,
    client,
    data_dir,
    start: date,
    end: date | None = None,
    *,
    fetch_limit: int | None = None,
    log=print,
) -> dict:
    """Walk both tables month by month, ingest, then fetch what is not yet held."""
    end = end or forward_since(con) or date.today()
    summary: dict = {"range": (start.isoformat(), end.isoformat())}
    for action in (FILINGS, DECISIONS):
        log(f"=== {action} {start} .. {end}")
        summary[action] = walk.walk_observations(
            con, client, action, start, end, data_dir=data_dir, log=log
        )
        summary[f"{action}:ingest"] = ingest_pending(con, data_dir, action, log)
    try:
        summary["parties"] = resolve.run(con, log)
    except Exception as e:  # noqa: BLE001 — resolution must not cost the documents
        con.rollback()
        summary["parties"] = f"FAILED ({type(e).__name__}: {e})"
        log(f"parties: {summary['parties']}")
    log("=== documents")
    summary["documents"] = documents.fetch_attachments(
        con,
        data_dir,
        lambda url: client.download(url, data_dir),
        limit=fetch_limit,
        ingest_mode="backfill",
    )
    log(f"wave {summary}")
    return summary
