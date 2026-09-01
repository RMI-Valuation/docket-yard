# ADR 0017 — Citation edges ship from the API extractor, at measured confidence, with the registry and a reviewer between the model and the page

- **Status:** Proposed — amended 2026-09-01, declined by the schema-critic the same day,
  **and corrected against that review; awaiting a second critic pass**
- **Date:** 2026-08-30 (drafted; revised the same day after schema-critic review — see
  § Review; figures corrected 2026-08-31 when the batch finished). Acceptance was taken on
  2026-08-31 and **held** by the operator the same day. On 2026-09-01 the operator settled
  the one question the hold rested on and directed the amendments to be folded in: they are
  now **in § Decision**, and the tables they need are proposed in
  [`../citator-schema.md`](../citator-schema.md). See § What acceptance would have rested on.

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
  **ten** misses are real (`FD 36797`, `NOR 42124`, `EP 705`, `FD 32760 (Sub-No. 21)`, …) —
  225 truth less 215 found *(corrected 2026-09-01: this said "nine", and the sibling
  arithmetic error "5 + 214" against 225 was caught in `citator-schema.md` without this one
  being swept up with it)*. The further 27 misses are reporter cites and date-named
  decisions, which resolve differently; they are misses against the **977-row sheet**, not
  against the 225 docket-shaped rows, and do not add to the ten.
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
   what regex cannot reach.** *(Amended 2026-09-01. The sentence this replaces read "the
   extractor that ships is the API model" and was written before the batch reported.)* A
   regular expression over the text layer, with the own-proceeding rule, scores **97.8%**
   recall on docket-shaped targets at no per-page cost — above Claude's 95.6% and every one
   of the nine local candidates (best: qwen3:14b, 93.8%).

   **That 97.8% is what the finder emits, and it is not what a reader sees** *(scoped
   2026-09-01, third critic pass)*. The six targets the move recovers are registry-**un**
   resolvable by definition, so they land in `docket, unresolved` and are never projected:
   they become decision 6's second review queue, which a finder-side filter had emptied by
   construction. The **projected** class still carries 214 of 225 — **95.1%**, or 97.7% of
   the 219 targets that are resolvable at all. Both figures are true of different things and
   this record publishes both, because the earlier draft stamped the finder's 97.8% on the
   class row decision 9 shows a reader.

   Against Claude the comparison stays finder-to-finder and stays honest: Measured 2026-09-01: the benchmark run filtered its emissions against the
   registry inside the finder, which scored 95.1% (214 of 225). Moving the check into
   resolution — see the next paragraph — recovers **exactly six targets, and all six are real
   edges in the sheet**: `EP 445`, `EP 445 (Sub-No. 1)`, `EP 392 (Sub-No. 1)`, `FD 757`,
   `FD 36873 (Sub-No. 2)` and `FD 37470`, which are precisely the six this record already
   named as unresolvable against the registry copy. Not one false positive comes with them
   (249 emitted against 243; precision as scored moves 88.1% → 88.4%, and after decision 5 it
   is 98.2% either way). The correction the schema-critic forced does not cost recall to buy
   correctness — it buys both.

   **The registry check is rule 1 of the RESOLUTION pass, not a filter inside the finder**
   *(corrected 2026-09-01, schema-critic)*. The measured run filtered its emissions against
   the registry, and a finder that can only emit held dockets cannot emit an unresolvable
   one — which empties decision 6's second queue by construction, makes decision 4's "shown
   as `cites EP 445` (not in the record)" a display this extractor can never produce, and
   makes `citator-gate.md` rule 1 — *record the span and the raw string; do not guess, and do
   not discard* — unimplementable, because the span is never seen. It also caps recall on the
   sheet at 219 of 225: the six ICC-era and not-yet-held targets are outside what a
   registry-filtered finder can say. So the finder emits every docket-shaped hit, and
   resolution decides what the registry holds. It still cannot invent a proceeding, because
   an unresolved target is stored as unresolved and never projected — and those six are now
   the `docket, unresolved` class decision 4 describes and decision 6's second queue holds,
   which were both unreachable before.

   The API model — `method = 'model:claude-sonnet-5'`, `method_version = <prompt version>`
   (`2026-08-29` for the measured prompt) — ships for reporter cites, date-named decisions,
   court citations and dated obligations. **Not the role of a same-docket mention**, which
   this record's own § What the finished batch changed settles: the record already knows
   which proceeding a decision sits in, and that is the one thing no extractor should be
   asked to decide.

   **One owning method per `target_form`**, because decision 2's natural key has no method in
   it: two extractors emitting the same target on the same page would collide, one row
   silently dropped or the edge counted twice. A finding outside its method's class is
   recorded at run level — an `extraction_run` row carrying counts — so "not kept" is an
   auditable number and never a silent drop. The score
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
   re-read. **Each reading is a row of its own in `citation_reading`** *(added 2026-09-01,
   second critic pass)*: `(citation natural key, reading_channel, reading_method,
   reading_method_version, source_location, quoted_passage)`. "The passage is payload" does
   not cover a **location**, and ADR 0007 requires one per assertion — under a key stable
   across readings the losing reading's `source_location` was simply lost. The child also
   makes `reading_channel` a joinable fact rather than a value set by whichever pass wrote
   first, which is what both the confidence stamp and the on-page veto have to key on.
   Repeats of one target on one page collapse to one row;
   repeats across pages fold at projection. A row is never discarded for failing to resolve.

3. **Resolution is its own assertion, in its own table.** `citation_resolution` rows are
   keyed on **the citation's natural key plus `(method, method_version, reading_channel)`**
   — the same composite decision 8 anchors human rows on, carried as typed columns and
   rendered canonically, never a surrogate id and never a digest. *(`reading_channel` added
   2026-09-01: without it, rule 1 run over a text-layer reading and over an OCR reading of
   the same page collide on the whole primary key, and so does a veto that names the reading
   it checked — the same defect `citator-schema.md` § B fixed one table over by keying
   `decision_decided_date` on the channel with the engine version outside it.)* *(Corrected 2026-09-01: this
   paragraph said `(citation_id, …)` while decision 8 said the natural key, so one record
   declared two primary keys for one table.)* Each row carries ADR 0007's block, its own
   `confidence`, its own `superseded_by`, the `class` it was assigned (decision 4), and:

   **a typed `outcome`** — `resolved` | `unresolved` | `repaired` | `vetoed` — because a null
   `cited_docket_id` otherwise means three different things at once, and Q2 cannot tell them
   apart.

   **Precedence is a rank in the method registry, not a value on the row** *(corrected
   2026-09-01, second critic pass)*. Supersession is *within* a method and several
   resolutions are live per edge (two extraction methods, rule 1, rule 2, the on-page veto,
   a human), so "every projection reads the live resolution" is singular only against an
   order. But a rank stored per row records a **policy** where the row should record an
   **observation**: re-ranking, or admitting a sixth pass, becomes an UPDATE of every row on
   an append-only table, and a closed enum has no rank for the three further passes decision
   8 promises (treatment typing, a reporter→work resolver, `cited_filing_id` for record
   cites). The rank is a column beside the method in the registry decision 1 already
   creates, joined at projection: adding a pass is one INSERT, re-ranking is one UPDATE of
   one registry row, and no assertion is ever rewritten. The order it currently holds is a
   human first, then a veto, then rule 1, then rule 2.

   Then the outcome itself: `cited_docket_id` (**rule 1**: the normalised key — prefix, sequence,
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
   not the model's opinion.** *(Amended 2026-09-01, and corrected the same day.)* It **stays
   on the resolution row**, `NOT NULL`, and the row carries an **FK to the exact score row it
   was stamped from**. An earlier draft of this amendment moved the number off the row into a
   joined registry; that deleted the column ADR 0007 requires every assertion to *carry*,
   which is a larger departure than the NULL it was trying to avoid, and it made the
   per-edge display of decision 9 a join that is neither unique nor reachable — the registry
   is keyed on EXTRACTION methods and the row being displayed is a RESOLUTION.

   The registry is **one append-only table**, `class_measurement`, keyed
   `(extraction method+version, resolution method+version, class, reading_channel,
   projection_rule_version, benchmark_date)`, carrying the score file, recall and precision.
   **The row's `score_row_id` names the exact measurement it was stamped from** — one target,
   stated once.

   *(A split into `confidence_class` + `class_measurement` was made on 2026-09-01 for the
   second critic pass and is **withdrawn** the same day, because the argument for it was
   wrong. It held that keeping `projection_rule_version` in the FK'd key would force
   `UPDATE citation_resolution SET score_row_id = …` over every row whenever decision 5's
   closure changed. It would not. A pointer into an **append-only** measurement table never
   needs updating: a rule change mints a new measurement, later rows stamp the new one, and
   earlier rows keep the historical one — which is exactly the snapshot Q3 wants. The
   every-row rewrite only arises if each row's stamp must always name the *current*
   measurement, which is the opposite of a snapshot and was never the design. The split also
   left the FK naming two different tables in eight lines and gave `class_measurement` no
   join key. Withdrawn, and the argument retracted rather than quietly replaced.)*

   What the row carries is a **snapshot**: the `confidence` shown to a reader and the
   measurement it came from. What the projection view joins is the measurement **in force**
   for the class under the rule version currently running. Both are available, neither is
   ever rewritten, and re-measuring strands nothing.

   **Confidence is NOT NULL, and a typed `confidence_state` carries the rest** (the
   operator, 2026-09-01): `measured` | `human` | `unmeasured` | `not-applicable`. The earlier draft
   permitted NULL "where the class is unmeasured", which narrowed ADR 0007's categorical text
   — every extracted fact carries a confidence — inside a record that is not 0007, and
   against the live convention (`0006_parties.sql` declares
   `confidence REAL NOT NULL CHECK (> 0 AND <= 1)` on all four party assertion rows). The
   state makes projection a positive predicate on the projection view rather than a test on
   absence. That predicate is **`confidence_state IN ('measured', 'human')`**.

   *(An earlier draft justified this by claiming NULL makes `WHERE confidence >= 0.9` and
   `WHERE NOT (confidence < 0.9)` disagree. It does not: in SQL both evaluate to NULL and
   both drop the row. The claim was wrong and is withdrawn; the reasons above are the
   reasons.)*

   **An unmeasured row must not carry a plausible number**, or a reader selecting
   `confidence` without `confidence_state` publishes an invention as a measurement:
   `CHECK ((confidence_state IN ('measured','human') AND confidence > 0 AND confidence <= 1)
   OR (confidence_state IN ('unmeasured','not-applicable') AND confidence = 0))
   AND ((confidence_state = 'measured') = (score_row_id IS NOT NULL))`. *(Corrected
   2026-09-01, third critic pass: the previous form said `confidence_state <> 'measured' AND
   confidence = 0`, which forced **every human row to a confidence of zero** — and `human` is
   in the projection predicate, so the rows carrying the most trust in this design would have
   projected showing a reader a zero, and any `AVG` over the view would have been wrong by
   exactly those rows. It also contradicted the live convention this decision cites in its own
   defence: the four assertion tables in `0006_parties.sql` carry real numbers on human rows.
   A human review has a confidence; what it does not have is a **benchmark**, which is what
   `score_row_id IS NULL` now says.)* The second clause
   binds the **pointer** as well as the number *(added 2026-09-01)*: without it a `measured`
   row can name no measurement and an `unmeasured` row can name a real one, which is the
   whole content of the correction above.

   **A human review is its own state, `human`** *(corrected 2026-09-01, second critic pass)*.
   The draft folded it into `not-applicable` with the on-page veto, and those two have
   **opposite** projection semantics: the veto suppresses an edge, while a human review of an
   exposed edge is precisely the row the exposed class is projected *on the strength of*. One
   state for both made the review queue's own output unprojectable by this decision's own
   rule — the same one-value-means-three-things defect `outcome` was introduced to fix,
   reproduced one column over. So: `human` for a reviewed row, which has no benchmark and
   must still meet ADR 0007 and 0016; `not-applicable` for the on-page veto, which carries a
   false-veto rate and not a confidence; `unmeasured` for a class not yet scored.

   The `0` sentinel is a real cost and is accepted with its eyes open: `0006_parties.sql`
   declares `confidence REAL NOT NULL CHECK (> 0 AND <= 1)` on all four party assertion
   rows, so this table **cannot reuse that idiom**, and any cross-assertion view written as
   `WHERE confidence > 0` silently drops every unmeasured citation row. `AVG`, `MIN` and
   `MAX` ignore NULL and are correct by default; they include `0` and are silently wrong.
   The rule is therefore not a convention but a constraint on every reader: **`confidence`
   is never selected without `confidence_state`**, and the projection view is the only
   supported path to it.

   `reading_channel` is in the key because every figure below was measured over the **text
   layer**, and decision 1 ships OCR at 10.8% CER: without it the first backfill would stamp
   a text-layer confidence on an OCR edge and decision 9 would show it to a reader. OCR is
   `unmeasured` on every class until somebody measures it, and therefore projects nothing.

   The classes, and what each is fit for:

   | class | reading | measured | projected as "cited by" |
   | --- | --- | --- | --- |
   | docket, resolved, **not exposed**, `regex-docket-cite` | text layer | **95.1%** recall of the 225 (214 projected; 97.7% of the 219 that are registry-resolvable); **98.2% precision after decision 5** (88.4% as scored), under `cite.py`'s family closure | **yes, unreviewed** |
   | docket, **unresolved**, `regex-docket-cite` | text layer | the 6 targets moving the registry check out of the finder recovers — all real edges, none projectable | never; decision 6's second queue |
   | docket, resolved, **exposed** (both readings are held: `AB 1242` / `AB 124`), or resolved only by rule 2 | text layer | see the note below — the count is stale | **after review** |
   | any class | OCR | **`unmeasured`** | **never** |
   | docket, unresolved | text layer | 6 of 171, none invented | **never**; shown as "cites `EP 445` (not in the record)"; queued if in range |
   | reporter (`4 S.T.B. 303`) or date-named, unresolved to a work | text layer | unreadable (the sheet folds the forms) | not in this slice; stored |
   | `court` | text layer | 0.977 recall; precision unreadable → `unmeasured` | not in this slice; stored, typed |
   | `record` | text layer | `unmeasured`; **explicitly not scored** | not in this slice; stored |

   **The exposed count in this record is stale, and the test needs stating.** "5 of 225" was
   measured against 220 targets, before the scorer's suffix fix moved the docket-shaped truth
   to 225, and was carried into the new denominator without being re-taken (measured
   2026-09-01). Under the test as this record describes it — the last-digit-stripped reading
   is also a held docket — today's figure is **14 of 225** if it applies to any target, or
   **3** if it applies only to bare numbers with no sub-number (`AB 1014`, `AB 1071`,
   `AB 1242` — which is what "all four-digit AB numbers" describes). Decision 6 sizes its
   review queue on this number; the test must be written down once before it does.

   The 0.953 — Claude's docket-shaped precision, the row above — is measured *before* the
   projection rule of decision 5; on the sheet that rule
   absorbs all ten extras, so what readers see is better than the stamp. The stamp stays
   the conservative figure and the coverage page says which set it was measured on.

5. **An edge to the citing decision's own proceeding is a self-reference, and the store
   treats it as one without deleting it.** **The classifier this rule was measured with is
   the quoted span, not the extractor's `kind`** *(corrected 2026-09-01, second critic
   pass)*. 98.2% was produced by absorbing an extra only when **its quoted span names no
   document** — a span carrying `Decision No. …`, `slip op.` or a served date is projected —
   and this decision called `kind` "the primary classifier", which is a different test
   measured at a different rate (88.1% precision on the own-docket call).

   **The span test is not the same rule as this decision's own "resolves to a different
   work", and the difference is measured** *(2026-09-01, third critic pass)*. Under the work
   test the pipeline can actually execute, all four projected extras are **suppressed**, and
   precision after decision 5 reads **100%** — the exact figure this record already retracted
   as false. The reason is that the work test cannot resolve them: `decision_record
   .decision_number` is populated for **0 of 23,713 rows in production** (measured on the
   instance; the column is filled by extraction later), and none of the four spans carries a
   served date — they read `Decision No. 1, FD 36744 et al., slip op. at 6` and
   `FD 36730 and FD 36731. Decision No. 1, FD 36732 et al., slip op. at 6`. So the work test
   is not the conservative rule it looks like. It is **blind**, and its 100% is produced by
   hiding four candidate wrong edges behind a resolver that resolves nothing.

   The **span test therefore governs**, and 98.2% is the honest figure precisely because it
   does not wait for a resolver that has no data. Because the span test decides what every
   published edge is, it is **a stored assertion and not a predicate computed inside a
   view**: `span_names_document` is a typed column with its own `method`, `method_version`,
   `confidence` and ADR 0007 block — the same discipline that demoted `kind`, which at least
   had a column. A projection rule with no provenance is a derived claim published without
   one, which this project does not do. `kind` is stored beside it, and **`kind` gets a class row of its own in the confidence registry** — one
   ADR 0007 block on the `citation` row currently covers four independent judgements
   (`cited_raw`, `kind`, `target_kind`, `target_form`) measured at different rates, and
   decision 9 shows a reader none of them. Adding the row is an addition, not a migration,
   but it must land in the first edge, because 98.2% is only honest beside it. On top of the
   span test, a resolved edge whose target docket is in the
   **family — the docket, its sub-dockets, and its parent, which is `web/cite.py`'s closure
   and NOT `schema-draft.md` Q3's CTE** (self plus transitive descendants, no parent; this
   record named the CTE and meant the other, and the difference is the parent). Measured
   2026-09-01: with the parent, precision after this rule is 98.2% and every emitted edge
   falls inside the closure; without it, 97.3% and two do not. Of any docket the citing
   decision carries a `decision_record` row in, a mention is
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
   the sheet the second queue is no longer empty by construction, because decision 1's
   registry check moved into resolution. **The first queue's size is undefined until the
   exposure test is** — "5 of 225" was measured against 220 targets, before the scorer's
   suffix fix, and is stale (decision 4); the same test reads 14 of 225 applied to any
   target today, or 3 applied only to bare numbers. The queue is bounded by the
   tail, not the record, and nothing in the unreviewed class waits on it.

