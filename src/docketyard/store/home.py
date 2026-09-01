"""The home-page projection: what moved at the Board in a window. Derived, rebuildable.

A record entered in a docket and its sub-docket is one record: decisions and filings are
folded by their STB id across the family, so neither is counted twice. What they are
listed UNDER is the proceeding the Board entered them in — the sub-docket where there is
one, never its parent (revised 2026-08-30; see the note on the `moved` query).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from sqlite3 import Connection

from docketyard.capture import walk
from docketyard.capture.stb import DECISIONS, FILINGS
from docketyard.store.db import load_json

WEEK_DAYS = 7

# The corridor of week addresses that exist at all (navigation-review.md A4). Without a
# floor, "← previous week" walks backwards for ever on a single-process box, and
# `/week/0001-01-01` is a 500 the moment the page subtracts seven days from it; without a
# horizon, `/week/9999-12-31` is the same 500 going the other way. Both bounds are FIXED,
# not read from the record: a bound that moved with the waves would let an address that
# answered 200 start answering 404. The floor sits six years below the Board's own
# beginning — it was created by the ICC Termination Act of 1995, effective 1 January 1996 —
# so it can never cut into the record, and the horizon is a year, which is as far ahead as
# a week is worth naming.
WEEK_FLOOR = date(1990, 1, 1)
WEEK_HORIZON_DAYS = 366


@dataclass(frozen=True)
class DecisionServed:
    docket_id: int
    docket_raw: str
    docket_title: str | None
    stb_decision_id: str
    service_date: str
    deciding_body: str | None
    decision_type: str | None
    summary: str | None
    also_in: list[str]  # raw docket spellings of the other family members it was entered in


@dataclass(frozen=True)
class ProceedingMoved:
    docket_id: int
    docket_raw: str
    title: str | None
    filings: int  # distinct filings in THIS proceeding (the sub-docket, where there is one)
    last_activity: str


@dataclass(frozen=True)
class Week:
    start: str
    end: str
    checked: str | None
    decisions: list[DecisionServed]
    distinct_decisions: int
    decision_entries: int  # record rows, counting a decision once per docket it is entered in
    moved: list[ProceedingMoved]
    filings: int  # distinct filings the Board published in the window
    filing_entries: int  # rows, counting a filing once per proceeding it is entered in


def _numeric(record_id: str) -> int:
    return int(record_id) if record_id.isdigit() else 0


def week(con: Connection, start: str, end: str) -> Week:
    rows = con.execute(
        """
        SELECT r.docket_id, d.raw_docket, dc.latest_payload, r.stb_decision_id,
               r.service_date, r.deciding_body, r.decision_type, e.payload
          FROM decision_record r
          JOIN docket d ON d.docket_id = r.docket_id
          JOIN docket_current dc ON dc.docket_id = r.docket_id
          JOIN event e ON e.event_id = r.observed_in_event
         WHERE r.service_date BETWEEN ? AND ?
         ORDER BY r.stb_decision_id, COALESCE(d.sub_sequence, -1), COALESCE(d.suffix, '')
        """,
        (start, end),
    ).fetchall()
    by_id: dict[str, list] = {}
    for row in rows:
        by_id.setdefault(row[3], []).append(row)  # parent first, by the ORDER BY
    decisions = [
        DecisionServed(
            docket_id=e[0][0],
            docket_raw=e[0][1],
            docket_title=load_json(e[0][2])["title"] if e[0][2] else None,
            stb_decision_id=e[0][3],
            service_date=e[0][4],
            deciding_body=e[0][5],
            decision_type=e[0][6],
            summary=load_json(e[0][7]).get("summary"),
            also_in=[x[1] for x in e[1:]],
        )
        for e in by_id.values()
    ]
    decisions.sort(key=lambda x: (x.service_date, _numeric(x.stb_decision_id)), reverse=True)
    moved = [
        ProceedingMoved(
            docket_id=d,
            docket_raw=raw,
            title=load_json(p)["title"] if p else None,
            filings=n,
            last_activity=last,
        )
        for d, raw, p, n, last in con.execute(
            # The proceeding that moved is the docket the filing was entered in — the
            # SUB-docket where there is one, never its parent (revised 2026-08-30, the
            # operator: "I don't care that Norfolk Southern had something moving, I care
            # what was moving"). For AB, the biggest user of sub-numbers, the sub IS the
            # proceeding: `/about/AB` says a Sub-No. is "each line a carrier abandons",
            # and AB 290 alone holds 391 unrelated abandonments. Rolling up to the family
            # named the carrier's series instead of the action, and named it badly: only
            # 11.5% of AB family roots carry a caption (the Board publishes rows for the
            # sub-dockets, not the bare parent), against 100% of the proceedings that
            # actually filed. Folding also bought nothing it was worth — measured over
            # 136 weeks, 95.4% of family-weeks hold exactly one moving proceeding and the
            # most ever is four. The sheet still folds (ADR 0005); a list of what moved
            # must not.
            """
            SELECT d.docket_id, d.raw_docket, dc.latest_payload,
                   COUNT(DISTINCT f.stb_filing_id), MAX(f.filed_date)
              FROM filing f
              JOIN docket d ON d.docket_id = f.docket_id
              JOIN docket_current dc ON dc.docket_id = d.docket_id
             WHERE f.filed_date BETWEEN ? AND ?
             GROUP BY d.docket_id
             ORDER BY MAX(f.filed_date) DESC, COUNT(DISTINCT f.stb_filing_id) DESC, d.raw_docket
            """,
            (start, end),
        )
    ]
    checked = con.execute("SELECT MAX(captured_at) FROM capture").fetchone()[0]
    return Week(
        start=start,
        end=end,
        checked=checked,
        decisions=decisions,
        distinct_decisions=len(decisions),
        decision_entries=len(rows),
        moved=moved,
        # One filing entered in a docket AND its sub-docket is two `filing` rows (the
        # natural key is (docket_id, stb_filing_id)), so summing the per-proceeding counts
        # would publish it twice — the same trap the decisions half of this page already
        # names. Count the Board's filings once, and keep the row total beside it.
        filings=con.execute(
            "SELECT COUNT(DISTINCT stb_filing_id) FROM filing WHERE filed_date BETWEEN ? AND ?",
            (start, end),
        ).fetchone()[0],
        filing_entries=sum(m.filings for m in moved),
    )


def latest_activity_date(con: Connection, today: date | None = None) -> date:
    """The newest plausible date the record prints, never in the future: the anchor for
    'this week'. A malformed stored date (shape-checked at ingest, not range-checked) is
    skipped rather than allowed to break the page."""
    today = today or date.today()
    candidates = [
        r[0]
        for r in con.execute(
            "SELECT d FROM (SELECT filed_date AS d FROM filing"
            " UNION ALL SELECT service_date FROM decision_record)"
            " WHERE d IS NOT NULL AND d <= ? ORDER BY d DESC LIMIT 15",
            (today.isoformat(),),
        )
    ]
    for value in candidates:
        try:
            return date.fromisoformat(value)
        except ValueError:
            continue
    return today


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def calendar_week(con: Connection, monday: date) -> Week:
    """A fixed Monday–Sunday week at a permanent address (ADR 0013 addendum): the same
    projection as the home page, over the ISO week."""
    return week(con, monday.isoformat(), (monday + timedelta(days=6)).isoformat())


def _months(start: date, end: date) -> set[str]:
    """Every YYYY-MM the window touches."""
    months, cursor = set(), start.replace(day=1)
    while cursor <= end:
        months.add(cursor.strftime("%Y-%m"))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def _days(start: date, end: date) -> set[date]:
    days, cursor = set(), start
    while cursor <= end:
        days.add(cursor)
        cursor += timedelta(days=1)
    return days


def walked_days(con: Connection, action: str, months: set[str]) -> set[date]:
    """The days of `months` a wave actually asked the endpoint for, on one table.

    The grammar is `walk.slice_days`, read from beside the only thing that writes it. This
    module used to match `f"{action}:{month}"` exactly, which read the ledger's one
    partly-walked month as never walked — and since that month sat between the reader and
    everything older, it walled off the whole 1996–2026 archive behind three weeks of
    records the page was already holding (navigation-review.md A1).

    A range-suffixed slice expands to the days it names and never to the month around them:
    the fix is to stop hiding what was walked, not to start claiming what was not."""
    days: set[date] = set()
    for month in months:
        for (key,) in con.execute(
            "SELECT slice_key FROM walk_slice WHERE table_action = ? AND"
            " (slice_key = ? OR slice_key LIKE ?) AND status IN ('done', 'empty')",
            (action, f"{action}:{month}", f"{action}:{month}:%"),
        ):
            days |= walk.slice_days(key)
    return days


def covered(con: Connection, start: date, end: date) -> bool:
    """Whether the record claims this window: the watch has been running across the whole
    of it, or every day of it was walked by a backfill wave for both record tables.
    Anything else is 'not yet covered' — an honest empty page, not a quiet week.

    The watch test is on `start`, not on `end`. The poller's first pass reaches back a
    seven-day window, so the watch covers `[watch - 6, ...)` — but this function answers
    "is EVERY day of this window covered", and testing `end` answered "does this window
    OVERLAP what the watch covers", which claimed up to six days before the watch ever ran
    (stb-ingest-specialist, 2026-08-31). A straddling week now falls through to the ledger,
    which is the authority.

    This is the ledger's answer alone, and the ledger cannot see what the window holds.
    Callers rendering the 'not covered' sentence must use `coverage_state`, which will not
    print it over records the page is holding."""
    row = con.execute(
        "SELECT MIN(captured_at) FROM capture WHERE ingest_mode = 'forward'"
        " AND filter_asserted = 1 AND table_action IN (?, ?)",
        (FILINGS, DECISIONS),
    ).fetchone()
    watch = date.fromisoformat(row[0][:10]) if row and row[0] else None
    if watch and start >= watch - timedelta(days=WEEK_DAYS - 1):
        return True
    months, window = _months(start, end), _days(start, end)
    return all(window <= walked_days(con, action, months) for action in (FILINGS, DECISIONS))


# The states a week page can be in. `uncovered` is the only one that may print the sentence
# claiming the record does not reach here, and it is reachable only when the window holds
# nothing — the invariant this enum exists to hold (navigation-review.md A2). The sentence
# asserted three things and measured one: that the ledger was short (measured), that nothing
# was here (never checked), and that a covered week is complete (a claim the record cannot
# make anywhere).
COVERED, PARTIAL, UNCOVERED, FUTURE = "covered", "partial", "uncovered", "future"


def coverage_state(con: Connection, w: Week, start: date, end: date, today: date) -> str:
    """What a week page may say about itself.

    - `future`  — the week has not happened yet; the record is not silent about it, it
      has nothing to be silent about.
    - `covered` — the ledger reaches here; render the week.
    - `partial` — the ledger is short and the window holds records anyway. Render them,
      and say how far the walk reached. A wave that stopped mid-month is the ordinary
      cause, and hiding held records behind a coverage sentence is the defect A1 measured.
    - `uncovered` — the ledger is short and the window is empty. Only here is the sentence
      true, and it is still a statement about the walk, never about the Board.
    """
    if start > today:
        return FUTURE
    if covered(con, start, end):
        return COVERED
    return PARTIAL if (w.filings or w.decision_entries) else UNCOVERED


def walked_through(con: Connection, start: date, end: date) -> date | None:
    """The last day of an UNBROKEN run from the window's start that a wave walked for both
    record tables, or None if the window's first day was never walked.

    The contiguity matters because the page prints this as "it walked as far as X". Taking
    the latest walked day instead would name a date past a hole: two waves leaving
    01..03 and 05..07 both `done` would print "as far as the 7th" while the 4th was never
    requested. A statement about the walk has to be true of every day it covers."""
    months = _months(start, end)
    walked = walked_days(con, FILINGS, months) & walked_days(con, DECISIONS, months)
    reached, cursor = None, start
    while cursor <= end and cursor in walked:
        reached, cursor = cursor, cursor + timedelta(days=1)
    return reached


@dataclass(frozen=True)
class WeekSummary:
    monday: str  # ISO, the week's own permanent address
    end: str  # its Sunday, so the page can print the range without re-deriving it
    filings: int
    decisions: int


@dataclass(frozen=True)
class WeekYear:
    year: int
    weeks: list[WeekSummary]  # newest first
    filings: int
    decisions: int


def weeks_index(con: Connection, today: date | None = None) -> list[WeekYear]:
    """Every week the record holds anything for, newest first, grouped by year.

    ~1,590 week pages render correctly and were reachable only by clicking "previous week"
    sixteen hundred times; they are in neither the sitemap nor `llms.txt`, so no search
    engine could be the index the site lacked either (navigation-review.md § C). This is
    that index, and it is one aggregate over the two record tables — no per-week query.

    A week is Monday–Sunday, the same unit `/week` serves: SQLite's `weekday 0` moves
    forward to Sunday, so backing up six days is the Monday whose week the date falls in —
    the arithmetic `monday_of` does. Only well-formed dates inside the corridor count: a
    Board-side typo is shape-checked at ingest, not range-checked, and must not stretch
    this page to the year 2062 or invent a week before the record."""
    today = today or date.today()
    floor, ceiling = WEEK_FLOOR.isoformat(), today.isoformat()
    per_week: dict[str, list[int]] = {}
    for column, table, slot in (
        ("filed_date", "filing", 0),
        ("service_date", "decision_record", 1),
    ):
        ident = "stb_filing_id" if slot == 0 else "stb_decision_id"
        for monday, n in con.execute(
            f"SELECT date({column}, 'weekday 0', '-6 days'), COUNT(DISTINCT {ident})"
            f" FROM {table} WHERE {column} IS NOT NULL AND {column} BETWEEN ? AND ?"
            f" GROUP BY 1",
            (floor, ceiling),
        ):
            if monday:  # date() answers NULL for anything it cannot read
                per_week.setdefault(monday, [0, 0])[slot] = n
    years: dict[int, list[WeekSummary]] = {}
    for monday in sorted(per_week, reverse=True):
        f, d = per_week[monday]
        end = (date.fromisoformat(monday) + timedelta(days=WEEK_DAYS - 1)).isoformat()
        years.setdefault(int(monday[:4]), []).append(WeekSummary(monday, end, f, d))
    return [
        WeekYear(
            year=y,
            weeks=weeks,
            filings=sum(w.filings for w in weeks),
            decisions=sum(w.decisions for w in weeks),
        )
        for y, weeks in sorted(years.items(), reverse=True)
    ]


def this_week(con: Connection, today: date | None = None) -> Week:
    """The one definition of the window: the seven days ending on the latest activity."""
    end = latest_activity_date(con, today)
    start = end - timedelta(days=WEEK_DAYS - 1)
    return week(con, start.isoformat(), end.isoformat())
