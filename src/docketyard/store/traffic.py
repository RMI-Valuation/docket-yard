"""Hourly request counts with no identifier, ever (docs/traffic.md; the sentence on /privacy
the operator signed 2026-08-26).

The web tier counts in memory — route class, status class, bot or not, bytes, a latency
bucket — and forgets the request. Once an hour the counters are written to a separate
file, `traffic.sqlite`, beside the store and never into it: the store is the record of the
Board's proceedings and stays free of anything about readers, and the snapshot never sees
this file. No per-request row exists anywhere, at any point, even transiently on disk.

What is never here: an address or any hash of one, a User-Agent string, a referrer, a
query, a path, a docket or party or record id, a cookie, a session, a country.
"""

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROUTE_CLASSES = (
    "home",
    "sheet",
    "record",
    "party",
    "parties",
    "search",
    "week",
    "stats",
    "feed",
    "json",
    "sitemap",
    "data",
    "trust",
    "subscribe",
    "static",
    "other",
)
TRUST = {"/about", "/contribute", "/coverage", "/methodology", "/corrections", "/privacy"}
LATENCY_BUCKETS = ("lt100", "lt500", "lt2000", "ge2000")  # milliseconds
HOURLY_DAYS = 90  # hourly rows kept this long, then folded into daily rows kept indefinitely
# a crawler is a User-Agent that says so; the string is looked at in memory and never kept
_BOT_MARKS = ("bot", "crawl", "spider", "slurp", "curl/", "wget", "python-requests", "go-http")

SCHEMA = """
CREATE TABLE IF NOT EXISTS traffic_hour (
    hour         TEXT NOT NULL,                   -- ISO hour, UTC: 2026-08-26T18
    route_class  TEXT NOT NULL,
    status_class TEXT NOT NULL,                   -- 2xx | 3xx | 4xx | 5xx
    bot          INTEGER NOT NULL CHECK (bot IN (0, 1)),
    requests     INTEGER NOT NULL,
    bytes        INTEGER NOT NULL,
    lt100        INTEGER NOT NULL,
    lt500        INTEGER NOT NULL,
    lt2000       INTEGER NOT NULL,
    ge2000       INTEGER NOT NULL,
    PRIMARY KEY (hour, route_class, status_class, bot)
);
CREATE TABLE IF NOT EXISTS traffic_day (
    day          TEXT NOT NULL,                   -- ISO date, UTC
    route_class  TEXT NOT NULL,
    status_class TEXT NOT NULL,
    bot          INTEGER NOT NULL CHECK (bot IN (0, 1)),
    requests     INTEGER NOT NULL,
    bytes        INTEGER NOT NULL,
    lt100        INTEGER NOT NULL,
    lt500        INTEGER NOT NULL,
    lt2000       INTEGER NOT NULL,
    ge2000       INTEGER NOT NULL,
    PRIMARY KEY (day, route_class, status_class, bot)
);
"""


def route_class(path: str) -> str:
    """The kind of page, never the page: no docket, party or record id survives this."""
    if path == "/":
        return "home"
    if path.startswith("/d/") or path == "/d":
        return "json" if path.endswith(".json") else ("feed" if path.endswith("/feed") else "sheet")
    if path.startswith(("/filing/", "/decision/")):
        return "json" if path.endswith(".json") else "record"
    if path.startswith("/p/"):
        return "feed" if path.endswith("/feed") else "party"
    if path.startswith("/feed"):
        return "feed"
    if path == "/parties":
        return "parties"
    if path in ("/search", "/suggest"):
        return "search"
    if path.startswith("/week"):
        return "week"
    if path == "/stats":
        return "stats"
    if path.startswith("/sitemap") or path == "/robots.txt":
        return "sitemap"
    if path.startswith("/data"):
        return "data"
    if path in TRUST:
        return "trust"
    if path.startswith(("/subscribe", "/s/", "/ses/")):
        return "subscribe"
    if path.startswith("/static/"):
        return "static"
    return "other"


def is_bot(user_agent: str | None) -> bool:
    ua = (user_agent or "").lower()
    return not ua or any(mark in ua for mark in _BOT_MARKS)


def latency_bucket(ms: float) -> str:
    if ms < 100:
        return "lt100"
    if ms < 500:
        return "lt500"
    if ms < 2000:
        return "lt2000"
    return "ge2000"


