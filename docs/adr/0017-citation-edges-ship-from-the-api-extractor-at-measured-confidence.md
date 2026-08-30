# ADR 0017 — Citation edges ship from the API extractor, at measured confidence, with the registry and a reviewer between the model and the page

- **Status:** Proposed
- **Date:** 2026-08-30 (drafted; revised the same day after schema-critic review — see § Review)

## Context

The extraction benchmark (`docs/extraction-benchmark.md`) exists to decide what the citator
(capability C2) reads decisions with, before any extraction commits. Its step 3 is this
record. The evidence it rests on is the 977-row label sheet over sixty decisions, **checked
by the operator on 2026-08-30** (all 884 queue cards judged, one row wrong, none missing),
and the runs scored against it after the check. Figures published before the check are not
readable — an unlabelled real citation scored as a false positive — and are not used here.

What the benchmark settled, all dated after the check:

- **The extractor is the whole game; OCR is not.** On identical text, Claude Sonnet 5 finds
  89.2% of the sheet's STB edges and a local 14B model (qwen3:14b) 73.5%. Over Textract's
  OCR of the same pages Claude finds 91.9%. A local model that misses a quarter of the
  edges is a different product, not a cheaper one; a 10.8% character error rate costs no
  measurable edges. Money therefore belongs at extraction (~$1,075 batched for the backfill)
  and OCR should be as cheap as is adequate (~$260, `docs/ocr-plan.md`).
- **Precision as the scorer keys it is 64.2%, and most of that loss is not a wrong docket.**
  Of the 165 STB findings not in the sheet, 155 are forms the sheet's conventions fold or do
  not hold: reporter cites (`3 I.C.C.2d 606`), pin-cite short forms (`IHB II, 3 I.C.C.2d at
  610`), `id.`-style references (`Decision at 15`), and narrative `decision served October
  5, 2017` phrases. None resolves to a docket.
- **On docket-shaped targets — what a citator resolves — Claude scores 95.6% recall and
  95.6% precision** (225 edges in the sheet, 215 found, 10 extra; over OCR 217 found, the
  same 10 extra; figures after the on-page check and the scorer's suffix fix, both
  2026-08-30 — the first draft read 95.9% / 95.5% on 220). **All ten extras name the citing decision's own proceeding** — a caption
  or a consolidated member (`Docket No. NOR 42150` in a decision entered in NOR 42144 et al.)
  read as a citation. **Not one is an edge to a docket the decision never touched.** The
  nine misses are real (`FD 36797`, `NOR 42124`, `EP 705`, `FD 32760 (Sub-No. 21)`, …); the
  other 27 misses are reporter cites and date-named decisions, which resolve differently.
- **The extractor invents no docket numbers.** Against the registry (32,605 docket rows in
  the production copy), 6 of the 171 distinct docket targets in the sheet fail to resolve
  — and Claude emits exactly the same six and no other. Four are ICC-era proceedings that
  predate the 1996 record (`EP 445`, `EP 445 (Sub-No. 1)`, `EP 392 (Sub-No. 1)`, `FD 757`),
  one is a sub-docket the copy does not yet hold (`FD 36873 (Sub-No. 2)`), one (`FD 37470`)
  neither resolves nor repairs. A model reading the text layer *has* emitted a fused
  footnote marker as a docket (`NOR 421441`; `docs/citator-gate.md`), so the class exists
  even though this run produced none.
- **The fused-footnote exposure is measurable per target.** A resolved target is exposed
  when the reading with its last digit removed is *also* a held docket (`AB 1242` and
  `AB 124` both exist, so `AB 1242` may be `AB 124` plus footnote 2). On the sheet that is
  **5 of 225** docket targets, all four-digit `AB` numbers; the other 214 — every five-digit
  docket and every three-digit `EP` — have no held shorter reading. On the 214 Claude scores
  95.3% recall and 95.3% precision, the ten extras being the same self-references.
- **A consolidated decision carries one `decision_record` row per member docket** (measured:
  1,736 of 19,827 held decisions have more than one; decision 51532 has five, `EP 328
  (Sub-No. 2)` and four `NOR`s). The work is identified by `stb_decision_id`, which the
  site already counts by; the per-docket row is not the work.
- **Court citations** are found at 97.7% but cannot be validated against any registry.
  **Record cites** (`IANR Reply 2, Aug. 14, 2024, FD 36798`) cannot be measured: the sheet
  holds 12 and one decision alone prints about 20.

