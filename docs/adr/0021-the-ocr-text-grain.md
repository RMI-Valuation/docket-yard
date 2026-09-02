# ADR 0021 — The OCR text grain

- **Status:** Proposed
- **Date:** 2026-09-02
- **Scope:** the grain only — what a stored reading of a page *is*. The review layer
  (ranking, the queue, agreement as a stored judgement, and the rebuilds of two shipped
  tables) is **deliberately not here**; see § What this record does not decide.
- **Reviewed:** three schema-critic passes and a four-lens panel, 2026-09-02. Findings are
  answered below or recorded in [`../ocr-migration.md`](../ocr-migration.md). The panel's
  strongest finding was that this record was deciding a review layer before the measurement
  that shapes it existed. That measurement now exists, and it removed half of what this
  record used to say.

## Context

**Nothing of the record's text is in the store.** `extract_text.py` writes JSON on the
enrichment box, `citator.find.findings_document` takes its pages as an argument, and the
store holds captures, the registry, the ledger, the party module and the citator's five
assertion families — and not one word of any document. So `document_text` is the first place
the record's own text lands, and its grain is a one-way door in ADR 0003's sense: reversing
it means re-reading the archive.

**What is to be read is counted** (`tools/rmi-ai-machine/text_layer_census.py`, 2026-09-02,
with the corrections it forces recorded in `ocr-plan.md`): **15,085 image-only documents
holding 247,923 pages**, against 59,210 text-layer documents holding 857,012. The image-only
side is 42% above the plan's estimate, so the backfill is about **187 hours** of routed
reading rather than 132. It is almost entirely the pre-2005 record — the boundary at which
search, the citation graph and the registers all degrade.

**Two benchmark findings bear on the grain** (`research/ocr-benchmark/README.md` §§ 3–6,
authoritative for every figure). *No single engine wins*, so the read is routed per page:
dots.mocr reads best overall and gets every docket number on all 90 pages, while PP-OCRv6 is
the only engine that reads a map without inventing. *And the render moves the reading*:
dots.mocr peaks at 200 DPI where 300 exhausts the card, and crop and mask each change its
output. **Those are the same engine at the same version producing different text.**

**Agreement between two engines was measured** (§ Step 6) at AUC 0.93–0.97 against measured
CER, holding the tier constant — a real per-page confidence signal, and the only one
available. It is bought cheaply: the second reader is the cheapest non-family engine, about
+23% on the backfill rather than the doubling an earlier draft of this record assumed.

**The paper schema predates all of it.** `docs/schema-draft.md` § 2 drafts `document_page`
with a singular `ocr_method` — one engine per page, current state, updated by a re-run — and
`page_block`. Two engines' readings of one page have to coexist, because their agreement is
the confidence. The drafted shape cannot hold it.

## Decision

1. **The grain is one row per reading of one page.** `document_text`, append-only, natural
   key `(document_sha256, page_no, method, method_version, render_profile)`, enforced by a
   **partial unique index over live rows** — not a table-wide `UNIQUE`, which would forbid
   the retraction and self-pointer idioms `superseded_by` exists for. A surrogate `text_id`
   is minted for pointers and used by nothing else. Every row carries ADR 0007's block, plus
   `superseded_by` and **`superseded_at`** — the latter a deliberate departure from the
   0006/0009 idiom, whose missing date `deferred.md` already records as a cost.

   **A human row's key is pinned**: `method = 'human'`, `method_version = 'unversioned'`,
   `render_profile = 'human'`. The shipped convention for a human assertion is
   `citator.methods.HUMAN_VERSION`, a *dated* queue-convention version, and carried into this
   key it would put two live human rows on one page the day that date changes. What a
   reviewer was shown belongs in `review_action.method_version`, the row that records it.

2. **The render is in the key, not in a convention.** `render_profile` names the DPI and any
   preprocessing (`native`, `150`, `200`). Measured fact forces it: two renders of one page
   through one engine at one version are different text, so without the column they collide
   and the second read overwrites the first or is dropped. Folding it into `method_version`
   by convention works until somebody writes the convention differently — the `web/cite.py`
   drift ADR 0018 D7 names. One column, before a single row exists.

3. **The text layer is a reading, in the same table**, at `reading_channel = 'text-layer'`
   with `render_profile = 'native'`. Not a second table, not a branch on `media_type`. One
   join for the viewer, the search index and the citator; "which pages have been read, and
   how?" becomes a query; and it is the shape ADR 0018 D3 already assumes.

