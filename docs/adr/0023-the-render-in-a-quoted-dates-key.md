# ADR 0023 — The render in a quoted date's key, and the rebuild that reaches what an ALTER cannot

- **Status:** Accepted
- **Date:** 2026-09-02
- **Accepted:** 2026-09-03 (the operator: "ADR 0023 is approved")
- **Scope:** `decision_decided_date` only. The OCR engine's VERSION in that key, the dated
  `HUMAN_VERSION` sitting in four shipped citator keys, the positional `ordinal`, and the
  display's pick rule are **deliberately not here**; see § What this record does not decide.
- **Supersedes no decision of ADR 0021**, which stays Accepted and unedited. None of 0021's
  D1–D9 decides anything about `decision_decided_date`. What D7 below does is *discharge, for
  this table only*, an interim rule 0021 stated in § Consequences and assigned to "ADR 0018's
  to revisit" — this record is that revisit for one of the two tables 0021 named, and is not a
  revision of ADR 0018, which decides nothing about this table either (see § What this record
  does not decide).
- **Reviewed:** two schema-critic passes and one code review, 2026-09-02. The first critic pass
  is why this record exists: it found that migration 0019 as drafted — an `ADD COLUMN` — could
  not reach three of the things it needed to, and that the difference was a table rebuild free
  today and against live rows tomorrow. The second corrected this record's own attributions
  (see decision 6 and § Validation). The code review found that decision 6's key did not hold
  for readings that name no engine, which is the biconditional in decision 2. **Every finding
  taken here was reproduced by execution before it was taken.** One was recorded rather than
  fixed, in `docs/deferred.md`, because it is class-level and not this migration's.

## Context

ADR 0021 D2 put `render_profile` in `document_text`'s natural key, because the render moves
the reading: dots.mocr peaks at 200 DPI where 300 exhausts the card, and crop and mask each
change its output. Two renders of one page through one engine at one version are different
text, so both readings are kept and neither displaces the other.

ADR 0021 § Consequences then named the two tables that argument does not reach, and said so in
terms:

> **Decision 2's argument does not reach `citation_reading` or `decision_decided_date`.** Both
> live-index without a render, so a re-render at a better DPI produces a reading that
> supersedes its predecessor. For `decision_decided_date` that is sharper than a general
> consequence: a **date** is the dispositive artefact in validation query 4, dates are quoted
> and never computed, and the quoted evidence is destroyed one join over from where
> `document_text` preserves it. Widening those keys is ADR 0018's to revisit; until then the
> pipeline's rule is that a re-render does not re-extract without a new method version.

Three things make this the moment rather than later.

**The evidence destroyed is a quotation, not a derivation.** `printed_text` is `NOT NULL`
because `CLAUDE.md` says dates are quoted and never computed. A supersession here does not
replace a worse estimate with a better one; it deletes the string a page printed. That is why
ADR 0021 called it sharper than a general consequence, and it is the whole argument for
treating this table differently from `citation_reading`, whose readings are not quotations in
the same sense.

**The table is empty, and the window is narrower than "cheap".** Measured on production
2026-09-02: `decision_decided_date` holds 0 rows, and so does `citation` — the citator shipped
its schema at migration 0014 and has never run a real load. Verified on SQLite 3.50.4 while
drafting: `ALTER TABLE ADD COLUMN` does accept a `CHECK`, including one referencing another
column of the row, **and it validates the rows already in the table and fails the ALTER if any
violates**. So after one contradicting row the cheap path is not costly, it is refused.

**An `ADD COLUMN` cannot reach three of the four things needed.** The first draft of migration
0019 was an ALTER, and the schema-critic pass found:

1. `ADD COLUMN` under `NOT NULL` **requires** a non-NULL default, so the render column would
   have carried `DEFAULT 'native'`. An `ocr` writer that omitted it would take that silently —
   a false render stamped on a quoted date. `document_text` gives the same column no default
   and fails an omitting writer loudly. SQLite has no `ALTER COLUMN`, so removing the default
   later is the same rebuild, against rows by then.