def hour_of(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y-%m-%dT%H")


class Counter:
    """The in-memory counters: (hour, route class, status class, bot) → the row's numbers.
    `record` is what the middleware calls per request; `drain` hands the finished rows to
    the writer and forgets them. Thread-safe; nothing here touches disk."""

    def __init__(self):
        self._lock = threading.Lock()
        self._rows: dict[tuple[str, str, str, int], list[int]] = {}

    def record(self, path: str, status: int, size: int, ms: float, user_agent: str | None, now):
        key = (hour_of(now), route_class(path), f"{status // 100}xx", int(is_bot(user_agent)))
        bucket = LATENCY_BUCKETS.index(latency_bucket(ms))
        with self._lock:
            row = self._rows.setdefault(key, [0, 0, 0, 0, 0, 0])
            row[0] += 1
            row[1] += max(size, 0)
            row[2 + bucket] += 1

    def drain(self, *, before_hour: str | None = None) -> list[tuple]:
        """Rows for hours before `before_hour` (all rows when None), removed from memory."""
        with self._lock:
            keys = [k for k in self._rows if before_hour is None or k[0] < before_hour]
            out = [(*k, *self._rows.pop(k)) for k in keys]
        return out


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), timeout=30)
    con.executescript(SCHEMA)
    return con


def write(con: sqlite3.Connection, rows: list[tuple]) -> int:
    """Add drained rows to their hour (a restart mid-hour adds to what is already there)."""
    con.executemany(
        """
        INSERT INTO traffic_hour (hour, route_class, status_class, bot, requests, bytes,
                                  lt100, lt500, lt2000, ge2000)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (hour, route_class, status_class, bot) DO UPDATE SET
            requests = requests + excluded.requests, bytes = bytes + excluded.bytes,
            lt100 = lt100 + excluded.lt100, lt500 = lt500 + excluded.lt500,
            lt2000 = lt2000 + excluded.lt2000, ge2000 = ge2000 + excluded.ge2000
        """,
        rows,
    )
    con.commit()
    return len(rows)


def fold(con: sqlite3.Connection, now: datetime, keep_days: int = HOURLY_DAYS) -> int:
    """Hourly rows older than `keep_days` are summed into daily rows and removed. A sum,
    not a sample: nothing is lost but the hour."""
    cutoff = (now.astimezone(UTC) - timedelta(days=keep_days)).strftime("%Y-%m-%dT%H")
    con.execute(
        """
        INSERT INTO traffic_day (day, route_class, status_class, bot, requests, bytes,
                                 lt100, lt500, lt2000, ge2000)
        SELECT substr(hour, 1, 10), route_class, status_class, bot, SUM(requests), SUM(bytes),
               SUM(lt100), SUM(lt500), SUM(lt2000), SUM(ge2000)
          FROM traffic_hour WHERE hour < ? GROUP BY 1, 2, 3, 4
        ON CONFLICT (day, route_class, status_class, bot) DO UPDATE SET
            requests = requests + excluded.requests, bytes = bytes + excluded.bytes,
            lt100 = lt100 + excluded.lt100, lt500 = lt500 + excluded.lt500,
            lt2000 = lt2000 + excluded.lt2000, ge2000 = ge2000 + excluded.ge2000
        """,
        (cutoff,),
    )
    folded = con.execute("DELETE FROM traffic_hour WHERE hour < ?", (cutoff,)).rowcount
    con.commit()
    return folded


def flush(counter: Counter, path: str | Path, now: datetime, *, all_hours: bool = False) -> int:
    """What the hourly timer (and shutdown) calls: finished hours to disk, then the fold."""
    rows = counter.drain(before_hour=None if all_hours else hour_of(now))
    if not rows:
        return 0
    con = connect(path)
    try:
        n = write(con, rows)
        fold(con, now)
    finally:
        con.close()
    return n


def report(path: str | Path, days: int = 1) -> list[tuple]:
    """The operator's view: per route class over the last `days`, requests (readers and
    crawlers), bytes, and the share answered under 500 ms. Published nowhere."""
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H")
    con = connect(path)
    try:
        return con.execute(
            """
            SELECT route_class, SUM(CASE WHEN bot = 0 THEN requests ELSE 0 END) AS readers,
                   SUM(CASE WHEN bot = 1 THEN requests ELSE 0 END) AS crawlers,
                   SUM(bytes), SUM(CASE WHEN status_class = '5xx' THEN requests ELSE 0 END),
                   ROUND(100.0 * SUM(lt100 + lt500) / MAX(SUM(requests), 1))
              FROM traffic_hour WHERE hour >= ? GROUP BY route_class ORDER BY 2 DESC
            """,
            (since,),
        ).fetchall()
    finally:
        con.close()


def start_timer(counter: Counter, path: str | Path, every: float = 3600.0) -> threading.Thread:
    """A daemon thread that flushes finished hours; the process's exit flushes the rest."""

    def loop():
        import time

        while True:
            time.sleep(every)
            try:
                flush(counter, path, datetime.now(UTC))
            except Exception as e:  # noqa: BLE001 — counting must never cost a page
                print(f"traffic flush failed ({type(e).__name__}: {e})")

    t = threading.Thread(target=loop, name="traffic-flush", daemon=True)
    t.start()
    return t
