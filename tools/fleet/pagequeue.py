#!/usr/bin/env python3
"""The page queue: leased work for the LAN's readers (docs/compute-fleet.md).

One SQLite file holds every page a pass still owes, who holds it, and what came back. A
worker CLAIMS a few pages under a lease, reads them, and posts each result or failure; a
lease that expires — the worker died, the box went away, the operator sat down at it —
returns the page to the queue by itself. Nothing is lost when a process dies, which is the
property the 2026-09-06 `dots` run lacked: its server died at page 8,839 of 41,688 and the
driver walked the remaining 32,849 pages against a closed port, wrote every document as
`failed`, and exited 0.

A PASS IS A KEY. `dots` means dots.mocr 1.5 at 200 DPI, and a worker claiming for `dots`
must declare exactly that key (ADR 0023: the engine and the render are the reading's
identity; ADR 0024 § Owed 1: the producer declares itself). A worker on another box with
another engine build is another pass, never a quiet substitute — the pick rule compares
readings by key, and a key that meant two engines is a false number on a page.

THE OUTPUT IS UNCHANGED. `collect` writes the same reading documents `ocr_wave.py dots`
wrote, one per document under `<out>/dots/<xx>/<sha>.json` in the loader's shape
(`docketyard/text/load.py`), once every page of the document is terminal, through the same
`dots_page` the driver uses (each pass names its page builder: `tabular` writes under
`<out>/hunyuan-tabular` through `hunyuan_page`). `ran_at` is the moment of collection,
written once. The root's `_manifest.json` names every producer that read for it. The
loader, the rsync and the roots' order are as before.

    python3 pagequeue.py --db Q seed --pass dots --out /data/docketyard/ocr  # from the route root
    python3 pagequeue.py --db Q status
    python3 pagequeue.py --db Q reap                        # expire dead leases; claim does too
    python3 pagequeue.py --db Q collect --out /data/docketyard/ocr
    python3 pagequeue.py --db Q fail --job N --error '...' [--page-owned]  # an operator's call

Standard library only. `Queue` is the whole protocol; `queue_server.py` puts the six calls a
worker makes over HTTP for a machine that does not hold the file, and `RemoteQueue` is that
machine's client, with the same six methods and nothing else.
"""

import argparse
import calendar
import hashlib
import http.client
import json
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "rmi-ai-machine"))

from ocr_wave import (  # noqa: E402 — the driver's keys, roots, page builders and clock
    DOTS,
    HUNYUAN,
    PAGE_OWNED,
    ROOTS,
    dots_page,
    hunyuan_page,
    now,
    page_list,
)


class Unloadable(Exception):
    """A pass whose readings the store would refuse. Raised at the SEED, before any machine
    time is spent, because the loader's refusal comes hours later and per document."""


STATES = ("pending", "leased", "done", "failed")
HEX64 = frozenset("0123456789abcdef")

PASSES = {
    # pass -> the reading key a worker must declare; which routed class it reads; the roots a
    # re-read of a document invalidates besides its own (a second reading names the primary
    # it was measured against, and a re-read primary is not that text); and the page bound,
    # which belongs to the pass so `oversize` means one thing on every node; and `page`, the
    # one function that turns a worker's raw answer into the engine page and its text
    "dots": {
        "key": DOTS,  # the driver's own constant: one key, never two copies
        "role": "primary",
        "payload_kind": "dots.mocr.json",
        "class": "degraded",
        "seeded_from": "route",
        "route_root": ROOTS["route"],
        "root": ROOTS["dots"],
        "invalidates": ("second",),
        "max_megapixels": 6.0,
        "page": dots_page,
    },
    # ocr-plan.md decision 6, built 2026-09-15: HunyuanOCR-1.5 in-process through transformers,
    # at the router's 150 DPI (the benchmark's pages were 150). No second reading is measured
    # against it, so a re-read invalidates nothing else. 6 MP: measured 2026-09-15 over the
    # 26,294 tabular pages at 150 DPI, median 2.1 MP, p99 2.4, 29 pages over 6
    "tabular": {
        "key": HUNYUAN,
        "role": "primary",
        "payload_kind": "hunyuan-ocr.json",
        "class": "tabular",
        "seeded_from": "route",
        "route_root": ROOTS["route"],
        "root": ROOTS["tabular"],
        "invalidates": (),
        "max_megapixels": 6.0,
        "page": hunyuan_page,
    },
    # The text-layer re-read (docs/research/text-quality/, the operator 2026-09-18). The pages
    # are flagged live text-layer primaries, which this project has never routed — the router
    # takes `image_only_documents` only — so `class` is None and the pass is seeded from a page
    # list instead of the route root (`seed_from_list`). Two consequences follow from that and
    # are the reason this is its own pass rather than more pages for `dots`:
    #
    #   - `role` is `second`, not `primary`. `document_text_one_primary` is UNIQUE per live
    #     page and every one of these pages already holds a text-layer primary, so a primary
    #     here could not load without superseding the publisher's own text layer. Whether it
    #     ever should is the operator's, deferred 2026-09-18 with the readings in hand.
    #   - the key is DOTS, unchanged: same engine, same version, same render, so it IS the same
    #     reading. `document_text_live` is unique on (document, page, method, method_version,
    #     render_profile) and does NOT carry the role, so it does not keep the two passes apart
    #     — it makes it impossible for one page to hold both, and the loader then refuses the
    #     whole document ("a reading does not change role by being posted again"). What keeps
    #     them apart is that no document is both image-only and text-layer, which nothing in
    #     the store, the queue or these tests asserts (schema-critic, 2026-09-18).
    #
    # ITS PAGES ARE ROUTED FIRST, by `ocr_wave.py route-list` (the operator, 2026-09-18). They
    # must be: `text/load.py` refuses an `ocr` reading whose page names no routed class and
    # `document_text`'s own CHECK refuses the row (ADR 0021 D4), so an unrouted re-read would
    # have been read, written and thrown away. `class` is None because no single class selects
    # these pages — the list does — so each page carries its OWN class from the route document,
    # and the routes live apart from the wave's under `reread_route` so `seed_pass` never pulls
    # a text-layer document into `dots`.
    "reread": {
        "key": DOTS,
        "role": "second",
        "payload_kind": "dots.mocr.json",
        "class": None,
        "seeded_from": "list",
        "route_root": ROOTS["reread_route"],
        "root": ROOTS["reread"],
        "invalidates": (),
        "max_megapixels": 6.0,
        "page": dots_page,
    },
}