2. `method` and `method_version` are key columns rendered into `review_action.target_key` and
   `correction.target_key`, and carried no `/`-CHECK, so a value holding a `/` renders a key
   that cannot be parsed back into its columns — the defect migration 0018 pins for
   `document_text`. A constraint cannot be added to a column that already exists. The
   *example* does not carry across from 0018, and an earlier draft imported it unadjusted:
   there, `method` is the engine, so a HuggingFace id (`rednote-hilab/dots.ocr`) is the live
   case. Here `method` is the date extractor's, and its own exposure is a `/` in an
   extractor's name — `rmi/date-layout` — which nothing has ruled out. The engine id lands in
   `reading_method`, which decision 6 moves into the key, so the HuggingFace case is live here
   after all. `ADD COLUMN` could have reached none of the three.
3. There was no `superseded_at`. ADR 0021 D1 added one to `document_text` so that "what a
   reader saw on date D" is replayable. Widening the live set without it makes that read
   strictly *harder*, because rows now sit beside one another and there is often no successor
   whose `asserted_at` bounds the predecessor.

## Decision

1. **The render is in the quoted date's live key.** `decision_decided_date_live` becomes
   `(document_sha256, date_kind, ordinal, reading_channel, method, method_version,
   render_profile, COALESCE(reading_method, '')) WHERE superseded_by IS NULL` — that last term,
   and its coalesce, are decision 6's. A re-read of one page at a better DPI sits **beside**
   the earlier quotation instead of deleting it, and the projection is handed two quotations to
   choose between rather than one that quietly changed.

2. **It ships as a table rebuild, not an `ADD COLUMN`.** The three gaps above are closed in the
   same migration, because each of them is unreachable afterwards: `render_profile` has **no
   default**, `method`/`method_version`/`render_profile` all carry
   `CHECK (<col> <> '' AND <col> NOT GLOB '*/*')`, and `superseded_at` exists with
   `CHECK ((superseded_by IS NULL) = (superseded_at IS NULL))`. One thing is added that the
   first draft did not have and that is not about the render: **the engine and the channel are
   a biconditional**, `CHECK ((reading_channel = 'ocr') = (reading_method IS NOT NULL))`.
   Forward, it is ADR 0007, a `CLAUDE.md` non-negotiable — the pairing constraint alone let a
   quotation be stored as "read by OCR" with the engine unrecorded. Backward, it is what makes
   decision 6's key hold: a `text-layer` row naming an engine and one naming none differ in a
   key column, so both would be live and the key would enforce nothing for them. Confirmed by
   execution, not argued (code review, 2026-09-02).

   The backfill takes the same care. It copies `render_profile` as
   `CASE WHEN reading_channel = 'text-layer' THEN 'native' END` rather than a bare literal: a
   literal would have stamped the text layer's render on an `ocr` row that never had one —
   precisely the silent falsehood this decision rejects `DEFAULT 'native'` for, committed by
   the copy instead. Only a text-layer row's render is recoverable; anything else is NULL and
   refused.

   **A nullable `page_no` is added in the same window** (operator, 2026-09-02), outside the key
   and typed where `source_location` held it in unconstrained JSON. ADR 0021 D4 makes this safe:
   `document_sha256` fixes the byte stream, so page order is a property of the bytes and a page
   number is channel-independent. Three things want it — joining a reading to the page's text in
   `document_text`, letting a work-level resolution record *which* row it matched (ADR 0007),
   and 0014's owed fix for the positional `ordinal`, which must be assigned "from something
   stable on the page". It is not `NOT NULL` because no writer exists to be held to it and a
   text-layer extractor quoting from a document-level parse would be refused for nothing; the
   obligation to set it falls on the first writer.

   The rebuild follows SQLite's documented procedure, which `db.migrate` already implements —
   every script runs under `PRAGMA foreign_keys = OFF` with `PRAGMA foreign_key_check` after —
   and is the same procedure migration 0014 used on `correction` at 0 rows for the same reason.

3. **A stated decision is enforced or it is a comment.** ADR 0021 D3 ties the text layer to the
   `native` render; migration 0018 enforces that for `document_text` and the first draft of
   0019 only mentioned it. The rebuilt table carries
   `CHECK (reading_channel <> 'text-layer' OR render_profile = 'native')`.