7. **Projection folds by work.** "Cited by" and every count are distinct `(citing work,
   target)` pairs, so an erratum's second hash does not double an edge and short-form
   density does not inflate a count. Readers cite counts.

   **`stb_decision_id` is the fold; the `supersedes_sha256` chain is not** *(settled
   2026-09-01, second critic pass — the draft named both mechanisms and picked neither)*. The
   fold is `decision_attachment.document_sha256` → `decision_pk` → `decision_record`, then
   `DISTINCT` on `stb_decision_id`, which is correct because every member row of a
   consolidated decision carries the same id (`0002_filings_decisions.sql:64,71`; 1,736
   multi-row ids measured, **0 disagreements**). The chain is the wrong instrument here: it
   states no direction, it lives on `document_source` at several rows per document, and a
   regenerated file changes bytes without changing content. It stays for the case the fold
   cannot reach — *conjecture, unmeasured* — an erratum published under a **new**
   `stb_decision_id` rather than as replaced bytes under the known one. Whether STB does
   that is worth measuring before the projection view is written; the fold is authoritative
   either way.

8. **Not in this slice, doors kept.** Every edge is `cites`. **Treatment is typed in
   `citation_treatment`, its own table on the citation's natural key** *(settled 2026-09-01,
   second critic pass; `citator-schema.md` § F proposed it and this record said "a later,
   higher-`method_version` resolution pass", so the two documents named different homes for
   the column query 2 exists to read)*. It is not a resolution row: putting it there forces
   the typing pass either to restate `cited_decision_id` or to write NULLs into a column
   whose NULL already means three things, and it would have to compete in a precedence order
   that ranks *resolutions*, which a treatment is not. Its own table carries ADR 0007's
   block, its own `superseded_by`, and a `treatment_vocab` with a polarity, which is what Q2
   joins.

   **`extraction_run` is a table, not a phrase** *(defined 2026-09-01, second critic pass)*:
   one row per `(document, method, method_version)` that was passed over, with its outcome.
   Three separate claims in this record and in `citator-schema.md` lean on it — decision 1's
   out-of-class counts, "read, and there is no `Decided:` line" for the five decisions that
   print none, and the pass record itself — and none is expressible without it, because
   nothing else distinguishes *read and found nothing* from *not yet read*. Absence is not a
   measurement. Statutes are not extracted — adding them is a
   `target_kind` value and a **re-extraction at a new prompt version (~$1,335 again),
   which supersedes every extraction row**; not a migration, but not free. Reporter cites
   resolve later through a reporter→work table (an addition). Record cites take a nullable
   `cited_filing_id` on the resolution row (an addition; the draft does not yet have it).

   **`review_action` carries `key_version`, and the rendering declares its delimiter**
   *(added 2026-09-01, second critic pass)*. `schema-draft.md` § 6 declares `target_key`,
   `produced_key` and `method_version` and no `key_version`, while the supersession path
   below requires one; and the canonical rendering
   `<sha256>/<page>/<target_kind>/<key>` goes into `review_action.target_key TEXT` under
   `UNIQUE (queue, target_table, target_key)` with no stated escape. STB docket forms contain
   no `/`; *conjecture* — consolidated **court** case numbers, which `target_kind = 'court'`
   will carry, do. Both are free today, because `reviewer`, `reviewer_token` and
   `review_action` are paper only (no migration exists past `0013_search_caption.sql`), and
   both become a backfill the day `/review` ships. So: `key_version` is a column; the four
   fields are **also** stored typed on `review_action`, and the rendered string is a display
   and a uniqueness convenience rather than the only place the key exists.

   **Human rows survive a re-extraction** *(amended 2026-09-01)*. A re-extraction mints new
   `citation` rows, so a `citation_resolution` or a `review_action` anchored on a surrogate
   id would be stranded — and amendment 1 makes that event cheap and frequent, because the
   docket class now ships from a **free** extractor whose pattern is tweaked whenever the
   registry grows. Resolutions and review actions therefore anchor on the **natural key**,
   carried as typed columns and rendered canonically, never digested: the normalisation has
   already changed once (the suffix fix, 2026-08-30), and under a digest that class of change
   silently rewrites every key. `key_version` makes such a change a migration somebody can
   see. One limit, stated: `citing_document` is a sha256, so a review of an edge in the
   original does not follow into an erratum's bytes.

   **The decided date is extracted in the same pass** *(amended 2026-09-01; it was
   `citator-gate.md`'s open question and is settled here)*. 55 of the sixty decisions print a
   `Decided:` line, 5 print none and **none prints two** (measured 2026-09-01), and 34 of 52
   differ from the service date — so this record and a paper copy disagree today with nothing
   explaining why. It is stored as an assertion carrying ADR 0007's block, never a
   `decision_record` column and never a ledger event, both fenced in `citator-gate.md`. The
   table, its key and its projection rule are proposed in
   [`../citator-schema.md`](../citator-schema.md) § B.

9. **What a reader sees.** A "cited by" list shows, per edge, the citing passage, its page,
   the extraction method and version, the class and its measured confidence, and the
   reviewer's credit name where a human resolved it (ADR 0016). The coverage page counts
   edges by class and resolution state from the store. No count is published without its
   class.

## Consequences

The citator's first slice can be built and its numbers are known before the first edge is
stored: 95.1% of docket-level edges project unreviewed, at **98.2%** precision after
decision 5's rule (88.4% as scored). *(Corrected 2026-09-01: this said "at 95% precision,
with the whole measured error being self-references the projection rule absorbs" — which is
the retracted 100%-precision reasoning verbatim. The rule does not absorb the whole error;
four extras name a document and are projected, which is what 98.2% rather than 100% says.)* Re-measurement is a
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