# A failure's reason says whose it is. `page:` is the page's own — a cut answer, an oversize
# sheet, a page that will not rasterise, a timeout with the server healthy — and is final:
# the document is whole with it failed. Anything else (`server:`, `blob:`, `lease`,
# `operator:`) is not the page's, and a document holding one is re-read at the next seed.
# It is a prefix, agreed by convention among the writers in this directory; a column with a
# CHECK would be the stronger form and is recorded as owed in docs/deferred.md. `PAGE_OWNED`
# is `ocr_wave.PAGE_OWNED`, imported above, because `ocr_wave.failure_reason` is the one
# classifier that turns these strings into the store's reason codes (migration 0031).

SCHEMA = """
CREATE TABLE IF NOT EXISTS job (
    job_id          INTEGER PRIMARY KEY,
    pass            TEXT NOT NULL,
    document_sha256 TEXT NOT NULL,
    page_no         INTEGER NOT NULL,
    state           TEXT NOT NULL CHECK (state IN ('pending', 'leased', 'done', 'failed')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    lease_owner     TEXT,
    lease_until     REAL,
    error           TEXT,
    created_at      TEXT NOT NULL,
    finished_at     TEXT,
    UNIQUE (pass, document_sha256, page_no)
);
CREATE INDEX IF NOT EXISTS job_claim ON job (pass, state, document_sha256, page_no);
CREATE INDEX IF NOT EXISTS job_leased ON job (lease_until) WHERE state = 'leased';
CREATE INDEX IF NOT EXISTS job_finished ON job (pass, finished_at);
CREATE TABLE IF NOT EXISTS result (
    job_id      INTEGER PRIMARY KEY REFERENCES job (job_id),
    worker      TEXT NOT NULL,
    raw         TEXT NOT NULL,
    finished_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS result_worker ON result (worker);
CREATE TABLE IF NOT EXISTS worker (
    name       TEXT PRIMARY KEY,
    pass       TEXT NOT NULL,
    producer   TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collected (
    pass            TEXT NOT NULL,
    document_sha256 TEXT NOT NULL,
    ran_at          TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    pages_read      INTEGER NOT NULL,
    pages_failed    INTEGER NOT NULL,
    PRIMARY KEY (pass, document_sha256)
);
"""


class KeyMismatch(Exception):
    """A worker declared a key that is not the pass's key."""


# WHOSE FAULT A BLOB MISS IS — ADR 0025's addendum, proposals 5 and 6 (Accepted 2026-09-19).
# Three classes and not one, because the queue's failure grammar already turns on whose fault a
# thing is and each of these deserves a different answer from a worker. They live HERE, beside
# the client that raises them, so the coordinator and both workers read one definition: the
# server maps them onto status codes and `RemoteQueue.blob` maps the codes back.
class BlobMissing(Exception):
    """Absent from the mirror AND from the store: the DOCUMENT's. The page goes back unspent
    and the document is not counted whole."""


class BlobUnavailable(Exception):
    """The fetch could not be made — no credential, a refused one, a broken connection. The
    ENVIRONMENT's, so a worker must stop rather than spend pages on it: every page in the
    fleet would fail the same way, and a worker that merely retried would loop."""


class BlobCorrupt(Exception):
    """The store answered with bytes that are not the sha asked for: the STORE's, and the one
    failure here worth an alarm. Never cached, never served (ADR 0002: the sha is identity)."""