What is contested: whether a measured 95% is fit to publish as fact; where the rest goes;
what a reviewer sees; and how a decision — not a docket, not a hash — becomes the target,
which is what validation query 2 needs and ADR 0002 forbids keying on bytes. The labelling
conventions and the two docket-resolution rules in `docs/citator-gate.md` are inputs here,
not decisions; this record makes them decisions.

## Decision

1. **The extractor that ships is the API model: `method = 'model:claude-sonnet-5'`,
   `method_version = <prompt version>` (`2026-08-29` for the measured prompt).** The score
   file that measured a version is recorded beside it in a small `method` registry table
   (method, version, benchmark date, score file) — the draft has none, and confidence
   stamps need one. It reads the publisher's text layer where one exists and Textract's OCR
   where the file is image-only; which reading is recorded on the row. **The local model
   does not write citation edges.** RMI-AI-MACHINE remains where anything is tried first,
   at no cost, and a local model may be re-measured against the same sheet; it ships when
   it scores, not before.

2. **Every finding is stored as a `citation` row that is never rewritten.** It carries
   `cited_raw` (the string as printed), `kind` (`citation` or `caption` — the extractor's
   own *document versus proceeding* call on the text), `target_kind` (`stb`, `court`,
   `record`), `target_form` (`docket`, `reporter`, `date`, `other` — so the classes below
   are columns, not a regex over `cited_raw` at projection time), the reading it came from
   (text layer or OCR method and version), the quoted passage, and ADR 0007's block for the
   *extraction*. Its **natural key is `(citing_document, page, target_kind, normalised
   target key)`** — stable across a text-layer and an OCR reading of the same bytes, which
   differ in the quoted passage (10.8% CER) and would otherwise double every edge on
   re-read; the passage is payload. Repeats of one target on one page collapse to one row;
   repeats across pages fold at projection. A row is never discarded for failing to resolve.

3. **Resolution is its own assertion, in its own table.** `citation_resolution` rows are
   keyed `(citation_id, method, method_version)`, each with ADR 0007's block, its own
   `confidence`, its own `superseded_by`, the `class` it was assigned (decision 4), and
   the outcome: `cited_docket_id` (**rule 1**: the normalised key — prefix, sequence,
   sub-number, suffix — matches the registry exactly, else null), `cited_decision_id`
   **keyed on the work, `stb_decision_id`**, never on a per-docket `decision_record` row
   and never on a hash; and, for a **rule 2** repair (the raw fails, exactly one
   trailing-digit-stripped reading resolves, and the printed number has five digits), the
   repaired key, as a distinct `method` at lower confidence. Because resolution is a row
   and not a column on the extraction, the registry growing (`FD 36873 (Sub-No. 2)`
   arriving), a better resolver, and a reviewer's `human` row each supersede the previous
   *resolution* and leave the extraction row and its provenance intact; a `human`
   resolution is never superseded by a model pass, and a new extractor version still
   supersedes the extraction. Every projection reads the live resolution.

   A decision is resolved to a work when the text names a document — a decision number,
   a service date, `slip op.`, `NPRM`, `order` — and exactly one `stb_decision_id` in that
   docket matches. **The phrase's own verb gates the column:** `served <date>` matches
   `service_date`; `decided <date>` matches nothing until a decided-date assertion exists
   (34 of 52 decisions on the sheet print a `Decided:` line that differs from the service
   date, so matching it against `service_date` would resolve to the wrong decision when a
   sibling was served that day) and stays at docket level. Only `service_date` as the
   Board's table observed it is used; `decision_record` mirrors the latest observation and
   is not the ledger.

4. **Confidence is the measured precision of the resolution's class on the checked sheet,
   not the model's opinion.** It is stamped on the resolution row, per class, from the
   `method` registry's benchmark date; NULL where the class is unmeasured, and **a NULL
   confidence is never projected** — a schema rule on the projection view, not prose. The
   classes, and what each is fit for:

   | class | measured (2026-08-30) | projected as "cited by" |
   | --- | --- | --- |
   | docket, resolved, **not exposed** (the trailing-digit-stripped reading is not a held docket) | 0.953 precision, 0.953 recall, 214 of 225 | **yes, unreviewed** |
   | docket, resolved, **exposed** (both readings are held: `AB 1242` / `AB 124`), or resolved only by rule 2 | 5 of 225; no wrong edge among them | **after review** |
   | docket, unresolved | 6 of 171, none invented | **never**; shown as "cites `EP 445` (not in the record)"; queued if in range |
   | reporter (`4 S.T.B. 303`) or date-named, unresolved to a work | unreadable (the sheet folds the forms) | not in this slice; stored |
   | `court` | 0.977 recall; precision unreadable | not in this slice; stored, typed |
   | `record` | not measured | not in this slice; stored; **explicitly not scored** |

   The 0.953 is measured *before* the projection rule of decision 5; on the sheet that rule
   absorbs all ten extras, so what readers see is better than the stamp. The stamp stays
   the conservative figure and the coverage page says which set it was measured on.

