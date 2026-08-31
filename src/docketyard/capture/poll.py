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
from datetime import UTC, date, datetime, timedelta
from sqlite3 import Connection

from docketyard.capture import documents, walk
from docketyard.capture.stb import DECISIONS, DOCKETS, FILINGS
from docketyard.ingest import dockets, observations
from docketyard.parties import resolve
from docketyard.store import projections, search
from docketyard.store.db import load_json

WINDOW_DAYS = 7
MIN_WINDOW_DAYS = 3  # below this a quiet weekend makes the page-1 envelope a false alarm
PAGES = 20  # 1,000 rows: an order of magnitude over a week's activity; loud if ever hit
FETCH_LIMIT = 200  # ~7 minutes at the polite interval: a backlog drains across passes
RECHECK_BUDGET_SECONDS = 300  # a hung document host must not hold the next forward pass
RECHECK_LIMIT = 40  # held files re-fetched per pass, oldest-checked first: ~1,900 a day,
# the whole record (~78k files) about every six weeks; a replaced file is an erratum event


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
    problem — the raw is retained, but a record is missing from its sheet.

    The dockets table has its own parser: it carries the registry, not observations."""
    parse = dockets.ingest_capture if action == DOCKETS else observations.ingest_capture
    counts: dict = {}
    for capture_id in projections.pending_capture_ids(con, action):
        try:
            stats = parse(con, data_dir, capture_id)
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


# The caption refresh, bounded three ways: how many dockets a pass asks about, how recent
# a record must be for its docket to be worth asking, and how many times one docket may be
# asked before the record concludes the Board does not publish it. Measured on production
# 2026-08-31: 3 dockets of 5,076 with records lacked a caption, all opened within 3 days.
CAPTION_LOOKUPS = 10
CAPTION_WINDOW_DAYS = 45
CAPTION_ATTEMPTS = 8  # ~4 hours of passes; then it is reported, not asked again
CAPTION_RETRY_HOURS = 6  # one ask per docket per this many hours, whatever the pass rate


def _caption_asks(con: Connection) -> dict[tuple[str, int, int | None], tuple[int, str]]:
    """How often each docket has been asked about, and when last, read from the capture
    ledger — the same trick the errata re-check uses, so this costs no schema change.

    A caption ask is the only forward DOCKETS capture the poller makes, and its criteria
    are recorded on the capture row, so the ledger already answers "did we ask, and when".
    """
    out: dict[tuple[str, int, int | None], tuple[int, str]] = {}
    for params, captured_at in con.execute(
        "SELECT request_params, captured_at FROM capture"
        " WHERE table_action = ? AND ingest_mode = 'forward' ORDER BY captured_at",
        (DOCKETS,),
    ):
        # the capture records the POST fields as the endpoint takes them —
        # `search-criteria[i][name]` and `[value]`, never (name, value) pairs — so the
        # criteria are reassembled by index (code review, 2026-08-31)
        names: dict[str, str] = {}
        values: dict[str, str] = {}
        for field, value in load_json(params) or []:
            if field.startswith("search-criteria["):
                index, part = field[len("search-criteria[") :].split("][", 1)
                (names if part.startswith("name") else values)[index] = value
        criteria = {names[i]: values[i] for i in names if i in values}
        prefix = criteria.get("docketNum_one")
        sequence = criteria.get("docketNum_two")
        if not prefix or not sequence:
            continue
        third = criteria.get("docketNum_three")
        key = (prefix, int(sequence), int(third) if third else None)
        seen = out.get(key)
        out[key] = ((seen[0] if seen else 0) + 1, captured_at)
    return out


def _uncaptioned(con: Connection, today: date) -> list[tuple[int, str, int, int | None]]:
    """(docket_id, prefix, sequence, sub_sequence) for proceedings the record holds records
    FOR but has never seen in the Board's own dockets table, newest activity first.

    A new proceeding reaches the filings table before the dockets table, so its docket row
    is minted from the filing (`docket_inferred`) and carries no caption: the operator
    found `AB 290 (Sub-No. 423X)`, `FD 36951` and `AB 55 (Sub-No. 827X)` reading
    "(caption not yet observed)" on the home page, three days after they opened.

    Only dockets holding a record of their own are asked about, so the ~2,400 parents
    minted for sub-dockets (`AB_1_0`, implied by `AB_1_6`) — which the Board never prints
    and which hold nothing — are never asked about at all.
    """
    since = (today - timedelta(days=CAPTION_WINDOW_DAYS)).isoformat()
    return [
        (docket_id, prefix, sequence, sub_sequence)
        for docket_id, prefix, sequence, sub_sequence, _ in con.execute(
            """
            SELECT d.docket_id, d.prefix, d.sequence, d.sub_sequence, MAX(x.happened) AS newest
              FROM docket d
              JOIN docket_current dc ON dc.docket_id = d.docket_id
              JOIN (SELECT docket_id, filed_date AS happened FROM filing
                    UNION ALL SELECT docket_id, service_date FROM decision_record) x
                ON x.docket_id = d.docket_id
             WHERE dc.latest_payload IS NULL
               AND x.happened >= ?
               AND EXISTS (SELECT 1 FROM event e
                            WHERE e.docket_id = d.docket_id AND e.event_type = 'docket_inferred')
             GROUP BY d.docket_id
             ORDER BY newest DESC, d.docket_id DESC
            """,
            (since,),
        )
    ]


def _captioned_ids(con: Connection) -> set[int]:
    return {
        r[0]
        for r in con.execute(
            "SELECT docket_id FROM docket_current WHERE latest_payload IS NOT NULL"
        )
    }


def _fill_captions(
    con: Connection, client, data_dir, *, online: bool, problems: list[str], today: date, log
) -> dict:
    """Ask the Board's dockets table about each uncaptioned docket — ONE row, one request.

    The registry was walked once (627 requests, `docs/stb-data-source.md`) and nothing
    refreshed it, so a proceeding opened after that walk never gained its caption. The
    criteria name the docket itself, never its family: `docketNum_three` is the
    sub-sequence, measured against the live endpoint 2026-08-31, and asking `AB 290` by
    family answers 392 rows where asking `AB 290 (Sub-No. 423)` answers 1. Asking by
    family would have cost 20 requests every half hour for `AB 55` alone, and its
    thousand-row family would not even have reached the docket in question
    (stb-ingest-specialist, 2026-08-31).
    """
    out: dict = {"asked": 0, "answered": 0, "captioned": 0, "exhausted": []}
    if not online:
        return out
    wanted = _uncaptioned(con, today)
    if not wanted:
        return out
    asks = _caption_asks(con)
    cutoff = (datetime.now(UTC) - timedelta(hours=CAPTION_RETRY_HOURS)).isoformat(
        timespec="seconds"
    )
    due = []
    for docket_id, prefix, sequence, sub_sequence in wanted:
        attempts, last = asks.get((prefix, sequence, sub_sequence), (0, ""))
        if attempts >= CAPTION_ATTEMPTS:
            out["exhausted"].append(
                f"{prefix} {sequence}" + (f" ({sub_sequence})" if sub_sequence else "")
            )
            continue
        if last and last > cutoff:  # asked recently: the Board publishes on its own clock
            continue
        due.append((docket_id, prefix, sequence, sub_sequence))
    if out["exhausted"]:
        problems.append(
            f"captions: {len(out['exhausted'])} dockets asked about {CAPTION_ATTEMPTS} times"
            f" with no row returned, and no longer asked: {', '.join(out['exhausted'][:5])}"
        )
    if len(due) > CAPTION_LOOKUPS:
        problems.append(f"captions: {len(due)} due, asking about {CAPTION_LOOKUPS} this pass")
        due = due[:CAPTION_LOOKUPS]
    for _docket_id, prefix, sequence, sub_sequence in due:
        criteria = [("docketNum_one", prefix), ("docketNum_two", str(sequence))]
        if sub_sequence is not None:
            criteria.append(("docketNum_three", str(sub_sequence)))
        out["asked"] += 1
        try:
            result = walk.capture_slice(
                con,
                client,
                DOCKETS,
                criteria,
                data_dir=data_dir,
                pages=1,  # one docket is one row; more than a page means the filter slipped
                mode="forward",
                # The one query whose empty answer is the answer: the Board may not have
                # published a docket row for this proceeding yet, which is why its caption
                # is missing. What that hides is narrow — a dead nonce answers `0` or 403
                # and an ignored filter answers rows that fail the per-row criteria check,
                # both of which stay loud — so only the envelope itself is read as benign,
                # and CAPTION_ATTEMPTS turns a permanently empty answer into a problem
                # rather than silence (stb-ingest-specialist, 2026-08-31).
                expected_empty=True,
                log=log,
            )
        except Exception as e:  # noqa: BLE001 — a caption is never worth failing a pass
            con.rollback()
            problems.append(
                f"caption {prefix} {sequence}: capture failed ({type(e).__name__}: {e})"
            )
            continue
        if result.status in ("done", "empty"):
            out["answered"] += 1
        else:
            problems.append(f"caption {prefix} {sequence}: {_describe(result)}")
    asked_ids = [d for d, _, _, _ in due]
    return out | {"wanted": len(wanted), "captioned_ids": asked_ids}


def forward_pass(
    con: Connection,
    client,
    data_dir,
    *,
    today=None,
    days=WINDOW_DAYS,
    fetch_limit=FETCH_LIMIT,
    recheck_limit=RECHECK_LIMIT,
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
    # a proceeding reaches the filings table before the dockets table, so ask about the
    # ones we have inferred and never seen (the operator, 2026-08-31)
    # a proceeding reaches the filings table before the dockets table, so ask about the
    # ones we have inferred and never seen (the operator, 2026-08-31)
    summary["captions"] = {"asked": 0, "answered": 0, "captioned": 0}
    try:
        before = _captioned_ids(con)
        summary["captions"] = _fill_captions(
            con,
            client,
            data_dir,
            online=online,
            problems=summary["problems"],
            today=today or date.today(),
            log=log,
        )
    except Exception as e:  # noqa: BLE001 — never at the cost of the pass
        con.rollback()
        before = None
        summary["problems"].append(f"captions: failed ({type(e).__name__}: {e})")
    # unconditional, exactly as the record tables are: whatever an earlier pass left
    # asserted-but-pending is consumed even when the endpoint is down or nothing was asked
    summary["captions"]["ingested"] = _ingest_pending(con, data_dir, DOCKETS, summary["problems"])
    if before is not None:
        # the dockets THIS pass asked about that now carry a caption — never a store-wide
        # delta, which a family page or a concurrent wave would inflate
        gained = _captioned_ids(con) - before
        summary["captions"]["captioned"] = len(
            gained & set(summary["captions"].pop("captioned_ids", []))
        )
        summary["captions"].pop("captioned_ids", None)
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
    # errata, after the alerts so a pass's own entries never wait on it: a slice of
    # the held files, the longest-unchecked first (ADR 0002), under a time budget; skipped
    # when this pass's own fetch aborted (the host is the same)
    if fetched.get("failed") == -1:
        summary["rechecked"] = {"skipped": "fetch aborted"}
    else:
        try:
            summary["rechecked"] = documents.fetch_attachments(
                con,
                data_dir,
                client.fetcher(data_dir),
                limit=recheck_limit,
                refresh=True,
                recheck_after_days=observations.RECHECK_AFTER_DAYS,
                recheck_max_bytes=observations.RECHECK_MAX_BYTES,
                ingest_mode="forward",
                budget_seconds=RECHECK_BUDGET_SECONDS,
            )
        except Exception as e:  # noqa: BLE001
            con.rollback()
            summary["rechecked"] = {"failed": -1}
            summary["problems"].append(f"re-check aborted ({type(e).__name__}: {e})")
    if summary["rechecked"].get("failed", 0) > 0:  # a held file the host no longer serves
        summary["problems"].append(f"re-check refused: {summary['rechecked']['failed']}")
    summary["search"] = search.rebuild_or_report(con, summary["problems"])
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