4. **`page_no` is a function of the document's identity, and the page count is a
   per-document assertion.** `document_sha256` fixes the byte stream, so page order is a
   property of the bytes; both passes take the order the PDF gives, 1-based. This matters
   because `citation_key`'s primary key carries `page` as the location, and a
   channel-dependent page number would mint two keys for one edge.

   The count lives in **`document_pagination`** — one row per document, carrying
   `page_count`, `had_text_layer`, its own method, version and timestamp because both are
   derived, and **a typed outcome**. The outcome is not decoration: without it, a document
   with no row is *not a PDF*, *not yet paginated* and *failed to open* all at once, which is
   decision 5's own rule — absence is not a measurement — broken one level up from where
   decision 5 enforces it. A non-PDF gets a row saying so. An unread page is then
   `page_count` minus its readings, over documents whose pagination succeeded.

   **This is a deliberate shrink**: a per-page table would be ~1.10M rows and ~400 MB of the
   measured row budget, to hold a `rotation` column no code reads and a flag the existing
   pipeline already computes per document. Per-page rows remain a later
   projection from the same PDFs — an addition, never a re-read.

5. **An empty reading is a row; a failed read is not.** A page an engine correctly reads as
   blank writes a row with empty text. A page whose read failed — the OOM at 300 DPI is a
   measured example — writes no text row and is recorded in `ocr_run`: one row per
   `(document, method, method_version, reading_channel, render_profile)` with a typed outcome
   and pages read, **appending rather than replacing on a re-run**, because
   `extraction_run`'s replace semantics are why its own header forbids deriving a published
   coverage number from it.

   **This is a mistake already made and paid for.** The benchmark's runner treated empty
   output as an error and dropped the page, penalising exactly the safest behaviour:
   Tesseract lost the two graphic pages it correctly emitted nothing for, while an engine
   that invents prose about a map kept all nine. ADR 0018 D10 says it from the other side —
   *absence is not a measurement.*

6. **Layout is captured as the engine's own payload, and block identity is fixed now.** The
   payload is kept whole as a blob under the `blobs/` prefix, content-addressed by its own
   digest and recorded in a table with `document`'s discipline; `document_text` carries that
   digest and a member path. **No block table ships here** — ADR 0003's argument is that
   layout cannot be added later without re-reading, which keeping the payload satisfies
   exactly, while a block table today would have to invent one vocabulary across engines that
   return HTML tables, line boxes, and regions with no text in them at all.

   **`block_id` is a deterministic function of the payload digest and the engine's own index
   path**, because `citation_reading.source_location` is documented as `{page, block_id,
   bbox}` and an id minted by a later projection would strand every `source_location` written
   before it.

   **And this narrows ADR 0003, recorded rather than left implicit**, in the form
   `schema-draft.md` uses for ADR 0016's narrowing. 0003 holds that the IR carries font size
   and weight. For a scan nothing is lost — no OCR payload carries a font. For a
   **born-digital** page they are extractable and no payload holds them, so the text-layer
   pass keeps its own extractor output as its payload, or that half of 0003 is dropped
   knowingly.

7. **Display is ungated; assertion is gated.** These are different acts and this record
   treats them differently.

   **Every read page shows its text**, labelled machine-read, with the engine and version,
   its confidence band, a link to the agency's own scan, and a way to report a misreading.
   Nothing is withheld for being imperfect, and search covers all of it. The scan being one
   click away is what makes that honest: the text is a route to the document and never a
   substitute, so the failure mode is a missed hit rather than a false quotation. Withholding
   would itself be a claim, and a worse-calibrated one — *"scanned; not yet read"* on a page
   we have read says something untrue, where a stated band says something true.

   **No derived assertion is published from it until its class is measured.** ADR 0017 D3,
   unchanged: `document_text` joins `measured_target_vocab` with its `class_vocab` left
   empty, so no row claims `confidence_state = 'measured'`, and no OCR-channel citation,
   party attribution or alert reaches a reader on an unmeasured reading. Showing a person
   text they can check against the scan is reversible in their head; mining it into a fact
   whose derivation they never see is not.

8. **What the engine reported and what the pipeline concluded are different columns.** The
   engine's self-reported confidence is stored verbatim, is uncomparable across engines, and
   is **never shown to a reader as a number**. `confidence_state` — `measured | human |
   unmeasured | not-applicable`, the vocabulary `citation` already uses — is the predicate,
   the number inert beside it. What a reader sees is a band derived from the measured
   agreement signal, never an engine's opinion of itself.