## Re-checked against `../validation-queries.md` (2026-09-01, against § Decision as amended)

`CLAUDE.md` does not let this record be accepted without a check against the five queries,
and the check below the next heading was taken on 2026-08-30 against the drafted decisions —
before amendments 1, 4 and 8. It is kept for the history and **superseded by this one**,
which the schema-critic's review of the amended text forced: its claim that "the query's join
is unchanged" was true of the draft and false of the amendment.

- **Q1 — segment history. Expressible, untouched.** No table it reads changes.
- **Q2 — negative treatment. Writable, and it was not before the corrections above.**
  Six things had to be settled and are. `citation_resolution` has **one** key (decision 3;
  it previously declared two), and that key now carries `reading_channel`, without which
  rule 1 over a text-layer reading and over an OCR reading of the same page — or a veto that
  names the reading it checked — collide on the whole primary key and two live rows are
  indistinguishable. It has a typed `outcome`, so a null `cited_docket_id` no longer means
  three things and `outcome IN ('resolved','repaired')` is a real predicate. Precedence is a
  **rank in the method registry**, joined at projection, so "the live resolution" is singular
  *and* the order can admit the three later passes decision 8 promises without a rewrite —
  as a closed enum on the row it could rank none of them, so the `ORDER BY` this query needs
  was unwritable. `confidence` is back on the row with an FK to its measurement, so the
  display join is unique and reachable. And **`treatment` has one home**, `citation_treatment`
  (decision 8), where it does not have to restate a resolution, write NULLs into `outcome`,
  or compete in an order that ranks resolutions — Q2 *is* the treatment query, and it joins
  that table and a `treatment_vocab` polarity.

  The citing-side fold is sound as written: `citation.citing_document` →
  `document_source.stb_decision_id` with `DISTINCT` folds a consolidated decision's 1,736-id
  population correctly, because every member `decision_record` row carries the same
  `stb_decision_id`.
