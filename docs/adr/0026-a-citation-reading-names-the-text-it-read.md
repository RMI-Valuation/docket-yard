# ADR 0026 — A citation reading names the text it read

- **Status:** Proposed
- **Date:** 2026-09-12
- **Scope:** `citation_reading` only. The GRAIN of a finding, whether `citation_resolution`
  becomes per-occurrence, and whether the engine's name and render profile belong in this
  table's key are **deliberately not here**; see § What this record does not decide, and read
  § Consequences § Foreclosed before accepting, because one of those three gets dearer.
- **Supersedes no decision.** ADR 0018 D3 stays Accepted and unedited — D3 below affirms it.
  What this record does is take two decisions earlier records left open and assigned:
  migration 0019's header ("it does not widen `citation_reading`, whose live key has the same
  shape and **the same exposure** ... revisiting it is a decision this migration does not
  take") and ADR 0021 § Validation ("no shipped consumer has a `text_id` column, and adding
  one to `place_mention` or `citation_reading` is theirs to decide"). This is that decision for
  `citation_reading`, and it is not one for `place_mention`, which is paper.

## Context

`citation_reading` asserts what one reading of a page printed: `cited_raw`, `quoted_passage`,
and a `source_location` of `{"page": page}`. **It cannot name the reading it read.**
`walk._PAGES` selects `page_no, text, reading_channel` and drops `document_text.text_id` on
the floor, and the table has no column to put it in.

So the text under a live reading can change without the reading being superseded, and nothing
in the store records that it happened. Three sequences do it, all ordinary:

1. **A human page correction.** `0018_document_text.sql:483` makes `document_text` a
   correction target today. A live `human` row removes the `primary` from
   `document_text_display` **without superseding it** (that migration's own note, lines
   556-558), and `walk._PAGES:43-49` excludes a primary a live human row shadows while
   `walk.documents:108-114` never reads the human row itself — so the page's text changes and
   **no model pass will ever revisit it.** This one cannot be repaired by re-loading, and it is
   the sequence D2 is built to see.
2. **A re-read at the same natural key.** `text/load.py:52`: within the natural key, a changed
   `text_sha256` supersedes. The reading row is untouched until someone re-walks.
3. **A re-read at a new `method_version` or `render_profile`**, which displaces the page's live
   primary through `document_text_one_primary`.

`quoted_passage` is self-contained provenance — it carries its evidence, so a reader can check
the claim from the row. `source_location` is a pointer, and a pointer into a text the row
cannot name is provenance that looks checkable and is not. ADR 0007 requires "the location
within it"; **"within WHAT" is the missing column.** The store's own idiom already answers this
one module over: `filing_party_span` (`0006_parties.sql:73-88`) ships `span_start` and
`span_end` beside the `raw_text` they index. The citator cannot store a page of prose 73,838
times, so it must store the pointer instead.

This surfaced from a smaller question — whether `find` should report each match's character
offset — which measured at 12 of 506 rows of recoverable document loss, 0.016% of live
readings (`../citation-grain.md` § The one number nobody had). **That is not why this is being
done.** It is being done because a reading that cannot name its text cannot be checked, and the
record's whole claim is that its assertions can be.

## Decision

**D1. `citation_reading` gains `text_id INTEGER REFERENCES document_text (text_id)`** — a real
column, **nullable**, and **outside the live key** — together with **`text_ref`**, which says
what the null means.

- **A column, not a key inside `source_location`'s JSON**, because it is a relationship.
  SQLite enforces the foreign key, it can be indexed and joined, and `document_text.text` is
  immutable per `text_id` (the trigger `document_text_text_is_immutable`,
  `0020_display_mask.sql:48`), so the pointer resolves for ever to the exact bytes read. A
  digest would prove which bytes without finding them; an unenforced JSON pointer would prove
  neither.
- **Outside the key**, for the reason `0014` removed `source_location` from a key and `0019`
  kept `page_no` out of `decision_decided_date`'s: a re-read that renders or paginates
  differently would mint a row superseding nothing.
