"""The forward poller: one pass over the recent window, on a timer in production.

Each pass captures the filings and decisions tables for the trailing window, ingests every
asserted capture, and fetches attachments not yet in the blob store. Captures are
idempotent to ingest, so a window that overlaps the last pass costs requests, not
correctness — and the overlap is what catches a record the Board back-dates into a day
already polled. The window is a week: wide enough that a genuinely empty result is
implausible at the agency's rate (~60 records a week), which is what lets the no-results
envelope on page 1 be treated as the trap it usually is (`stb-data-source.md`).

Each pass starts by scraping fresh nonces: WordPress rotates them on a 12–24 hour clock and
the client would otherwise carry a dead one for the life of the container.
"""

import time
from datetime import date, timedelta
from sqlite3 import Connection

from docketyard.capture import documents, walk
from docketyard.capture.stb import DECISIONS, FILINGS
from docketyard.ingest import observations
from docketyard.parties import resolve
from docketyard.store import projections

WINDOW_DAYS = 7
MIN_WINDOW_DAYS = 3  # below this a quiet weekend makes the page-1 envelope a false alarm
PAGES = 20  # 1,000 rows: an order of magnitude over a week's activity; loud if ever hit
FETCH_LIMIT = 200  # ~7 minutes at the polite interval: a backlog drains across passes


def window(today: date, days: int = WINDOW_DAYS) -> tuple[str, str]:
    """The trailing window as the endpoint spells dates: MM/DD/YYYY, inclusive."""
    start = today - timedelta(days=days - 1)
    return start.strftime("%m/%d/%Y"), today.strftime("%m/%d/%Y")


def _describe(result: walk.SliceResult) -> str:
    """Which trap fired, in the log line, so the store need not be opened to know."""
    notes = [result.status]
    if result.envelope_on_first_page:
        notes.append("TRAP: no-results envelope on page 1 (criteria, sort or nonce)")
    elif result.quarantined:
        notes.append("a page failed its filter assertion")
    if result.capped:
        notes.append("display cap reported")
    if result.status == "partial" and not result.quarantined and not result.capped:
        notes.append(f"page limit {PAGES} reached before the end")
    return f"{'; '.join(notes)} ({result.rows} rows in {result.captures} captures)"


def _ingest_pending(con: Connection, data_dir, action: str, problems: list[str]) -> dict:
    """Every asserted, unprocessed capture of one table. Rows dropped at parse are a
    problem — the raw is retained, but a record is missing from its sheet."""
    counts: dict = {}
    for capture_id in projections.pending_capture_ids(con, action):
        try:
            stats = observations.ingest_capture(con, data_dir, capture_id)
        except Exception as e:  # noqa: BLE001 — one bad capture must not strand the pass
            con.rollback()
            problems.append(f"capture {capture_id}: {type(e).__name__}: {e}")
            continue
        dropped = stats.get("unparsed", 0) + stats.get("markup_skipped", 0)
        if dropped:
            problems.append(f"capture {capture_id}: {dropped} rows dropped at parse; raw retained")
        for key, value in stats.items():
            if isinstance(value, int):
                counts[key] = counts.get(key, 0) + value
    return counts


def forward_pass(
    con: Connection,
    client,
    data_dir,
    *,
    today=None,
    days=WINDOW_DAYS,
    fetch_limit=FETCH_LIMIT,
    alerts=None,  # callable run after the pass: sweep, build and deliver alerts
    log=print,
):
    """Capture, ingest, fetch. Every failure lands in the summary's `problems`; nothing a
    bad page or a dead endpoint can cause escapes, so one table's outage never costs the
    other table or the attachment fetch."""
    if days < MIN_WINDOW_DAYS:
        raise ValueError(f"window must be at least {MIN_WINDOW_DAYS} days (see module doc)")
    start, end = window(today or date.today(), days)
    summary: dict = {"window": (start, end), "captured": {}, "ingested": {}, "problems": []}
    try:
        client.refresh_nonces()
        online = True
    except Exception as e:  # noqa: BLE001 — the search page itself is unreachable
        online = False
        summary["problems"].append(f"nonce refresh failed ({type(e).__name__}: {e})")
    for action in (FILINGS, DECISIONS):
        spec = observations.SPECS[action]
        criteria = [(spec.date_criteria[0], start), (spec.date_criteria[1], end)]
        if not online:
            summary["captured"][action] = "skipped"
        else:
            try:
                result = walk.capture_slice(
                    con,
                    client,
                    action,
                    criteria,
                    data_dir=data_dir,
                    pages=PAGES,
                    mode="forward",
                    log=log,
                )
            except Exception as e:  # noqa: BLE001 — transport failure after the client's retries
                con.rollback()
                summary["captured"][action] = "failed"
                summary["problems"].append(f"{action}: capture failed ({type(e).__name__}: {e})")
            else:
                summary["captured"][action] = result.status
                if result.status != "done":
                    summary["problems"].append(f"{action}: {_describe(result)}")
        # ingest needs no network: whatever an earlier pass left asserted-but-pending is
        # consumed even while the endpoint is down
        summary["ingested"][action] = _ingest_pending(con, data_dir, action, summary["problems"])
    try:
        summary["parties"] = resolve.run(con, log=lambda _: None)
    except Exception as e:  # noqa: BLE001 — a resolution bug must not cost the capture
        con.rollback()
        summary["problems"].append(f"party resolution failed ({type(e).__name__}: {e})")
    try:
        fetched = documents.fetch_attachments(
            con,
            data_dir,
            client.fetcher(data_dir),
            limit=fetch_limit,
            ingest_mode="forward",
            observed_in="forward",  # the watch's own files first; a wave fetches its own
        )
    except Exception as e:  # noqa: BLE001
        con.rollback()
        fetched = {"failed": -1}
        summary["problems"].append(f"attachment fetch aborted ({type(e).__name__}: {e})")
    summary["fetched"] = fetched
    if fetched.get("failed"):
        summary["problems"].append(f"attachments failed: {fetched['failed']}")
    if alerts is not None:
        try:
            summary["alerts"] = alerts()
        except Exception as e:  # noqa: BLE001 — delivery must never cost the next capture
            con.rollback()
            summary["problems"].append(f"alerts failed ({type(e).__name__}: {e})")
    log(f"poll {start}..{end}: {summary}")
    return summary


def run_forever(make_pass, every: float, log=print) -> None:
    """Call make_pass, sleep, repeat. A pass that raises is logged (as ABORTED, distinct
    from a pass's own summary line) and the loop continues: a bug in one pass must not stop
    the poller, and the off-box heartbeat is what notices a poller that keeps failing
    (architecture.md)."""
    while True:
        started = time.monotonic()
        try:
            make_pass()
        except Exception as e:  # noqa: BLE001
            log(f"pass ABORTED ({type(e).__name__}: {e})")
        time.sleep(max(0.0, every - (time.monotonic() - started)))