4. **A human decided date is pinned to its own render, and no model pass may supersede one.**
   The three encodings the shipped writer already sets together (`citator/review.py`: method
   `human`, channel `human`, state `human`) are bound to each other, a human row's
   `render_profile` is `human` — a person read a page, not a DPI — and the table gains the
   trigger `citation` carries at migration 0014 and `document_text` at 0018. Without the render
   pin, a human quotation would record that it was read off the publisher's text layer at
   native render, which is a claim nobody made.

   **And the live human set is single-valued, by index rather than by pinning the key**
   (operator, 2026-09-02): `UNIQUE (document_sha256, date_kind, ordinal) WHERE superseded_by IS
   NULL AND reading_channel = 'human'`. The live key cannot do this work, because
   `citator.methods.HUMAN_VERSION` is a dated string sitting in `method_version` — so the day it
   changes, a second human correction of one date is a second live row and the display has two
   human answers. `document_text` escapes it by pinning human rows to `unversioned`; this table
   cannot, because the same dated convention sits in four shipped citator keys and pinning one
   makes two conventions where there is one. The index is the analogue of
   `document_text_one_human` and, like it, is what lets a display rule say "the human row" and
   mean exactly one thing.

5. **The rendered review key is eight segments from migration 0019 forward.**

   ```text
   <document_sha256>/<date_kind>/<ordinal>/<reading_channel>/<method>/<method_version>/<render_profile>/<reading_method>
   ```

   The last segment is **empty** for a text-layer or human row, which has no engine — the same
   empty string the live index coalesces to, so the rendered key and the index agree about what
   "no engine" is. A trailing empty segment still parses by splitting on `/`, because none of
   the other seven may contain one.

   Migration 0014 documents the six-segment form and is deployed, so it cannot be edited;
   migration 0019's header is the append-only place a reader of the chain reaches, and
   `docs/citator-schema.md` § B and `docs/schema-draft.md` (which states the six-column key at
   line 705, and which `0014:3` records as tracking the migration) are where it is otherwise
   documented and where the correction is owed. Both forms satisfy the
   `GLOB '*/*/*/*'` shape checks in `correction` and `review_action`, which only count to
   four, and `review_action_live` is `UNIQUE (queue, target_table, target_key)` — so a
   six-segment and an eight-segment key naming **one row** do not collide, and would be two live
   review decisions on one item with nothing saying so. **The first writer of either form must
   set `review_action.target_key_version` to distinguish them.** Nothing renders this key today
   — no renderer for this table exists in `src/` — so the obligation lands with the first one,
   and `citator/keys.py` is where it belongs.

6. **The engine's NAME is in the key; its VERSION is not.** Migration 0014 kept both as payload
   on one argument: a re-OCR at a better version must *match and supersede* rather than
   doubling the live rows over the 1,480 of 9,663 image-only files it measured. That argument
   is about a **version bump** — one reader improving, so the two readings are ordered and the
   newer wins — and it is preserved exactly, because `reading_method_version` stays outside the
   key.

   It does not reach **two different engines**, which have no such ordering and which ADR 0021
   D8 runs deliberately as the agreement pair. With both payload, dots.mocr and PP-OCRv6
   reading one page at one render collided, and whichever was written second silently destroyed
   the other's `printed_text`. The case that forced this (the operator, 2026-09-02): *an engine
   can read a page better overall and get the date wrong.* No page-level score orders those two
   readings — every CER this project measures is per page or per tier, and a decided date is one
   line of about thirty characters — so a disagreement between engines is **a finding for a
   person, not a tie to break**, and it is only a finding if both rows survive. See § The pick
   rule, which this decision is inseparable from.

   Two mechanical consequences, both verified rather than reasoned about. `reading_method` is a
   key column now, so it carries the `/`-CHECK the others carry — and here the HuggingFace case
   is the *live* one, since `rednote-hilab/dots.ocr` is how these engines are published; the
   short name is what may be stored, which is the convention `document_text` already takes. And
   the live index coalesces it: **SQLite holds NULLs distinct in a unique index**, so the bare
   column would have left every text-layer and human row — which have no engine — unconstrained
   by the key it belongs to, silently. Measured on 3.50.4: the bare column accepts a second NULL
   row, `COALESCE(reading_method, '')` refuses it, and two named engines stay live under both.

