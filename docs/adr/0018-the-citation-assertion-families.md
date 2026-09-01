# ADR 0018 — A citation is five append-only assertion families over one natural key

- **Status:** Proposed — cleared by the schema-critic 2026-09-01 (sixth pass); the operator's
  decision is outstanding.
- **Date:** 2026-09-01. Split from [ADR 0017](0017-citation-edges-ship-at-measured-confidence.md),
  which had grown to 1,082 lines by bundling a shipping decision with a schema. 0017 decides
  *what ships and at what confidence*; this record decides *what shape holds it*. Table
  sketches are in [`../citator-schema.md`](../citator-schema.md).

## Context

An extracted citation is not one fact. It is a string read off a page, a reading of that
page, a resolution of the string to a proceeding, a judgement about what kind of reference
it is, and — later — a treatment saying what the citing decision did to it. These are
measured at different rates, change at different times, and are asserted by different
methods: the regex resolves, a model judges, a human corrects.

The first draft put them in one row with one confidence and one provenance block. Six
review passes found the same defect in different clothes each time: a value that must be
superseded sitting inside a key, or two values sharing one confidence, or a live row nobody
could order against another. The shape below is what survived.

**Nothing here exists yet.** No citator table is in any migration, so every decision in this
record is still free.

## Decision

1. **One natural key, with no method in it:**
   `(citing_document, page, target_kind, normalised target key)`. It is stable across a
   text-layer and an OCR reading of the same bytes, which differ in the quoted passage
   (10.8% CER) and would otherwise double every edge on re-read. Resolutions, reviews and
   corrections anchor on it as **typed columns rendered canonically** — never a surrogate id
   and never a digest, because the normalisation has already changed once and under a digest
   that silently rewrites every key. A `key_version` makes such a change visible.

   Because the key has no method in it, **one method owns each `(target_kind, target_form)`**
   — two extractors emitting the same target on the same page would collide, one row dropped
   or the edge counted twice. Ownership is fixed at insert time from the owning method's own
   declaration, never from a later judgement row, or a supersession could move a row out of
   the class that admitted it. A finding outside its method's class is counted at run level
   (decision 10), so "not kept" is an auditable number and never a silent drop.

2. **`citation` carries identity only:** `cited_raw`, `target_kind`, and ADR 0007's block for
   the extraction. `target_kind` is in the key, so it cannot be corrected by supersession —
   a corrected row would mint a *different* key. A misclassification is a **retraction and a
   fresh assertion**: the new row is written and the mis-keyed row's `superseded_by` points
   at it. Superseding the *row* is legal though the *key* is not; without that pointer the
   old row stays live beside its replacement and the count doubles.

   `citation` carries **no `source_location`** — `page` in the key is its location. That is a
   deliberate departure from `schema-draft.md` § 5's uniform block and must not be reversed
   by restoring the column.

3. **`citation_reading`** holds one row per reading: key is the natural key plus
   `reading_channel`, with the reading method and its version as **payload outside the key**,
   or a re-OCR at a better engine mints a row that supersedes nothing and doubles the live
   readings — over a measured 1,480 of 9,663 image-only files. It carries the
   `source_location` and quoted passage, its own ADR 0007 block and its own `superseded_by`,
   because OCR text is derived. `reading_channel` is `text-layer | ocr | human`; the third
   value exists because the channel is in every key and a human row must carry something
   legal.

4. **`citation_resolution`** is keyed on the natural key plus
   `(method, method_version, reading_channel)` — without the channel, one rule run over two
   readings of a page collides on the whole primary key. It carries a typed **`outcome`**
   (`resolved | unresolved | repaired | vetoed`), because a null docket id otherwise means
   three things at once; its own confidence and state; and its own `superseded_by`. A row is
   never discarded for failing to resolve. Rule 1 matches the normalised key against the
   registry; a **rule 2** repair — the raw fails, exactly one trailing-digit-stripped reading
   resolves, and the printed number has five digits — is a distinct method at lower
   confidence, never a rewrite of the raw.

   A citation resolves to a **work** when the text names a document and exactly one
   `stb_decision_id` in that docket matches. **The phrase's own verb gates which column is
   matched:** `served <date>` matches `service_date`; `decided <date>` matches nothing until a
   decided-date assertion exists, and stays at docket level. 34 of 52 decisions print a
   `Decided:` line differing from the service date, so matching one against the other would
   resolve to the wrong decision whenever a sibling was served that day.

5. **`citation_judgement`** holds what is *judged* rather than identified — `kind`,
   `target_form`, `span_names_document` — keyed on the natural key plus
   `(judgement, method, method_version, reading_channel)`, with `value` as payload. They are
   measured at different rates (88.1% for `kind`, 98.2% for the span test) and one confidence
   column on the parent could never have carried three.

6. **`citation_treatment`** is its own table on the natural key plus method, version and
   channel, with a `treatment_vocab` carrying polarity. It is not a resolution row: putting
   it there would force the typing pass to restate the resolution or write NULLs into
   `outcome`. A review may write a `human` treatment row, or the one column query 2 reads
   would have no correction path.

