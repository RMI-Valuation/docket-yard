# ADR 0024 — Text for new material is read where it lands

- **Status:** Accepted 2026-09-10 (the operator)
- **Date:** 2026-09-05; D1, D3, D4, D6 and § Owed amended the same day; accepted and withdrawn
  the same day on the critic's findings, rewritten, and accepted 2026-09-10
- **Addendum to:** [ADR 0012](0012-deployment-topology.md), which otherwise stands
- **Companion to:** [ADR 0021](0021-the-ocr-text-grain.md) (what a reading row means) and
  [ADR 0022](0022-where-the-records-text-lives.md) (where its bytes live). Neither moves.
- **Overturns a position that was never written down:** `pyproject.toml`'s "everything else
  stays standard library" and `citator/__init__`'s "Nothing here reads a PDF." Comments, not
  decisions — which is why this record exists.

## Context

A filing served today never gets text. `forward_pass` ends at `fetch_attachments`, which
stores the PDF's bytes and stops; there is no extraction stage in the poller and no `text
extract` in the CLI. Text arrives only when a person runs `extract_text.py` on the enrichment
box, rsyncs, and runs `text load`. Between those runs new material is invisible to search, to
the citator and to `/text`.

Measured 2026-09-05: **104,163 documents held, 74,295 with any text, 29,868 with none.** The
forward gap grows by about 25 documents a day. Extraction is almost always enough — across
1,476 filings and 358 decisions served in 2026, **one** document lacked a text layer:

| year | 2026 | 2025 | 2024 | 2023 | 2020 | 2014 |
| --- | --- | --- | --- | --- | --- | --- |
| decisions | 0.3% | 0.4% | 0.0% | 0.0% | 0.0% | 23.9% |
| filings | 0.0% | 0.3% | 0.6% | 0.0% | 0.0% | — |

**What makes this contested:** the instance today fetches PDF bytes and never parses them.
Extraction puts a large C codebase with a CVE history over untrusted input on the machine
holding the store and the ADR 0014 subscriber ciphertext. That is answered by isolation (D2),
not by the age of the input.

## Decision

**D1. The scope is the DOCUMENT: it is the instance's if any capture that ever observed it
ran in `forward` mode and positively asserted its filter**, joined through
`document_source.capture_id`, whose rows accumulate and are never repointed. The filter term
is the endpoint's first trap applied where it always is — nothing downstream of `capture`
trusts a row that did not assert what it asked for — though on this join it excludes nothing
today and stands against a future widening. Not `observed_in_event`, which is current state
and moves; and not a record filter, which leaves the erratum re-check ownerless: that re-check
walks every held URL by design, so a replaced file mints a new document under a forward
capture that no record filter would reach and no finished wave would claim.

Two costs are taken deliberately. A REPLACED file mints a new document under the re-check's
forward capture, so an erratum on an archive document is in scope and D2's isolation is the
security argument, not the age of the input. An earlier draft said the re-check gives every
archive document a forward `document_source` row; it does not — on an unchanged re-check
`capture/documents.py` writes one only where a row cited the file without its hash yet, wave
documents are fetched under `ingest_mode = 'backfill'`, and nothing repoints `capture_id`. And
environmental-comment attachments are
in scope though a comment's page has no text address, so their text is stored and not yet
displayable — ADR 0022's rule is that all of the record's text lives in the store, and a few
documents a week is the price of having it there when that address exists.

**D2. The parser runs in its own container and never touches the store** — `pymupdf` and
nothing else, no store, no `DY_EMAIL_KEY`, no network, a read-only blob mount. **Its input is
an explicit list of `document_sha256` handed to it, never a directory scan**: the blob pool is
flat and content-addressed with no type marker, so a self-scoping container would read every
capture body in it. It writes to a spool directory; the loader, which has no PDF library,
loads from there.

**D3. The bound is a cap, a retry interval, a time budget and a size limit, newest first.**
`EXTRACT_LIMIT` documents per pass ordered by `document.first_seen_at` **descending**, an
`EXTRACT_BUDGET_SECONDS` after which the stage stops starting work (the idiom
`RECHECK_BUDGET_SECONDS` already uses), and an `EXTRACT_MAX_BYTES` of 64 MB matching
`RECHECK_MAX_BYTES`, above which the document is refused with its reason rather than attempted
— the record holds a 1.07 GB PDF that OOM-killed the wave process twice. **Until § Owed 2
lands, that refusal cannot be written**: `ocr_run` requires a method, version, channel and
render that never ran. The interim behaviour is silent exclusion by the queue, counted under
§ Owed 6.

**`EXTRACT_ATTEMPTS` has an `EXTRACT_RETRY_HOURS` beside it**, one ask per document per that
many hours whatever the pass rate. `_fill_captions` pairs `CAPTION_ATTEMPTS` with
`CAPTION_RETRY_HOURS` for this reason: a cap alone means a container down for 90 minutes burns
every attempt of everything dispatched in those three passes, and they leave the queue unread
for ever with no `ocr_run` row and nothing raised.

**The size and media-type limits are terms of the QUEUE, not only of the loader.** D2 hands
the container an explicit list, so the queue is the only filter that exists: without them it
dispatches the 1.07 GB PDF and every `.xlsx`, `.zip`, `.jpg` and `.docx` the record holds, the
container dies or raises, the attempt burns, and the document is exhausted — never read and
never refused with a reason, which is this decision and D5 both defeated by the queue.

Newest first is a promise: a decision served this morning is read this pass, and the archive
documents D1 admits drain from the recent end backwards. Oldest first would read all of them
before today's material, and the re-check keeps feeding that backlog, so the drain has no
known end. A look-back window was refused outright — it is the one shape that can strand a
document for ever when a pass dies or a wave lands late.

**D4. A dispatch is recorded before the container is invoked, and the queue is bounded by
dispatches at the current pin.** A new `extraction_dispatch` table, `dispatch_id` surrogate,
is written by the **poller** at hand-off, carrying the document, the pin it was handed off on
and the time. A document is owed extraction when it has no `ocr_run` row for the text-layer
reading key — `reading_channel = 'text-layer'` and `render_profile = 'native'`, at any
method version — **whose outcome is `read`**, and fewer than `EXTRACT_ATTEMPTS`
dispatches **at the pin now in force**, and no dispatch at all inside `EXTRACT_RETRY_HOURS`.
The cap is per pin so that a version bump is the reset; **the interval is per document**, or a
pin that flaps — two pollers, a rollback, an undeclared constant before § Owed 1 lands —
re-dispatches with no interval at all.

**The outcome is part of that test, not merely the row's existence.** D5 records a refusal AS
a run, and `run_outcome_vocab` holds `failed` and `skipped` beside `read` — so under "no row
at that key" one `failed` silences the queue for that document for ever, at every version and
after a single attempt, and the release that fixes those bytes changes nothing. That would
make the pin below inert for the one case it exists for.

The counter cannot be `ocr_run`, which only ever exists because the loader read a spool file
the container wrote. A container that is down, OOM-killed or stuck records nothing, so no
attempt would ever count, the same documents would be selected every pass, and every newer
document would go unread — silently, because nothing raised.

**The count is per pin so that a version bump is the reset.** Otherwise exhaustion is
permanent and version-blind: a document that burned every attempt because one `pymupdf`
release fails on those bytes is out of the queue for ever, the release that fixes it changes
nothing, and the only recovery is hand surgery. The pin on the row is what the poller was
**configured** to hand off on — it cannot be an observation, because the row is written before
the container runs. `ocr_run` records what actually ran, and the loader holds both, so "the
spool file disagrees with the dispatch" is a detectable event and the loader's to report.

**The attempt's number is not stored**, and no column is unique. A second dispatch for one
document is the point of the table, so uniqueness constrains no real error, while a stored
number costs a read-before-write whose stale `MAX+1` is an `IntegrityError` at hand-off — and
a hand-off that raises is a hand-off the record does not remember, which is this decision's
own failure. The number a reader sees is `ROW_NUMBER()` over the document's rows. A surrogate
key is also the rebuild-class choice that matters here — a published inline CHECK is the
other, and this table ships three it will never want to widen — and the table is public.

**The pass reconciles, and can stop.** It compares what it dispatched against what landed,
appends the difference and the newly exhausted to `problems`, and halts dispatch while
nothing is landing **and reading**. The test is landed-and-`read`, not landed: a container
that is up and failing every document lands rows, so a ratio measured on landing alone never
halts and the whole backlog retires at one attempt each. **The halt is a query, not a
state**: dispatch is halted while the last N dispatches have no matching successful run, with
one canary document sent per pass so the condition stays measurable. Held as a flag it either
never clears — nothing dispatched means nothing lands means the condition holds for ever — or
it clears every other pass, halving a dead container's burn rate instead of stopping it. Without
this the head-of-line block is merely traded for silent mass
exhaustion, which is the worse of the two: a repeat is visible in the next pass, a discard is
visible nowhere.

**The poller commits to a known point, writes the dispatch, commits, asserts it holds no
transaction, and only then invokes.** `forward_pass` threads one connection through every
stage and `commit()` commits everything open on it, so this is ordering, not isolation. A
second connection is the wrong answer — it contends for the write lock against Litestream's
checkpoint. Wrapping the invocation in the house `try/except: con.rollback()` is also wrong:
it rolls back dispatch rows for bytes the container has already read, and the bound stops
being a bound for the most likely failure there is.

**D5. A refusal is recorded as a run and carries its reason**, in `ocr_run.note`. A refusal
recording *that* it failed and never *why* is an ADR 0007 assertion missing its reason.

**D6. The pinned version is declared and a mismatch is refused at load time; the queue never
mentions the version when it asks whether a document has been READ.** Two producers at two
`pymupdf` versions make one document supersede itself on alternate passes, each alternation
costing an FTS5 delete and insert per page. The refusal follows `methods.declare`, which
raises `Conflict` rather than ignoring a contradicting declaration. The predicate is "no
SUCCESSFUL run at any version" — under "no run at the pinned version" a point release would
re-read 74,295 documents and rewrite ~1.1M rows, and those 74,295 all carry `read` rows, so
testing the outcome costs that reasoning nothing.

That is the `ocr_run` half. **D4's dispatch count is per pin and necessarily mentions the
version**, because the two halves ask different questions: "has this been read?" is
version-free, and "has this pin already failed on it?" cannot be. **The registry holding this
declaration (§ Owed 1 below) lands before the poller reads a pin**, not after — with no single
declaration the poller writes its own constant, and the silent direction is the container
moving ahead of it, leaving every document the new version could read exhausted for ever at a
pin that no longer exists. It gates the POLLER, not this table's DDL. **If the registry is
held, the dispatch columns cannot reference it at all** — `extraction_dispatch` is public, no
public table in the shipped store has ever referenced a held one, and such an FK fails at a
third party's `foreign_key_check` rather than at ours (migration 0018 settled that case by
name for `ocr_run` and `reading_vocab`). If it is public the argument has to be made afresh,
and it is not made here; either way SQLite cannot add an FK by `ALTER`, so the choice is taken
when the table ships.

**D7. The OCR queue is per page, and a page under a live human reading is not in it.** Pages
whose live text-layer reading is empty, with no live `ocr` reading and no live `human` row for
that page. A human row does not displace the primary, so without the last clause a corrected
page is re-queued for ever — the rule `citator/walk.py` already states. The wave routed whole
documents and so skipped 51,189 blank pages inside 3,744 mixed documents.

**D8. Nothing here reads a PDF to make a claim.** Extraction quotes; it does not interpret.

**D9. The spool file is an extraction record, written atomically, and deleted only when it has
landed.** The record carries `tool`, `tool_version`, `extracted_at`, `pages`, `image_only`,
`page_text`, so one file feeds both `text paginate` and `text load` and `document_pagination`
is written — the denominator ADR 0022 D3 publishes, without which every forward document's
`/text` page would print "the page count is not yet recorded" about a number the machine had
just computed. It is written `<sha>.json.tmp` and renamed, because the header alone is enough
to assert a page count: a file truncated mid-write publishes a count whose text never loads,
every pass, for ever. A file is removed only after the loader reports a landed outcome — never
on `unreadable`, `failed` or `aborted`, or a parse failure would destroy the raw D5 needs a
reason from.

**D10. The stage runs last, its counted failures reach `problems`, and the loader re-checks
index ownership per batch.** Last means after the errata re-check and `search.rebuild_or_report`,
both of which run after `alerts()` today and both of which feed published numbers; nothing
downstream needs the readings early, because `page_index` keeps `page_fts` in step row by row.
A `try/except` alone is not enough: `batches.run` **returns** `unreadable`, `failed` and
`aborted` as counts rather than raising, so those must be appended to `problems` the way
`_ingest_pending` already appends its dropped rows. And `load.run` checks index ownership only
at the top, so a rebuild starting mid-load is undetected and duplicate rowids enter an
external-content FTS5 in silence — a hand-run loader met that window rarely, a 30-minute timer
meets it about half the times a 13-minute rebuild runs.

## Owed before this ships

1. **The registry table holding the version declaration (D6), which lands FIRST.** A schema
   question for the critic, and it gates the dispatch table rather than following it.
2. `ocr_run.note` written on a refusal (D5), and a per-page failure record, which does not
   exist today — a page the OCR pass attempted and failed is re-queued by D7 until it does.
   The oversize refusal is the hard case: `ocr_run` requires a method, version, channel and
   render, so recording one would claim a channel nothing read on and a version that never
   ran, in a public table, under D8. `run_outcome_vocab` is a table so it can be widened by
   INSERT; the four NOT NULLs are migration 0018's and are the harder half. **A fourth outcome,
   `not-paginable`, goes in BEFORE any refusal ships as `skipped`** — `skipped` today means
   permanently-not-a-document, and D5's refusal is transient, and a published word that means
   both cannot be un-published. Measured 2026-09-05: 3,271 `skipped` rows at the text-layer
   key and 0 of them on a `media_type = 'pdf'` document, so D4's `read` test is safe until
   then and not after. Migration 0022 landed that word on 2026-09-05 and put the historical
boundary in a `correction` row; their media types are null, xlsx, zip, jpg and docx, so the
queue's media term excludes all 3,271 and this predicate never meets them.
3. `search_meta.page_built` re-stamping, which `page_index` records as owed.
4. `EXTRACT_LIMIT` sized against the queue **measured with D1's own join**, not against the
   forward record count, which is a different and smaller number.
5. `ocr_run` and `extraction_dispatch` record no `ingest_mode`, so neither row can say which
   producer made it — the gap `deferred.md` already records for `extraction_run`. **This gates
   D4's reconciliation**, not only D6: the two tables share nothing but `document_sha256`, and
   `ocr_run.ran_at` is the parser's clock from a spool header that may have been written on
   the enrichment box weeks earlier, so a wave load landing during a container outage can
   satisfy the reconciliation and clear the halt for documents the container never read. The
   floor `ran_at >= dispatched_at` narrows it; a producer column settles it, and `ADD COLUMN`
   survives publication.
6. **`EXTRACT_ATTEMPTS` and the queue's exclusions rendered on `/methodology` from the
   constants themselves**, as `poll.CAPTION_ATTEMPTS` and `RECHECK_MAX_BYTES` already are.
   The table is published expressly to separate "handed over and nothing came back" from
   "never attempted", and a third category — never eligible: no asserted forward capture,
   oversize, or a `media_type` that is NULL because nothing sniffed it — is representable
   nowhere. Without the cap a third party also cannot tell a terminal count from one in
   flight. The NULL-media-type drop is counted into `problems` rather than left silent.
7. **`first_seen_at` is when the bytes were FETCHED, not when the record was made.** D1
   excludes a wave's own documents at capture time, so the walk is not swamped by a running
   backfill — but a REPLACED archive file is re-fetched under a forward capture and jumps
   ahead of this morning's decision in the newest-first walk. Ordering by the record's own date
   would deliver D3's promise exactly. Not measured; recorded in `deferred.md`.
8. `/security-review` before the container first ships.

## Consequences

**Easy.** A decision served this morning is readable this afternoon with nobody touching a box
in a house. The page index stays correct with no rebuild and no maintenance window. The box is
needed for OCR alone.

**Hard.** Production grows a dependency and a container, and a `pymupdf` CVE becomes a release
rather than a note. Two extraction paths exist and D6 is what keeps them apart. The pass gains
CPU-bound work it never had, against a cycle that already runs ~14–15 minutes of its 30 and
whose overrun is invisible — `run_forever` sleeps zero and nothing measures duration, while
`/coverage` publishes "every thirty minutes" and `/methodology` computes `recheck_cycle_days`
from it. And until owed item 4 lands, the page signature sits permanently ahead of the built
signature, so `search rebuild-pages` never short-circuits: every deploy that runs it does a
full ~1.1M-row rebuild, measured at 13 minutes on 2026-09-05.

**Foreclosed.** Nothing this record can establish. ADR 0022's rule appears untouched — the
spool file *is* the payload and goes where 0022 sends it — but the instance would now write
content-addressed payloads into `blobs/` every 30 minutes while a wave does the same
elsewhere, and that sync topology is not traced here.

## Validation

Against [`validation-queries.md`](../validation-queries.md):

- **Q1 segment history** — unaffected; no party, place or succession row is written.
- **Q2 negative treatment** — text becomes *readable* within a pass, so the citator's walk
  reaches a decision served today. The edge still waits: `find` and `load` are not in
  `forward_pass`.
- **Q3 point-in-time state** — unaffected in grain. Not improved: `ocr_run` carries one
  timestamp, so a refusal records when the parser ran, never when the store learned of it.
- **Q4 trail-use lifecycle** — unaffected. The condition is D6 as amended: the `ocr_run` half
  of the predicate is version-free, so no point release re-reads and re-supersedes the record's
  text; the dispatch count is per pin and touches no assertion a query reads.
- **Q5 service-list alert** — unaffected, conditional on D10 and on D4's commit ordering. The
   endpoint traps are untouched:
  no request is built, the filter assertion and the quiet-table proof are not on this path, and
  politeness holds across back-to-back passes because the client outlives one pass. The only
  coupling is time, which is why D3 has a budget and D10 puts the stage last.

No query breaks and none needs a grain change. Every row this stage writes is keyed on a
`document_sha256` that already exists.

## Cost of reversing

Cheap. Delete a call in `forward_pass` and a container from the compose file; the rows it wrote
are ordinary ADR 0021 readings and stay valid, and the dependency leaves with the container.
`extraction_dispatch` is derived data and can be dropped — though once a snapshot has
shipped it, a third party holds the shape, which is why its key was settled before it landed. The
expensive half is D6: if two paths
run different versions before anyone notices, the repair is a re-read that supersedes rather
than corrupts — a pass, not a migration, and only while D6's queue predicate holds.