7. **ADR 0021's interim pipeline rule is discharged for this table and still governs the
   other.** "A re-render does not re-extract without a new method version" existed because a
   re-extraction would have destroyed a quotation. For `decision_decided_date` it may now
   re-extract freely, because the render is in the key. For `citation_reading` the rule stands
   unchanged, and so does ADR 0021 § Consequences as written about it.

## What this record does not decide

- **The engine's VERSION in the key.** Decision 6 takes the engine's *name* and deliberately
  leaves its version out, so a re-OCR at dots.mocr 1.6 still matches and supersedes the 1.5
  reading — destroying that reading's `printed_text` if the two differ. The argument for
  accepting that is migration 0014's and it is preserved on purpose: one reader improving
  produces *ordered* readings, and the newer is the better evidence in a way that two different
  engines' readings never are. The argument against is decision 1's, one axis over: a version
  bump also changes text, and what is destroyed is still a quotation. Two things make it
  tolerable where the engine axis was not — a version bump is deliberate and dated, so the
  supersession is traceable through `ocr_run`, and nothing forces two versions to be run
  against one page the way ADR 0021 D8 forces two engines. **Free to revisit until the
  citator's first load**, which is the operator's to start.
- **`citation_reading`**, ADR 0021's other named table, which has the same key shape and the
  same exposure. That table is ADR 0018 D3's, D3 is accepted, and revisiting it is a decision
  this record does not take. ADR 0021's interim rule still governs it — see decision 7.
- **Whether the human reading wins the display.** Decision 4's index now makes the live human
  set *singular*; nothing yet makes it *preferred*, because there is no `reading_role` here and
  no analogue of ADR 0021 D9's primary index. § The pick rule recommends that a human row win
  outright, and that recommendation is not yet a decision.
- **`route_class`.** ADR 0021 D4 requires every OCR reading to know the tier it was routed as,
  because every benchmark CER is per tier and `class_measurement` is keyed on class. An
  OCR-channel row here carries no tier. It is now *recoverable* — decision 2's `page_no` gives
  the join into `document_text`, which does carry one — where before it was not, but that is a
  join and not a record. The operator declined the column in the same window that took
  `page_no` (2026-09-02), on the ground that nothing scores this stage and the gate is shut.
- **`citator.methods.HUMAN_VERSION` in the key.** It is a dated string (`2026-09-01`) sitting in
  `method_version` in four shipped citator keys, so the day it changes a human correction
  doubles the live rows. `document_text` escapes it by pinning human rows to `unversioned`.
  Pinning this one table alone would make two conventions where there is now one; fixing all
  four is its own record.
- **The positional `ordinal`.** Migration 0014 already owes a fix — the ordinal is
  parser-assigned from reading order, so a layout change mints a row that supersedes nothing.
  The render in the key **sharpens** that debt rather than paying it: two renders that disagree
  about how many `Decided:`-shaped lines a degraded page carries assign the same printed line
  different ordinals, and the rows are then keyed as two *date instances* rather than two
  readings of one. Inert while none of the sixty benchmark decisions prints two lines, and now
  owed sooner than it was.
- **The display's pick rule**, which decision 1 makes underdetermined. See below.

### The pick rule, named rather than hidden

`docs/citator-schema.md` § B states the projection rule as: *"prefer the text-layer reading,
else the OCR reading whose own confidence is higher"*, on the measured ground that none of the
sixty decisions prints two `Decided:` lines, so no tie-break was needed. Decision 1 creates a
tie the rule cannot break, because **that `confidence` is inert by this project's own rule** —
an unmeasured class still has to put some number in the column, and `citator-schema.md` says in
terms that whatever it is must never be read.

What the replacement must satisfy, so the first consumer does not invent one:

- It **may not read `confidence`** on an unmeasured row.
- **It must not rank readers, because the available measurement is the wrong grain.** The first
  draft of this section proposed inheriting ADR 0021 D9's single live `primary` per page:
  prefer the decided date whose render and channel match it, so the date shown was read off the
  text shown. The operator's question killed it (2026-09-02): *who wins between an engine that
  reads the page better overall but gets the date wrong, and one that reads the page worse and
  gets the date right?* The primary is chosen on **page-level** text quality, and every CER
  this project has measured is per page or per tier. A date is **one line of about thirty
  characters**. A page-level winner is not a line-level winner, so that rule would select the
  wrong date in exactly the case that matters, confidently and invisibly.