7. **`assertion_method` is the single ordering registry for all five families:**
   `(target_table, method, method_version, reading_channel, role, precedence_rank,
   rank_version)`, **append-only**. Several assertions are live per edge, so "the live one"
   is singular only against an order — and an order stored per row records a *policy* where
   the row should record an *observation*, making a re-rank an update of every row.

   - **`role` is `suppress` or `resolve`, and projection is not "rank 1".** It is: *if any
     live `suppress` row exists, no edge; else the highest-ranked live `resolve` row whose
     `outcome IN ('resolved','repaired')`.* A flat rank made every rule-2 repair unreachable,
     because rule 1 writes a row when it fails and outranks the repair that exists because it
     failed.
   - **The projection predicate goes on the candidate set**, not the rank-1 row. On the
     rank-1 row it *deletes* edges: an unmeasured OCR resolution outranking a measured
     text-layer one takes rank 1 and the edge vanishes. The text layer outranks OCR for every
     method, held as registry data.
   - **A `suppress` row exists only once its false-veto rate is measured.** Absence of the
     row is how the record says "not yet trusted".
   - The formula is stated **per family**: treatment and judgement have no `outcome`, so
     theirs is the highest-ranked live row and nothing else.

8. **`class_measurement` is the single home for every score**, append-only, keyed on
   `(extraction method+version, resolution method+version, class, reading_channel,
   projection_rule_version, benchmark_date)` with a surrogate `measurement_id` so the
   pointer from an assertion is one column. `projection_rule_version` names three things
   together — the span test's version, the family closure's version, and `rank_version` —
   because the projection is that product.

   Confidence is `NOT NULL` on the assertion row with a typed `confidence_state`
   (`measured | human | unmeasured | not-applicable`), and
   `CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL))`. A human review has
   a confidence; what it lacks is a *benchmark*. Because unmeasured rows carry `0`, this
   table cannot reuse `0006_parties.sql`'s `CHECK (confidence > 0)` idiom, and **`confidence`
   is never selected without `confidence_state`** — the projection view is the only supported
   path to it.

9. **Projection folds by work.** "Cited by" and every count are distinct
   `(citing work, target)` pairs — `decision_attachment` → `decision_record.stb_decision_id`,
   falling back to `COALESCE(stb_decision_id, citing_document)` so an edge mined from a filing
   folds to itself rather than being dropped by an inner join. An erratum's second hash does
   not double an edge and short-form density does not inflate a count. Readers cite counts,
   which is why this is a decision and not an implementation detail. The `supersedes_sha256`
   chain is **not** the instrument: it states no direction and holds several rows per document.

10. **`extraction_run`** records the pass, one row per
   `(document, method, method_version, reading_channel)`, with a typed outcome. Nothing else
   distinguishes *read and found nothing* from *not yet read*. Absence is not a measurement.

## Consequences

Every value that can be superseded lives where it can be, and every live row can be ordered
against every other. What becomes hard: five tables where a first draft had one, and a
projection that is a documented formula rather than a `WHERE` clause anyone can guess.

## Cost of reversing

Free today — nothing is in a migration. One live table is touched: `correction` is at
migration 0006 with `target_id INTEGER NOT NULL`, and addressing a natural-keyed citation
row needs a text key and a CHECK, which SQLite can only do by rebuilding the table. Small,
and cheapest now.

## Owed at the migration that creates these tables

Four the first edge exercises: `measured_target` inside `class_measurement`'s COALESCE unique
index with a scoped `class` vocabulary; the projection predicate stated per family; a
`resolve` row asserting the *complete* outcome (or `cited_decision_id` moving to its own
family) since query 2 keys on it; and `citation_judgement`'s key declared with `value` as
payload.

Three cheap now, a table rebuild later: an `ordinal` in the decided-date key;
`(target_kind, target_form)` columns on `assertion_method` so the one-owner rule has a table;
a home for the veto's false-veto rate.

One deferred with its cost named: nothing dates `rank_version`, so the projection binds a
version rather than reading one. A `projection_rule` table is an addition any day; what is
**not** recoverable is which ranking was in force between the first edge and the day it lands.

## Checked against `../validation-queries.md`

**Query 2 is writable end to end** — the join path was written in full SQL by the
schema-critic, not asserted, across `citation`, `citation_reading`, `citation_resolution`,
`citation_judgement`, `citation_treatment`, `assertion_method` and the work fold. Queries 1
and 5 read no table here. Query 3 is untouched: no proposal writes to `event`, and a
confidence a reader saw is reconstructible from the row's own snapshot for `measured` rows —
`human` rows carry no `score_row_id` by decision 8's CHECK, which is the stated limit.
Query 4 is expressible on the deviation in decision 2.

Folding to the work (`decision_attachment` → `decision_record.stb_decision_id`) was measured
rather than assumed: 1,736 ids carry several `decision_record` rows with **0 disagreements**,
and 5 documents of 20,992 hang under two `stb_decision_id`s — the same bytes published under
two decisions served years apart, so the fold yields two citing works for those five, which
is correct and not a doubling.
