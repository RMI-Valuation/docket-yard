# ADR 0018 — A citation is five append-only assertion families over one natural key

- **Status:** **Accepted 2026-09-01 by the operator**, together with
  [ADR 0017](0017-citation-edges-ship-at-measured-confidence.md). Cleared by the schema-critic
  (six passes) and by a 13-agent adversarial review; validation query 2 is written out at
  [`../citator-query-2.sql`](../citator-query-2.sql) rather than asserted here.

  **What the acceptance covers:** the grain, the identity model, and the five families. **What
  it does not:** the eight items in § Owed at the migration — four of which the first edge
  exercises — and whether `citation_treatment` is in the first migration at all, which the
  adversarial review recommends deferring since it ships empty and is a DROP later, not a
  door.
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
   corrections anchor on it as **typed columns rendered canonically**, and a review anchors on
   `review_action.target_key` (the row reviewed), never `produced_key` (the row it wrote) —
   never a surrogate id
   and never a digest, because the normalisation has already changed once and under a digest
   that silently rewrites every key. A `key_version` makes such a change visible.

   Because the key has no method in it, **one method owns each `(target_kind, target_form)`**
   — two extractors emitting the same target on the same page would collide, one row dropped
   or the edge counted twice. Ownership is fixed at insert time from the owning method's own
   declaration, never from a later judgement row, or a supersession could move a row out of
   the class that admitted it. A finding outside its method's class is counted at run level
   (decision 10), so "not kept" is an auditable number and never a silent drop.

2. **`citation` carries identity only:** `target_kind`, the natural key itself, and ADR
   0007's block for the extraction. **`cited_raw` is not here** — the string as printed
   differs between a text-layer and an OCR reading (10.8% CER), so on a row keyed stably
   across readings whichever channel inserted first would own it for ever. It belongs beside
   the quoted passage it came from, in `citation_reading`. `target_kind` is in the key, so it cannot be corrected by supersession —
   a corrected row would mint a *different* key. A misclassification is a **retraction and a
   fresh assertion**: the new row is written and the mis-keyed row's `superseded_by` points
   at it. Superseding the *row* is legal though the *key* is not; without that pointer the
   old row stays live beside its replacement and the count doubles.

   **For that to change anything, the projection must join live `citation`** *(added
   2026-09-01, multi-agent review)*. A retraction supersedes the `citation` row and nothing
   else: the resolutions, judgements and treatments anchored on the retracted key still carry
   `superseded_by IS NULL`, so a projection that reads only those tables still publishes the
   mis-kinded edge. Joining `citation` and requiring it live is what makes the retraction
   effective — and it is the reason the stranded child rows are harmless rather than
   double-counting, which decision 2 asserted without the join that delivers it.

   `citation` carries **no `source_location`** — `page` in the key is its location. That is a
   deliberate departure from `schema-draft.md` § 5's uniform block and must not be reversed
   by restoring the column.