class Queue:
    def __init__(self, path: Path, *, readonly: bool = False, shared: bool = False):
        """`readonly` opens an existing file and only that: a monitor pointed at the wrong
        path must fail, not create an empty queue and report that nothing is owed. `shared`
        lets one connection serve a threaded server (its calls are then serialised by the
        caller's lock); the alternative, one connection per request, never hit a cache."""
        kw = {"timeout": 60, "isolation_level": None, "check_same_thread": not shared}
        if readonly:
            if not path.exists():
                raise FileNotFoundError(f"no queue at {path}")
            self.con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, **kw)
        else:
            self.con = sqlite3.connect(path, **kw)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA busy_timeout=60000")
        if not readonly:
            self.con.execute("PRAGMA journal_mode=WAL")
            self.con.executescript(SCHEMA)

    @contextmanager
    def tx(self):
        """One write transaction, taken immediately so two workers serialise on the lock."""
        self.con.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.con.execute("ROLLBACK")
            raise
        self.con.execute("COMMIT")

    # --- workers ------------------------------------------------------------------------

    def register(self, name: str, pass_: str, producer: dict) -> None:
        """A worker says what it is. Refused unless its key IS the pass's key."""
        want = PASSES[pass_]["key"]
        got = {k: producer.get(k) for k in want}
        if got != want:
            raise KeyMismatch(f"pass {pass_!r} is {want}, worker declared {got}")
        self.con.execute(
            "INSERT INTO worker (name, pass, producer, first_seen, last_seen) VALUES (?,?,?,?,?)"
            " ON CONFLICT (name) DO UPDATE SET pass = excluded.pass,"
            " producer = excluded.producer, last_seen = excluded.last_seen",
            (name, pass_, json.dumps(producer, sort_keys=True), now(), now()),
        )

    # --- the lease ----------------------------------------------------------------------

    def _reap(self) -> int:
        """Inside a transaction: every lease past its time goes back to pending, or to failed
        if that was the last attempt."""
        return self.con.execute(
            "UPDATE job SET"
            " state = CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'pending' END,"
            " finished_at = CASE WHEN attempts >= max_attempts THEN ? END,"
            " error = CASE WHEN attempts >= max_attempts"
            "   THEN 'lease expired on attempt ' || attempts ELSE error END,"
            " lease_owner = NULL, lease_until = NULL"
            " WHERE state = 'leased' AND lease_until < ?",
            (now(), time.time()),
        ).rowcount

    def reap(self) -> int:
        with self.tx():
            return self._reap()

    def claimable(self, pass_: str) -> int:
        """How many pages a `claim` could lease now: pending with an attempt left, or leased
        past its time with one left (the reap `claim` runs first would return it). Read-only.
        A gate asks this before it starts a worker: starting one against an empty queue is
        what loaded a model and relaunched six workers a minute for nothing (2026-09-11)."""
        return self.con.execute(
            "SELECT COUNT(*) FROM job WHERE pass = ? AND attempts < max_attempts"
            " AND (state = 'pending' OR (state = 'leased' AND lease_until < ?))",
            (pass_, time.time()),
        ).fetchone()[0]

    def claim(self, worker: str, pass_: str, n: int, lease_seconds: int) -> list[dict]:
        """Up to `n` pending pages, leased to `worker`. Atomic: two workers never hold one.
        Every claim reaps first, in the same transaction, so a dead worker's pages return
        without an operator. An attempt is spent at claim; `release` refunds it for a page
        never started."""
        with self.tx():
            self._reap()
            rows = self.con.execute(
                "SELECT job_id, document_sha256, page_no, attempts FROM job"
                " WHERE pass = ? AND state = 'pending' AND attempts < max_attempts"
                " ORDER BY document_sha256, page_no LIMIT ?",
                (pass_, n),
            ).fetchall()
            until = time.time() + lease_seconds
            self.con.executemany(
                "UPDATE job SET state = 'leased', attempts = attempts + 1,"
                " lease_owner = ?, lease_until = ? WHERE job_id = ?",
                [(worker, until, r["job_id"]) for r in rows],
            )
            self.con.execute("UPDATE worker SET last_seen = ? WHERE name = ?", (now(), worker))
        return [dict(r) for r in rows]

    def extend(self, worker: str, job_ids: list[int], lease_seconds: int) -> None:
        until = time.time() + lease_seconds
        self.con.executemany(
            "UPDATE job SET lease_until = ? WHERE job_id = ? AND lease_owner = ?"
            " AND state = 'leased'",
            [(until, j, worker) for j in job_ids],
        )
        self.con.execute("UPDATE worker SET last_seen = ? WHERE name = ?", (now(), worker))

    def release(self, worker: str, job_ids: list[int]) -> None:
        """Leased pages the worker never started, given back with their attempt refunded.
        The page in flight when the server died is not released but `fail`ed, not finally,
        so its attempt stays spent — it may be the cause."""
        with self.tx():
            self.con.executemany(
                "UPDATE job SET state = 'pending', lease_owner = NULL, lease_until = NULL,"
                " attempts = attempts - 1 WHERE job_id = ? AND lease_owner = ?"
                " AND state = 'leased'",
                [(j, worker) for j in job_ids],
            )

    # --- results ------------------------------------------------------------------------

    def done(self, worker: str, job_id: int, raw: str) -> bool:
        """Records the engine's answer if the worker still holds the lease. An answer to an
        expired lease is dropped and `False` returned: another worker may hold the page."""
        with self.tx():
            own = self.con.execute(
                "SELECT 1 FROM job WHERE job_id = ? AND lease_owner = ? AND state = 'leased'",
                (job_id, worker),
            ).fetchone()
            if not own:
                return False
            self.con.execute(
                "INSERT OR REPLACE INTO result (job_id, worker, raw, finished_at) VALUES (?,?,?,?)",
                (job_id, worker, raw, now()),
            )
            self.con.execute(
                "UPDATE job SET state = 'done', finished_at = ?, lease_owner = NULL,"
                " lease_until = NULL, error = NULL WHERE job_id = ?",
                (now(), job_id),
            )
        return True

    def fail(self, worker: str, job_id: int, error: str, *, final: bool) -> None:
        """A page that did not read. `final` fails it now (a deterministic refusal: a cut
        answer, an oversize page); otherwise it goes back for another attempt if one is left,
        and fails if none is."""
        with self.tx():
            row = self.con.execute(
                "SELECT attempts, max_attempts FROM job WHERE job_id = ? AND lease_owner = ?"
                " AND state = 'leased'",
                (job_id, worker),
            ).fetchone()
            if not row:
                return
            failed = final or row["attempts"] >= row["max_attempts"]
            if final and not error.startswith(PAGE_OWNED):
                raise ValueError(f"a final failure must be the page's own: {error!r}")
            self.con.execute(
                "UPDATE job SET state = ?, finished_at = ?, error = ?, lease_owner = NULL,"
                " lease_until = NULL WHERE job_id = ?",
                ("failed" if failed else "pending", now() if failed else None, error[:500], job_id),
            )

    # --- seeding and collecting ---------------------------------------------------------

    def seed(self, pass_: str, pages: list[tuple[str, int]], *, reread: set[str]) -> int:
        """Queues pages not already known. A document in `reread` is being read AGAIN — its
        reading document on disk was `failed` or partial — so its old jobs, results and
        collection go first; otherwise the unique key would keep the old answer."""
        with self.tx():
            for sha in sorted(reread):
                self.con.execute(
                    "DELETE FROM result WHERE job_id IN"
                    " (SELECT job_id FROM job WHERE pass = ? AND document_sha256 = ?)",
                    (pass_, sha),
                )
                self.con.execute(
                    "DELETE FROM job WHERE pass = ? AND document_sha256 = ?", (pass_, sha)
                )
                self.con.execute(
                    "DELETE FROM collected WHERE pass = ? AND document_sha256 = ?", (pass_, sha)
                )
            before = self.con.total_changes
            self.con.executemany(
                "INSERT OR IGNORE INTO job (pass, document_sha256, page_no, state, created_at)"
                " VALUES (?, ?, ?, 'pending', ?)",
                [(pass_, sha, no, now()) for sha, no in pages],
            )
            return self.con.total_changes - before

    def pages_held(self, pass_: str, sha: str) -> set[int] | None:
        """Every page of a document this pass has ever had a job for, or None if it has none.
        A list-seeded pass compares this with what the list now names: what the pass owes a
        document can grow between seeds, so `whole` alone would drop the new pages."""
        rows = self.con.execute(
            "SELECT page_no FROM job WHERE pass = ? AND document_sha256 = ?", (pass_, sha)
        ).fetchall()
        return {r["page_no"] for r in rows} if rows else None

    def known(self, pass_: str, sha: str) -> str | None:
        """What the queue knows of a document: `None` (nothing), `open` (pages not terminal),
        `whole` (collected, every failure the page's own) or `reread` (collected, and a page
        failed for a reason that was not the page's)."""
        if not self.con.execute(
            "SELECT 1 FROM job WHERE pass = ? AND document_sha256 = ? LIMIT 1", (pass_, sha)
        ).fetchone():
            return None
        if not self.con.execute(
            "SELECT 1 FROM collected WHERE pass = ? AND document_sha256 = ?", (pass_, sha)
        ).fetchone():
            return "open"
        foreign = self.con.execute(
            "SELECT 1 FROM job WHERE pass = ? AND document_sha256 = ? AND state = 'failed'"
            " AND error NOT LIKE ? LIMIT 1",
            (pass_, sha, PAGE_OWNED + "%"),
        ).fetchone()
        return "reread" if foreign else "whole"

    def collectable(self, pass_: str) -> list[str]:
        """Documents whose every page is terminal and that have not been written yet."""
        return [
            r[0]
            for r in self.con.execute(
                "SELECT document_sha256 FROM job j WHERE pass = ?"
                " AND NOT EXISTS (SELECT 1 FROM collected c WHERE c.pass = j.pass"
                "   AND c.document_sha256 = j.document_sha256)"
                " GROUP BY document_sha256"
                " HAVING SUM(state IN ('pending', 'leased')) = 0",
                (pass_,),
            )
        ]

    def pages_of(self, pass_: str, sha: str) -> list[dict]:
        return [
            dict(r)
            for r in self.con.execute(
                "SELECT j.job_id, j.page_no, j.state, j.error, r.raw, r.worker"
                " FROM job j LEFT JOIN result r USING (job_id)"
                " WHERE j.pass = ? AND j.document_sha256 = ? ORDER BY j.page_no",
                (pass_, sha),
            )
        ]

    def mark_collected(self, pass_: str, sha: str, doc: dict) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO collected VALUES (?,?,?,?,?,?)",
            (pass_, sha, doc["ran_at"], doc["outcome"], len(doc["pages"]), doc["pages_failed"]),
        )

    def producers(self, pass_: str) -> list[dict]:
        return [
            json.loads(r[0])
            for r in self.con.execute(
                "SELECT producer FROM worker WHERE pass = ? ORDER BY name", (pass_,)
            )
        ]

    # --- what the monitor reads ---------------------------------------------------------

    def status(self) -> dict:
        """Counts, rates and ages. `last_read_age_seconds` is the number the stall alarm
        watches — a page READ, not a page finished, because a fleet failing every page
        finishes pages briskly and that is the 2026-09-06 shape. Pages owed plus a growing
        age is a fleet that has stopped reading; pages owed plus an hour of more failures
        than reads is a fleet that is failing."""
        t = time.time()
        hour, day = now(t - 3600), now(t - 86400)
        passes: dict[str, dict] = {}
        for r in self.con.execute(
            "SELECT pass, state, COUNT(*) n FROM job GROUP BY pass, state ORDER BY 1, 2"
        ):
            passes.setdefault(r["pass"], {s: 0 for s in STATES})[r["state"]] = r["n"]
        for r in self.con.execute(
            "SELECT pass, MAX(CASE WHEN state = 'done' THEN finished_at END) last_read,"
            " SUM(state = 'done' AND finished_at >= ?) hd,"
            " SUM(state = 'failed' AND finished_at >= ?) hf,"
            " SUM(state = 'done' AND finished_at >= ?) dd,"
            " SUM(state = 'failed' AND finished_at >= ?) df"
            " FROM job WHERE state IN ('done', 'failed') GROUP BY pass",
            (hour, hour, day, day),
        ):
            c = passes[r["pass"]]
            c["last_read_at"] = r["last_read"]
            c["last_read_age_seconds"] = (
                round(t - _epoch(r["last_read"])) if r["last_read"] else None
            )
            c["last_hour"] = {"done": r["hd"], "failed": r["hf"]}
            c["last_day"] = {"done": r["dd"], "failed": r["df"]}
        for c in passes.values():
            c.setdefault("last_read_at", None)
            c.setdefault("last_read_age_seconds", None)
            c.setdefault("last_hour", {"done": 0, "failed": 0})
            c.setdefault("last_day", {"done": 0, "failed": 0})
            rate = c["last_hour"]["done"] / 3600
            c["pages_per_second"] = round(rate, 4)
            left = c["pending"] + c["leased"]
            c["eta_hours"] = round(left / rate / 3600, 1) if rate else None
        workers = []
        for r in self.con.execute(
            "SELECT w.name, w.pass, w.producer, w.first_seen, w.last_seen,"
            " (SELECT COUNT(*) FROM result r WHERE r.worker = w.name) done,"
            " (SELECT COUNT(*) FROM job j WHERE j.state = 'leased' AND j.lease_owner = w.name)"
            " holding FROM worker w ORDER BY w.name"
        ):
            w = dict(r)
            w["producer"] = json.loads(w["producer"])
            w["last_seen_age_seconds"] = round(t - _epoch(w["last_seen"]))
            workers.append(w)
        errors = [
            dict(r)
            for r in self.con.execute(
                "SELECT pass, error, COUNT(*) n FROM job WHERE state = 'failed'"
                " GROUP BY pass, error ORDER BY n DESC LIMIT 12"
            )
        ]
        collected = self.con.execute(
            "SELECT pass, COUNT(*) n, SUM(outcome = 'read') read, SUM(pages_failed) pages_failed"
            " FROM collected GROUP BY pass"
        ).fetchall()
        return {
            "at": now(),
            "passes": passes,
            "workers": workers,
            "errors": errors,
            "collected": {r["pass"]: dict(r) for r in collected},
        }