- **`text_ref TEXT NOT NULL REFERENCES text_ref_vocab (text_ref)`**, members
  `('store', 'benchmark', 'human', 'pre-0026')`, with
  `CHECK ((text_ref = 'store') = (text_id IS NOT NULL))`. A bare nullable pointer would mean
  three things at once — a benchmark reading with no store row to point at (`find.pages()`
  over `===== page N =====` markers), a row this migration's pass never reached, and a human
  row that points at no machine reading — and D6 holds `FINDER_VERSION`, so **no other column
  could tell the first two apart.** That would leave D2 with an unknowable denominator. This is
  `route_class_vocab`'s idiom (`0018:82-96`: "'unrouted' is a MEMBER rather than a null,
  because a page read without a route says so; it does not say nothing") and it answers
  `0014:251-252`'s objection to a null meaning three things. The rebuild backfills `'pre-0026'`
  for free.

**D2. A reading standing on text the record no longer shows is detectable, and that is what
this buys.** The predicate is against the **display view**, not against the pointer's
`superseded_by`:

    SELECT * FROM citation_reading r
     WHERE r.superseded_by IS NULL AND r.text_ref = 'store'
       AND NOT EXISTS (SELECT 1 FROM document_text_display v WHERE v.text_id = r.text_id)

`superseded_by IS NOT NULL` would have been wrong, and wrong on the worst case: sequence 1
removes a primary from the display view **without superseding it**, so a `superseded_by` test
returns nothing for the one sequence that can never be repaired by re-loading. One term over
the view catches supersession and shadowing together, and `document_text_one_human`
(`0018:390`) is the index that makes it cheap.

It is a **re-walk trigger, not an error**: the passage may still be right, but it is
unverified. It goes where ADR 0019's telemetry can see it, because the fleet's lesson was that
the failure is a derivation dying **unnoticed**, not the death.

**D3. The live key does not move.** ADR 0018 D3 stands: the reading method and its version stay
payload, and a better engine's reading matches and supersedes rather than doubling the live
readings.

The ground is the DDL, not a reading of today's callers. `citation_reading_live`
(`0014:689-691`) is UNIQUE over the four key columns plus `reading_channel` where live, and
`document_text_one_primary` (`0018:388-389`) is UNIQUE over `(document_sha256, page_no)` where
live and primary — so `walk._PAGES` yields **at most one row per page whatever engine wrote
it**, and a cross-engine collision is closed upstream at `document_text`. That argument
survives the next engine; a list of today's callers would not. (It is also true of the callers:
only `load.py:287` and `review.py:481` insert, `restamp` touches `citation_resolution` alone,
and no `second` reading reaches a findings document.)

**D4. `source_location` becomes `{page, spans}`, and `find` reports each match's character
span** in the text it was handed. Each span is `[start, end, raw]`.

- The spans are **provenance and nothing else**. They recover 12 of 506 rows of document loss;
  `resolve._anchored` works in `quoted_passage` coordinates and is not changed to use them.
- **The raw travels with the span**, per occurrence. `cited_raw` on the row is the FIRST
  occurrence's printed form only (`find.py:193-199` sets it once; `load.py:200` takes it with
  `setdefault`), while `keys.DOCKET` matches `FD-36500` and `FD 36500` alike and
  `keys.normalise:47-52` records that `AB 1296X` and `AB 1296 (X)` are one key. So two
  occurrences of one key printing differently is ordinary — and without a per-span raw, the
  verification predicate below would return **false on a correct span** for every occurrence
  but the first, which is the "provenance that cannot be checked from the row" this record
  exists to refuse.
- A span verifies as `" ".join(text[start:end].split()) == raw`, **never** as plain equality:
  `_target_end` crosses a newline for a wrapped sub-docket while the printed form is
  whitespace-collapsed (`find.py:106`), a population `find.py:53-56` measures at 628
  citations.