- **Q3 — point-in-time. Expressible.** No proposal writes to `event`; an edge is an
  assertion. The one cost, now paid: a displayed confidence used to be un-reconstructible,
  because an append-only registry keyed by benchmark date silently re-dated every projected
  edge. The row's FK to its score row fixes that — what a reader saw is what the row names,
  **and it stays true because nothing ever re-stamps it**: `projection_rule_version` is out
  of the FK'd key and in `class_measurement` (decision 4), so a change to decision 5's
  closure moves the projection and leaves every snapshot standing. Held the other way this
  paragraph would have overclaimed, because the stamp would have been rewritten by UPDATE.
- **Q4 — lifecycle and provenance. Expressible at a cost this record now names.** Decision
  2's key is deliberately stable across a text-layer and an OCR reading of the same bytes, so
  one row survives and the other reading's `source_location` — which ADR 0007 requires per
  assertion — is lost. "The passage is payload" does not cover a location. **The fix is
  adopted in decision 2, not left here**: `citation_reading (natural key, reading_channel,
  reading_method, reading_method_version, source_location, quoted_passage)`. It also makes
  `reading_channel` a joinable fact rather than a value chosen by whichever pass wrote
  first, which is what the confidence stamp and the on-page veto both key on — a check that
  named this fix in its own prose while no binding section held it would have accepted the
  defect and not the fix.
