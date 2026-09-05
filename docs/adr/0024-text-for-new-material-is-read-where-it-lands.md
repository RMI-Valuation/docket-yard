# ADR 0024 — Text for new material is read where it lands

- **Status:** Proposed
- **Date:** 2026-09-05
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
ran in `forward` mode**, joined through `document_source.capture_id`, whose rows accumulate
and are never repointed. Not `observed_in_event`, which is current state and moves — and not
a record filter, which leaves the erratum re-check ownerless: that re-check walks every held
URL by design, so a replaced file mints a new document under a forward capture that no record
filter would reach and no finished wave would claim.

Two costs are taken deliberately. The re-check also gives archive documents a forward
`document_source` row, so the queue is larger than the forward record count and D2's isolation
is the security argument, not the age of the input. And environmental-comment attachments are
in scope though a comment's page has no text address, so their text is stored and not yet
displayable — ADR 0022's rule is that all of the record's text lives in the store, and a few
documents a week is the price of having it there when that address exists.

**D2. The parser runs in its own container and never touches the store** — `pymupdf` and
nothing else, no store, no `DY_EMAIL_KEY`, no network, a read-only blob mount. **Its input is
an explicit list of `document_sha256` handed to it, never a directory scan**: the blob pool is
flat and content-addressed with no type marker, so a self-scoping container would read every
capture body in it. It writes to a spool directory; the loader, which has no PDF library,
loads from there.

**D3. The bound is a cap, a time budget and a size limit, newest first.** `EXTRACT_LIMIT`
documents per pass ordered by `document.first_seen_at` **descending**, an `EXTRACT_BUDGET_SECONDS`
after which the stage stops starting work (the idiom `RECHECK_BUDGET_SECONDS` already uses),
and an `EXTRACT_MAX_BYTES` of 64 MB matching `RECHECK_MAX_BYTES`, above which the document is
refused with its reason rather than attempted — the record holds a 1.07 GB PDF that OOM-killed
the wave process twice.

Newest first is a promise: a decision served this morning is read this pass, and the archive
documents D1 admits drain from the recent end backwards. Oldest first would read all of them
before today's material, and the re-check keeps feeding that backlog, so the drain has no
known end. A look-back window was refused outright — it is the one shape that can strand a
document for ever when a pass dies or a wave lands late.

**D4. A dispatch is recorded before the container is invoked, and the queue is bounded by
dispatches.** A new `extraction_dispatch` table keyed `(document_sha256, attempt_no)` is
written by the **poller** at hand-off. A document is owed extraction when it has no `ocr_run`
row for the text-layer reading key and fewer than `EXTRACT_ATTEMPTS` dispatches.

The counter cannot be `ocr_run`, which only ever exists because the loader read a spool file
the container wrote. A container that is down, OOM-killed or stuck records nothing, so no
attempt would ever count, the same documents would be selected every pass, and every newer
document would go unread — silently, because nothing raised.

**D5. A refusal is recorded as a run and carries its reason**, in `ocr_run.note`. A refusal
recording *that* it failed and never *why* is an ADR 0007 assertion missing its reason.

**D6. The pinned version is declared and a mismatch is refused at load time; the queue never
mentions the version.** Two producers at two `pymupdf` versions make one document supersede
itself on alternate passes, each alternation costing an FTS5 delete and insert per page. The
refusal follows `methods.declare`, which raises `Conflict` rather than ignoring a
contradicting declaration. The predicate is "no run at any version" — under "no run at the
pinned version" a point release would re-read 74,295 documents and rewrite ~1.1M rows.

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

1. `extraction_dispatch`'s shape past the schema critic; it is a migration (D4).
2. `ocr_run.note` written on a refusal (D5), and a per-page failure record, which does not
   exist today — a page the OCR pass attempted and failed is re-queued by D7 until it does.
3. The registry table holding the version declaration (D6) — a schema question for the critic.
4. `search_meta.page_built` re-stamping, which `page_index` records as owed.
5. `EXTRACT_LIMIT` sized against the queue **measured with D1's own join**, not against the
   forward record count, which is a different and smaller number.
6. `ocr_run` records no `ingest_mode`, so the row cannot say which producer made it — the gap
   `deferred.md` already records for `extraction_run`, and D6 makes it matter.
7. `/security-review` before the container first ships.

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
- **Q4 trail-use lifecycle** — unaffected, conditional on D6's version-free queue predicate.
- **Q5 service-list alert** — unaffected, conditional on D10. The endpoint traps are untouched:
  no request is built, the filter assertion and the quiet-table proof are not on this path, and
  politeness holds across back-to-back passes because the client outlives one pass. The only
  coupling is time, which is why D3 has a budget and D10 puts the stage last.

No query breaks and none needs a grain change. Every row this stage writes is keyed on a
`document_sha256` that already exists.

## Cost of reversing

Cheap. Delete a call in `forward_pass` and a container from the compose file; the rows it wrote
are ordinary ADR 0021 readings and stay valid, and the dependency leaves with the container.
`extraction_dispatch` is derived data and can be dropped. The expensive half is D6: if two paths
run different versions before anyone notices, the repair is a re-read that supersedes rather
than corrupts — a pass, not a migration, and only while D6's queue predicate holds.
