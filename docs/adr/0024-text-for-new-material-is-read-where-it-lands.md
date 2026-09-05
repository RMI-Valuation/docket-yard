# ADR 0024 — Text for new material is read where it lands

- **Status:** Accepted
- **Date:** 2026-09-05
- **Accepted:** 2026-09-05 (the operator: "ADR 0024 APPROVED")
- **Addendum to:** [ADR 0012](0012-deployment-topology.md), which otherwise stands
- **Companion to:** [ADR 0021](0021-the-ocr-text-grain.md) (what a reading row means) and
  [ADR 0022](0022-where-the-records-text-lives.md) (where its bytes live). Neither moves.
- **Overturns a position that was never written down.** `pyproject.toml` says the web tier
  earns its dependencies and "everything else stays standard library"; `citator/__init__`
  says "Nothing here reads a PDF. Text extraction runs on the enrichment box." Those are the
  rule this record changes, and they were comments rather than a decision — which is why
  this exists.

## Context

**A filing served today never gets text.** The forward pass (`capture/poll.py`,
`forward_pass`) runs capture → ingest → captions → `decision_work` repair → party resolve →
`fetch_attachments`, and that last stage stores the PDF's bytes and stops. There is no
extraction stage in the poller and no `text extract` subcommand in the CLI — only `paginate`
and `load`. Text arrives when a person runs `extract_text.py` on the enrichment box, rsyncs
the output and runs `text load`. Between those runs, new material is invisible to search, to
the citator and to `/text`.

Measured against production, 2026-09-05:

| | |
|---|---|
| documents held | 104,163 |
| with any text | 74,295 |
| **with none** | **29,868** |

That backlog is almost entirely not the poller's. Split by the `ingest_mode` of the capture
that observed the owning record:

| observed by | documents |
|---|---|
| **forward** | **158** (10 decisions · 141 filings · 7 comments) |
| backfill | 29,710 (3,272 filings · 26,438 environmental comments) |

**So the forward gap is 158 documents, and it grows by about 25 a day** — the volume
`CLAUDE.md` has always named. The rest belongs to the waves.

### Extraction is nearly always enough

The reason this can run on the instance at all is that the OCR half is a rare exception
forward. Image-only rate by year, measured 2026-09-05:

| | 2026 | 2025 | 2024 | 2023 | 2020 | 2014 |
|---|---|---|---|---|---|---|
| decisions | 0.3% | 0.4% | 0.0% | 0.0% | 0.0% | 23.9% |
| filings | **0.0%** | 0.3% | 0.6% | 0.0% | 0.0% | — |

Across 1,476 filings and 358 decisions served in 2026, **one** document lacked a text layer.
The 14,961 image-only documents in the store are the scanned historical record, and they are
the waves' problem, not the poller's.

### What makes this contested

Today the instance **fetches PDF bytes and never parses them.** Six dependencies, all
web-tier; `src/` names `pymupdf` only as a method string. Extraction means running a large C
codebase with a real CVE history over untrusted third-party input, on the machine that holds
the store and the ADR 0014 subscriber ciphertext. That is the whole argument against, and it
is a good one. It is answered by isolation rather than by refusal.

## Decision

**D1. The forward pass extracts the text layer of forward-observed documents, and only
those.** The filter is `observed_in="forward"`, exactly as `fetch_attachments` already uses
one stage earlier. `observations.attachments` states the seam in its own docstring — "the
poller fetches the watch's own files first; a backfill wave's backlog is the wave's" — and
extraction sits on it. **A wave extracts its own, on the enrichment box, as now.**

**D2. The parser runs in its own container and never touches the store.** A short-lived
service with `pymupdf` and nothing else: no store, no `DY_EMAIL_KEY`, no network, a
read-only mount of the blob path. It writes reading documents to a spool directory in the
shape `text load` already reads, and the existing loader — which has no PDF library — loads
them. **The process that opens untrusted input holds nothing worth stealing**, and the load
path is the one proven in production on 2026-09-05 (11,452 documents, 169,516 pages, zero
failures).

