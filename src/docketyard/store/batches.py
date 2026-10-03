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
- THE LOCK IS WAITED OUT, THE STORE FAILING IS NOT. An `OperationalError` counted per
  document, with a 30 s timeout, would make every remaining document wait, fail and be
  counted, for hours, under an exit status that said nothing — so neither kind is. But the
  two are not the same trouble. A LOCK (`database is locked`) is someone else holding the
  write lock, and on this box that someone is Litestream's TRUNCATE checkpoint: the batch is
  rolled back — which hands the lock over, and is the part that matters — and replayed, up
  to `LOCK_RETRIES` times with a doubling wait, because the rollback left nothing behind for
  the replay to trip over. Anything else (a disk error, a read-only file) will not clear by
  waiting: the pass stops at once. Either way the open batch is rolled back, and a pass that
  really does stop is counted under `aborted`.
- AN ITEM THAT IS AN ERROR IS COUNTED, NOT RAISED. A reader yields `(label, thing)`, and
  `thing` may be the exception that stopped it being made — malformed input is the reader's
  finding, and the loop counts it under `unreadable` beside the store's own outcomes.
  `walk` is that reader for the sharded directories every pass reads.
"""

import sqlite3
import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import TypeVar

COMMIT_EVERY = 200
LOG_EVERY = 2000  # items between progress lines
LOCK_RETRIES = 5  # replays of ONE batch before the pass gives up; see `_with_retries`
LOCK_BACKOFF = 2  # seconds before the first replay, doubling: 2, 4, 8, 16, 32 — 62 in all

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


def _is_lock(e: sqlite3.OperationalError) -> bool:
    """Whether this is the write lock being held by someone else, rather than the store
    being broken. SQLite says `database is locked` (SQLITE_BUSY) or `database table is
    locked`; a disk I/O error, a read-only file and a corrupt page say none of those and
    must not be retried — retrying them is how a pass spends its retries on a failure that
    will never clear."""
    return "locked" in str(e).lower()


def _chunk(items: Iterable[tuple[str, object]], size: int) -> Iterator[list]:
    batch: list = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class _StoreTrouble(sqlite3.OperationalError):
    """The store's own failure, carrying the document it happened at. The batch is what gets
    rolled back and replayed, but a disk error is worth naming its document — `batch[-1]`
    would name whichever document the batch happened to end on.

    An `OperationalError` itself, so `under_lock` and `_is_lock` read it as what it wraps."""

    def __init__(self, label: str, cause: sqlite3.OperationalError):
        super().__init__(str(cause))
        self.label = label
        self.cause = cause


def under_lock(
    con, do, *, what: str, log=print, lock_retries: int = LOCK_RETRIES, sleep=time.sleep
):
    """Run `do()` — ONE whole transaction, begun and committed inside it — waiting out the
    write lock if someone else holds it. Returns what `do` returns; raises the last
    `OperationalError` when the retries run out, or at once when it is not a lock.

    THE ROLLBACK IS THE POINT, NOT THE SLEEP. Migration A's `text load` aborted seven times
    against Litestream's `checkpoint: mode=TRUNCATE err=database is locked` (2026-09-04,
    `deferred.md`): the two want the same write lock, our transaction is the one holding it,
    and the 30 s busy timeout expires without either giving way. Rolling back hands the lock
    over, so the checkpoint finishes in the first wait and the retry finds it free. A shell
    loop of twelve restarts was doing this by hand, one whole pass at a time.

    RETRYING IS SAFE BECAUSE THE ROLLBACK LEFT NOTHING. `do` must therefore be one
    transaction and must be replayable — deriving what it writes from the store as it now
    is, not from anything the failed attempt left behind. Both callers are: the batch loop
    below re-reads nothing (`one` sees the store it saw), and `search.rebuild_pages` re-runs
    one batch of inserts it still holds in memory.

    It lives HERE, beside the loop that first needed it, so "how this project waits out the
    write lock" has one definition and one backoff rather than one per pass.
    """
    for attempt in range(lock_retries + 1):
        try:
            return do()
        except sqlite3.OperationalError as e:
            con.rollback()  # gives the lock up, which is what the other writer is waiting for
            if not _is_lock(e) or attempt == lock_retries:
                raise
            wait = LOCK_BACKOFF * 2**attempt
            log(
                f"  write lock busy at {getattr(e, 'label', what)} ({e}); rolled back,"
                f" retrying {what} in {wait}s ({attempt + 1} of {lock_retries})"
            )
            sleep(wait)
    raise AssertionError("unreachable: the last attempt returns or raises")


def _apply(con, batch: list, one: Callable[[object], str], log) -> Counter:
    """One batch in ONE transaction: applied whole and committed, or raised out with
    nothing written. Returns the batch's own counts, which the caller folds in only when
    the commit lands — so a batch replayed after a lock is not counted twice.

    The commit is inside, because SQLITE_BUSY is as likely there as at the first write —
    and `at` names the commit rather than the last document when it is, because "aborted at
    the last file in the batch" would send the operator to a file that is not the trouble.

    THE LOG LINES ARE HELD UNTIL THE COMMIT LANDS, for the reason the counts are: a batch
    replayed after a lock re-derives them, and a log showing a document refused six times
    beside a total of one is a log that has to be explained away (code review, 2026-09-04).
    """
    counts: Counter = Counter()
    lines: list[str] = []
    at = batch[0][0]
    try:
        con.execute("BEGIN")  # or the savepoint below is the outermost, and RELEASE commits
        for label, thing in batch:
            at = label
            if isinstance(thing, Exception):
                lines.append(f"  unreadable {label}: {thing}")
                counts["unreadable"] += 1
                continue
            con.execute("SAVEPOINT document")
            try:
                outcome = one(thing)
            except sqlite3.OperationalError:
                raise  # the store, not the document
            except Exception as e:  # noqa: BLE001 — the document is refused, the pass goes on
                con.execute("ROLLBACK TO document")
                lines.append(f"  failed {label}: {type(e).__name__} {e}")
                counts["failed"] += 1
                continue
            finally:
                con.execute("RELEASE document")
            counts[outcome] += 1
        at = f"the commit after {at}"
        con.commit()
    except sqlite3.OperationalError as e:
        raise _StoreTrouble(at, e) from e
    for line in lines:
        log(line)
    return counts


def run(
    con,
    items: Iterable[tuple[str, object]],
    one: Callable[[object], str],
    *,
    log=print,
    commit_every: int = COMMIT_EVERY,
    lock_retries: int = LOCK_RETRIES,
    sleep=time.sleep,
) -> Counter:
    """`one(thing)` returns the outcome word to count. Returns the counts: one key per
    outcome, plus `unreadable`, `failed` and `aborted` as above.

    A batch is a batch of ITEMS, not of applied documents — an unreadable one occupies a
    place in it and touches nothing — because the batch is the unit that gets replayed.
    """
    totals: Counter = Counter()
    seen = 0
    for batch in _chunk(items, commit_every):
        counts = _with_retries(con, batch, one, log, lock_retries, sleep)
        if counts is None:
            totals["aborted"] += 1
            break
        totals += counts
        before, seen = seen, seen + len(batch)
        if seen // LOG_EVERY != before // LOG_EVERY:
            log(f"  {dict(totals)}")
    con.commit()
    return totals


def _with_retries(con, batch: list, one, log, lock_retries: int, sleep) -> Counter | None:
    """The batch's counts, or None when the pass must stop. `under_lock` does the waiting;
    this turns the give-up into the `aborted` the passes report rather than an exception."""
    try:
        return under_lock(
            con,
            lambda: _apply(con, batch, one, log),
            what=f"{len(batch)} documents",
            log=log,
            lock_retries=lock_retries,
            sleep=sleep,
        )
    except sqlite3.OperationalError as e:
        cause = getattr(e, "cause", e)
        log(f"  aborted at {getattr(e, 'label', batch[0][0])}: {type(cause).__name__} {e}")
        return None