3. **`citation_reading`** holds one row per reading: key is the natural key plus
   `reading_channel`, with the reading method and its version as **payload outside the key**,
   or a re-OCR at a better engine mints a row that supersedes nothing and doubles the live
   readings — over a measured 1,480 of 9,663 image-only files. It carries the
   `cited_raw` (the string as printed by that reading), the `source_location` and the quoted
   passage, its own ADR 0007 block and its own `superseded_by`, because OCR text is derived. `reading_channel` is `text-layer | ocr | human`; the third
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
   measured at different rates (88.1% for `kind`; the span test is what the 98.0% projected precision was measured with) and one confidence
   column on the parent could never have carried three.

   **A `judgement_vocab` declares each judgement's value domain**, because one `value` column
   otherwise holds a boolean (`span_names_document`) and two enumerations (`kind`,
   `target_form`) untyped — which is the EAV shape `citator-schema.md` § B rejects one
   document over, and it would leave the projection comparing a boolean as a string.

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

   - **`role` is `suppress` or `resolve`, and projection is not "rank 1".** The resolution
     family's term is: *if any live `suppress` row exists **for the same reading channel**,
     no edge; else the highest-ranked live `resolve` row whose
     `outcome IN ('resolved','repaired')`.* A flat rank made every rule-2 repair unreachable,
     because rule 1 writes a row when it fails and outranks the repair that exists because it
     failed. The channel match is required because a veto names **the reading it checked**: a
     text-layer extraction checked against OCR text would be vetoed spuriously.

   - **That term is not the whole projection, and must never be read as if it were**
     *(restored 2026-09-01 — the split put this formula here and ADR 0017's self-reference
     gate there, and the formula read complete without it, which would publish every
     own-proceeding mention at 88.4% instead of 98.0%)*. **An edge projects only when the
     resolution term holds AND one of the two family terms does** *(the wording said "all
     three hold" and then joined 2 and 3 with "or", which is not a formula)*:
     1. the resolution term above; **and**
     2. the target docket is **outside** the citing work's family — the docket, its
        sub-dockets and its parent, unioned over every docket a consolidated decision is
        entered in (ADR 0017 decision 4);
     3. or, if it is inside, a live `span_names_document` judgement says `true` —
        **defaulting to suppress when no live judgement row passes** (ADR 0017 decision 4).

     The family closure is **registry data, not application code**, and its version is one of
     the three things `projection_rule_version` names (decision 8). `web/cite.py` computes the
     same closure for the lookup page; the projection may not depend on that being kept in
     step by hand.
   - **The projection predicate goes on the candidate set**, not the rank-1 row. On the
     rank-1 row it *deletes* edges: an unmeasured OCR resolution outranking a measured
     text-layer one takes rank 1 and the edge vanishes. The text layer outranks OCR for every
     method, held as registry data.
   - **A `suppress` row exists only once its false-veto rate is measured, and carries
     `confidence_state = 'measured'`.** Absence of the registry row is how the record says
     "not yet trusted". The state matters because the predicate above filters the candidate
     set: a veto left at `not-applicable` would be filtered out before it could suppress, and
     the suppression mechanism would be silently inert *(caught 2026-09-01 — moving the
     predicate to the candidate set fixed one defect and opened this one)*.
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

   **The target half of the pair is typed**, because not every edge resolves to a work — with
   `decision_record.decision_number` populated for 0 of 23,713 rows, docket-level edges are
   the normal case. A pair is `(citing work, target_kind, cited_docket_id | cited_decision_id)`
   with which one is set recorded, or a public "cited by" count silently mixes two grains.

10. **`extraction_run`** records the pass, one row per
   `(document, method, method_version, reading_channel)`, with a typed outcome **and its
   out-of-class counts** — decision 1 promises "not kept" is an auditable number, and only a
   count makes it one. Nothing else distinguishes *read and found nothing* from *not yet
   read*. Absence is not a measurement.

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

**Query 2 is writable end to end** — the SQL is on disk at [`../citator-query-2.sql`](../citator-query-2.sql) rather than asserted here, across `citation`, `citation_reading`, `citation_resolution`,
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

## Addendum (2026-09-13): a retraction retires the key's readings too

**Status: Accepted 2026-09-13 by the operator**, after four schema-critic passes (the last
clean). Narrows decision 2's "a retraction supersedes the `citation` row and nothing else".

A re-load that retracts a key retired its `citation` and left every child row live. The first
retracting load (v2026.09.15) left **903 live readings** that no pass can replace, because no
finder emits those keys again. Measured 2026-09-13 on a restore taken after the OCR load: all
text-layer, finder 2026-09-01, none decided by a person; 768 citations retracted to a successor
and 135 at themselves. The same keys also hold 903 live resolutions and 2,709 live judgements.
None of them projects, since every consumer joins a live `citation`. But a live reading of a
retracted key still trips `load.SharedPage` for any later pass over that page on another channel.
It also stays for ever in the `pre-0026` count ADR 0026 uses for readings a re-load has not yet
reached, because no finder emits the key again.

**Decided by the operator:**

1. **When `load` retracts a key, it retires every live non-`human` reading of that key** in the
   same transaction. The rule is: a live machine reading whose key holds no live `citation`. A
   key a person decided is already held back from retraction (`load._decided`), so no `human`
   reading is touched. Each retired reading carries `superseded_at` (ADR 0026 D5). It points at
   the successor key's live reading on its own channel where exactly one exists, and at itself
   otherwise. The successor is found by following the retraction's stored `superseded_by` to its
   KEY. That row need not still be live, because a later load replaces it on the same key. The
   retraction is the key's `citation` row with the highest `citation_id`, retired at itself or
   pointed at another key.
   **The rule is one held view.** The loader reads it filtered to its document. The migration
   copies it once into a temporary table before writing, so no row reads another's half-done
   update. Its temporary objects carry no foreign keys and are dropped before `COMMIT`: the
   migrating connection is handed to the app, and on 3.46.1 they were tested to survive
   otherwise. After a load or the migration it is empty. Order of writes: the `citation`, then
   the reading (pointer and date in one statement), then the retirement row.
2. **Every retirement writes a retirement row**, append-only: the reading, the retracted
   `citation` row, the reason from a vocabulary (`retracted-key`), the method and version that
   retired it, and the date. **It is a record of an action, like `review_action`, not an ADR 0007
   assertion**: it claims nothing about the document, so it carries no confidence and no source.
   The reading's own columns are not edited beyond the pointer and the date. Triggers refuse a
   row whose reading is not retired, whose date differs from the reading's `superseded_at`, or
   whose citation is not its key's retraction as defined above, and they refuse any update or
   delete. The table and its vocabulary are held. It becomes a child of `citation_reading` and
   `citation`, so a later rebuild of either must carry it.
3. **The 903 are retired by the migration that creates that table**, named by the migration as
   their method, behind the maintenance wall (ADR 0020). They carry one instant, taken once and
   written in the loader's ISO form to the reading and its row alike. That instant is when the
   store retired them, not when v2026.09.15 retracted their keys, which is not recorded. **If a
   person has decided any of those keys** (`load._decided`'s two tests; the key the SQL renders
   for `review_action` is pinned to `keys.render` by a test), the migration creates the view, then
   aborts whole with `RAISE(ROLLBACK)` before any row is written. On 3.46.1 that was tested to undo
   the view too, leaving no table and `user_version` unchanged, even for a caller that commits
   afterwards. The runbook names the keys, because production's SQLite (Debian 13's 3.46.1) cannot
   build a `RAISE` message from a value (that arrived in 3.47.0). Its pre-check runs on production
   before the wall, where the view does not yet exist, so it is a SECOND COPY of the predicate. A
   test runs both copies over a store holding a decided retracted key and asserts both name it.
   Measured 0, and unreachable while the queues join a live `citation`, so a match
   means something upstream is wrong.

