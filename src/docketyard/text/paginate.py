"""The pagination pass: one row per document in `document_pagination` (migration 0018).

`page_count` is the DENOMINATOR of the coverage arithmetic — unread pages are the count
minus the readings — and the table is the one new table the snapshot publishes (ADR 0022
D3). So this runs as ITS OWN COMMAND and not inside `migrate` (`docs/ocr-migration.md`
item 12): `migrate` is a service the whole stack blocks on and every migration to date runs
in one transaction, so ~74k rows written inside it would hold the write lock against `ingest`
and Litestream for the whole pass. Here the shape is `citator load`'s — batched, resumable,
one document at a time — and a pass killed mid-way keeps all but its last batch.

THE INPUT IS THE EXTRACTION THE BOX ALREADY WRITES (`tools/rmi-ai-machine/extract_text.py`):
`<root>/<sha[:2]>/<sha>.json`, one record per PDF, carrying `pages`, `image_only`, and the
tool and its version that produced both. That is what the weld in migration 0018 asks for:
both values come from ONE pass under one method, because `had_text_layer` is a judgement
about junk characters (`MIN_CHARS_PER_PAGE`) that a different tool over the same bytes can
make differently. `method` is therefore the TOOL (`pymupdf`, `pdftotext`) and not the
extraction's own name for itself (`text-layer`), which is a channel and not a method.

ONLY THE HEAD OF EACH FILE IS READ. `page_text` is written last and holds the whole text of
the document, so the fields wanted here sit in the first few hundred bytes of every file;
the census (`text_layer_census.py`) took a minute over the record on that rule where a parse
of every file would take an hour, and it is what "streams rather than parsing a directory
into memory" (item 13) means for this pass. The record is VALIDATED, not coerced: a count
that is not an integer or a text-layer answer that is not a boolean is `Unreadable`, because
`bool("false")` is True and `int(9.7)` is 9, and either would land in a published table.

WHAT SUPERSEDES IS A CHANGED ANSWER OR A CHANGED TOOL. A re-run by the same tool that
agrees — the same outcome, count and text-layer answer, at whatever version — writes
nothing: the live row already says what the record's pages are, and its provenance says who
first found it. A different TOOL supersedes even when it agrees, because `had_text_layer` is
that tool's judgement and the row's `method` is what a correction traces it to. The write is
`store.supersede.if_changed` with `retire_at`, the citator's own idiom — retire at itself,
insert, repoint, in one transaction — now carrying `superseded_at` in the same statement
because this table's biconditional refuses the write without it. A `human` row is never
superseded by this pass: the trigger would refuse it, and refusing here makes it a counted
outcome rather than an exception mid-batch (the idiom the citator's loader uses for ADR
0017 D5).

THE COMMIT IS PER BATCH, THE ROLLBACK PER DOCUMENT. Measured 2026-09-03 in WAL mode on
NVMe: a commit per row costs 1.2 ms a row and a commit per 200 rows 0.028 ms, so over ~74k
documents the first is minutes of fsync where the second is seconds, and every commit is a
WAL transaction Litestream ships. A SAVEPOINT per document keeps what the per-document
commit gave: one bad record is rolled back alone and the pass goes on. What is lost is at
most one batch on a kill, and every document in it is re-derived on restart as `unchanged`.
The write lock is held for one batch of point inserts, tens of milliseconds, against the
30 s the poller waits. A lock that is NOT released in that time — `OperationalError`, the
store held by a long write — ABORTS the pass rather than being counted per document: with
the 30 s timeout each remaining document would otherwise wait, fail, and be counted, for
hours, under an exit status that said nothing.

WHAT THE EXTRACTOR DOES NOT YET EMIT. `extract_text.py` writes no record for a file whose
magic bytes are not a PDF's, and none for a PDF that failed to open, so `not-paginable` and
`failed` rows cannot be written from today's directory. A record MAY carry `outcome` and this
pass honours it; until the extractor emits one, those documents stay absent here and the
coverage denominator is the paginated set. Recorded in `TODO.md`, not silently rounded.
"""

import json
import sqlite3
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from docketyard.store import supersede
from docketyard.store.db import utcnow

HEAD = 4096  # bytes: every header field of an extraction record sits inside this
COMMIT_EVERY = 200  # documents per transaction; see the module docstring for the numbers


class Unreadable(ValueError):
    """A record this pass cannot turn into a row: malformed, or naming no document."""


@dataclass(frozen=True)
class Pagination:
    """One row of `document_pagination`, as the pass asserts it."""

    document_sha256: str
    outcome: str
    page_count: int | None
    had_text_layer: int | None
    method: str
    method_version: str


def outcomes(con) -> frozenset[str]:
    """`pagination_outcome_vocab`, read from the store rather than copied into Python — the
    vocabulary is a table precisely so it can be widened by an INSERT (migration 0018)."""
    return frozenset(r[0] for r in con.execute("SELECT outcome FROM pagination_outcome_vocab"))


def read_head(path: Path) -> dict:
    """The record's header fields, without reading its text. The record is a JSON object
    whose LAST member is `page_text`; everything before it is parsed as an object of its
    own. A record with no `page_text` in its first bytes is parsed whole, which is the
    correct (slow) answer for a stub and the correct (loud) answer for a corrupt file."""
    with path.open("rb") as f:
        head = f.read(HEAD).decode("utf-8", "replace")
    cut = head.find('"page_text"')
    if cut < 0:
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(head[:cut].rstrip().rstrip(",") + "}")


