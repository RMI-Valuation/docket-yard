"""What the record covers, measured from the store — never typed by hand (coverage.md).

Every number on the public coverage page comes from here, so the page cannot claim more
than the ledger holds. Forward and backfill are reported separately because they mean
different things: forward is the promise (watched continuously since a date); backfill is
whatever has been walked so far.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from sqlite3 import Connection

from docketyard.capture import walk
from docketyard.capture.stb import (
    DECISIONS,
    DOCKETS,
    ENVIRO_COMMENTS,
    EXPECTED_EMPTY_PREFIXES,
    FILINGS,
)
from docketyard.ingest import observations
from docketyard.store import home


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
    # Months neither a wave nor the watch has finished, BY TABLE — never unioned. The page's
    # sentence about them has filings and decisions for its subject, and the comment walk's own gaps
    # reach four and a half years further back than either (navigation-review.md A3): one
    # list under that sentence told readers that 1996-01 through 2000-08 were incomplete
    # for filings and decisions, which they are not.
    records_incomplete: tuple[str, ...]  # filings and decisions
    comments_incomplete: tuple[str, ...]  # environmental comments
    comments_from: str | None  # earliest comment the record holds, by the Board's own date
    empty_prefixes: tuple[str, ...]
    gaps: list[Gap]


def _watch_starts(q, actions) -> dict[str, date]:
    """Per table, the first day the forward watch asked the Board for: its first asserted
    forward capture, less the trailing window that pass asked for (`home.covered`'s rule).
    Per table, because comments joined the watch later than filings and decisions."""
    starts = {}
    for action in actions:
        (first,) = q(
            "SELECT MIN(captured_at) FROM capture WHERE ingest_mode = 'forward'"
            " AND filter_asserted = 1 AND table_action = ?",
            (action,),
        ).fetchone()
        if first:
            starts[action] = date.fromisoformat(first[:10]) - timedelta(days=home.WEEK_DAYS - 1)
    return starts


def _incomplete(con: Connection, *actions: str, today: date | None = None) -> tuple[str, ...]:
    """The YYYY-MM months neither a wave nor the watch has finished for these tables, oldest
    first.

    A month is finished only when the days its slices actually asked for cover the whole
    month. Testing the STATUS alone was not enough: a wave that walked 15–31 July records a
    range-suffixed slice as `done`, and a month-status test read that as a finished July —
    so this page would assert by omission that the first fourteen days were walked, while
    `/week` correctly called them partial. Two modules, one ledger, and the same defect A1
    was, pointing the other way (code review, 2026-08-31).

    THE WATCH'S DAYS COUNT TOO (the operator's decision, 2026-09-11). A wave walks the archive
    up to where the watch began, so the month the watch began in was listed unfinished for
    ever while every day of it was held — 2026-08 on production. The watch's days are
    `home.covered`'s: from `_watch_starts` through today, less every span a recorded outage
    left it unable to ask for (`home.gap_shadows`), so nothing is claimed that was not asked.

    The grammar is `walk.slice_days`, shared with `home.walked_days`, so a key shape only
    one of them understands cannot arise."""
    q = con.execute
    today = today or date.today()
    starts = _watch_starts(q, actions)
    shadows = home.gap_shadows(con, today)
    placeholders = ", ".join("?" * len(actions))
    # One pass. Every (table, month) the ledger mentions is a month a wave has begun, and
    # only its done/empty slices count toward finishing it — so a month holding nothing but
    # a `partial` slice arrives here with an empty day set and is reported, exactly as it
    # was before.
    finished: dict[tuple[str, str], set] = {}
    for action, key, status in q(
        f"SELECT table_action, slice_key, status FROM walk_slice"
        f" WHERE table_action IN ({placeholders})",
        actions,
    ):
        month = walk.slice_month(key)
        if month is None:  # the dockets walk keys by prefix; it is not a month's business
            continue
        days = finished.setdefault((action, month), set())
        if status in ("done", "empty"):
            days |= walk.slice_days(key)
    for (action, month), days in finished.items():
        start = starts.get(action)
        if start is None:
            continue
        days |= {
            d
            for d in walk.month_days(month)
            if start <= d <= today and not any(lo <= d <= hi for lo, hi in shadows)
        }
    return tuple(
        sorted({month for (_, month), days in finished.items() if days < walk.month_days(month)})
    )


def month_runs(months: tuple[str, ...]) -> tuple[str, ...]:
    """Consecutive months collapsed into ranges: 56 unfinished comment months print as
    `1996-01 to 2000-08`, not as 56 comma-separated strings. Presentation only — the
    measurement is the month list itself."""
    runs: list[list[str]] = []
    for m in months:
        year, month = int(m[:4]), int(m[5:7])
        prev = f"{year - 1:04d}-12" if month == 1 else f"{year:04d}-{month - 1:02d}"
        if runs and runs[-1][-1] == prev:
            runs[-1].append(m)
        else:
            runs.append([m])
    return tuple(r[0] if len(r) == 1 else f"{r[0]} to {r[-1]}" for r in runs)


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
        # Each walked record table reports its own unfinished months. A comment month a
        # wave has not finished is as unfinished as a filings month and the page exists to
        # say so — but it is not a filings month, and the sentence that names them is about
        # filings and decisions.
        records_incomplete=_incomplete(con, FILINGS, DECISIONS),
        comments_incomplete=_incomplete(con, ENVIRO_COMMENTS),
        comments_from=one("SELECT MIN(NULLIF(date_received_or_sent, '')) FROM enviro_comment"),
        empty_prefixes=tuple(sorted(EXPECTED_EMPTY_PREFIXES)),
        gaps=[
            Gap(*row)
            for row in q(
                "SELECT started_at, ended_at, failure, note FROM coverage_gap"
                " ORDER BY started_at DESC"
            )
        ],
    )