**Left live, and deferred** (`../deferred.md`, 2026-09-13): the key's resolutions and judgements.
Neither table has `superseded_at`, so retiring them now would be undated. They reach nothing
while the `citation` join stands.

**Not covered:** a page whose primary text moves to another channel keeps its old channel's
readings. No retraction happens there, so the OCR guard's never-clearing refusal stays in
`../deferred.md` (0 such pages on 2026-09-13).

**Validation queries.** Query 2's answer set is unchanged, because a retired reading was never
projected. Query 3 reads the event ledger, not this table. Extended to readings, "live on date D"
stops answering yes for ever and answers "live until the migration ran" for the 903. For the 135
retired at themselves, when the key was actually retracted stays unknown, because `citation` has
no `superseded_at`. Queries 1, 4 and 5 read no citation table.

## Addendum (2026-09-14): a footnote digit fused onto the document's own docket keys as that docket

**Status: Accepted 2026-09-14 by the operator**, including proposals 6-12, after five schema-critic
passes (the last clean). Narrows decision 1's "normalised target key".

The Board prints a footnote marker straight after a docket number, and the text layer fuses the
two: `STB Finance Docket No. 340071` in a decision filed in FD 34007. Measured 2026-09-14 on a
production restore, applying the rule below to finder 2026-09-13b's output:

- **346 text-layer findings in 331 documents**, none on OCR, read as a six-digit number;
- **no such six-digit number is a held docket**, so each is stored `unresolved`, shown nowhere and
  queued for nobody, although it names the document's own proceeding;
- all 346 read `citation` today, because the six-digit key is not own. Keyed as the own docket,
  the span test makes every one a `caption`;
- **177 of them sit on a page that also prints the five-digit own key** (116 caption, 61 citation);
- **6 further six-digit numbers** strip to a held docket that is *not* own. They stay out of this
  rule (`../deferred.md`).

**Decided by the operator** (2026-09-13 and 2026-09-14):

1. **The rule.** A bare six-digit key that is not own, and whose last digit stripped is the
   document's own docket, is keyed as that own docket. `cited_raw` stays as printed.
2. **The finding carries its key.** `find` applies the rule and writes the key on the finding.
   Every reader that rebuilt a key from the printed number reads that key instead: `load`, the span
   check, and the check-sheet tools.
3. **The finder never reads the registry** (ADR 0017 D2 stands). `load`, which holds the registry,
   refuses a document carrying a re-keyed finding whose six-digit number is a held docket, counted
   apart from a fault. None is today, and 104 held dockets carry a six-digit sequence. **This
   refusal does not clear on a later walk**: the finder cannot see the registry, so it re-emits the
   same finding. A document not yet loaded has its citations withheld until the code changes; one
   already loaded keeps its earlier rows live, since a refusal writes nothing. Either way `load`
   counts and names every such document in its totals, on every run, and that count is the signal.