- **Q5 — service lists. Expressible, untouched.**

**One thing this check does not clear, and it is the last open blocker: the exposure test has
no single definition**, and the shipping class is *defined* by it. The same test — a target
whose last-digit-stripped reading is also a held docket — yields 3, 5 or 14 of 225 depending on
which reading is applied, and this record has published all three. Moving the registry check
out of the finder (decision 1) **enlarges what that test must catch**: a fused footnote such as
`EP 445` → `EP 4451` used to emit only if it resolved against the scored 32,605-row copy, and
now always emits, with resolution decided against a production registry that only grows. The
test is the sole defence in front of that, so it must be defined once, in one place, before the
first edge ships — not chosen at the migration.

*(`kind`'s 88.1% is no longer on this list: decision 5 no longer claims it as the classifier
behind 98.2%, and it now has a class row of its own. It remains first-edge work, not a
blocker.)*

## Checked against `../validation-queries.md` (2026-08-30, before proposing — superseded above)

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

> **Folded into § Decision on 2026-09-01**, at the operator's direction, and corrected where
> the schema-critic showed them wrong — see § What acceptance would have rested on. Kept as written because
> each says what it replaced, and because the third of them (the role of a same-docket
> mention) was struck rather than adopted.

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

## Offered for acceptance 2026-09-01, and declined by the schema-critic