- `spans` is the occurrence list for this key on this page and is **not parallel to
  `quoted_passage`'s `" | "` elements.** `find` de-duplicates identical lines (`find.py:206`),
  and the separator is an unescaped in-band string in `find`, `load.py:208` and `resolve.py:193`
  alike, so the element counts need not agree and **nothing may zip them.**
- The spans index `document_text.text`, not `document_text_display.text`. The mask is
  length-changing (`0020_display_mask.sql:34`), so a span is wrong against what a reader is
  shown by the sum of the mask deltas above it on the page. Anything highlighting a citation on
  the text page must re-derive against the displayed string.
- **A human row carries no `spans` key at all** — not an empty list, which would assert that a
  reviewer found no occurrences. `review._human_reading` builds its own
  `{"page": …, "reviewer_id": …}` (`review.py:495`) and passes no `text_id`, so this is an
  invariant of the code and not an obligation on a writer: a human row **cannot** inherit a
  machine's offsets. (It does copy `cited_raw` and `quoted_passage` off the machine reading,
  `review.py:90, 492-493`. That copy predates this record and is not changed here; whether it
  deserves the same objection is noted in `../deferred.md`.)

**D5. `citation_reading` gains `superseded_at` — with NO biconditional CHECK, and a
forward-only trigger instead.**

`document_text` pairs the two columns with `CHECK ((superseded_by IS NULL) = (superseded_at IS
NULL))` (`0018:357`). **That CHECK cannot be applied to this table.** It holds 73,838 live rows
plus their retired predecessors, every one of which has `superseded_by` non-null and no
`superseded_at` to have filled, so the rebuild's `INSERT … SELECT` would violate the
biconditional on every retired row and the migration would roll back whole. And the only
backfill available is forbidden by accepted precedent — `0019:212-217`: "`superseded_at` has no
value to recover for a row already retired, and **inventing one is a computed date in the one
table whose whole rule is that nothing is computed**."

So: the column is nullable and unconstrained at rest, and a `BEFORE UPDATE OF superseded_by`
trigger requires `NEW.superseded_at IS NOT NULL`. Legacy retirements stay honestly undated;
nothing retired after this migration can be. That is the idiom this store already uses for a
constraint SQLite cannot express (`0009`, `0014:639`, `0018:410`, `0019:285`).

**This is validation query 3's fix**, and not only migration 0019's third defect: "which
reading was live on 18 August" is answerable today only from a successor's `asserted_at`, and a
row retired at itself has no successor and no recovery.

**D6. The shipped writers change in the same commit.** `load.py:285` calls
`supersede.retire(con, "citation_reading", "reading_id", old_reading[0])` with no `at`, and
`supersede.retire` then writes `superseded_by` alone (`supersede.py:20-23`, whose docstring
records that "the citator's families carry no `superseded_at` … and pass nothing"). Under D5's
trigger that aborts on **the first supersession of the corpus pass** — which is the first row
it touches. `0019:300-304` named the same obligation for its own table and this record names it
for this one: `load.py`'s retire call and `supersede.if_changed`'s retire path must pass the
timestamp.

