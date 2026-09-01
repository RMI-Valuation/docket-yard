"""Hourly request counts with no identifier, ever (docs/traffic.md; the sentence on /privacy
the operator signed 2026-08-26).

The web tier counts in memory — route class, status class, bot or not, bytes, a latency
bucket — and forgets the request. Once an hour the counters are written to a separate
file, `traffic.sqlite`, beside the store and never into it: the store is the record of the
Board's proceedings and stays free of anything about readers, and the snapshot never sees
this file. No per-request row exists anywhere, at any point, even transiently on disk.

What is never here: an address or any hash of one, a User-Agent string, a referrer, a
query, a path, a docket or party or record id, a cookie, a session, a country — nor a
page's exact length, which would name the page in a quiet hour (sizes are rounded).
"""

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROUTE_CLASSES = (
    "home",
    "sheet",
    "record",
    "document",
    "party",
    "parties",
    "search",
    "week",
    "stats",
    "register",
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
# a page's exact length would name the page in an hour with one reader (sheets are
# deterministic for a store state): sizes are rounded up to this before they are summed
SIZE_GRAIN = 64 * 1024
# a crawler is a User-Agent that says so; the string is looked at in memory and never kept
# (the compose healthcheck's Python-urllib is one: it probes the home page every minute)
_BOT_MARKS = (
    "bot",
    "crawl",
    "spider",
    "slurp",
    "curl/",
    "wget",
    "python-requests",
    "python-urllib",
    "go-http",
)

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
    if path.startswith("/document/"):
        return "document"
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
    if path in ("/court", "/protective"):
        return "register"
    if path == "/cite":
        return "search"
    if path.startswith("/sitemap") or path == "/robots.txt":
        return "sitemap"
    if path.startswith("/data") or path in ("/api", "/llms.txt", "/openapi.json"):
        return "data"
    if path in TRUST or path.startswith("/about/"):
        return "trust"
    if path.startswith(("/subscribe", "/s/", "/ses/")):
        return "subscribe"
    if path.startswith("/static/"):
        return "static"
    return "other"


def is_bot(user_agent: str | None) -> bool:
    """A crawler is a User-Agent that says so; a missing one is a reader (a hardened
    browser or a privacy proxy strips it)."""
    ua = (user_agent or "").lower()
    return any(mark in ua for mark in _BOT_MARKS)


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
            row[1] += -(-max(size, 0) // SIZE_GRAIN) * SIZE_GRAIN  # rounded up, never exact
            row[2 + bucket] += 1

    def drain(self) -> list[tuple]:
        """Every row, removed from memory. Rows are additive on disk (an upsert), so the
        current hour may be drained too and finished later."""
        with self._lock:
            out = [(*k, *v) for k, v in self._rows.items()]
            self._rows.clear()
        return out

    def restore(self, rows: list[tuple]) -> None:
        """Give drained rows back (a write failed): nothing is lost, only delayed."""
        with self._lock:
            for hour, route, status, bot, *nums in rows:
                row = self._rows.setdefault((hour, route, status, bot), [0, 0, 0, 0, 0, 0])
                for i, n in enumerate(nums):
                    row[i] += n


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), timeout=30)
    con.execute("PRAGMA journal_mode = WAL")  # the operator's report never blocks a flush
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


def flush(counter: Counter, path: str | Path, now: datetime) -> int:
    """What the hourly timer and the shutdown call: everything counted so far to disk (the
    upsert makes a partial hour safe to write and finish later), then the fold. The
    counter is drained only once the file is open, and refilled if the write fails."""
    con = connect(path)
    rows = counter.drain()
    try:
        if rows:
            write(con, rows)
        fold(con, now)
    except Exception:
        counter.restore(rows)
        raise
    finally:
        con.close()
    return len(rows)


def report(path: str | Path, days: int = 1, now: datetime | None = None) -> list[tuple]:
    """The operator's view: per route class over the last `days`, requests (readers and
    crawlers), bytes, and the share answered under 500 ms. Published nowhere.

    `now` is the end of the window, defaulting to the clock. The digest passes its own, so
    the table it prints covers the week its subject line names — they were computed from
    two different instants, which is harmless in a pass and made the digest impossible to
    test against a fixed date (2026-09-01)."""
    since = (now or datetime.now(UTC)) - timedelta(days=days)
    con = connect(path)
    try:
        return con.execute(
            """
            WITH rows AS (
                SELECT route_class, status_class, bot, requests, bytes, lt100, lt500
                  FROM traffic_hour WHERE hour >= ?
                UNION ALL
                SELECT route_class, status_class, bot, requests, bytes, lt100, lt500
                  FROM traffic_day WHERE day >= ?
            )
            SELECT route_class, SUM(CASE WHEN bot = 0 THEN requests ELSE 0 END) AS readers,
                   SUM(CASE WHEN bot = 1 THEN requests ELSE 0 END) AS crawlers,
                   SUM(bytes), SUM(CASE WHEN status_class = '5xx' THEN requests ELSE 0 END),
                   ROUND(100.0 * SUM(lt100 + lt500) / MAX(SUM(requests), 1))
              FROM rows GROUP BY route_class ORDER BY 2 DESC
            """,
            (since.strftime("%Y-%m-%dT%H"), since.strftime("%Y-%m-%d")),
        ).fetchall()
    finally:
        con.close()