5. **An edge to the citing decision's own proceeding is a self-reference, and the store
   treats it as one without deleting it.** The extractor's `kind` is stored and is the
   primary classifier. On top of it, a resolved edge whose target docket is in the
   **family** (the docket, its parent, its sub-dockets — the family CTE the schema draft
   already uses) of any docket the citing decision carries a `decision_record` row in is
   **not projected at docket level** — the record already holds that membership — and **is
   projected when `cited_decision_id` resolves to a different work**, which is exactly the
   reconsideration edge query 2 exists to find. A projection rule over kept rows, not a
   deletion: the 86 same-docket document citations the gate protects remain edges. A
   same-docket edge that names a document but does not resolve to a work goes to review.

6. **What is left to a human, under ADR 0016.** Four queues, in this order of yield: the
   exposed class and every rule-2 repair; unresolved docket targets whose prefix and
   sequence fall inside the held record (an ICC-era number is expected to fail and is not
   queued; `FD 37470` is); same-docket document citations that did not resolve to a work;
   and every reader report (`/contribute`). A review writes a `human` resolution row. On
   the sheet the first two queues hold 5 and 1 of 225 edges; the queue is bounded by the
   tail, not the record, and nothing in the unreviewed class waits on it.

7. **Projection folds by work.** "Cited by" and every count are distinct `(citing work,
   target)` pairs, the citing side reached through `decision_attachment` and the
   `document_source.supersedes_sha256` chain, so an erratum's second hash does not double
   an edge and short-form density does not inflate a count. Readers cite counts.

8. **Not in this slice, doors kept.** Every edge is `cites`; treatment typing is a later,
   higher-`method_version` resolution pass. Statutes are not extracted — adding them is a
   `target_kind` value and a **re-extraction at a new prompt version (~$1,335 again),
   which supersedes every extraction row**; not a migration, but not free. Reporter cites
   resolve later through a reporter→work table (an addition). Record cites take a nullable
   `cited_filing_id` on the resolution row (an addition; the draft does not yet have it).
   The decided date (`docs/citator-gate.md`) is a separate decision and is not made here.

9. **What a reader sees.** A "cited by" list shows, per edge, the citing passage, its page,
   the extraction method and version, the class and its measured confidence, and the
   reviewer's credit name where a human resolved it (ADR 0016). The coverage page counts
   edges by class and resolution state from the store. No count is published without its
   class.

## Consequences

The citator's first slice can be built and its numbers are known before the first edge is
stored: 95% of docket-level edges arrive unreviewed at 95% precision, with the whole
measured error being self-references the projection rule absorbs. Re-measurement is a
scorer run, not a migration, because the sheet, the scorer and the conventions are in the
repository and every row names its method version. A better extractor supersedes
extraction rows; a better resolver, a grown registry or a reviewer supersedes resolution
rows; neither touches the other. The `citation` table exists in no migration yet, so the
shape above costs nothing today and a full re-extraction later.

The costs: the API bill (~$1,335 backfill, then the forward trickle at ~250 documents a
month); an operator-issued key per run, revoked after (the last one is); two assertion
tables and a method registry where the draft sketched one table, with the schema draft's
citation section to be revised on acceptance; a resolution pass written against the
registry and the decision records rather than borrowed from the scorer; and the review
area (`/review`, ADR 0016) before the first review-class edge is projected. The measured
figures are from born-digital decisions of one two-year window; older, scanned decisions
are read through OCR at a bound of *no measured damage*, and the first backfill wave's
edges should be sampled against a fresh sheet before the class confidences are trusted on
the 1996–2005 record.

Foreclosed: publishing an edge with no provenance or no class; a local-only citator at the
measured recall; deleting an unresolved citation; rewriting an extraction row.

## Cost of reversing