def _text(record: dict, key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise Unreadable(f"{key} is {value!r}, not a non-empty string")
    return value


def from_record(record: dict, allowed: frozenset[str] | set[str]) -> Pagination:
    """A row from an extraction record, or `Unreadable` — never a guess. `allowed` is the
    store's outcome vocabulary (`outcomes`)."""
    if not isinstance(record, dict):
        raise Unreadable("not a JSON object")
    sha = _text(record, "document_sha256")
    if len(sha) != 64:
        raise Unreadable("document_sha256 is not 64 characters")
    method, version = _text(record, "tool"), _text(record, "tool_version")
    outcome = record.get("outcome", "paginated")
    if outcome not in allowed:
        raise Unreadable(f"outcome {outcome!r} is not one of {sorted(allowed)}")
    if outcome != "paginated":
        return Pagination(sha, outcome, None, None, method, version)
    count, image_only = record.get("pages"), record.get("image_only")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise Unreadable(f"pages is {count!r}, not a whole number")
    if not isinstance(image_only, bool):
        raise Unreadable(f"image_only is {image_only!r}, not a boolean")
    return Pagination(sha, outcome, count, int(not image_only), method, version)


def records(root: Path, allowed: frozenset[str]) -> Iterator[tuple[Path, Pagination | Unreadable]]:
    """Every record under `<root>/<xx>/<sha>.json`, shard by shard, in a fixed order — so a
    restart walks the same sequence and the skipped prefix is all `unchanged`. The root's
    own files (`_manifest.json`) are not records. An unreadable record is yielded as its
    error, so the caller counts it in the same loop that counts the rows."""
    for shard in sorted(p for p in root.iterdir() if p.is_dir()):
        for path in sorted(shard.glob("*.json")):
            try:
                row = from_record(read_head(path), allowed)
            except Unreadable as e:
                yield path, e
                continue
            except (OSError, ValueError) as e:  # json.JSONDecodeError is a ValueError
                yield path, Unreadable(f"{type(e).__name__}: {e}")
                continue
            if row.document_sha256 != path.stem:
                yield (
                    path,
                    Unreadable(f"names {row.document_sha256[:12]}, filed as {path.stem[:12]}"),
                )
                continue
            yield path, row


def paginate_document(con, row: Pagination, now: str | None = None) -> str:
    """One document into `document_pagination`; the CALLER holds the transaction. Returns
    the outcome as a word `run` counts: asserted, superseded, unchanged, human_held, or
    unknown_document (a record for bytes the store does not hold — nothing to attach it to,
    and the FK would refuse it)."""
    now = now or utcnow()
    live = con.execute(
        "SELECT pagination_id, confidence_state FROM document_pagination"
        " WHERE document_sha256 = ? AND superseded_by IS NULL",
        (row.document_sha256,),
    ).fetchone()
    if live is not None and live[1] == "human":
        return "human_held"
    if live is None:
        held = con.execute(
            "SELECT 1 FROM document WHERE document_sha256 = ?", (row.document_sha256,)
        ).fetchone()
        if held is None:
            return "unknown_document"
    written = supersede.if_changed(
        con,
        table="document_pagination",
        id_col="pagination_id",
        where="document_sha256 = ?",
        where_args=(row.document_sha256,),
        compare="outcome, page_count, had_text_layer, method",
        values=(row.outcome, row.page_count, row.had_text_layer, row.method),
        insert=(
            "INSERT INTO document_pagination (document_sha256, outcome, page_count,"
            " had_text_layer, method, method_version, asserted_at, confidence,"
            " confidence_state) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'unmeasured')"
        ),
        insert_args=(
            row.document_sha256,
            row.outcome,
            row.page_count,
            row.had_text_layer,
            row.method,
            row.method_version,
            now,
        ),
        retire_at=now,
    )
    if not written:
        return "unchanged"
    return "superseded" if live is not None else "asserted"


ATTACHED = ("asserted", "superseded", "unchanged", "human_held")  # a record met its document


def run(con, root: Path, *, log=print, commit_every: int = COMMIT_EVERY, every: int = 2000):
    """The pass over a directory. Returns the counts: one key per `paginate_document`
    outcome, `unreadable` for records that made no row, `failed` for documents the store
    refused (rolled back alone, the pass goes on), and `aborted` when the store itself
    could not be written and the pass stopped."""
    totals: Counter = Counter()
    allowed = outcomes(con)
    since_commit = 0
    for path, row in records(root, allowed):
        if isinstance(row, Unreadable):
            log(f"  unreadable {path.parent.name}/{path.name}: {row}")
            totals["unreadable"] += 1
            continue
        try:
            con.execute("SAVEPOINT document")
            try:
                outcome = paginate_document(con, row)
            except sqlite3.IntegrityError as e:
                con.execute("ROLLBACK TO document")
                log(f"  failed {path.stem[:12]}: {type(e).__name__} {e}")
                totals["failed"] += 1
                continue
            finally:
                con.execute("RELEASE document")
            since_commit += 1
            if since_commit >= commit_every:
                con.commit()
                since_commit = 0
        except sqlite3.OperationalError as e:  # the store, not the document: stop
            con.rollback()
            log(f"  aborted at {path.stem[:12]}: {type(e).__name__} {e}")
            totals["aborted"] += 1
            break
        totals[outcome] += 1
        if sum(totals[k] for k in ATTACHED) % every == 0:
            log(f"  {dict(totals)}")
    con.commit()
    return totals