- **So compare the VALUES, not the readers.** For one `(document_sha256, date_kind, ordinal)`,
  over live rows: a `human` row wins outright and is now single-valued by index (decision 4); a
  `text-layer` row wins over any OCR row, because it is the publisher's own text rather than a
  reading of it; and among the remaining OCR rows, **if they agree on `printed_text` there is
  no tie to break** — the quotation is the same and which engine or render produced it does not
  matter to a reader. If they disagree, **nothing picks**. This needs no page, no primary join
  and no ranking of engines, and it is the rule this record recommends.

- **A disagreement is a finding, not a tie.** Where two live readings print different dates,
  that is precisely the signal ADR 0021 D8 stores `agreement_distance` to capture, one grain
  down: it goes to a person, and until a person answers, **no decided date is published for
  that document**. Withholding is cheap — 55 of 60 decisions print exactly one `Decided:` line
  and the disagreement set will be a fraction of that — and it is the only answer consistent
  with dates being quoted and never computed. It is also detectable only if both rows survive,
  which is decision 1's whole point, and is the argument the engine axis turns on (above).

This remains **a recommendation and not a decision**: it is a display rule, it needs the
operator, and no consumer exists to need it yet.

**Nothing may publish a single decided date until this is decided.** Nothing can today:
`web/cite.py` short-circuits every `decided` phrase to the sheet, and ADR 0018 D4's
work-level resolution says `decided <date>` matches nothing until a decided-date assertion
exists.

## Consequences

**What becomes easy.**

- A better render is a free improvement. Re-reading the degraded tier at 200 DPI (the operator's
  open decision in `TODO.md` § Next) adds quotations without deleting any, so the earlier
  reading stays checkable against the scan.
- "What was live on date D" becomes replayable for this table, which it was not: `superseded_at`
  did not exist before this record.
- An omitting or malformed writer fails at the store rather than at the published page. Three
  columns that render into a review key can no longer carry a `/`.

**What becomes hard, or costs.**

- **The live set is no longer single-valued**, on two axes rather than one — the render
  (decision 1) and the engine's name (decision 6) — and the documented pick rule cannot break
  either tie. That is the cost this record accepts, and § The pick rule is where it is paid.
  The bound is small: a document's live rows are one per (channel, extractor, extractor
  version, render, engine) actually run, and the pipeline runs two engines at one render.
- **A disagreement between two readings becomes a queue item that does not exist yet.** Under
  the old key it was not a queue item, because it was not detectable — the second write simply
  won. Making it visible is the point, and it is also work: § The pick rule says nothing may
  publish a decided date while two live readings disagree, so until a review path exists the
  effect of a disagreement is that the date is withheld. That is the correct failure and it is
  still a failure.
- **`citator.load._retire` is not reusable against this table.** As shipped it writes only
  `superseded_by`, and the new biconditional refuses that. Neither is the generic
  `_supersede_if_changed` that calls it. Nothing writes here today; the first writer inherits
  the obligation, stated in migration 0019's footer in the same terms migration 0018 states it
  for `document_text`.
- **A dev store holding retired rows will refuse the migration**, because `superseded_at` has no
  value to recover for a row already retired and inventing one would be a computed date in the
  one table whose whole rule is that nothing is computed. Production holds 0 rows; `data/` is
  disposable.
- **Migrations 0018 and 0019 land as one irreversible step.** `web/app.py` refuses to serve a
  store whose `user_version` differs from the build's in *either* direction, so rollback is a
  Litestream restore. ADR 0022 D6's raised retention window covers this only if 0019 ships
  inside it.

## Validation

Checked against `docs/validation-queries.md`.

