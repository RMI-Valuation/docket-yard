"""Paged capture of one slice, and the backfill walk built from slices.

A slice is one criteria set (e.g. one docket prefix) paged to its end under the table's
pinned sort. A walk runs a list of slices in backfill mode and records how each one ended in
walk_slice — done, empty, capped, or partial — so an interrupted walk resumes where it
stopped and a finished walk is auditable: never silently short.

Loudness is the point. The endpoint answers the wrong criteria, an expired nonce, and a
renamed sort key with the same "There are no X available" envelope it uses for a genuinely
empty result; this module only ever calls that envelope benign when the census says the
slice is empty, or when it arrives after the slice's rows already reconcile with the
reported total.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from sqlite3 import Connection

from docketyard.capture import records
from docketyard.capture.stb import (
    AJAX,
    DECISIONS,
    DOCKET_PREFIXES,
    DOCKETS,
    EXPECTED_EMPTY_PREFIXES,
    FILINGS,
    PAGE_CLAMP,
    TABLE_SORT,
)
from docketyard.ingest import dockets, observations
from docketyard.store.db import dump_json, utcnow


@dataclass
class SliceResult:
    rows: int = 0  # from asserted pages only
    captures: int = 0
    total: int | None = None  # the endpoint's reported total on the last asserted page
    complete: bool = False  # paged to the end AND reconciled with the total where possible
    capped: bool = False  # reported total hit the display cap: incomplete by construction
    quarantined: bool = False  # a capture failed assertion (or a suspicious envelope)
    envelope_on_first_page: bool = False  # trap OR truly empty — the caller decides which
    expected_empty: bool = False

    @property
    def status(self) -> str:
        """The one definition of how a slice ended."""
        if self.envelope_on_first_page and self.expected_empty:
            return "empty"
        if self.capped:
            return "capped"
        if self.complete and not self.quarantined:
            return "done"
        return "partial"


@dataclass(frozen=True)
class Slice:
    key: str
    criteria: list[tuple[str, str]]
    expected_empty: bool = False


def capture_slice(
    con: Connection,
    client,
    action: str,
    criteria: list[tuple[str, str]],
    *,
    data_dir,
    per_page: int = PAGE_CLAMP,
    pages: int = 10,
    mode: str = "forward",
    expected_empty: bool = False,
    log=print,
) -> SliceResult:
    spec = observations.SPECS.get(action)  # None for the dockets table
    sort_by, sort_order = TABLE_SORT[action]
    result = SliceResult(expected_empty=expected_empty)
    nonce_refreshed = False
    page = 1
    while page <= pages:
        status, body, fields = client.query_table(
            action, criteria, page=page, per_page=per_page, sort_by=sort_by, sort_order=sort_order
        )
        # capture-first: the raw is durable (and quarantined) before anything parses it
        capture_id = records.save_capture(
            con,
            data_dir,
            source_system=dockets.SOURCE_SYSTEM,
            endpoint=AJAX,
            table_action=action,
            request_params=fields,
            body=body,
            http_status=status,
            ingest_mode=mode,
        )
        result.captures += 1
        try:
            if spec is None:
                parsed = dockets.parse_response(body)
                asserted = dockets.assert_filter(criteria, parsed)
            else:
                parsed = observations.parse_response(spec, body)
                asserted = observations.assert_filter(spec, criteria, parsed)
        except ValueError as e:
            envelope = dockets.is_no_results_envelope(body)
            if page > 1 and envelope and _reconciles(action, result):
                # genuine end of results: every row the endpoint promised is already here
                records.set_verdict(
                    con,
                    capture_id,
                    filter_asserted=True,
                    row_count=0,
                    reported_total=result.total or 0,
                )
                records.mark_processed(con, capture_id)
                log(f"capture {capture_id}: page {page}, end of results")
                result.complete = True
                return result
            if page > 1 and envelope and not nonce_refreshed:
                # rows do not reconcile: most likely the nonce rotated mid-walk. One retry
                # of the same page with a fresh nonce; the failed capture stays quarantined
                nonce_refreshed = True
                records.set_verdict(
                    con, capture_id, filter_asserted=False, row_count=0, reported_total=0
                )
                client.refresh_nonces()
                log(f"capture {capture_id}: mid-slice envelope; nonce refreshed, retrying")
                continue
            # judged and failed (not merely unjudged): the verdict is recorded
            records.set_verdict(
                con, capture_id, filter_asserted=False, row_count=0, reported_total=0
            )
            result.quarantined = True
            result.envelope_on_first_page = page == 1 and envelope
            log(f"capture {capture_id}: QUARANTINED, unparseable response ({e})")
            return result
        records.set_verdict(
            con,
            capture_id,
            filter_asserted=asserted,
            row_count=len(parsed.rows),
            reported_total=parsed.total,
        )
        log(f"capture {capture_id}: page {page}, {len(parsed.rows)} rows, total={parsed.total}")
        if not asserted:
            log("  QUARANTINED: filter assertion failed — will not be ingested")
            result.quarantined = True
            return result
        result.rows += len(parsed.rows)
        result.total = parsed.total
        if dockets.hit_display_cap(parsed.total):
            log(f"  WARNING: total={parsed.total} is the display cap; this slice is INCOMPLETE")
            result.capped = True
        # the server clamps per-page and `total` may count records rather than rows on the
        # multi-row tables, so the last page is the first SHORT page. A slice that fills
        # its last page exactly ends on the reconciled envelope above.
        if not parsed.rows or len(parsed.rows) < min(per_page, PAGE_CLAMP):
            if _reconciles(action, result):
                result.complete = True
            else:
                log(f"  WARNING: short page but only {result.rows} of {result.total} rows seen")
            return result
        page += 1
    log(f"  WARNING: stopped at {pages} pages with {result.rows} rows; more may remain")
    return result


def _reconciles(action: str, result: SliceResult) -> bool:
    """On the dockets table one row is one docket, so a complete slice has exactly `total`
    rows (a capped slice can only reach the cap). The multi-row tables cannot be reconciled
    this way and rely on the short-page rule alone."""
    if action != DOCKETS or result.total is None:
        return True
    if result.capped:
        return result.rows >= 10_000
    return result.rows == result.total


def slice_status(con: Connection, slice_key: str) -> str | None:
    row = con.execute("SELECT status FROM walk_slice WHERE slice_key = ?", (slice_key,)).fetchone()
    return row[0] if row else None


def record_slice(
    con: Connection, slice_key: str, action: str, criteria, result: SliceResult
) -> str:
    con.execute(
        "INSERT OR REPLACE INTO walk_slice"
        " (slice_key, table_action, criteria, status, rows, captures, completed_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            slice_key,
            action,
            dump_json(criteria),
            result.status,
            result.rows,
            result.captures,
            utcnow(),
        ),
    )
    con.commit()
    return result.status


def walk(
    con: Connection,
    client,
    action: str,
    slices: Iterable[Slice],
    *,
    data_dir,
    redo: bool = False,
    pages: int = 200,  # 10,000 / 50: the most any uncapped slice can need
    log=print,
) -> dict:
    """Every slice in backfill mode. Skips slices already done/empty/capped unless redo."""
    summary = {"done": 0, "empty": 0, "capped": 0, "partial": 0, "skipped": 0}
    for s in slices:
        key = f"{action}:{s.key}"
        if not redo and slice_status(con, key) in ("done", "empty", "capped"):
            summary["skipped"] += 1
            continue
        log(f"== {s.key}")
        try:
            result = capture_slice(
                con,
                client,
                action,
                s.criteria,
                data_dir=data_dir,
                pages=pages,
                mode="backfill",
                expected_empty=s.expected_empty,
                log=log,
            )
        except Exception as e:  # noqa: BLE001 — one slice must not strand the walk
            con.rollback()
            # a long walk straddles the nonce's rotation; a dead nonce is a 403, not the
            # envelope, so the in-slice refresh never sees it. Refresh once and retry.
            log(f"   {s.key}: FAILED ({type(e).__name__}: {e}); refreshing nonce, retrying")
            try:
                client.refresh_nonces()
                result = capture_slice(
                    con,
                    client,
                    action,
                    s.criteria,
                    data_dir=data_dir,
                    pages=pages,
                    mode="backfill",
                    expected_empty=s.expected_empty,
                    log=log,
                )
            except Exception as e2:  # noqa: BLE001
                con.rollback()
                result = SliceResult(quarantined=True)
                log(f"   {s.key}: FAILED again ({type(e2).__name__}: {e2})")
        status = record_slice(con, key, action, s.criteria, result)
        summary[status] += 1
        note = ""
        if result.envelope_on_first_page and not result.expected_empty:
            note = (
                " — no-results envelope on the first page: a trap or a truly empty slice, and"
                " the walker cannot tell which (prove it by a neighbour window and declare it"
                " in EXPECTED_EMPTY_MONTHS, or find the criterion that was wrong)"
            )
        if result.capped:
            note = " — display cap: this slice needs sub-slicing"
        log(f"   {s.key}: {status} ({result.rows} rows, {result.captures} captures){note}")
    return summary


def docket_prefix_slices() -> list[Slice]:
    return [
        Slice(key=p, criteria=[("docketNum_one", p)], expected_empty=p in EXPECTED_EMPTY_PREFIXES)
        for p in DOCKET_PREFIXES
    ]


def walk_dockets(con: Connection, client, *, data_dir, redo: bool = False, log=print) -> dict:
    return walk(con, client, DOCKETS, docket_prefix_slices(), data_dir=data_dir, redo=redo, log=log)


# Months the operator has measured to be genuinely empty on a table, with why. A page-1
# no-results envelope is the trap everywhere else; here it is the truth, and the slice
# records `empty`. Add a month only after probing the endpoint (stb-data-source.md).
# The thin early years: 41 months of 1996–2000 that answer the envelope on their first
# page and add nothing to a window shared with a done neighbour (stb-data-source.md
# § Measured 2026-08-27). The walker has no census for a month slice, so this list is
# the measurement, kept as data.
_EARLY_FILINGS = (
    "no filings the endpoint will return: a window over this month and an adjacent done"
    " month reconciles to the done month's total alone (measured 2026-08-27,"
    " stb-data-source.md)"
)
_EARLY_DECISIONS = (
    "no decisions the endpoint will return: a window over this month and an adjacent done"
    " month reconciles to the done month's total alone (measured 2026-08-27,"
    " stb-data-source.md)"
)
EXPECTED_EMPTY_MONTHS: dict[str, dict[str, str]] = {
    FILINGS: {
        "2025-10": "federal shutdown: filings stop 2025-09-30 and resume 2025-11-13"
        " (measured 2026-08-26, stb-data-source.md)",
        "1996-02": _EARLY_FILINGS,
        "1996-03": _EARLY_FILINGS,
        "1996-04": _EARLY_FILINGS,
        "1996-05": _EARLY_FILINGS,
        "1996-06": _EARLY_FILINGS,
        "1996-07": _EARLY_FILINGS,
        "1996-08": _EARLY_FILINGS,
        "1996-10": _EARLY_FILINGS,
        "1996-11": _EARLY_FILINGS,
        "1997-02": _EARLY_FILINGS,
        "1997-03": _EARLY_FILINGS,
        "1997-04": _EARLY_FILINGS,
        "1997-07": _EARLY_FILINGS,
        "1997-08": _EARLY_FILINGS,
        "1997-09": _EARLY_FILINGS,
        "1997-10": _EARLY_FILINGS,
        "1997-11": _EARLY_FILINGS,
        "1997-12": _EARLY_FILINGS,
        "1998-01": _EARLY_FILINGS,
        "1998-02": _EARLY_FILINGS,
        "1998-08": _EARLY_FILINGS,
        "1998-10": _EARLY_FILINGS,
        "1998-12": _EARLY_FILINGS,
        "1999-01": _EARLY_FILINGS,
        "1999-06": _EARLY_FILINGS,
        "1999-07": _EARLY_FILINGS,
        "1999-08": _EARLY_FILINGS,
        "1999-09": _EARLY_FILINGS,
        "1999-10": _EARLY_FILINGS,
        "1999-11": _EARLY_FILINGS,
        "1999-12": _EARLY_FILINGS,
        "2000-01": _EARLY_FILINGS,
        "2000-07": _EARLY_FILINGS,
    },
    DECISIONS: {
        "1996-01": _EARLY_DECISIONS,
        "1996-02": _EARLY_DECISIONS,
        "1996-03": _EARLY_DECISIONS,
        "1996-04": _EARLY_DECISIONS,
        "1996-05": _EARLY_DECISIONS,
        "1996-06": _EARLY_DECISIONS,
        "1996-07": _EARLY_DECISIONS,
        "1996-09": _EARLY_DECISIONS,
    },
}


def month_slices(action: str, start: date, end: date) -> list[Slice]:
    """One slice per calendar month, [start, end] inclusive, in the endpoint's own date
    spelling. A month is far below the display cap for either table (~200 filings, ~100
    decisions at the busiest), so no slice can be capped; the criteria pair is the one
    that actually filters (stb-data-source.md), read from the table's spec."""
    spec = observations.SPECS[action]
    first, last = spec.date_criteria
    slices = []
    cursor = start.replace(day=1)
    while cursor <= end:
        nxt = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        lo, hi = max(cursor, start), min(nxt - timedelta(days=1), end)
        # the key carries the day range: a later wave with a wider range must not skip a
        # month that was only partly walked
        key = cursor.strftime("%Y-%m")
        if lo != cursor or hi != nxt - timedelta(days=1):
            key += f":{lo.isoformat()}..{hi.isoformat()}"
        slices.append(
            Slice(
                key=key,
                criteria=[(first, lo.strftime("%m/%d/%Y")), (last, hi.strftime("%m/%d/%Y"))],
                expected_empty=cursor.strftime("%Y-%m") in EXPECTED_EMPTY_MONTHS.get(action, {}),
            )
        )
        cursor = nxt
    return slices


def walk_observations(
    con: Connection, client, action: str, start: date, end: date, *, data_dir, redo=False, log=print
) -> dict:
    """Backfill one record table over a date range, oldest month first, resumably."""
    if end < start:
        raise ValueError(f"backfill range is empty: {start} .. {end}")
    return walk(
        con, client, action, month_slices(action, start, end), data_dir=data_dir, redo=redo, log=log
    )
