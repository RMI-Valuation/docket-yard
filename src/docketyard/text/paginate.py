"""The pagination pass: one row per document in `document_pagination` (migration 0018).

`page_count` is the DENOMINATOR of the coverage arithmetic — unread pages are the count
minus the readings — and the table is the one new table the snapshot publishes (ADR 0022
D3). So this runs as ITS OWN COMMAND and not inside `migrate` (`docs/ocr-migration.md`
item 12): `migrate` is a service the whole stack blocks on and every migration to date runs
in one transaction, so ~74k rows written inside it would hold the write lock against `ingest`
and Litestream for the whole pass. Here the loop is `store.batches` — one document at a
time, committed per batch — and a pass killed mid-way keeps all but its last batch.

THE INPUT IS THE EXTRACTION THE BOX ALREADY WRITES (`tools/rmi-ai-machine/extract_text.py`):
`<root>/<sha[:2]>/<sha>.json`, one record per PDF, carrying `pages`, `image_only`, and the
tool and its version that produced both. That is what the weld in migration 0018 asks for:
both values come from ONE pass under one method, because `had_text_layer` is a judgement
about junk characters (`MIN_CHARS_PER_PAGE`) that a different tool over the same bytes can
make differently. `method` is therefore the TOOL (`pymupdf`, `pdftotext`) and not the
extraction's own name for itself (`text-layer`), which is a channel and not a method.

ONLY THE HEAD OF EACH FILE IS READ (`fields.read_head`). `page_text` is written last and
holds the whole text of the document, so the fields wanted here sit in the first few
hundred bytes of every file; the census (`text_layer_census.py`) took a minute over the
record on that rule where a parse of every file would take an hour. The record is
VALIDATED, not coerced: a count that is not an integer or a text-layer answer that is not a
boolean is `Unreadable`, because `bool("false")` is True and `int(9.7)` is 9, and either
would land in a published table.

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

WHAT THE EXTRACTOR DOES NOT YET EMIT. `extract_text.py` writes no record for a file whose
magic bytes are not a PDF's, and none for a PDF that failed to open, so `not-paginable` and
`failed` rows cannot be written from today's directory. A record MAY carry `outcome` and this
pass honours it; until the extractor emits one, those documents stay absent here and the
coverage denominator is the paginated set. Recorded in `TODO.md`, not silently rounded.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from docketyard.store import batches, supersede
from docketyard.store.db import utcnow
from docketyard.text.fields import Unreadable, read_head, sha_field, text_field

ATTACHED = ("asserted", "superseded", "unchanged", "human_held")  # a record met its document
NOUN = "extraction record"


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


def from_record(record: dict, allowed: frozenset[str] | set[str]) -> Pagination:
    """A row from an extraction record, or `Unreadable` — never a guess. `allowed` is the
    store's outcome vocabulary (`outcomes`)."""
    if not isinstance(record, dict):
        raise Unreadable("not a JSON object")
    sha = sha_field(record)
    method, version = text_field(record, "tool"), text_field(record, "tool_version")
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


def read_file(path: Path, allowed: frozenset[str]) -> Pagination:
    row = from_record(read_head(path), allowed)
    if row.document_sha256 != path.stem:
        raise Unreadable(f"names {row.document_sha256[:12]}, filed as {path.stem[:12]}")
    return row


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


def run(con, root: Path, *, log=print, commit_every: int = batches.COMMIT_EVERY) -> Counter:
    """The pass over a directory, through `store.batches`: one key per `paginate_document`
    outcome, plus `unreadable`, `failed` and `aborted`."""
    allowed = outcomes(con)
    return batches.run(
        con,
        batches.walk(root, lambda path: read_file(path, allowed)),
        lambda row: paginate_document(con, row),
        log=log,
        commit_every=commit_every,
    )