> **The critic's verdict on the amended record: no.** Seventeen defects, six of them
> every-row, and three of the amended decisions contradict each other or an accepted record
> in ways that determine table shape. Its own summary of what the amendments got right is
> worth keeping — the typed natural key over a digest, `target_key` vs `produced_key`,
> `reading_channel` and `benchmark_date` in the confidence key, the honest retraction of 100%
> to 98.2%, and `decision_work` keyed after measuring 1,736 consolidated ids rather than
> before. **None of that is re-litigated.** What follows the list below is what must change.
>
> **Corrected the same day** — what each correction did is recorded in § Decision beside the
> text it replaced, and the validation check has been re-taken against the amended decisions
> (§ Re-checked, 2026-09-01), which is the thing `CLAUDE.md` will not let an acceptance skip.
> Six of the seventeen were structural and are fixed: the registry check moved out of the
> finder; `citation_resolution` has one key rather than two; it gained a typed `outcome` and
> a `precedence`, so Q2 can be written; confidence went back onto the assertion row with an
> FK to the measurement it was stamped from; the family closure is named once and correctly;
> and the false NULL-comparison argument is withdrawn.
>
> The largest finding is one nobody had caught, including the critic's own first pass:
> **`regex-docket-cite` filters its emissions against the registry, so it cannot emit an
> unresolvable docket target at all.** That empties decision 6's second review queue by
> construction, makes decision 4's "shown as `cites EP 445` (not in the record)" a display the
> shipping extractor can never produce, and makes `citator-gate.md`'s rule 1 — *record the
> span and the raw string; do not guess, and do not discard* — unimplementable, because the
> span is never seen. It also puts the shipped recall ceiling at 219 of 225, not 225. The fix
> is cheap today and needs a paid re-run later: **the registry check belongs in the resolution
> pass, which is what decision 3 already says resolution is.**