**Cheap for the method, dear for the promise.** Swapping extractor or prompt is a new
`method_version` and a supersession pass — no row is lost. Changing the class boundaries
re-runs resolution over kept rows. What cannot be cheaply reversed is a published "cited
by" count that turns out to include self-references, doubled errata or invented dockets:
readers cite counts. That is why the boundary sits at the measured, unexposed class with
self-references projected only at work level, and why nothing below it is projected at all.

## Checked against `../validation-queries.md` (2026-08-30, before proposing)

- **Query 2 (negative treatment)** — the edge keys on the cited **work**
  (`stb_decision_id`), resolved from a document-naming citation within a docket: not a
  hash (ADR 0002's boundary) and not a per-docket `decision_record` row, which would return
  a subset of a consolidated decision's edges — the revision-1 failure one level up.
  Decision 5 keeps the same-docket document citations that are the commonest negative
  treatment. Treatment typing is a later resolution pass; the query's join is unchanged.
- **Query 3 (point-in-time)** — an edge is an assertion, not a ledger event; the replay
  in the draft's sketch reads only `event` and is untouched. Where a reconstruction wants
  "what cited this by then", the citing side is reached as a work through
  `decision_attachment`, and its date is the `decision_observed` event, not
  `decision_record.service_date` and not `asserted_at`. An erratum's edges are the
  original work's edges by decision 7, so a date between original and erratum loses none.
- **Query 4 (lifecycle, provenance)** — the extraction and each resolution carry their own
  ADR 0007 block; a rule-2 repair is a resolution row, never a rewrite of the raw.
- **Queries 1 and 5** — untouched; no table they read changes.
- **ADR 0004's lesson, one level down** — a target cell may be a list (`NOR 42144; NOR
  42150; …`); each member is its own row, never the first match only.

## Amendment candidates (2026-08-30, after the local batch began)

Measured the same day, after this record was drafted, and left for the operator to fold
in at acceptance rather than rewritten silently:

- **The docket-shaped class needs no model.** A regular expression over the text layer,
  validated against the registry, with one rule — a hit is a caption only when it is the
  citing decision's own proceeding *and* no document word sits near it — scores **94.7%
  recall on docket-shaped targets** (`tools/rmi-ai-machine/benchmark_regex.py`, 213 of
  225); on the unexposed class 97.2%, above Claude's 95.3%. Its extras are own-proceeding
  mentions the projection rule of decision 5 absorbs. Decision 1 would then read: the
  docket class ships from `regex-docket-cite` (the method the schema draft already names)
  and the API extractor is bought for what regex cannot do — reporter and date-named
  forms, court citations, deadlines, and the role of a same-docket mention.
- **The on-page rule belongs in the resolution pass, not only in the scorer.** A small
  local model copied the prompt's own worked examples onto pages where they do not exist
  (13 of 26 extras); the docket named is real, so rule 1 passes it. *A quoted passage that
  is not in the decision's text is not an edge* — checked with the scorer's matcher
  (`benchmark_score.on_page`), which passes all but 15 page-spanning quotes of the checked
  sheet's 977.
- **A local extractor is closer than the first draft said.** qwen3:14b on the current
  prompt, after the on-page check, scores 93.8% / 93.8% on the docket-shaped class against
  Claude's 95.6% / 95.6%; the batch of nine local candidates is still running. Where it is
  clearly weaker is courts (74% vs 98%) and dated deadlines (84% vs 99%).

## Review (schema-critic, 2026-08-30)

Seven defects were reported against the first draft and are folded in above: resolution,
repair and review needed rows of their own, not columns on the extraction (decisions 2–3);
`kind`, `target_kind`, `target_form`, the class and a method registry were named but had
no column (2, 3, 1); the natural key doubled on an OCR re-read (2); the "four or more
digits" boundary admitted `EP 445` + a footnote as `EP 4451`, replaced by the measured
exposure test (4); `decided` phrases would mis-resolve against `service_date` (3); the
self-reference test was docket-exact where the record is a family (5); errata and repeats
doubled counts (7). Two of the critic's readings were measured rather than assumed: a
consolidated decision does carry a row per member docket, and the exposed class is 5 of
220. What remains the operator's: acceptance, and the decided-date placement.

*Proposed, not accepted. Accept only after this decision has been checked against
`../validation-queries.md` — the check above is the drafter's, revised on the critic's
findings; the operator's acceptance is still to come, in a later session.*
