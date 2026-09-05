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

Measured 2026-09-05: **104,163 documents held, 74,295 with any text, 29,868 with none.** Of
that backlog roughly 158 are the poller's and the rest the waves'; the forward gap grows by
about 25 documents a day.

Extraction is almost always enough. Image-only rate by year:

| year | 2026 | 2025 | 2024 | 2023 | 2020 | 2014 |
| --- | --- | --- | --- | --- | --- | --- |
| decisions | 0.3% | 0.4% | 0.0% | 0.0% | 0.0% | 23.9% |
| filings | 0.0% | 0.3% | 0.6% | 0.0% | 0.0% | — |

Across 1,476 filings and 358 decisions served in 2026, one document lacked a text layer.

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

**D2. The parser runs in its own container and never touches the store** — `pymupdf` and
nothing else, no store, no `DY_EMAIL_KEY`, no network, a read-only blob mount. It writes to a
spool directory; the loader, which has no PDF library, loads from it.

**D3. The bound is a cap, not a window**: `EXTRACT_LIMIT` per pass, ordered by
`document.first_seen_at`, draining across passes. A window is the one shape that can strand a
document for ever, silently, when a pass dies or a wave lands late.

**D4. The extraction queue is keyed on `ocr_run`, and bounded by attempts.** A document is
owed extraction when it has no `ocr_run` row for the text-layer reading key and fewer than
`EXTRACT_ATTEMPTS` rows with `outcome = 'failed'`. It cannot be keyed on `document_text`: a
non-PDF attachment, a file that will not open and a 0-page PDF each write a run row and **no
text rows**, so that queue would re-extract them every pass for ever. The attempt bound
exists because `ocr_run` is append-only with `ran_at` in its key — without it one transient
failure removes a document from the queue permanently and silently.

**D5. A refusal is recorded as a run and carries its reason**, in `ocr_run.note`. A refusal
recording *that* it failed and never *why* is an ADR 0007 assertion missing its reason.

**D6. The pinned version is declared and a mismatch is refused at load time; the queue never
mentions the version.** Two producers at two `pymupdf` versions make one document supersede
itself on alternate passes, each alternation costing an FTS5 delete and insert per page. The
refusal follows `methods.declare`, which raises `Conflict` rather than ignoring a
contradicting declaration. The queue predicate is "no run at any version" — under "no run at
the pinned version" a point release would re-read 74,295 documents and rewrite ~1.1M rows.

**D7. The OCR queue is per page, and a page under a live human reading is not in it.** Pages
whose live text-layer reading is empty, with no live `ocr` reading and no live `human` row
for that page. A human row does not displace the primary, so without the last clause a
corrected page is re-queued for ever — the rule `citator/walk.py` already states. The wave
routed whole documents and so skipped 51,189 blank pages inside 3,744 mixed documents.

**D8. Nothing here reads a PDF to make a claim.** Extraction quotes; it does not interpret.

**D9. The spool file is an extraction record**, not a general reading document — `tool`,
`tool_version`, `extracted_at`, `pages`, `image_only`, `page_text`. One file then feeds both
`text paginate` and `text load`, so `document_pagination` is written. That table is the
denominator ADR 0022 D3 publishes; without it every forward document's `/text` page would
print "the page count is not yet recorded" about a number the machine had just computed.

**D10. The stage runs after `alerts()` and is wrapped** `try/except → problems.append`, like
every other stage. `load.run` raises by design when a rebuild owns the page index, and an
unwrapped raise before `alerts()` would cost a pass its alert delivery.

## Owed before this ships

1. **The reverse rebuild guard.** `load.run` checks `owned_by_rebuild` once at the top; a
   rebuild started *while* a load runs is undetected, and the symptom is duplicate rowids
   FTS5 takes in silence. Today the mitigation is a sentence in the runbook; on a 30-minute
   timer that sentence is unenforceable, and this change is what makes it so.
2. `ocr_run.note` written on a refusal (D5), and a per-page failure record, which does not
   exist today — a page the OCR pass attempted and failed is re-queued by D7 until it does.
3. The registry table holding the version declaration (D6) — a schema question for the critic.
4. `search_meta.page_built` re-stamping, which `page_index` records as owed.
5. `/security-review` before the container first ships.

## Consequences

**Easy.** A decision served this morning is readable this afternoon with nobody touching a
box in a house. The page index stays correct with no rebuild and no maintenance window — the
loader keeps `page_fts` in step row by row. The box is needed for OCR alone.

**Hard.** Production grows a dependency and a container, and a `pymupdf` CVE becomes a
release rather than a note. Two extraction paths exist and D6 is what keeps them apart. And
until owed item 4 lands, the page signature sits permanently ahead of the built signature, so
`search rebuild-pages` never short-circuits again: every deploy that runs it does a full
~1.1M-row rebuild, measured at 13 minutes on 2026-09-05.

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
- **Q5 service-list alert** — unaffected, conditional on D10's placement and wrapper.

No query breaks and none needs a grain change. Every row this stage writes is keyed on a
`document_sha256` that already exists.

## Cost of reversing

Cheap. Delete a call in `forward_pass` and a container from the compose file; the rows it
wrote are ordinary ADR 0021 readings and stay valid, and the dependency leaves with the
container. The expensive half is D6: if two paths run different versions before anyone
notices, the repair is a re-read that supersedes rather than corrupts — a pass, not a
migration, and only while D6's queue predicate holds.