## What acceptance would have rested on (2026-09-01)

The acceptance taken on 2026-08-31 was held the same day because the schema-critic, reviewing
the amended record, found six things it would have claimed and could not keep. The operator
settled the one that was his on 2026-09-01 and directed the rest to be folded in. They are:
§ Decision 1, 4 and 8 above carry the amendments, and the tables they need are proposed in
[`../citator-schema.md`](../citator-schema.md), which the critic reviewed in turn.

**What the hold produced, which is the argument for holding it.** The first draft of those
proposals published **100% precision after projection** for the shipping method. That was
wrong: decision 5 does not *absorb* an own-proceeding mention, it suppresses one at docket
level and **projects one whose span resolves to a different work**. Four of regex's 29 extras
carry spans like `Decision No. 1, FD 36744 et al., slip op. at 6`, so the honest figure is
**98.2%**. Two further corrections came with it — the family closure used was a root-level
comparison that folds unrelated AB siblings together, where the live one is `web/cite.py`'s
(self, children, parent); and both sides must be normalised by the scorer's own
`norm_target`, or `EP 328 (2)` and `EP 328 (Sub-No. 2)` read as different dockets.

**What is measured now that was asserted before:**

- **Neither engine emits an edge to a proceeding the citing decision was not entered in** —
  29 of 29 regex extras and 10 of 10 Claude extras are own-proceeding. That is
  `citator-gate.md`'s governing rule measured directly.
