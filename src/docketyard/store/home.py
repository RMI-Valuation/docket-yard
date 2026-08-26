"""The home-page projection: what moved at the Board in a window. Derived, rebuildable.

A record entered in a docket and its sub-docket is one record: decisions and filings are
folded by their STB id across the family, headlined by the parent docket.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from sqlite3 import Connection

from docketyard.capture.stb import DECISIONS, FILINGS
from docketyard.store.db import load_json

WEEK_DAYS = 7


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
    filings: int  # distinct filings across the family
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
    filings: int


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
            """
            SELECT root.docket_id, root.raw_docket, dc.latest_payload,
                   COUNT(DISTINCT f.stb_filing_id), MAX(f.filed_date)
              FROM filing f
              JOIN docket d ON d.docket_id = f.docket_id
              JOIN docket root ON root.docket_id = COALESCE(d.parent_docket_id, d.docket_id)
              JOIN docket_current dc ON dc.docket_id = root.docket_id
             WHERE f.filed_date BETWEEN ? AND ?
             GROUP BY root.docket_id
             ORDER BY MAX(f.filed_date) DESC, COUNT(DISTINCT f.stb_filing_id) DESC, root.raw_docket
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
        filings=sum(m.filings for m in moved),
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


def covered(con: Connection, start: date, end: date) -> bool:
    """Whether the record claims this window: it ends on or after the day the watch began,
    or every month it touches was walked to completion by a backfill wave for both
    record tables. Anything else is 'not yet covered' — an honest empty page, not a
    quiet week."""
    row = con.execute(
        "SELECT MIN(captured_at) FROM capture WHERE ingest_mode = 'forward'"
        " AND filter_asserted = 1 AND table_action IN (?, ?)",
        (FILINGS, DECISIONS),
    ).fetchone()
    watch = date.fromisoformat(row[0][:10]) if row and row[0] else None
    if watch and end >= watch - timedelta(days=WEEK_DAYS - 1):
        return True
    months = set()
    cursor = start.replace(day=1)
    while cursor <= end:
        months.add(cursor.strftime("%Y-%m"))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    for action in (FILINGS, DECISIONS):
        for m in months:
            done = con.execute(
                "SELECT 1 FROM walk_slice WHERE slice_key = ? AND status = 'done'",
                (f"{action}:{m}",),
            ).fetchone()
            if not done:
                return False
    return True


def this_week(con: Connection, today: date | None = None) -> Week:
    """The one definition of the window: the seven days ending on the latest activity."""
    end = latest_activity_date(con, today)
    start = end - timedelta(days=WEEK_DAYS - 1)
    return week(con, start.isoformat(), end.isoformat())
