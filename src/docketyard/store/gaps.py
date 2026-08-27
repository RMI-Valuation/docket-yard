"""Coverage gaps: the operator's record of a window in which the record was not kept.

The heartbeat runs off-box and cannot write the store (docs/alerts.md § gaps), so the
operator records what it found: when the gap began, what failed in the decomposition's
terms, and when it ended. The coverage page is generated from these rows; an alert that
carried entries observed late cites the row covering them (`alert_event.late_gap_id`).
Nothing here infers a gap — lateness is derived from the capture ledger by the alerts;
this is only the operator saying so in public.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from sqlite3 import Connection

FAILURES = ("captures", "events", "documents", "delivery")  # the CHECK on the table
CITED = ("captures", "events")  # the failures a late entry can fall inside
# a late entry is carried by the catch-up pass, which runs AFTER the gap ends: the window
# that cites a gap reaches past its end by the lateness threshold (alerts.build.LATE_AFTER)
CATCH_UP = "+3 hours"
CITES = "c.captured_at >= ? AND (? IS NULL OR datetime(c.captured_at) <= datetime(?, ?))"


@dataclass(frozen=True)
class GapRow:
    gap_id: int
    started_at: str
    ended_at: str | None
    failure: str
    note: str | None


def when(text: str | None) -> str:
    """An ISO instant, normalised to UTC seconds; `None` is now."""
    if text is None:
        return datetime.now(UTC).isoformat(timespec="seconds")
    try:
        t = datetime.fromisoformat(text)
    except ValueError as e:
        raise ValueError(f"not an ISO-8601 instant: {text!r}") from e
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t.astimezone(UTC).isoformat(timespec="seconds")


def _check_note(note: str | None) -> str | None:
    """The note is published on /coverage and in the snapshot: never an address."""
    if note and "@" in note:
        raise ValueError("a gap note is public and must not carry an address")
    return note or None


def open_gap(
    con: Connection, failure: str, *, since: str | None = None, note: str | None = None
) -> int:
    """Record a gap that began at `since` (now by default). One open gap per failure."""
    if failure not in FAILURES:
        raise ValueError(f"failure must be one of {', '.join(FAILURES)}")
    started = when(since)
    if started > when(None):
        raise ValueError("a gap cannot begin in the future")
    open_row = con.execute(
        "SELECT gap_id FROM coverage_gap WHERE failure = ? AND ended_at IS NULL", (failure,)
    ).fetchone()
    if open_row:
        raise ValueError(f"gap {open_row[0]} for {failure} is still open; close it first")
    cur = con.execute(
        "INSERT INTO coverage_gap (started_at, ended_at, failure, note) VALUES (?, NULL, ?, ?)",
        (started, failure, _check_note(note)),
    )
    gap_id = cur.lastrowid
    cite(con, gap_id)
    con.commit()
    return gap_id


def close_gap(con: Connection, gap_id: int, *, at: str | None = None) -> GapRow:
    """End a gap at `at` (now by default)."""
    row = get(con, gap_id)
    if row is None:
        raise ValueError(f"no gap {gap_id}")
    if row.ended_at is not None:
        raise ValueError(f"gap {gap_id} was closed at {row.ended_at}")
    ended = when(at)
    if ended < row.started_at:
        raise ValueError(f"gap {gap_id} began at {row.started_at}; it cannot end before that")
    con.execute("UPDATE coverage_gap SET ended_at = ? WHERE gap_id = ?", (ended, gap_id))
    cite(con, gap_id)
    con.commit()
    return get(con, gap_id)  # type: ignore[return-value]


def cite(con: Connection, gap_id: int) -> int:
    """Point every late alert entry the gap covers at it, where none was cited yet: the
    alert that carried them may have been built before the operator recorded the gap.
    Entries this gap cited while open but which its end now excludes are released, so a
    later gap can claim them. The email already sent is not changed; the record is.
    Returns rows now citing the gap."""
    row = get(con, gap_id)
    if row is None or row.failure not in CITED:
        return 0
    window = (row.started_at, row.ended_at, row.ended_at, CATCH_UP)
    covered = (
        "SELECT e.event_id FROM event e JOIN capture c ON c.capture_id = e.capture_id WHERE "
        + CITES
    )
    con.execute(
        f"UPDATE alert_event SET late_gap_id = NULL WHERE late_gap_id = ?"
        f" AND event_id NOT IN ({covered})",
        (gap_id, *window),
    )
    con.execute(
        f"UPDATE alert_event SET late_gap_id = ? WHERE late = 1 AND late_gap_id IS NULL"
        f" AND event_id IN ({covered})",
        (gap_id, *window),
    )
    return con.execute(
        "SELECT COUNT(*) FROM alert_event WHERE late_gap_id = ?", (gap_id,)
    ).fetchone()[0]


def get(con: Connection, gap_id: int) -> GapRow | None:
    row = con.execute(
        "SELECT gap_id, started_at, ended_at, failure, note FROM coverage_gap WHERE gap_id = ?",
        (gap_id,),
    ).fetchone()
    return GapRow(*row) if row else None


def list_gaps(con: Connection) -> list[GapRow]:
    return [
        GapRow(*r)
        for r in con.execute(
            "SELECT gap_id, started_at, ended_at, failure, note FROM coverage_gap"
            " ORDER BY started_at DESC"
        )
    ]