class RemoteQueue:
    """The six calls a worker makes, against `queue_server.py` on the node that holds the
    file. Same names, same arguments, same answers as `Queue`, so a worker holds either."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            self.url + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
        )
        try:  # longer than the server's 60 s busy wait, so a write that lands is reported
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            e.close()  # a response, not just an exception: close it
            if e.code == 409:
                raise KeyMismatch(detail) from e
            if e.code == 400:
                raise ValueError(detail) from e
            if e.code >= 500:
                raise RuntimeError(f"queue server {e.code}: {detail}") from e
            raise

    def register(self, name: str, pass_: str, producer: dict) -> None:
        self._post("/register", {"name": name, "pass": pass_, "producer": producer})

    def claimable(self, pass_: str) -> int:
        req = urllib.request.Request(
            f"{self.url}/pending?pass={urllib.parse.quote(pass_)}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return int(json.loads(resp.read())["claimable"])

    def claim(self, worker: str, pass_: str, n: int, lease_seconds: int) -> list[dict]:
        body = {"worker": worker, "pass": pass_, "n": n, "lease_seconds": lease_seconds}
        return self._post("/claim", body)["jobs"]

    def extend(self, worker: str, job_ids: list[int], lease_seconds: int) -> None:
        body = {"worker": worker, "job_ids": job_ids, "lease_seconds": lease_seconds}
        self._post("/extend", body)

    def release(self, worker: str, job_ids: list[int]) -> None:
        self._post("/release", {"worker": worker, "job_ids": job_ids})

    def done(self, worker: str, job_id: int, raw: str) -> bool:
        return self._post("/done", {"worker": worker, "job_id": job_id, "raw": raw})["accepted"]

    def fail(self, worker: str, job_id: int, error: str, *, final: bool) -> None:
        body = {"worker": worker, "job_id": job_id, "error": error, "final": final}
        self._post("/fail", body)

    # LONGER THAN IT WAS, because the node's answer now starts later. On a mirror miss the
    # coordinator downloads the WHOLE document from the store and verifies its hash before it
    # sends a byte — it must, or it would serve bytes it has not checked — so a large refetch
    # can be silent for minutes. At 300 s a worker gave up on a fetch the coordinator went on
    # to finish and cache, exiting 4 for a document that was about to be there (code review).
    BLOB_TIMEOUT = 1800

    def blob_into(self, sha: str, dest: Path) -> Path:
        """Stream the document from the node into `dest`, and return it.

        NOTHING IS BUFFERED, at either end. A document in this record reaches 1.07 GB and
        reading one into memory is what OOM-killed the instance on 2026-08-26; this path only
        became reachable for big documents when a pruned mirror stopped being a 404, so the
        worker's `resp.read()` had to go with the coordinator's (code review). The smallest
        box that leases pages has 8 GB.

        THE STATUS CODE IS THE CLASSIFICATION, and it is turned back into the three exceptions
        here so that neither worker reads an HTTP code. Before ADR 0025's addendum both workers
        matched `e.code == 404` themselves and re-raised everything else bare — so a 502 or 503
        escaped the per-page handlers entirely, killed the worker with a traceback, left the
        claim leased and recorded nothing. A restart then did it again: the fleet looped and no
        page was ever charged. That is the failure this mapping exists to end."""
        # THE WORKER CHECKS THE SHA TOO, though it came from the coordinator's own job table.
        # It is now a FILENAME on this machine (`args.scratch / f"doc-{sha}.pdf"`), which it was
        # not before this change, so a sha carrying path separators would write the download
        # outside the scratch directory. Reaching that needs an already-compromised
        # coordinator, which owns the worker anyway (security review rated it 2 and did not
        # report it) — but the guard is one line, at the boundary where this side stops
        # trusting the other, and the server has had the same one since it was written.
        if len(sha) != 64 or set(sha) - HEX64:
            raise BlobMissing(f"{sha!r} is not a sha256; nothing was asked for")
        req = urllib.request.Request(
            self.url + "/blob/" + sha, headers={"Authorization": f"Bearer {self.token}"}
        )
        digest = hashlib.sha256()
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with (
                urllib.request.urlopen(req, timeout=self.BLOB_TIMEOUT) as resp,
                dest.open("wb") as out,
            ):
                for chunk in iter(lambda: resp.read(1 << 20), b""):
                    out.write(chunk)
                    digest.update(chunk)
        except urllib.error.HTTPError as e:
            dest.unlink(missing_ok=True)
            detail = e.read().decode("utf-8", "replace")
            if e.code == 404:
                raise BlobMissing(detail) from e
            if e.code == 502:
                raise BlobCorrupt(detail) from e
            if e.code == 503:
                raise BlobUnavailable(detail) from e
            raise
        except (
            TimeoutError,
            urllib.error.URLError,
            ConnectionError,
            http.client.HTTPException,  # IncompleteRead: a body that stopped early
            OSError,
        ) as e:
            # the NODE is unreachable, which is the environment's in exactly the way a refused
            # credential is: every page would fail identically. `URLError` is an `OSError`, and
            # so is `ConnectionError`; all are named because none implies the others here.
            dest.unlink(missing_ok=True)
            raise BlobUnavailable(f"the node did not answer: {type(e).__name__}: {e}") from e
        # THE MIRROR HIT IS CHECKED HERE OR NOWHERE. The coordinator verifies what it FETCHES,
        # but it serves what the mirror already holds unchecked — and the mirror is filled by
        # `pull_blobs.py`, which skips an object whose SIZE matches and never compares a digest
        # (ingest review; migration 0018 warns about size-only comparison in writing). So a
        # wrong-but-same-size or bit-rotted mirror entry would be rendered, read and loaded as
        # that document's text with nothing raising. The sha IS the identity (ADR 0002), and
        # this is the only place in the fleet where both paths pass.
        got = digest.hexdigest()
        if got != sha:
            dest.unlink(missing_ok=True)
            raise BlobCorrupt(f"the node served {sha[:12]} with bytes hashing {got[:12]}")
        return dest

    def blob(self, sha: str) -> bytes:
        """The document's bytes, for a caller small enough not to care. `blob_into` is what a
        worker uses; this exists for the monitor and the tests, and holds one document."""
        with tempfile.TemporaryDirectory() as tmp:
            return self.blob_into(sha, Path(tmp) / sha).read_bytes()


def _epoch(iso: str) -> float:
    return calendar.timegm(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))


# --- the commands -------------------------------------------------------------------------


def seed_pass(q: Queue, pass_: str, out: Path, *, dry_run: bool = False) -> dict:
    """Every page the pass owes, from the route root. The queue decides for a document it
    knows: `whole` (collected, every failure the page's own) is done; `reread` (a page failed
    for a reason that was not the page's) is set aside — its file, and any reading measured
    against it — and every page of it goes back on the queue, because the loader takes a
    document's reading whole under one `ran_at`, and a `failed` on disk is what silenced
    9,915 documents on 2026-09-06. A file the queue does not know is the old driver's, which
    kept no reasons: whole only if it says `read` with no page failed."""

    spec = PASSES[pass_]
    if spec["seeded_from"] != "route":
        raise ValueError(f"{pass_} is seeded from a page list (--from), not the route root")
    route_root = out / ROOTS["route"]
    pages, reread = [], set()
    n = {"documents": 0, "pages": 0, "whole": 0, "set_aside": 0, "new": 0, "missing_reading": 0}
    for p in sorted(route_root.glob("*/*.json")):
        sha = p.stem
        route = json.loads(p.read_text(encoding="utf-8"))
        wanted = sorted(int(k) for k, v in route["pages"].items() if v["class"] == spec["class"])
        if not wanted:
            continue
        if not _decide(q, pass_, spec, out, sha, n, reread, dry_run=dry_run):
            continue
        pages += [(sha, no) for no in wanted]
    n["pages"] = len(pages)
    n["new"] = 0 if dry_run else q.seed(pass_, pages, reread=reread)
    return n


def _decide(
    q: Queue, pass_: str, spec: dict, out: Path, sha: str, n: dict, reread: set, *, dry_run: bool
) -> bool:
    """`seed_pass`'s verdict on one document, shared with `seed_from_list` so the two seeds
    cannot drift: True to queue its pages. Counts land in `n` and re-reads in `reread`."""
    from ocr_wave import shard  # noqa: PLC0415

    known = q.known(pass_, sha)
    if known == "open":
        return False  # already queued and not yet collected
    existing = shard(out / spec["root"], sha)
    if known == "whole" and existing.exists():
        n["whole"] += 1
        return False
    # `whole` with no reading document on disk is a restore whose queue is NEWER than its file
    # tree, or a file removed by hand. Counting it whole would silence the document for ever —
    # nothing else ever queues it again, and nothing ever collects it: the 2026-09-06 shape.
    # So it falls through to the re-read verdict below, which already tolerates a missing file.
    # Counted apart from `set_aside`, because nothing was partial and nothing was renamed: the
    # number is the operator's signal that a restore was skewed and a wave is about to be re-read
    if known == "whole":
        n["missing_reading"] += 1
    if known is None and existing.exists():
        # the old driver's file: whole only if it says so, since it kept no reasons
        doc = json.loads(existing.read_text(encoding="utf-8"))
        if doc.get("outcome") == "read" and not doc.get("pages_failed"):
            n["whole"] += 1
            return False
    if known in ("reread", "whole") or existing.exists():
        # the queue's verdict stands whether or not the file is still there: a walk
        # that renamed it and then aborted must not leave the document stranded
        n["set_aside"] += 1
        reread.add(sha)
        if not dry_run:
            # `root` is a directory NAME already; `invalidates` holds ROOTS KEYS. Mixing the
            # two was a latent KeyError for every pass whose key and directory differ: it never
            # fired for `dots` (ROOTS["dots"] == "dots") and would have crashed the first
            # re-seed of `tabular`, whose root is "hunyuan-tabular" (found by the re-read's
            # tests, 2026-09-18)
            for root in (spec["root"], *(ROOTS[k] for k in spec["invalidates"])):
                f = shard(out / root, sha)
                if f.exists():
                    f.rename(f.with_suffix(".json.superseded"))
    n["documents"] += 1
    return True


def _routed_pages(route_root: Path, sha: str) -> set[int]:
    """The pages a route document classifies, or the empty set if it has none. `unrouted` is a
    real class that loads (the router met the page and could not place it), so it counts."""
    from ocr_wave import shard  # noqa: PLC0415

    path = shard(route_root, sha)
    if not path.exists():
        return set()
    route = json.loads(path.read_text(encoding="utf-8"))
    return {int(k) for k, v in route.get("pages", {}).items() if v.get("class")}


def _page_routes(route_root: Path, sha: str) -> dict[int, dict]:
    """Each routed page's own route stanza, carrying the route document's OWN method and
    version rather than this module's constants — a document routed by an earlier version must
    say so, which is what makes the reading scorable (ADR 0007)."""
    from ocr_wave import shard  # noqa: PLC0415

    path = shard(route_root, sha)
    if not path.exists():
        return {}  # the caller skips the document; collect must not raise on a service loop
    route = json.loads(path.read_text(encoding="utf-8"))
    return {
        int(k): {
            "class": v["class"],
            "method": route["method"],
            "method_version": route["method_version"],
        }
        for k, v in route.get("pages", {}).items()
        if v.get("class")
    }


def seed_from_list(
    q: Queue,
    pass_: str,
    out: Path,
    pages_csv: Path,
    *,
    column: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Seed a pass from a page list instead of the route root, for pages this project never
    routed — the router reads `image_only_documents` only, and the text-layer re-read's pages
    are by definition not in one (docs/research/text-quality/).

    `pages_csv` is the queue builder's output (`tools/rmi-ai-machine/text_quality_queue.py`,
    gzipped or plain): a header, then a row per page with `sha` and `page`. `column` names a
    flag column that must be `1` for the row to be taken — `prose` for the operator's
    prose-first order. The per-document verdict is `seed_pass`'s, unchanged: a document already
    whole is left alone and a partial one is set aside and read again whole, because the loader
    takes a document's reading whole under one `ran_at`.

    ONLY THE LISTED PAGES ARE QUEUED. A reading document covers the pages its pass selected and
    no others — the wave's own `dots` reading holds the degraded pages of a document and leaves
    its clean ones to the text layer — so pages 3 and 9 of an eleven-page document are a
    complete reading of what this pass owes it. "Whole" above means every page this pass owes
    reached a terminal state, not every page of the PDF.
    """
    from ocr_wave import shard  # noqa: PLC0415

    spec = PASSES[pass_]
    if spec["seeded_from"] != "list":
        raise ValueError(f"{pass_} is seeded from the {spec['seeded_from']}, not a page list")
    if not spec.get("route_root"):
        # WHERE THE PAGES COME FROM AND WHETHER THEY ARE ROUTED ARE TWO QUESTIONS, and only the
        # second decides whether a reading can load: `text/load.py` refuses an `ocr` reading
        # whose page names no routed class, and `document_text`'s CHECK refuses the row
        # (ADR 0021 D4). Reading thousands of pages to write files nothing can take is the
        # failure mode this guard exists for, and it fires before any machine time is spent
        raise Unloadable(
            f"{pass_} writes `ocr` readings with no route, which text/load.py refuses"
            " (ADR 0021 D4): route the pages first. docs/compute-fleet.md § The text-layer"
            " re-read"
        )
    wanted = page_list(pages_csv, column)
    if not wanted:
        raise ValueError(f"{pages_csv} names no page" + (f" with {column} = 1" if column else ""))
    pages, reread = [], set()
    n = {
        "documents": 0,
        "pages": 0,
        "whole": 0,
        "set_aside": 0,
        "new": 0,
        "missing_reading": 0,  # `_decide` is shared, so both seeds must carry its counters
        "listed_pages": 0,
        "topped_up": 0,
        "unrouted_documents": 0,
        "unrouted_pages": 0,
    }
    route_root = out / spec["route_root"]
    for sha in sorted(wanted):
        n["listed_pages"] += len(wanted[sha])
        # A PAGE WITHOUT A ROUTE IS NOT QUEUED. Its reading would be refused by the loader
        # (ADR 0021 D4), so the page waits for `ocr_wave.py route-list` rather than being read
        # and thrown away; and a document with no route document at all is skipped whole. This
        # is also the disjointness guard the schema-critic asked for (2026-09-18): the wave's
        # routes are under a different root, so a document that is BOTH image-only and
        # text-layer cannot reach this pass through the wave's route document
        routed = _routed_pages(route_root, sha)
        if not routed:
            n["unrouted_documents"] += 1
            continue
        if missing := wanted[sha] - routed:
            n["unrouted_pages"] += len(missing)
            wanted[sha] &= routed
            if not wanted[sha]:
                continue
        # WHAT THIS PASS OWES A DOCUMENT IS NOT FIXED, which is where a list seed parts company
        # with a route seed: the route document settles a page's class once, but this list comes
        # from a score whose lexicon grows with the record and from a cut and a screen the
        # operator can move. So a document already `whole` may now be owed pages the queue has
        # never held, and taking `whole` at its word would drop them silently (schema-critic and
        # /code-review, 2026-09-18). A document owed a page it has never held is read AGAIN,
        # whole, because the loader takes a reading under one `ran_at` and a top-up would
        # strand it.
        held = q.pages_held(pass_, sha)
        if held is not None and wanted[sha] - held:
            n["topped_up"] += 1
            n["documents"] += 1
            reread.add(sha)
            if not dry_run:
                for root in (spec["root"], *(ROOTS[k] for k in spec["invalidates"])):
                    f = shard(out / root, sha)
                    if f.exists():
                        f.rename(f.with_suffix(".json.superseded"))
            # `held` is filtered too: a page held from an earlier seed is not necessarily
            # routed now, and an unrouted page must not ride back in on the top-up
            pages += [(sha, no) for no in sorted((held | wanted[sha]) & routed)]
            continue
        if not _decide(q, pass_, spec, out, sha, n, reread, dry_run=dry_run):
            continue
        pages += [(sha, no) for no in sorted(wanted[sha])]
    n["pages"] = len(pages)
    n["new"] = 0 if dry_run else q.seed(pass_, pages, reread=reread)
    return n


def collect_pass(q: Queue, pass_: str, out: Path) -> int:
    """Writes each collectable document's reading, with a `page_failures` entry per failed
    page whose reason is `ocr_wave.failure_reason`'s.

    A document holding a `page:` error that classifier does not know is SKIPPED: logged, left
    uncollected, and written by a later run once the word is named. Every other document in the
    batch is still collected — one unnamed word must not stall a wave. A page-owned failure is
    final in the queue, so naming a new kind is a code change rather than a retry."""
    from ocr_wave import (  # noqa: PLC0415
        _write,
        page_failure,
        reading_document,
        route_of,
        shard,
    )

    spec = PASSES[pass_]
    to_page = spec["page"]
    out_root = out / spec["root"]
    written = skipped = 0
    for sha in q.collectable(pass_):
        engine_pages, pages, failures = [], [], []
        # A PASS WITH NO CLASS OF ITS OWN takes each page's class from the route document: the
        # list chose the pages, so they are of every class, and a reading that named one would
        # be false on most of them. A routed pass names its class once, as before.
        # A MISSING OR INCOMPLETE ROUTE SKIPS THE DOCUMENT rather than raising: this runs as a
        # tmux service every ten minutes, and one such document used to abort the whole batch
        # and crash-loop it (/code-review, 2026-09-18). The pages stay in the queue and a later
        # run collects them once the route is there
        routes = {} if spec["class"] else _page_routes(out / spec["route_root"], sha)
        if not spec["class"] and not routes:
            print(f"  SKIPPED {sha[:12]}: no route document yet", flush=True)
            skipped += 1
            continue
        try:
            for r in q.pages_of(pass_, sha):
                if r["state"] != "done":
                    failures.append(page_failure(r["page_no"], r["error"]))
                    continue
                engine_page, text = to_page(r["page_no"], r["raw"])
                engine_pages.append(engine_page)
                page = {
                    "page_no": r["page_no"],
                    "text": text,
                    "member": f"engine/pages/{len(engine_pages) - 1}",
                }
                if spec["class"]:
                    page["route"] = route_of(spec["class"])
                elif r["page_no"] not in routes:
                    raise ValueError(f"page {r['page_no']} has no route")
                else:
                    page["route"] = routes[r["page_no"]]
                pages.append(page)
        except ValueError as e:  # a `page:` word nobody has named, or a page with no route
            print(f"  SKIPPED {sha[:12]}: {e}", flush=True)
            skipped += 1
            continue  # left uncollected: a later run writes it once the word is named
        doc = reading_document(
            sha,
            spec["key"],
            spec["role"],
            spec["payload_kind"],
            engine_pages,
            pages,
            page_failures=failures,
            outcome="read" if pages else "failed",
        )
        _write(shard(out_root, sha), doc)
        q.mark_collected(pass_, sha, doc)
        written += 1
    if skipped:
        print(
            f"  {skipped} documents left uncollected: a `page:` reason the classifier does not"
            f" know. Name it in ocr_wave.failure_reason and collect again.",
            flush=True,
        )
    if written:
        s = q.status()
        _write(
            out_root / "_manifest.json",
            {
                "key": spec["key"],
                "pass": pass_,
                "queue": s["passes"].get(pass_, {}),
                "collected": s["collected"].get(pass_, {}),
                "producers": q.producers(pass_),
                "written_at": now(),
            },
        )
    return written


def cmd_seed(args) -> int:
    from_list = PASSES[args.pass_]["seeded_from"] == "list"
    if not from_list and args.from_:
        print(f"{args.pass_} is seeded from the route root: drop --from")
        return 2
    if from_list and not args.from_:
        print(f"{args.pass_} is seeded from a page list: give it one with --from")
        return 2
    if args.column and not args.from_:
        print("--column names a column of --from")
        return 2
    q = Queue(args.db)
    if args.from_:
        n = seed_from_list(
            q, args.pass_, args.out, args.from_, column=args.column, dry_run=args.dry_run
        )
    else:
        n = seed_pass(q, args.pass_, args.out, dry_run=args.dry_run)
    verb = "would be " if args.dry_run else ""
    listed = f" from {n['listed_pages']} listed" if "listed_pages" in n else ""
    print(
        f"{args.pass_}: {n['documents']} documents, {n['pages']} pages{listed} {verb}queued"
        f" ({n['new']} new); {n['whole']} documents already whole; {n['set_aside']} partial or"
        f" failed reading documents {verb}set aside as .superseded"
        + (
            f"; {n['missing_reading']} the queue called whole with NO reading document on disk"
            " — the queue is newer than the file tree, and those documents are read again"
            if n.get("missing_reading")
            else ""
        )
    )
    return 0


def cmd_collect(args) -> int:
    written = collect_pass(Queue(args.db), args.pass_, args.out)
    print(f"{args.pass_}: {written} reading documents written under {args.out}")
    return 0


def cmd_status(args) -> int:
    print(json.dumps(Queue(args.db).status(), indent=1))
    return 0


def cmd_reap(args) -> int:
    print(f"{Queue(args.db).reap()} leases expired")
    return 0


def cmd_fail(args) -> int:
    """An operator's decision. `--page-owned` says the fault is the page's — a sheet that
    kills the engine, a scan nothing can read — and the document is whole with it failed;
    without it the failure is the operator's, and the document is re-read at a later seed."""
    q = Queue(args.db)
    prefix = f"{PAGE_OWNED} operator: " if args.page_owned else "operator: "
    n = q.con.execute(
        "UPDATE job SET state = 'failed', finished_at = ?, error = ?, lease_owner = NULL,"
        " lease_until = NULL WHERE job_id = ? AND state IN ('pending', 'leased')",
        (now(), (prefix + args.error)[:500], args.job),  # `fail`'s bound, and the store's
    ).rowcount
    print(f"job {args.job}: {'failed' if n else 'not pending or leased; unchanged'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", required=True, type=Path)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("seed")
    p.add_argument("--pass", dest="pass_", choices=PASSES, required=True)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--from",
        dest="from_",
        type=Path,
        help="seed from a page list (csv or csv.gz with `sha` and `page`) instead of the route"
        " root, for a pass whose pages were never routed. Required for such a pass, refused"
        " for a routed one",
    )
    p.add_argument(
        "--column",
        help="a flag column in --from that must be `1` for a row to be taken, e.g. `prose`",
    )
    p = sub.add_parser("collect")
    p.add_argument("--pass", dest="pass_", choices=PASSES, default="dots")
    p.add_argument("--out", required=True, type=Path)
    sub.add_parser("status")
    sub.add_parser("reap")
    p = sub.add_parser("fail")
    p.add_argument("--job", type=int, required=True)
    p.add_argument("--error", required=True)
    p.add_argument("--page-owned", action="store_true", help="the page's own fault: final")
    args = ap.parse_args()
    return {
        "seed": cmd_seed,
        "collect": cmd_collect,
        "status": cmd_status,
        "reap": cmd_reap,
        "fail": cmd_fail,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
