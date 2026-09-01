# ADR 0017 — Citation edges ship from the API extractor, at measured confidence, with the registry and a reviewer between the model and the page

- **Status:** Accepted
- **Date:** 2026-08-30 (drafted; revised the same day after schema-critic review — see
  § Review; figures and status corrected 2026-08-31 when the batch finished — see
  § What the finished batch changed). **Accepted by the operator 2026-08-31 with three
  amendments folded in — see § Accepted.**

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

1. **The docket-shaped class ships from `regex-docket-cite`; the API model is bought for
   what regex cannot do.** *(Amended at acceptance, 2026-08-31; the sentence this replaces
   read "The extractor that ships is the API model" and was written before the batch.)* A
   regular expression over the text layer, validated against the registry, with the
   own-proceeding rule, scores **95.1%** recall on docket-shaped targets — unbeaten by any
   of the nine local candidates (best: qwen3:14b, 93.8%) and within half a point of Claude's
   95.6%, at no per-page cost. The registry is what makes it safe: it emits a docket only
   where one is held, so it cannot invent a proceeding.

   The API model — `method = 'model:claude-sonnet-5'`,
   `method_version = <prompt version>` (`2026-08-29` for the measured prompt) — ships for
   the forms regex cannot reach: reporter cites, date-named decisions, court citations and
   dated obligations. Each class names its own method on its own rows, so the two are never
   one undifferentiated confidence.

   **Not the role of a same-docket mention**, which the amendment candidate had listed and
   which is struck here (schema-critic, at acceptance). This record's own § What the
   finished batch changed concludes it: "neither beats reading which proceeding the
   deciding decision sits in. The record already knows that, so it is the one thing no
   extractor should be asked to decide" — own-docket rule 95.1%/88.1%, llama3.1:8b
   96.9%/79.3%, qwen3:14b 83.1%/95.9%. Buying a model for it would also collide on decision
   2's natural key, which does not include the method: the model would either mint a second
   `citation` row for a docket target regex has already extracted at that page, or write
   `kind` onto a row it did not extract, which § Foreclosed forbids. The role stays with the
   own-docket rule, on the extraction row. The score
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
  citing decision's own proceeding *and* no document word sits near it — scores ~~94.7%
  recall on docket-shaped targets~~ **95.1%, 214 of 225** (`benchmark_regex.py`; the 94.7%
  was measured before the scorer's quote matcher was corrected the same day, which had
  been case-folding away its own exceptions); on the unexposed class 97.2%, above Claude's
  95.3%. Its extras are own-proceeding
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
  Claude's 95.6% / 95.6%. Where it is clearly weaker is courts (74% vs 98%) and dated
  deadlines (84% vs 99%). ~~The batch of nine local candidates is still running.~~ **It
  finished 2026-08-31 — see § What the finished batch changed.**
- **Decision 8's re-extraction and the human rows** (schema-critic, on § 7 of the schema
  draft): a re-extraction supersedes every extraction row and mints new citation ids under
  stable natural keys — which would strand every human `citation_resolution` and every
  review action pointing at the superseded rows, defeating human-wins in projection while
  preserving it on paper. The migration that creates these tables must let resolutions
  follow the citation's **natural key** through supersession (or projections chase the
  chain); decide it before the first review-class edge, not after a ~$1,335 re-run.
- ~~Decision 3's verb gate conflicts with the live resolver's tested behaviour.~~
  **Settled 2026-08-30: the resolver changed, so decision 3 stands as written.** The
  citation resolver (`web/cite.py`, F2) had resolved `EP 711 decided 8/26/2026` to a
  decision whenever exactly one row in the family was *served* that day, with
  `test_registers.py` pinning it on purpose; on the sixty, 34 of 52 printed decided dates
  differ from the service date, so that "match" could be a sibling rather than the
  decision named — the wrong-edge failure `citator-gate.md` exists to prevent. `cite.py`
  now gates on the phrase's own verb: a decided date resolves to the docket sheet with a
  note, never to a decision, until a decided-date assertion exists. The test pins the new
  behaviour on both a date that would have matched and one that would not; `registers.md`
  and the module docstring carry the revised promise.

