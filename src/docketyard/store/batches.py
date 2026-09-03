"""One document at a time, committed in batches: the loop the passes over the record share.

Hoisted 2026-09-03 when `text/paginate.py` became a second copy of `citator load`'s loop and
`text/load.py` was about to be a third. Two of the three passes run on it; the citator's own
loop in `cli._citator` still commits per document and counts every failure kind per document
(`docs/deferred.md`, 2026-09-03). The shape, and why each part is there:

- THE COMMIT IS PER BATCH. Measured in WAL mode on NVMe: a commit per row costs 1.2 ms a row
  and a commit per 200 rows 0.028 ms, so over ~74k documents the first is minutes of fsync
  where the second is seconds — and every commit is a WAL transaction Litestream ships. The
  write lock is held for one batch of point writes, tens of milliseconds, against the 30 s
  the poller waits. A kill loses at most one batch, and a restartable pass re-derives it.

  THE TRANSACTION IS OPENED EXPLICITLY. Python's sqlite3 begins one implicitly before DML
  only; a SAVEPOINT issued outside a transaction is the OUTERMOST savepoint, and releasing
  it is a COMMIT (SQLite's documented rule). The first version of this loop did exactly
  that and committed per document while its docstring claimed batches (code review,
  2026-09-03, reproduced: `con.in_transaction` was False after RELEASE and a second
  connection saw the row). `BEGIN` first, and the savepoint nests.
- THE ROLLBACK IS PER DOCUMENT. A SAVEPOINT around each one keeps what a per-document commit
  gave: a document the store refuses (`IntegrityError`), or that the writer refuses on what
  it finds in the store (any other exception), is undone alone and the pass goes on, counted
  under `failed`. Only the store's own trouble is not a property of the document:
- THE STORE ITSELF FAILING ABORTS THE PASS. An `OperationalError` — the lock not released in
  the busy timeout, a disk error — with a 30 s timeout, counted per document, would make
  every remaining document wait, fail and be counted, for hours, under an exit status that
  said nothing. The pass stops, the open batch is rolled back, counted under `aborted`.
- AN ITEM THAT IS AN ERROR IS COUNTED, NOT RAISED. A reader yields `(label, thing)`, and
  `thing` may be the exception that stopped it being made — malformed input is the reader's
  finding, and the loop counts it under `unreadable` beside the store's own outcomes.
  `walk` is that reader for the sharded directories every pass reads.
"""

import sqlite3
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import TypeVar

COMMIT_EVERY = 200
LOG_EVERY = 2000  # items between progress lines

T = TypeVar("T")


def walk(root: Path, read: Callable[[Path], T]) -> Iterator[tuple[str, T | Exception]]:
    """Every file under `<root>/<xx>/<name>.json`, shard by shard, in a fixed order — so a
    restart walks the same sequence. The root's own files (`_manifest.json`) are not items.
    `read` turns a path into an item or raises; `OSError` and `ValueError` (which
    `Unreadable` and `json.JSONDecodeError` both are) are yielded as the item."""
    for shard in sorted(p for p in root.iterdir() if p.is_dir()):
        for path in sorted(shard.glob("*.json")):
            label = f"{shard.name}/{path.name[:12]}"
            try:
                yield label, read(path)
            except (OSError, ValueError) as e:
                yield label, e


def run(
    con,
    items: Iterable[tuple[str, object]],
    one: Callable[[object], str],
    *,
    log=print,
    commit_every: int = COMMIT_EVERY,
) -> Counter:
    """`one(thing)` returns the outcome word to count. Returns the counts: one key per
    outcome, plus `unreadable`, `failed` and `aborted` as above."""
    totals: Counter = Counter()
    since_commit = seen = 0
    for label, thing in items:
        seen += 1
        if seen % LOG_EVERY == 0:
            log(f"  {dict(totals)}")
        if isinstance(thing, Exception):
            log(f"  unreadable {label}: {thing}")
            totals["unreadable"] += 1
            continue
        try:
            if not con.in_transaction:
                con.execute("BEGIN")  # or the savepoint below is the outermost, and RELEASE commits
            con.execute("SAVEPOINT document")
            try:
                outcome = one(thing)
            except sqlite3.OperationalError:
                raise  # the store, not the document
            except Exception as e:  # noqa: BLE001 — the document is refused, the pass goes on
                con.execute("ROLLBACK TO document")
                log(f"  failed {label}: {type(e).__name__} {e}")
                totals["failed"] += 1
                continue
            finally:
                con.execute("RELEASE document")
            since_commit += 1
            if since_commit >= commit_every:
                con.commit()
                since_commit = 0
        except sqlite3.OperationalError as e:
            con.rollback()
            log(f"  aborted at {label}: {type(e).__name__} {e}")
            totals["aborted"] += 1
            break
        totals[outcome] += 1
    con.commit()
    return totals