- **1,736 `stb_decision_id`s carry more than one `decision_record` row and not one disagrees**
  on service date or decision number. Consolidation, not collision — so a `decision_work`
  registry keyed on that id is safe, and `cited_decision_id` gains the FK target it lacked.
- **55 of the sixty decisions print one `Decided:` line, 5 print none, none prints two**, so
  the decided date's projection rule needs no tie-break.
- **The exposed count is stale**: "5 of 225" was taken against 220 targets before the suffix
  fix. See decision 4.

**Still open, and each named rather than hidden** — none of them blocks acceptance, and all
of them block the first edge:

1. **The four projected extras have not been judged.** Sheet omissions, or real wrong edges?
   Four spans, one sitting. It decides whether 98.2% is the number or a floor.
2. **The exposure test needs one definition** (3 or 14 today, not 5), because decision 6
   sizes its human queue on it.
3. **Q2's join still does not run.** `citation_resolution` is keyed
   `(citation_id, method, method_version)` with supersession *within* a method, and several
   resolutions are now live per edge — two methods, plus the on-page veto — with no
   precedence column, so any "cited by" count is inflated. **A typed outcome and a precedence
   rule are owed before the first projection.**
4. **The classifier that produced the measurement is not in the repository.** If the figure is
   published it must be re-runnable beside `benchmark_score.py`.
5. **Nothing here is exercised by a validation query.** The decided date serves display, the
   calendar and paper reconciliation; none is one of the five. Its grain is unvalidated by the
   mechanism this project uses to validate grain, and this record should not borrow Q4's
   endorsement for it.

*Proposed, not accepted. Amended 2026-09-01 at the operator's direction, and reviewed again
by the schema-critic after amending. Accepting it means § Decision as it now stands, the
tables in `../citator-schema.md`, and the five open items above carried into the migration
that creates them.*