- **Q1** (a segment's history through successors) does not join this table; the path is
  `place_mention → docket → party_relationship`. Unchanged.
- **Q2** (negative treatment) does not join this table. The shipped statement,
  `docs/citator-query-2.sql`, runs `citation_resolution` ranked through `assertion_method` →
  `citation` on the four natural-key columns → `citing_work` → `citation_treatment` →
  `treatment_vocab` → `citation_reading` → `span`; it does not join `citation_key` at all, and
  an earlier draft of this section said it did. ADR 0018 D4's *extension* — resolving
  `decided <date>` to a work — would join this table, and after decision 1 that join can return
  more than one live row per document with different `decided_date` values. **It would join on
  `document_sha256` alone, because there is no page column** (see § What this record does not
  decide), and `citation_resolution` has no column naming *which* decided-date row it matched,
  so the resolution it produced would carry no provenance for its own operand — an ADR 0007
  gap this record creates and does not close. Unreachable today by construction (`web/cite.py`
  resolves every `decided` phrase to the sheet and says why). **This is the query this record
  puts a condition on**, and it is named rather than discovered later.
- **Q3** (point-in-time docket state) is answered by the ledger, and this table is deliberately
  not a ledger event (migration 0014's second fence: a decided date is a second clock, and a
  replay would show a decision existing before it was served). Where it touches Q3 at all —
  which quotation was live on date D — this record **helps and does not settle it**. The
  predicate is `asserted_at <= D AND (superseded_at IS NULL OR superseded_at > D)`, and
  `superseded_at` now exists where it did not. Two things it does not do, stated because an
  earlier draft of this section claimed more: the cross-key idiom the writer obligations
  mandate always *has* a successor — the point is that the successor's `asserted_at` does not
  **bound** the predecessor — and nothing constrains `superseded_at` itself (no CHECK that it
  is at or after `asserted_at`, no format check). The column makes the read possible, not
  reliable.
- **Q4** (trail-use lifecycle) is **unaffected**, and this record does not earn its
  endorsement. `date_kind_vocab` holds `decided` and `effective`; a NITU issuance, extension or
  expiration date is neither, and no instrument table ships — so this table is not on Q4's join
  path. ADR 0021 § Validation says the same ("Q4 is unaffected today"), and
  `citator-schema.md` § B warns in terms that this document "should not borrow Q4's
  endorsement, as its first draft did". An earlier draft of this section did it again. What is
  true and smaller: ADR 0021 § Consequences called the destroyed quotation "a Q4 finding"
  because a date is Q4's dispositive artefact *the day one is quoted from a page*, and decision
  1 removes that latent exposure before it becomes live.
- **Q5** (the service-list alert) reads subscription → snapshot event → `filing_party_link`.
  No join, and alerts never read derived text. Unchanged.

## Cost of reversing

**Today: free, and this is the entire reason the record is dated now.** `decision_decided_date`
holds 0 rows in production and in every store this repository builds, so the rebuild copies
nothing and reversing it is another rebuild that also copies nothing.

**After the citator's first load: a table rebuild against live rows.** Reversing decision 1
alone — narrowing the key back — would additionally have to *choose which quotation to delete*,
which is the destruction the record exists to prevent, so it is not a reversal so much as a new
decision about evidence.

**After the OCR backfill: dearer again, though smaller than an earlier draft of this record
claimed.** This table is bounded by decision *documents* — 23,716 `decision_record` rows, one
row per document per (channel, method, render) — not by the 247,923 image-only pages. It is not
"the largest thing the citator owns"; `0014:320` gives `citation_reading` that title, and it is
keyed per document, page and target. The urgency here comes from the rebuild being free
*today*, not from the table being large later.

The parts that are *not* reversible by a later ALTER at any point, and are therefore the reason
this is a rebuild and not a column: a `NOT NULL` column's default cannot be removed, and a
`CHECK` cannot be added to an existing column. Both are the same rebuild, later and dearer.

---

*Accepted 2026-09-03, after the check against `../validation-queries.md` recorded in
§ Validation. Three consequences were accepted deliberately with it: the live set is no longer
single-valued on two axes, so a document can carry two decided dates that disagree; the pick
rule that resolves them is recommended here and not decided, and until it is, nothing may
publish a single decided date; and the engine's VERSION stays out of the key, so a re-OCR at a
better version of one engine still replaces the quotation it read before.*