**D7. `find` gains its own provenance for the spans, and `FINDER_VERSION` still does not
move.** `span_method` and `span_method_version`, with the paired-null CHECK the store uses for
`route_method`/`route_method_version` (`0018:288-289`, "a route class is an assertion too, so
it names who said so") and `agreement_method`/`agreement_method_version` (`0018:307-308`).

A character offset **is** a derived assertion — a claim about where in a text a string sits —
and CLAUDE.md's non-negotiable is that every derived assertion carries its own method version.
Storing spans under a `method_version` that names a finder which never emitted them would be
false provenance of exactly the kind ADR 0017 made four times. With their own two columns the
provenance is honest, `FINDER_VERSION` holds (no answer changes, so no new `class_measurement`
card is owed — `load.py:146-151` would otherwise refuse the load), and the test D8 promises
still pins it.

**D8. It ships as a REBUILD, and the corpus pass that fills it is a RE-LOAD, priced
separately.**

- **Why a rebuild and not an ALTER**: D5's trigger and D1's `CHECK` belong in the table
  definition, `superseded_at`'s absence is `0019`'s third defect of an ALTER, and one pass must
  write `text_id` and `spans` together — adding the pointer after the spans would be a
  **second** rewrite of the largest citator table (`0014:320`), the every-row shape the five
  validation queries exist to catch. Correcting `0014:668`'s stale `-- JSON: {page, block_id,
  bbox}` comment, which SQLite keeps verbatim in `sqlite_master`, is a **minor** benefit and
  not the argument: `citation_reading` is in `dump.HELD_TABLES` (`dump.py:120`) and
  `dump.scrub` drops held tables outright, so that comment never reaches the CC0 snapshot.
- **Nothing references `citation_reading` but itself** (`0014:680`, `superseded_by`), verified
  across the repo — so the rebuild has no children to cascade, unlike `decision_decided_date`'s.
- **The `foreign_key_check` cost is fine.** `db.migrate` already runs it with no table
  argument after every script, walking the whole store — measured at ~280 s on a cold copy at
  976,058 text pages (`infra/deploy/README.md:158`), where `document_text`'s own outbound keys
  already dominate. `text_id` is an explicit `INTEGER PRIMARY KEY`, so each non-null value is
  an O(log n) rowid lookup: the increment is seconds against an existing five minutes.
- **The pass is a re-load through `load.py`, not an UPDATE.** `load.py:278-314` retires the
  live reading unconditionally and inserts a replacement — there is no `if_changed` on this
  family — so the pass appends ~73,838 rows and retires ~73,838. An `UPDATE` would be an edit
  to a stored assertion, which this project forbids.
- **Consequence to state rather than discover:** every live reading's `asserted_at` becomes the
  migration date. History survives on the predecessors, so query 3 still replays, but "what the
  record knew by then" for the reading family will say it learned every citation on migration
  day.
- **A maintenance wall is required** (ADR 0020 § Deploying a migrating release). Migration 0025
  needed none *because* `citation_resolution` held zero rows (`infra/deploy/README.md:297-300`);
  the inverse holds here.
- The rebuild moves no published shape and does **not** bump `JSON_SHAPE`, as `0025:49-50`
  states for `citation_resolution`.

## Checked against `../validation-queries.md`

| Query | Verdict |
| --- | --- |
| **Q1** segment history through successors | **Expressible, untouched.** `place_segment → proceeding_place → docket → party_relationship`; no citation table appears. |
| **Q2** what narrowed or overruled a decision | **Expressible, answer set unchanged.** `citator-query-2.sql:199-203` joins on the four key columns plus channel; no key moves, so the join is byte-for-byte the same. **Owed at the migration:** the select list at `:179` returns `rg.source_location` with no `rg.text_id`, so until it and `project.py`'s copy of it are edited, Q2 returns spans with no identity for the text they index — the same defect one level down. Q2 is the ONLY query that reads these tables. |
| **Q3** point-in-time docket state | **Repaired forward by D5.** Today `citation_reading` has `superseded_by` and no `superseded_at`, so a reading's live window is recoverable only from a successor's `asserted_at`, and a row retired at itself is undated with no recovery. D5 fixes it for everything retired after the migration and honestly leaves the legacy retirements undated. |
| **Q4** trail-use notice lifecycle | **Expressible, untouched.** Instruments, quoted dates and `decision_decided_date`; no `citation_reading`. |
| **Q5** service-list membership alert | **Expressible, untouched.** Snapshot events, `party`, subscriptions; alerts never read text. |

## Consequences

**Easy.** A citation's provenance resolves: from the edge to the reading, from the reading to
the exact immutable text row, and from that row to the engine, render profile, agreement
distance and blob payload it came from. A reading standing on text the record no longer shows
becomes a query instead of an invisible fact. `place_mention`, when it is built, has a settled
precedent to copy.

**Hard.** Two writers change in this commit, not later: `load.py`'s retire call must pass a
timestamp (D6), and both `citator-query-2.sql` and `project.py` must select `text_id` or Q2's
location stays unresolvable (§ Checked against).

**Foreclosed — read this before accepting.** With the key left at `reading_channel`, asserting
a SECOND engine's citation reading for the same page becomes unreachable without another
rebuild of this table. Reading the `second` row would put two live `'ocr'` rows on one key and
they would collide on `citation_reading_live`; declaring an `'ocr-b'` channel is an INSERT into
`reading_vocab` but a **bare CHECK** on the published `ocr_run` (`0018:444`), so widening that
is a rebuild of a published table.

That matters because ADR 0023 decided the opposite for the sibling object: "a disagreement
between engines is not a tie to break, it is a **FINDING** for a person. It is only a finding
if both rows survive" (`0019:65-72`) — and `cited_raw` is the same kind of object as
`printed_text`, which is why migration 0019 said this table has "the same exposure". **This
record spends the last cheap rebuild of `citation_reading` while leaving that decision open**,
and the next rebuild is dearer: `citation_occurrence(reading_id REFERENCES citation_reading)`
from `../citation-grain.md:263` would give this table its first child to cascade.

**But widening it now is not cheap either, and the first draft of this section said it was.**
Measured 2026-09-12: `citation_resolution`, `citation_judgement` and `citation_treatment` all
key on `(… , method, method_version, reading_channel)` — the RULE's method, with the channel as
the only thing naming the reading (`0014:747`, `:814`, `:857`). And both `project.py:170-173`
and `citator-query-2.sql:199-203` join `citation_reading` on the four key columns **plus
channel alone**, with `rg.cited_raw` and `rg.quoted_passage` in the select list.

So two live readings on one channel would fan the projection and validation query 2 out, two
rows per resolution, and `SELECT DISTINCT` could not collapse them because the printed string
and the passage differ per reading — **the same break shape A was withdrawn for, relocated from
query 2's treatment join to its reading join.** A resolution could also no longer say which
reading it resolved. Widening coherently is a FOUR-table key change plus both join sites, not a
column on this one.

**So the door is dear on both sides, and that is the honest statement.** D3 stands, and this
record does not pretend the alternative was a free upgrade it declined. Whoever opens that door
should open it with `citation_occurrence` and the per-occurrence resolution in one decision,
because those three want the same rebuild and the same fan-out analysis.

## What this record does not decide

- **The grain of a finding.** `../citation-grain.md` is open, and the 83.2% of measured
  document loss a per-occurrence `citation_resolution` would recover is not addressed here.
  Shape A broke validation query 2; this record touches no key and cannot.
  **A priced choice, not silence:** if `citation_occurrence` lands later, D4's `spans` is a
  denormalised duplicate of its `(reading_id, ordinal)` rows and the corpus pass will have been
  paid twice. A child table needs no parent rebuild, so nothing is foreclosed — but the second
  pass is real.
- **Whether the engine name and render profile belong in this table's key** — see § Foreclosed,
  which prices it in both directions and recommends it be opened together with the grain.
- **`place_mention`'s pointer**, named beside this one in ADR 0021 § Validation. That table
  does not exist outside `schema-draft.md`.
- **The review queue's predicate**, where the 66% caption burden lives and which needs no
  schema change at all.

## Cost of reversing

**A migration touching every row, and it is cheap only because it is done once.** The rebuild
copies `citation_reading` — 73,838 live rows plus their retired predecessors — and the re-load
that fills `text_id` and `spans` appends one row per live reading and retires one. Reversing
means a second rebuild to drop five columns, a trigger and a vocab table, plus another corpus
pass to strip the spans.

Nothing else would have to move: no key changes, no child table cascades, no measurement card
is invalidated, and `FINDER_VERSION` does not advance — so every stored confidence and every
human decision already made survives a reversal untouched.

---

*Proposed, not accepted. Accept only after this decision has been checked against
`../validation-queries.md`.*