4. **What stays open is stated, and its input recorded.** `own` is record data and waves 2-3 still
   add dockets, so a family that later gains a docket can change what this rule keys, with no
   finder bump. The old key would stay live beside the new one, the exposure the family closure
   already carries (finder 2026-09-12). Each reading the rule shaped records, once per reading,
   `key_rule: own-fused`, the printed six-digit key and **the own set `load` checked it against**.
   Two queries then find the drift:
   - comparing that recorded set with the record's current family finds any key the rule made that
     it would now make differently;
   - the other direction needs no record: a six-digit key with a live `citation` and a live
     `unresolved` resolution, whose last digit stripped is in the document's current own set, is
     one the rule would now re-key. The live `citation` matters: a retracted key keeps its
     resolutions live (the 2026-09-13 addendum defers them), so without it the 346 keys this
     rule already re-keyed would all read as drift.

   A six-digit number that later becomes a held docket outside the family is caught by neither
   query; `load`'s count under item 3 names the document on its next walk.
5. **`KEY_VERSION` does not move.** `normalise` is unchanged, and a bump would stamp every newly
   seen key as if the rule had shaped it. A re-keyed key's `key_version` names the normaliser
   only; the reading (item 4) is what says the rule shaped it.

**Proposed to hold them, for the operator's acceptance:**

6. **One function holds the rule**, in `keys.py`, taking the printed key and the document's `own`.
   `find` calls it. `find.verify_spans` gains `own` (which `walk` holds) and `load` rebuilds `own`
   from the record (`walk.own_by_document`'s query); both call it, and `load` then applies item 3's
   registry check.
7. **`load` refuses any other departure from the printed number, per finding and, for a `store`
   reading, per span.** Every span's printed number must normalise to the finding's key, or re-key
   to it under the rule for this document's `own`. A span printing another proceeding's number
   inside an own-key finding refuses its document, so a damaged or forged file cannot re-key one
   of the 6 other-proceeding numbers into a measured, unexposed, unreviewed edge. So does a finding
   the rule no longer re-keys at load time, `own` having changed since `find`. A refused document is
   counted apart from a fault and writes nothing. One refused here loads on a later walk at the
   same version; one refused under item 3 does not.
8. **A page printing both forms is one finding**, and the span check accepts both forms by item 7's
   test, so the 177 pages verify.
9. **The served-date window anchors on the key**: `resolve` takes the finding's key, and an
   occurrence of either printed form anchors the window. That changes what the window hands a row,
   so **the rules take a new version** (`resolve.py`'s note), as the fallback did.
10. **Its own finder version, v7.** v6 is live (v2026.09.23), and retraction fires only across
   finder versions (`load.py`), so the rule ships as `FINDER_VERSION` and the rules moving together,
   rank v7, new cards for both channels declared before the load, and a second full re-load. A work
   card measured on an older rule is not read (`methods._work_measurement` filters on the rule), so
   a load before the declaration would publish work-level answers at docket level. `stamp` refuses
   a resolution or projection card measured on an older rule, but it does not version-check the
   `citation` stage's card and it silently skips an older work card, so for those two the order
   is the runbook's to enforce.
11. **The retraction points the old six-digit key at the own key**, decision 2's successor shape:
   `load` gains that second shape beside the sub-docket one, used only where the rule fired. Its
   readings retire with it (the 2026-09-13 addendum). Item 4's record is a key of the reading's
   `source_location`, once per reading and **outside `spans`**, whose triples stay the offsets
   method's own. The shape is declared here: migration 0028's `{page, spans}` is a comment inside a
   `CREATE TABLE` that only a rebuild of every reading could correct.
12. **The tools that rebuild keys or anchor on the printed form read the finding's key**:
   `work_check_sheet.py`, `long_form_check_sheet.py`, `ocr_citation_sample.py`,
   `benchmark_review.py`, `review_queue_panel.py`, `caption_check_sheet.py`, and the scorers
   `benchmark_score.py`, `projection_score.py` and `ocr_citation_dryrun.py`.

**Validation queries.**

- **Query 2:** the 346 were unresolved and unprojected, and become captions, still unprojected.
  Item 7 keeps a forged file from adding an edge. **Not yet measured, and counted by the
  rehearsal:** the 61 own-key citations on shared pages gain occurrences in their date window, so
  their decisions could change; and any resolution that named a document before and names none
  after, which item 10's order should hold at 0.
- **Query 3:** the retraction's pointer to the own key keeps "which key was live on date D"
  answerable, dated by the successor's `asserted_at`; the reading, not `key_version`, says the rule
  shaped a key (items 4 and 5).
- **Queries 1, 4 and 5** read no citation table.