9. **Which reading is displayed is recorded, not ranked — in this migration.**
   `document_text` carries `reading_role` (`primary | second | human`), fixed at insert,
   because the router choosing this engine for this page is an observation rather than a
   policy. Display takes the human row if one exists, else the primary. **A model pass may
   never displace a human row**, enforced with a trigger as `citation` enforces it.

   The cost is named rather than hidden: this is a rule in code where the citator's
   equivalent is registry data. It is chosen because the alternative is rebuilding
   `assertion_method` — a table the citator reads on every projection, at schema 17 in
   production, before the citator has run its first real load. **Migration B replaces the
   rule with registry data** when the routing is settled enough for a rank to mean anything.

## What this record does not decide

Each deferred for a stated reason, not for lack of an opinion.

- **Ranking, `route_class`, and the `assertion_method` rebuild.** A rank matters only when
  something must choose between engines whose order is contested, and the routing that would
  order them rests on five tabular and nine graphic pages. `ocr-migration.md` records what
  the rebuild costs when it comes.
- **The review queue, and agreement as a stored judgement.** § Step 6 measured the flag rate
  at 20–60% — 19 to 58 years of a fifty-page week. A queue that must be *cleared* cannot be
  built on that, so the review layer is redesigned against the measurement in Migration B.
- **`page_route` as a table.** Nothing routes yet, and the engine that read a page is already
  recorded as that reading's `method`.
- **Which engine reads which tier, the render, and the order the tiers are read in** — the
  operator's, recorded in `ocr-plan.md`.
- **Where the bytes live, and what the public snapshot publishes** — ADR 0022.

## Consequences

**What becomes easy.** Two engines read a page and disagree without either being wrong in the
store. A re-run at a better engine, or a better render, is an insert. A human correction has
a home, an author and a date on the day the table ships. And the pre-2005 record becomes
findable, which is what capability M3 exists for.

**What becomes hard, or costs.**

- **~1.35M `document_text` rows**, and the store grows accordingly — ADR 0022 measures it.
- **The winner rule is code until Migration B**, a real departure from the citator's registry
  discipline, taken to avoid rebuilding a live table before its first load.
- **Decision 2's argument does not reach `citation_reading` or `decision_decided_date`.** Both
  live-index without a render, so a re-render at a better DPI produces a reading that
  *supersedes* its predecessor, and the evidence `document_text` keeps is destroyed one join
  over. Widening those keys is ADR 0018's to revisit; until then the pipeline's rule is that
  a re-render does not re-extract without a new method version.
- **Published pages move with this.** `coverage.html` says nothing is extracted from inside
  documents and `methodology.html` says documents are not searched. Both go wrong on ship
  day, and decision 3 means they go wrong for the born-digital record too.

**What this forecloses.** A store where one page has one text, and any pipeline that decides
its engine once, globally.

## Validation

Checked against `docs/validation-queries.md`.

- **Q1 and Q5** read assertions derived from document text, absent for the pre-2005 record
  today. Decision 1's `text_id` gives them a source naming the *reading*, and decision 7's
  gate keeps an unmeasured reading out of a published answer or an alert.
- **Q2** is the citator's and joins `document_text` nowhere. Decision 4 keeps it that way:
  one edge, one `citation_key` row, whichever channel read it.
- **Q3** needs `asserted_at` and `superseded_at` on every reading and gets both. It is **still
  not fully answered, and this record does not claim otherwise**: under decision 9 the
  displayed reading is a code rule, and a rule has no date. Migration B's registry will have
  one, and will inherit migration 0014's undated `rank_version` problem with it.
- **Q4** is unaffected today, and inherits Q1 the day a NITU date is quoted from a page.

**The consumers this record most affects are not among the five** — search, the viewer and
the public snapshot. That is a limit of the validation set, and it is why the four-lens panel
found what a query check did not.

## Cost of reversing

**The grain (decisions 1–5): expensive.** Not a migration but a re-read: 2.71 s a page over
247,923 pages, about 187 hours of box time plus the operator's re-checking. That is why the
render is in the key — a column added before the first row is free, and the same column added
after the backfill is the whole backfill.

**The payload instead of a block table (decision 6): cheap, and chosen because it is.**
Payloads are kept and block ids reproduce from them, so blocks project at any later date.

**The display rule (decision 7): cheap, and reversible in the direction that matters.** A
gate can be added later. Text already shown cannot be unshown — but it was never asserted,
and the scan beside it said so.

**The code rule for the winner (decision 9): cheap by design.** Migration B replaces it with
registry data and nothing about the rows changes.

---

*Proposed, not accepted. Accept only after this decision has been checked against
`../validation-queries.md`.*