DIGEST_DAY = 0  # Monday, UTC
DIGEST_HOUR = 6  # after the last hourly flush of the week has landed
DIGEST_GAP_DAYS = 6  # never twice in a week, however many passes run on a Monday


def digest_text(path: str | Path, days: int = 7, now: datetime | None = None) -> str:
    """The weekly summary the operator reads by email: the same table `docketyard traffic`
    prints, over the last `days`, and the totals. Numbers by kind of page only — nothing
    in it names a reader, a page or a docket (docs/traffic.md)."""
    rows = report(path, days=days, now=now)
    lines = [
        f"Docket Yard traffic, last {days} days (readers = no crawler User-Agent; probes and",
        "monitors count as readers). No identifiers are kept, so this is all there is.",
        "",
        f"{'route':10s} {'readers':>8s} {'crawlers':>9s} {'MB':>8s} {'5xx':>5s} {'<500ms':>7s}",
    ]
    readers = crawlers = errors = 0
    size = 0.0
    for route, r, c, b, e, fast in rows:
        lines.append(f"{route:10s} {r:8d} {c:9d} {b / 1e6:8.1f} {e:5d} {fast:6.0f}%")
        readers, crawlers, errors, size = readers + r, crawlers + c, errors + e, size + b
    lines += [
        "",
        f"total      {readers:8d} {crawlers:9d} {size / 1e6:8.1f} {errors:5d}",
        "",
        "Sent by the poller once a week (docs/traffic.md § The weekly digest). Nothing is",
        "published; the counts stay on the instance.",
    ]
    return "\n".join(lines) + "\n"


def _digest_state(con: sqlite3.Connection) -> str | None:
    con.execute("CREATE TABLE IF NOT EXISTS traffic_digest (sent_at TEXT NOT NULL)")
    row = con.execute("SELECT MAX(sent_at) FROM traffic_digest").fetchone()
    return row[0] if row else None


def digest_due(path: str | Path, now: datetime) -> bool:
    """Monday from DIGEST_HOUR UTC, once: the poller asks after every pass, so a pass that
    misses the hour still sends that day, and a Monday with many passes sends one."""
    if now.weekday() != DIGEST_DAY or now.hour < DIGEST_HOUR:
        return False
    con = connect(path)
    try:
        last = _digest_state(con)
    finally:
        con.close()
    if last is None:
        return True
    return datetime.fromisoformat(last) <= now - timedelta(days=DIGEST_GAP_DAYS)


def send_digest(path: str | Path, sender, to: str, now: datetime, log=print) -> bool:
    """The digest by email if it is due and can be sent; True when one went out. The mark
    is written only after the provider accepted it, so a failed send is retried next pass."""
    if not to or sender is None or not Path(path).exists() or not digest_due(path, now):
        return False
    from docketyard.alerts.mail import Outbound  # the mail module imports nothing from here

    subject = f"Docket Yard traffic, week to {now.date().isoformat()}"
    sender.send(Outbound(to=to, subject=subject, text=digest_text(path, now=now)))
    con = connect(path)
    try:
        _digest_state(con)
        con.execute("INSERT INTO traffic_digest (sent_at) VALUES (?)", (now.isoformat(),))
        con.commit()
    finally:
        con.close()
    log(f"traffic digest sent ({subject})")
    return True


def seconds_to_next_hour(now: datetime) -> float:
    nxt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return (nxt - now).total_seconds() + 5  # a few seconds past the boundary


def start_timer(counter: Counter, path: str | Path) -> threading.Thread:
    """A daemon thread that flushes just after every hour boundary; the process's exit
    flushes what is left. A crash between the two loses at most the current hour."""

    def loop():
        import time

        while True:
            time.sleep(seconds_to_next_hour(datetime.now(UTC)))
            try:
                flush(counter, path, datetime.now(UTC))
            except Exception as e:  # noqa: BLE001 — counting must never cost a page
                print(f"traffic flush failed ({type(e).__name__}: {e})")

    t = threading.Thread(target=loop, name="traffic-flush", daemon=True)
    t.start()
    return t