**D3. The bound is a cap, not a window.** `EXTRACT_LIMIT` per pass, oldest first, draining
across passes — the idiom `FETCH_LIMIT` and `RECHECK_LIMIT` already use. A look-back window
of 7 or 14 days was considered and refused: a window is the one shape that can strand a
document for ever, silently, when a pass dies or a wave lands late. With D1's scope the cap
will essentially never bind — 158 documents today, ~25 a day after — so it is a safety rail,
not a throttle.

**D4. An empty reading is a successful reading.** The queue is "has no text-layer *reading*",
never "has no text". An image-only document extracts to an all-empty reading, and that
reading is the record that we looked and found nothing. Without this the queue re-extracts
every image-only document on every pass, for ever.

**D5. A refusal is recorded as a run, not skipped.** A PDF that will not open writes an
`ocr_run` with `outcome = 'failed'` (ADR 0021's vocabulary already has it). Without this it
retries every 30 minutes and reaches `problems` on every pass, which teaches an operator to
ignore the exit status — the same failure the `decision_work` repair was written to avoid.

**D6. `method_version` is pinned in the image and moves deliberately.** ADR 0021 D1 keys a
reading on `(method, method_version, render_profile)`. If the instance and the box run
different `pymupdf` versions, one document yields two keys and supersedes itself on
alternate passes. One pinned version, changed as a release.

**D7. The OCR queue is per page, not per document.** Pages whose live text-layer reading is
empty and which have no live OCR reading — a query, never a table, the way the review queue
is. The wave routed whole documents and therefore skipped **51,189 blank pages inside 3,744
mixed documents** (a born-digital brief with scanned exhibits), measured 2026-09-05. The
store is already page-grained, so this costs nothing but the query.

**D8. Nothing here reads a PDF to make a claim.** Extraction quotes; it does not interpret.
No position, no date, no party is derived by this stage. Provenance is ADR 0021's, unchanged.

## Consequences

**Easy.** A decision served this morning is searchable this afternoon without anyone
touching a box in a house. The page index needs no rebuild — the loader keeps `page_fts` in
step row by row — so nothing here needs a maintenance window. The enrichment box becomes
needed for OCR alone, which is what it is actually for. And D4 makes the OCR queue build
itself: the empty readings *are* the queue.

**Hard.** Production grows a dependency and a container, and the deploy story grows a
service. The security review is now a standing obligation rather than a one-off: a `pymupdf`
CVE becomes a release, not a note. Two extraction paths exist (instance for forward, box for
waves) and D6 is what keeps them from fighting; if that pin drifts, the symptom is
supersession churn rather than an error, so it wants a test.

**Foreclosed.** Nothing. ADR 0022's rule — all of the text in the store, only the engine
payload to the blob tier — is untouched, because the spool file *is* the payload and goes
where 0022 sends it.

## Validation

Checked against [`validation-queries.md`](../validation-queries.md), per `CLAUDE.md`:

- **Q1 segment history** — unaffected. Extraction adds no party, place or succession fact.
- **Q2 negative treatment** — helped, and only in reach: the citator walks stored text, so a
  decision served today becomes citable within a pass instead of within a manual batch. The
  edges themselves are unchanged; nothing here types a citation.
- **Q3 point-in-time state** — unaffected in grain, and it strengthens the ledger's honesty:
  D5 makes a refusal a recorded event with a timestamp instead of an absence.
- **Q4 trail-use lifecycle** — unaffected. Dates stay quoted from a named document; D8 says
  so explicitly.
- **Q5 service-list alert** — unaffected. No alert fires on text, and D1's `observed_in`
  filter is the same ingest-mode flag Q5 forced into existence, used for the same reason.

None of the five is broken and none needs a grain change. The identity model is untouched:
every row this stage writes is keyed on a `document_sha256` that already exists.

## Cost of reversing

**Cheap, and that is why it can be tried.** Removing the stage is deleting a call in
`forward_pass` and a container from the compose file; the rows it wrote are ordinary ADR 0021
readings, indistinguishable from ones the box produced, and stay valid. The dependency leaves
with the container it was added in — the loader and the web tier never gained it.

The expensive half is D6. If the two paths run different `pymupdf` versions for a while
before anyone notices, the repair is a re-read of the affected documents under one version,
which supersedes rather than corrupts — a pass, not a migration.