- **Extract each decision's own decided date in the same pass** (the operator, 2026-08-30).
  A decision carries two dates and the record holds one. Measured that day on the sixty:
  **55 print a `Decided:` line** (`citator-gate.md`'s count of 52 undercounts) and 34 of 52
  differ from the service date — so our record and a paper copy of the same decision
  disagree, with nothing on the page explaining why. Measured the same day, and the reason
  this is *not* a citation-resolution question: **0 of the sheet's 727 citations name a
  decided date**; 240 name a served date. The Board cites by service date, so the resolver
  is right to answer a decided-date query with the docket sheet (`web/cite.py`, settled
  above) — the decided date is wanted for display, for reconciliation against paper, and
  for the docket calendar, not for edges. The pass is already reading the page and the line
  sits in a fixed position under the caption, so the marginal cost now is one field and one
  more assertion type; the cost of adding it after the backfill is the ~$1,335 re-run.
  Stored as an assertion with the full ADR 0007 block — **not** a `decision_record` column
  (that table mirrors the latest observation and would destroy the history) and **not** a
  ledger event (a third clock would replay a decision as existing before the Board served
  it), both fenced by schema-critic in `citator-gate.md`. Accepting this closes that
  record's open question; declining it leaves the record permanently one date short of the
  documents it publishes.

## What the finished batch changed (2026-08-31)

This record's own precondition for acceptance was "accept when the batch reports". It
reported. Nothing in § Decision is rewritten here — that is the operator's to fold in at
acceptance — but the evidence decision 1 turns on is now complete, and a record that still
described a run in progress would misstate what it rests on.

- **Nine local candidates ran; none beats the record's own knowledge on the docket class.**
  The finished table is in `../extraction-benchmark.md`: the best local docket-shaped recall
  is qwen3:14b at 93.8%, against **regex + registry at 95.1%** and Claude at 95.6%. The
  regex baseline is therefore unbeaten by any local model, which is what decision 1 was
  waiting to learn.
- **A model judges better than a word list, and worse than the record.** The role classifier
  (2026-08-31) fixes the finder and asks only the judgement: llama3.1:8b reaches 96.9%
  recall at 79.3% precision, qwen3:14b 83.1% at 95.9%, the keyword window 79.6% / 86.9% —
  and the own-docket rule 95.1% / 88.1%. Both models beat the word list; neither beats
  reading which proceeding the deciding decision sits in. The record already knows that, so
  it is the one thing no extractor should be asked to decide.
- **One candidate returned nothing readable, and the scorer now says so.** gpt-oss:20b
  answered all 443 pages with an empty response, which scored naively is a clean 0% and is
  indistinguishable from an engine that found no citations. The scorer separates *answered
  nothing* from *found nothing*. That is a harness result, not a measurement of the model,
  and it is the reason a 0% in that table can never be read as a finding on its own.

**What this leaves the operator**, unchanged in substance from 2026-08-30 and now decidable:
acceptance itself, the decided-date placement, and the three amendment candidates above —
the docket class shipping from `regex-docket-cite`, the on-page rule joining the resolution
pass, and decision 8's supersession path for human rows, which must be settled before the
first review-class edge rather than after a ~$1,335 re-run.

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

~~**Acceptance deferred by the operator, 2026-08-30**: five local candidates and the role
classifier are still running, and decision 1 turns on the complete table. Accept when the
batch reports.~~

**The batch reported, 2026-08-31.** All nine local candidates and the role classifier are
scored; the regex baseline's **95.1%** recall on the docket-shaped class is unbeaten by any
of them. The precondition this record set for its own acceptance is met, and decision 1 can
be taken on the complete table (§ What the finished batch changed). Still the operator's:
acceptance, and the decided-date placement.

## Accepted (the operator, 2026-08-31)

Accepted with three of the four amendment candidates folded in. The fourth is not settled
and is not accepted by this record.

1. **The docket class ships from regex + registry** (§ Decision 1, amended in place above).
   The batch is what decided it: 95.1% against nine local models' best of 93.8%, and the
   API extractor is bought for the classes regex cannot reach rather than for all of them.
2. **The on-page rule joins the resolution pass**, not only the scorer. A quoted passage
   that is not in the decision's own text is not an edge, checked with the scorer's own
   matcher (`benchmark_score.on_page`). This is a *resolution* test and therefore a
   `citation_resolution` row like any other (decision 3): the extraction row is never
   discarded for failing it, and the reason it failed is recorded rather than implied.
   It exists because a small local model copied the prompt's worked examples onto pages
   where they do not appear, 13 of 26 extras — a failure rule 1 cannot see, because the
   docket named is real.
3. **The decided date is extracted in the same pass.** 55 of the sixty decisions print a
   `Decided:` line and 34 of 52 differ from the service date, so this record and a paper
   copy of the same decision disagree today with nothing on the page explaining why. It is
   stored as an **assertion with the full ADR 0007 block** — never a `decision_record`
   column (that table mirrors the latest observation and would destroy the history) and
   never a ledger event (a third clock would replay a decision as existing before the Board
   served it), both fenced by schema-critic in `citator-gate.md`. Accepting it closes that
   record's open question. The reason it is folded in *now* rather than later is arithmetic:
   the pass is already reading the page and the line sits in a fixed position under the
   caption, so it costs one field today and a ~$1,335 re-run afterwards.

**Not accepted, and still open: decision 8's supersession path for the human rows.** A
re-extraction supersedes every extraction row and mints new citation ids under stable
natural keys, which would strand every human `citation_resolution` and every review action
pointing at the superseded rows — defeating human-wins in projection while preserving it on
paper. The migration that creates these tables must let a resolution follow the citation's
**natural key** through supersession, or projections must chase the chain. It is settled
before the first review-class edge is written, not after. Nothing else in this record waits
on it.

### Re-checked against `../validation-queries.md` (2026-08-31, at acceptance)

The check in § Checked against was the drafter's, against the unamended decisions. What the
three amendments change:

- **Amendment 1 changes the method, not the shape.** `method`/`method_version` were already
  columns on both the extraction and the resolution, and the `method` registry (decision 1)
  already keys a score file per method — `regex-docket-cite` is a row in it, which is the
  method name the schema draft has always used. Query 2's join is over resolved edges and
  is indifferent to which method resolved them; confidence stays per-method rather than
  becoming one blended number, which is the property query 2 needs to filter on.
- **Amendment 2 adds no table.** It is a resolution outcome, so it lands in
  `citation_resolution` with its own ADR 0007 block and its own `superseded_by` — the same
  row shape queries 2 and 4 were validated against. It strengthens query 2: an edge whose
  quoted passage is not on the page is exactly the wrong edge `citator-gate.md` exists to
  prevent.
- **Amendment 3 follows the record's assertion PATTERN, and has no table yet.** *(Corrected
  at acceptance after schema-critic review; the first draft of this bullet said "it is the
  grain the record already has", which is not supported by `schema-draft.md`.)* A decided
  date is a quoted assertion about a document, carrying provenance (ADR 0007) and superseded
  rather than rewritten. It is **not** an event, so **query 3's replay is untouched** — the
  ledger it reads gains no row, and a decision does not become replayable as existing before
  the Board served it. That much stands.
  What does not: every assertion table in `schema-draft.md` § 5 is purpose-shaped with typed
  value columns (`party_name`, `place_geometry`, `instrument_event`, …), and **none has a
  `(document, assertion type)` key or a generic value column**. So this amendment names a
  table that does not exist and leaves the fork undecided — a typed `decision_decided_date`
  against a generic `document_assertion` EAV row, which this draft has consistently refused
  elsewhere. It is settled in the migration that creates it; nothing is written until then.
  **Query 4 gains less than the first draft of this bullet claimed**: `instrument_event.
  effective_date` is already quoted from the document's own words, not a service date, so a
  decided date adds little to that join. The trap query 4 caught — a re-extraction silently
  doubling every NITU — does apply, and `(document, assertion type)` is **not** a sufficient
  answer to it: a text-layer reading and an OCR reading of the same bytes both produce a
  decided-date assertion under that key and, at 10.8% CER, can disagree on the date, with no
  rule ordering two methods asserting at the same time. The key must carry the reading and
  the source location, as `place_mention`'s `(document_sha256, source_location, raw_text)`
  already does, and the row must carry the **printed string** as well as the parsed date —
  dates are quoted, never computed, and recovering the printed form later is the ~$1,335
  re-run this amendment was folded in now to avoid.
- **Query 2 is expressible and its join is not yet writable**, which the first draft of this
  subsection passed over by saying the join was "unchanged". Two columns it needs have no
  home: `treatment` is enumerated on neither `citation` nor `citation_resolution` (decision 8
  defers typing to "a later resolution pass" without naming the column), and
  `cited_decision_id` keys on the work, `stb_decision_id`, which **is not a key of any
  table** — in the live store it is unique only as `(docket_id, stb_decision_id)`. Nothing
  therefore stops a resolution naming a work that does not exist, which is the
  invented-target failure the registry check prevents one level down. Both are settled in
  the migration; a `decision_work` registry minted from `decision_record` is the obvious
  home for the second.
- **Amendment 2 makes `citation_resolution` hold several live rows of different kinds** —
  a rule-1 resolution, a rule-2 repair at lower confidence, an on-page veto, a role row and
  a human row can all be live at once under a key of `(citation_id, method,
  method_version)`, because supersession is *within* a method. Decision 3 says "every
  projection reads the live resolution", singular, and there is no precedence column: a null
  `cited_docket_id` now means three different things (not attempted, attempted and failed,
  vetoed). A typed outcome and a precedence rule are owed before the first projection.
- **Queries 1 and 5** — untouched; no table they read changes.
- **ADR 0004's lesson still holds one level down**: a target cell may be a list, and each
  member is its own row.

### What must be settled before the first edge is written (schema-critic, at acceptance)

The critic reviewed the amended record against the five queries before this status changed.
Nothing it found breaks a query, and none of it is a reason to hold the decision — but each
is a claim this record would otherwise make and could not keep, so each is named here rather
than discovered in a migration. Two were corrected above (decision 1's class list, and the
re-check's account of amendment 3); these four remain:

1. **Decision 4's confidence table stamps the wrong engine for the class that ships.** Its
   docket row — "resolved, not exposed → 0.953 precision, 0.953 recall" — is Claude's
   figure, and after amendment 1 that class ships from `regex-docket-cite`, measured at
   **95.1% recall / 88.1% precision**. Decision 9 shows a reader the method and its measured
   confidence side by side, so as it stands a `regex-docket-cite` row would display a
   number Claude earned. Confidence must be keyed `(method, method_version, class)`, and the
   regex figures written into the table, before any edge is projected. The precision figure
   the amendment implies — regex on the unexposed class, after the projection rule — appears
   nowhere in this record and is a measurement, not a decision.
2. **Decision 8's supersession path is cheaper to defer than it was, and likelier to bite.**
   The deferral was priced against a ~$1,335 re-run. Amendment 1 moves the docket class —
   the only class projected unreviewed, and the one both human queues in decision 6 sit on —
   onto a **free** extractor, so the event that mints new citation ids and strands human
   `citation_resolution` and `review_action` rows is now cheap and frequent rather than dear
   and rare. Amendment 3 shows the fix: anchor on the natural key, not a surrogate id.
3. **The on-page veto has no declared reading scope.** It was measured on born-digital text
   (15 failures of 977, all page-spanning quotes) and decision 1 ships OCR at 10.8% CER; a
   text-layer extraction checked against OCR text would be vetoed spuriously. The veto must
   name the reading it checked, it must be the extraction's own reading, and its measured
   pass rate is its confidence.
4. **A NULL confidence is a narrowing of ADR 0007, and it is written here rather than
   there.** 0007's Decision is categorical — every extracted fact carries a confidence — and
   the live convention is stronger: `0006_parties.sql` declares
   `confidence REAL NOT NULL CHECK (confidence > 0 AND confidence <= 1)` on all four party
   tables. Decision 4 permits NULL "where the class is unmeasured", and amendment 1 widens
   the reach of that case, because the classes the model keeps are exactly the ones with no
   readable precision (court: unreadable; record: unmeasured). "A NULL confidence is never
   projected" keeps it off the page, so nothing reaches a reader wrongly — but a narrowing
   of an accepted ADR belongs in a record of its own, not inside this one.
   **This one is the operator's**: either 0018 narrows 0007 explicitly, or decision 4 drops
   the NULL case and an unmeasured class simply does not ship until it is measured.

Also drifting, and not a schema question: `docs/citator-gate.md` still says "Status: open
questions, not decisions … Nothing here is accepted", which this record has now made untrue,
and `schema-draft.md`'s citation section is three revisions behind the accepted design
(`citation.treatment`, `cited_decision_id` FK to `decision_record`, and the superseded
natural key). `web/cite.py` carries a promise — "until a decided-date assertion exists, a
decided phrase resolves to the sheet" — whose trigger amendment 3 creates without setting a
coverage condition for flipping it; a decided-date lookup against a partial assertion set
can confidently name the wrong decision, which is the failure the resolver was changed on
2026-08-30 to avoid.

*Accepted. Superseding any of this means a new record, never an edit to this one
(ADR 0001) — the amendments above are folded in at acceptance, which is the moment this
record itself reserved for them, and each says what it replaced.*
