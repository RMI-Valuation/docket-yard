# ADR 0021 — The OCR text grain

- **Status:** Accepted
- **Date:** 2026-09-02
- **Accepted:** 2026-09-02 (the operator: "ADR 0021 & 0022 are APPROVED")
- **Scope:** the grain, and what a reader is shown. Ranking as registry data, the review
  queue, and the rebuilds of two shipped tables are **deliberately not here**; see § What
  this record does not decide.
- **Reviewed:** four schema-critic passes and a four-lens panel, 2026-09-02. The last pass
  found the error that shaped this draft: an earlier split left decisions 7, 8 and 9 in this
  record while all three of their operands went to Migration B. **A decision and the thing it
  is computed from ship together, or the decision is a promise with nothing behind it.**

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
reading. It is almost entirely the pre-2005 record — the boundary at which search, the
citation graph and the registers all degrade.

**Two benchmark findings bear on the grain** (`research/ocr-benchmark/README.md` §§ 3–6,
authoritative for every figure). *No single engine wins*, so the read is routed per page:
dots.mocr reads best overall and gets every docket number on all 90 pages, while PP-OCRv6 is
the only engine that reads a map without inventing — **and PP-OCRv6 is the routed engine for
two different tiers**, which decision 4 turns on. *And the render moves the reading*:
dots.mocr peaks at 200 DPI where 300 exhausts the card, and crop and mask each change its
output. Those are the same engine at the same version producing different text.

**Agreement between two engines was measured** (§ Step 6) at AUC 0.93–0.97 against measured
CER, holding the tier constant — a real per-page confidence signal, and the only one
available. It is bought cheaply: the second reader is the cheapest non-family engine, about
+23% on the backfill.

**The paper schema predates all of it.** `docs/schema-draft.md` § 2 drafts `document_page`
with a singular `ocr_method` — one engine per page, current state, updated by a re-run. Two
engines' readings of one page have to coexist, because their agreement is the confidence.

## Decision

1. **The grain is one row per reading of one page.** `document_text`, append-only, natural
   key `(document_sha256, page_no, method, method_version, render_profile)` as a **partial
   unique index over live rows** — not a table-wide `UNIQUE`, which would forbid the
   retraction and self-pointer idioms `superseded_by` exists for. A surrogate `text_id` is
   minted for pointers. Every row carries ADR 0007's block, `superseded_by` and
   **`superseded_at`** — the latter a departure from the 0006/0009 idiom whose missing date
   `deferred.md` records as a cost — plus `measured_target` and `score_row_id` under the
   composite foreign key to `class_measurement`, which is what makes decision 7's gate a
   constraint rather than a convention.

   **A human row's key is pinned**: `method = 'human'`, `method_version = 'unversioned'`,
   `render_profile = 'human'`. The shipped convention for a human assertion is
   `citator.methods.HUMAN_VERSION`, a *dated* queue-convention version, and carried into this
   key it would put two live human rows on one page the day that date changes. What a
   reviewer was shown belongs in `review_action.method_version`.

   `/` is forbidden by CHECK in all three key columns, or a HuggingFace-style engine id
   renders a review key that cannot be parsed back into its columns.

2. **The render is in the key, not in a convention.** `render_profile` names the DPI and any
   preprocessing (`native`, `150`, `200`). Measured fact forces it: two renders of one page
   through one engine at one version are different text, so without the column they collide
   and the second read overwrites the first. Folding it into `method_version` by convention
   works until somebody writes the convention differently — the `web/cite.py` drift ADR 0018
   D7 names. One column, before a single row exists.

3. **The text layer is a reading, in the same table**, at `reading_channel = 'text-layer'`
   with `render_profile = 'native'`. One join for the viewer, the search index and the
   citator, and "which pages have been read, and how?" becomes a query.

   **But only the `primary` reading feeds the citator, and that rule is written here because
   the shipped shape cannot hold two.** `citation_reading_live` permits one live row per
   `(key, reading_channel)` with the engine deliberately outside the key, so two simultaneous
   live `ocr` readings of a page have one slot between them. Nothing writes it yet; the rule
   must exist before the first OCR-channel load does.

4. **`page_no` is a function of the document's identity; the page count and the routed class
   are recorded.** `document_sha256` fixes the byte stream, so page order is a property of
   the bytes; both passes take the order the PDF gives, 1-based. This matters because
   `citation_key`'s primary key carries `page` as the location, and a channel-dependent page
   number would mint two keys for one edge.

   The count lives in **`document_pagination`** — one row per document with `page_count`,
   `had_text_layer`, its own method, version and timestamp, a **typed outcome from a declared
   vocabulary**, and `superseded_by`/`superseded_at` with a live index like every other
   assertion here. The outcome is not decoration: without it a document with no row is *not a
   PDF*, *not yet paginated* and *failed to open* at once. The supersession is not decoration
   either — a re-pagination without it is an UPDATE, which is current state in the one new
   table the snapshot publishes, and it would leave decision 7's coverage arithmetic computed
   against a mutable denominator.

   **`document_text` carries `route_class`**, with the router's own method and version. The
   engine does not recover it: PP-OCRv6 is the routed reader for both the clean and the
   graphic tier, whose error profiles are not comparable. Every CER the benchmark reports is
   per tier, and `class_measurement` is keyed on class — so the day decision 7's gate opens,
   every row must be told which class it belongs to, and the router's answer would exist
   nowhere. Re-running the router later is not a recovery, because § Step 4 says it will
   change. One column, free now, unrecoverable after 1.35M rows.

   **This is still a deliberate shrink**: a per-page `document_page` would be ~1.10M rows and
   ~400 MB of the measured row budget, for a `rotation` column no code reads.

5. **An empty reading is a row; a failed read is counted.** A page an engine correctly reads
   as blank writes a row with empty text. A page whose read failed writes no text row, and
   `ocr_run` records the pass: one row per `(document, method, method_version,
   reading_channel, render_profile, ran_at)` — **`ran_at` is in the key, because a re-run
   appends where `extraction_run` replaces**, and the coverage read takes the latest. It
   carries a typed outcome, `pages_read` **and `pages_failed`**, because the measured failure
   is partial: the 300-DPI OOM died *nine pages into* a document, and without the count
   nothing distinguishes those pages from ones never attempted.

   **This is a mistake already made and paid for.** The benchmark's runner treated empty
   output as an error and dropped the page, penalising exactly the safest behaviour:
   Tesseract lost the two graphic pages it correctly emitted nothing for, while an engine
   that invents prose about a map kept all nine. ADR 0018 D10 says it from the other side —
   *absence is not a measurement.*

6. **Layout is captured as the engine's own payload, and block identity is fixed now.** The
   payload is kept whole as a blob under the `blobs/` prefix, content-addressed by its own
   digest and recorded in a table with `document`'s discipline; `document_text` carries the
   digest and a member path. **No block table ships here** — ADR 0003's argument is that
   layout cannot be added later without re-reading, which keeping the payload satisfies,
   while a block table today would invent one vocabulary across engines that return HTML
   tables, line boxes, and regions with no text at all.

   **`block_id` is a deterministic function of the payload digest and the engine's own index
   path**, because `citation_reading.source_location` is documented as `{page, block_id,
   bbox}` and an id minted by a later projection would strand every location written before
   it.

   **And this narrows ADR 0003, recorded rather than left implicit.** 0003 holds that the IR
   carries font size and weight. For a scan nothing is lost — no OCR payload carries a font.
   For a **born-digital** page they are extractable and no payload holds them, so the
   text-layer pass keeps its own extractor output as its payload.

7. **Display is ungated; assertion is gated — and search ships with the text.**

   **Every read page shows its text**, labelled machine-read, with the engine and version,
   the scan one click away, and a way to report a misreading. Nothing is withheld for being
   imperfect. Withholding would itself be a claim and a worse-calibrated one: *"scanned; not
   yet read"* on a page we have read says something untrue.

   **Search covers it in the same migration**, because findability is what this work is for
   and a viewer alone spends 187 hours to make text visible one document at a time. The page
   index is its own FTS5 table over the display view (ADR 0022 D4) and reaches readers
   through its own query path — **not** by joining the shipped `search()`, whose own comments
   record that `bm25()` in `ORDER BY` defeats FTS5's internal ordering and evaluates the
   select list for every matching row before `LIMIT`. **No OCR text reaches `/search`,
   `/suggest` or the MCP surface until `search.Hit` can carry the label, the band and the
   scan link**; today it carries `kind, path, title, fact, caption, snippet` and none of the
   three, and `web/mcp.py`'s `_search` hands the same results to a language model under a
   tool description promising permanent addresses. That is the display-becomes-assertion path
   on this site, and it is closed here rather than discovered later.

   **This needs a page-grained address, which does not exist.** The viewer is
   `/decision/<id>/view` and `/filing/<id>/view`, whole-document. A per-page address is a
   permanent URL under ADR 0013 and therefore a commitment; it is Migration A's to build.

   **No derived assertion is published from any of it until its class is measured.** ADR 0017
   D3 unchanged: `document_text` joins `measured_target_vocab` with its `class_vocab` left
   empty, so `confidence_state = 'measured'` requires a `class_measurement` row whose class
   cannot yet exist. Showing a person text they can check against the scan is reversible in
   their head; mining it into a fact whose derivation they never see is not.

8. **The confidence band ships with its operand, or it does not ship.** What a reader sees is
   never an engine's opinion of itself: the engine's self-reported number is stored in a
   **nullable `engine_confidence`**, distinct from ADR 0007's `confidence`, because a
   text-layer row and a human row have no such number and a NOT NULL column would make them
   invent one — the same overloading decision 5 refuses for empty text.

   The band is derived from the **measured agreement signal**, so the signal is stored here
   and not deferred: the `second` reading carries `agreement_distance` with the rule's own
   method and version. `text_agreement` as a table, and the queue built on it, stay in
   Migration B; the *operand* does not, because decision 7 shows it to every reader.

   **A text-layer page has no band and says so.** It is read once, so there is no agreement
   to measure — 857,012 of 1.10M pages. It is labelled *the publisher's own text layer*,
   which is a different and better statement than a confidence.

9. **One live primary per page, one live human, enforced by the index.** `document_text`
   carries `reading_role` (`primary | second | human`), and two partial unique indexes on
   `(document_sha256, page_no)` — one `WHERE superseded_by IS NULL AND reading_role =
   'primary'`, one for `'human'` — make the display single-valued by construction. Display
   takes the human row if one exists, else the primary.

   **Without the indexes the rule has no answer, which an earlier draft of this record
   missed.** `method_version` and `render_profile` are in the natural key precisely so a
   re-run inserts rather than collides — so the first re-run leaves two live primaries, and a
   born-digital page that is also OCR'd has two by construction. With them, a re-run *must*
   supersede the outgoing primary, and `superseded_at` makes "what was displayed on date D"
   replayable. **The cost, named:** supersession here is cross-key, an idiom this project has
   not used, where decision 1's append-only argument assumes within-key.

   **"Human" is encoded three ways and they are bound together**: `CHECK ((method = 'human')
   = (reading_role = 'human'))` and `CHECK ((reading_role = 'human') = (confidence_state =
   'human'))`. Unbound, a model row could be written with `reading_role = 'human'`, win the
   display, and be unprotected by the trigger — which fires on `confidence_state`, as
   `citation`'s does. A model pass may never displace a human row.

## What this record does not decide

- **Ranking as registry data, and the `assertion_method` rebuild.** Decision 9 makes display
  single-valued with an index instead. A rank matters when something must choose between
  engines whose order is contested, and that routing rests on five tabular and nine graphic
  pages. Migration B, and `ocr-migration.md` records what the rebuild costs.
- **The review queue and `text_agreement` as a table.** § Step 6 measured the flag rate at
  20–60%, which is 19 to 58 years of a fifty-page week, so a queue that must be cleared gets
  redesigned against the measurement first. Decision 8 keeps the operand regardless.
- **`page_route` as a table.** Decision 4 puts the routed class on the reading, which is what
  the class measurement will need; the router's rejected alternatives can wait.
- **Which engine reads which tier, the render, and the order the tiers are read** — the
  operator's, in `ocr-plan.md`.
- **Where the bytes live and what the snapshot publishes** — ADR 0022.

## Consequences

**What becomes easy.** Two engines read a page and disagree without either being wrong in the
store. A re-run at a better engine or render is an insert that supersedes cleanly. A human
correction has a home, an author and a date. And the pre-2005 record becomes findable, which
is what capability M3 exists for.

**What becomes hard, or costs.**

- **~1.35M `document_text` rows**, and the store grows accordingly — ADR 0022 measures it.
- **A per-page permanent address**, which is an ADR 0013 commitment this record creates.
- **Cross-key supersession** (decision 9), an idiom new to this project.
- **Decision 2's argument does not reach `citation_reading` or `decision_decided_date`.** Both
  live-index without a render, so a re-render at a better DPI produces a reading that
  supersedes its predecessor. For `decision_decided_date` that is sharper than a general
  consequence: a **date** is the dispositive artefact in validation query 4, dates are quoted
  and never computed, and the quoted evidence is destroyed one join over from where
  `document_text` preserves it. Widening those keys is ADR 0018's to revisit; until then the
  pipeline's rule is that a re-render does not re-extract without a new method version.
- **Published pages move in the same commit** — `coverage.html`, `methodology.html`,
  `search.md`, and the `/corrections` promise, which currently says a person reads every
  report within seven days and would now cover a misreading on any of 247,923 pages. Whether
  a misreading is a correction under that promise is the operator's.

## Validation

Checked against `docs/validation-queries.md`.

- **Q1 and Q5** read assertions derived from document text, absent for the pre-2005 record
  today. This record gives them a source, and decision 7's gate keeps an unmeasured reading
  out of a published answer or an alert — alerts are event-driven and never read text, so the
  gate holds by construction. **It does not yet give them a pointer**: no shipped consumer
  has a `text_id` column, and adding one to `place_mention` or `citation_reading` is theirs
  to decide, not this record's to assert.
- **Q2** is the citator's and joins `document_text` nowhere. Decision 4 keeps it that way:
  one edge, one `citation_key` row, whichever channel read it.
- **Q3** needs a dated history of what was displayed, and decision 9's indexes plus
  `superseded_at` now give one — a re-run supersedes rather than sitting beside, so "what a
  reader saw on date D" is replayable for this layer. `document_pagination` gains the same
  treatment in decision 4, or the coverage denominator would be current state.
- **Q4** is unaffected today and inherits Q1 the day a NITU date is quoted from a page — with
  the `decision_decided_date` caveat in § Consequences, which is a Q4 finding and not a
  general one.

## Cost of reversing

**The grain (decisions 1–6): expensive.** Not a migration but a re-read: 2.71 s a page over
247,923 pages, about 187 hours plus the operator's re-checking. That is why the render and
the routed class are in the table now — a column added before the first row is free, and the
same column added after the backfill is the whole backfill.

**The payload instead of a block table (decision 6): cheap, and chosen because it is.**

**The display rule (decisions 7–9): cheap, and reversible in the direction that matters.** A
gate can be added later; text already shown cannot be unshown, but it was never asserted and
the scan beside it said so. Decision 9's indexes are the expensive half to remove, because
rows written under them assume supersession.

---

*Accepted 2026-09-02, after the check against `../validation-queries.md` recorded in
§ Validation. The migration this record authorises is scoped in
[`../ocr-migration.md`](../ocr-migration.md) § Migration A, and schema-critic reviews it
before the tables exist.*

## Addendum (2026-09-04): what the display rule omits, and the page is not indexed

The operator decided two things about the text pages on the day after the first load, with
1,104,935 pages showing.

**Decision 9's display omits contact details.** `document_text_display`'s `text` is
`dy_display_text(text)` from migration 0020: the stored reading with email addresses and
North American telephone numbers (written with separators) replaced by `[email omitted]`
and `[phone omitted]`. The stored row is untouched — decision 1's append-only reading is
still the document's own words — and the Board's file is one click from every page. The
rule is one SQL function (`store/display.py`) registered on every connection, so what the
page shows, what `page_fts` indexes and what a `'delete'` carries are the same bytes by
construction, which FTS5 external content requires. It applies to everyone alike, counsel
and commenter, because telling them apart is an inference about a person; and it leaves
postal addresses, which no pattern finds reliably, and bare ten-digit runs, which are also
record identifiers, and it leaves a bare separated run with no telephone word beside it,
because a tariff item and a section are written 3-3-4 too. The methodology page says all
of that, and the text page says "where a pattern finds them". The view's version and the
rule's are the page index's format (`display@0020.1`), so the index is rebuilt after the
deploy and `web` refuses to serve an index that predates the format. **A change to the
patterns is a new migration**, never a code edit alone: that dates the rule in the store,
which is what keeps validation query 3 answerable — what a reader saw on date D is the
stored reading under the rule in force on D, and the store must say which that was. The
same migration makes `text`'s immutability a trigger; `leave` and the view both rest on it.

**This is not the mask dropped on 2026-08-31** (`schema-draft.md` § environmental
comments), and it holds to that decision's consequence: nothing published implies a name
can be held back. That design masked a *name* in one column while three other paths
printed it, which a reader takes for a promise. This one omits *contact details* from the
machine-readable text alone, says on the page that the scan carries them, and claims
nothing about privacy: the record is published as the Board publishes it, and what changes
is only what a million pages hand out at scale.

**Text pages are `noindex`, all of them, both tiers.** In the page and in the header;
robots.txt does not disallow them for ordinary crawlers, because a crawler that may not
fetch a page never sees the noindex. The case for: a search-engine snippet is exactly the
ungated hit ADR 0022 D4 keeps out of `/search` until a hit carries its label, band and
scan link; an indexed misreading is a published one under this project's name; the record
page and the Board's own PDF already rank; and a million whole-document pages is the
largest surface this site has offered a crawler. The case against, recorded because it is
real: findability is what the text is for (decision 7), the text-layer tier has no OCR
error rate, and noindex removes nothing from a harvester — masking does that. Revisit both
decisions together when the page search path ships; a tiered rule (text-layer indexable
with a canonical to its record, engine readings not) is derivable from `reading_channel`
and was the alternative considered.

## Addendum (2026-09-10): the noindex revisited, and held

The page search path shipped 2026-09-04, the condition the addendum above set for revisiting.
Revisited 2026-09-10 against what production then held — 72,341 documents (935,419 pages)
read from a text layer and 11,452 (169,516 pages) read by an engine — the operator held
the rule: **text pages stay `noindex`, all of them, both tiers.** The text-layer tier is
the text a search engine already reads from the Board's own PDF, so opening it duplicates
what ranks and adds a crawl surface to a box that starved on CPU on 2026-09-06; the tier an
index would add something for is the engine tier, at 10.8% CER and with no review layer.
The tiered rule (text-layer indexable, engine readings not) was weighed and set aside for
that reason. Revisit when Migration B gives an engine reading a measured band.

The same day: **`/search` joins the named AI agents' disallow list** (`docs/machine-surface.md`
§ The AI policy). A result page prints snippets of the held text and the party names, so
an agent that may not fetch `/text` or `/p/` could read both through the side door; the
rule now says what the prose says. People and ordinary crawlers are unaffected.

## Addendum (2026-09-15): the router's verdict is its own assertion

**Status: Accepted (2026-09-16), by the operator.** Narrows decision 4 and § What this record does not decide ("`page_route`
as a table"). Migration 0032.

1. **The router's verdict is a page-grain assertion of its own**, `page_route`: one live row
   per page, naming the router, its version and the render it saw, with ADR 0007's confidence
   block and supersession rather than update. **Two clocks**: `asserted_at` and
   `superseded_at` are the store's, when the row entered and left the record; `routed_at` is
   the router's own, in UTC, and only orders verdicts: a differing verdict routed no later than
   the live one as first loaded is stale and writes nothing (a load that changes nothing writes
   nothing, so agreement never moves that date). A different class, router, version or render
   is a new row; no column the row asserts changes in place. A page the router failed on has
   no verdict and no row.
2. **Decision 4's `route_class` on a reading is unchanged**: it is the class the page was read
   under, never back-filled from `page_route`, and a later verdict does not alter it.
3. **The marker rule.** A page whose live route is `tabular`, and whose shown reading is a text
   layer that is blank or belongs to a document paginated as having no text layer, or which has
   no shown reading, reads *Scanned; contains a table we have not read*, naming the router and
   linking the scan, and is not counted as read. Every other empty reading (an engine's, a
   person's, a text layer on a page routed otherwise) reads "Read as blank." One emptiness test
   decides both: the text with whitespace stripped.
4. **Held** from the snapshot, with `route_class_vocab`.

**Validation** (`docs/validation-queries.md`). Query 3, point-in-time state, is the one this
touches: what a page showed on date D is the display row live on D, the `document_pagination`
row live on D (its `page_count` and `had_text_layer` feed the rule) and the `page_route` row
live on D — each the row whose `asserted_at` ≤ D and whose `superseded_at` is null or after D,
on the store's clock throughout; `routed_at` is never read for it. Queries 1, 2, 4 and 5 read no page
text and no route, and are unchanged.

## Addendum (2026-09-17): a reading's quality is its own assertion, and the rule that judges it is dated

**Status: Proposed.** Narrows decision 7 by adding what a page may say *about* a reading it
shows. Migration 0034. Measured in `docs/research/text-quality/`: ~110,500 of 931,392 judged
text-layer pages are faulty (65,300–330,000), ~25,000 garbage. The operator's decisions of
2026-09-17: a stored flag feeding a page warning, search untouched. **Two schema-critic passes**;
what they broke is in § What the earlier drafts got wrong.

1. **The subject is a reading, not a page.** `text_quality`, keyed on `text_id` —
   `document_text`'s own key, never `(document_sha256, page_no)`. `document_text.text` is
   immutable by trigger and `text_id` is a surrogate, so the pointer resolves for ever to the
   exact bytes scored; a page key would re-point a published warning at words nobody measured
   on the first re-read, because supersession there is cross-key (decision 9).

2. **A score is superseded, never updated**, with `superseded_by`/`superseded_at` and a live
   partial index, as `page_route` has them. Re-scoring under the same instrument is an INSERT
   that retires its predecessor.

3. **A different lexicon is a second live score, not a supersession.** The live index is
   `UNIQUE (text_id, method, method_version, lexicon_digest) WHERE superseded_by IS NULL`, and
   the score row carries all three. **This is decision 2's render rule, for its reason**, and
   the second draft had it backwards: the lexicon is built from the record and the record grows
   through waves 2–3, so making a new lexicon supersede would put ~931k rows through a
   supersede-and-reinsert at every rebuild. It also keeps ADR 0023's finding rule — a candidate
   lexicon can be scored beside the incumbent and the disagreement is visible, which it is only
   if both rows survive. **The tie-break is not a race**: decision 4's rule names the instrument
   the page reads, so exactly one of a page's live scores is ever displayed.

4. **The rule that judges is a dated row on the store's clock.** `quality_rule`: the cut, the
   floor, `method`, `method_version`, `lexicon_digest`, `asserted_at`, `superseded_at`, and
   `UNIQUE WHERE superseded_by IS NULL` over the whole table — **one live rule, store-wide**.
   The page reads the live rule; a replay reads the rule whose `asserted_at <= D` and whose
   `superseded_at` is null or after D. **There is no separate in-force clock and no
   back-dating**: a rule takes effect when it enters the record, because a rule inserted on day
   two and in force from day one rewrites what the record says a reader saw — 0032's "two
   clocks, never one" seen from the other side, where the second clock would be the harm.
   Moving the cut or the floor is one INSERT and moves no stored score.

5. **The counts ship with the score, all three.** `lettered_tokens`, `word_shaped_tokens`,
   `lexicon_hits`; the score is `lexicon_hits / lettered_tokens`, pinned here because two
   denominators for one number is a mistake this work has already made. A third counter is free
   now and a re-score of 931k rows later.

6. **The lexicon is an artefact with a row, not a digest of something nobody kept.** `lexicon`:
   `lexicon_digest` as its key, the word count, what it was built from, the day, and the blob's
   own digest in the blob tier. A digest with no preimage is an unverifiable key, and § Reviewed
   already states the rule: a decision and the thing it is computed from ship together.

7. **Every live text-layer reading gets a row, and the floor is a read-time rule.** A blank
   page's row carries zeros — decision 5's rule, that an empty reading is a row. **Nothing about
   the floor is frozen onto a row**: "too short to judge" is evaluated from the rule live on the
   day, exactly as the cut is, or moving the floor would invalidate ~931k stored verdicts and
   make `/methodology`'s denominator unreplayable. So **"no row" means one thing: not yet
   scored** — which is what `text_quality_run` counts.

8. **A pass is a row.** `text_quality_run`: one row per pass, corpus-scoped and therefore *not*
   `ocr_run`'s per-document shape (which the second draft named in error), carrying the
   `rule_id` and `lexicon_digest` it ran under, `pages_scored`, `pages_blank`, `pages_failed`
   and the published counts the pass computed. `pages_failed` is there for ADR 0021 D5's
   reason — absence is not a measurement — and the published counts are stored here rather than
   recomputed, because a count joined through `document_text_display` pays `dy_display_text`
   per row and that view's cost is measured: 27m26s to rebuild the page index at 1.1M rows.

9. **A stale score is not shown, and staleness is defined against the view.** A `human` row
   removes a primary from `document_text_display` **without superseding it**, so
   `superseded_by IS NULL` is not the test — ADR 0026's lesson, in its shape:
   `NOT EXISTS (SELECT 1 FROM document_text_display v WHERE v.text_id = q.text_id)` is stale.
   **Every reader of that view calls `display.register` first** (ADR 0026 D2): the function is
   resolved over the whole view body at prepare time, so a CLI pass that opens the store bare
   cannot read it at all.

10. **Only a text-layer reading is scored, as a writer's obligation and a filtered index** —
    not a CHECK. The signal does not transfer (AUC 0.59 against the wave's agreement distance
    on 55,356 engine primaries), but SQLite cannot ALTER a CHECK, and a welded channel would
    make scoring an engine reading later a rebuild of a ~931k-row table. ADR 0026 D7's idiom
    for a pairing SQLite cannot express.

11. **The score is not ADR 0007's `confidence`**, which the row also carries: the block is
    `confidence`/`confidence_state`/`measured_target`/`score_row_id`, and the score is its own
    column, as `engine_confidence` is in decision 8.

12. **The gate is on the scored row, and it is a measurement of the instrument.**
    `score_row_id` and `measured_target` sit on `text_quality` under the composite FK, so
    decision 7's gate stays a constraint rather than a web-tier convention — D1's own argument.
    `measured_target_vocab` gains `text_quality`; `class_vocab` gains the **instrument**
    (`text-layer-lexicon-share`), never the cut.

    **One measurement row, not two.** The detector figures are the 64-page sample's — precision
    1.00 for any fault, 0.72 for garbage — and `score_file` names that file and that n. The
    band rates are **not** a `class_measurement` row and may not be made one: its
    `CHECK (recall IS NOT NULL OR precision IS NOT NULL OR false_veto_rate IS NOT NULL)` has no
    column for a rate, and a second row on one `benchmark_date` collides on
    `class_measurement_identity`, whose key ADR 0018 D8 declined to widen on 2026-09-01. The
    band rates live in the research directory, which is where a figure with no column belongs.
    **Recall is therefore not stored either**: 0.68 is population-weighted over two samples and
    an 866,497-page band, and `truth_count`/`found_count` beside it would name 32 labelled pages
    under a denominator that is an extrapolation.

    **The remaining cost, named:** `class_measurement` has no lexicon column, so a row scored
    under one lexicon may point at a measurement taken under another. Widening that key is ADR
    0018 D8's, and decision 3 makes a second instance likely.

13. **What the page says.** Below the live rule's cut, one sentence names the method, its
    version and the score, says what was counted — that most of this page's tokens are not words
    the record uses — and links the scan. It is a claim about a count, while the gate is opened
    by a measurement of that count **as a fault detector**, the stronger predicate; the record
    takes the honest reading, that a reader will hear "this page is suspect". **The count is
    taken over the stored reading, before the display rule omits contact details** — a
    length-changing mask — so a reader recounting tokens on the page will not reproduce it, and
    the sentence says so.

14. **A page with no warning gets no sentence.** One text-layer page in eight is faulty and
    3.5% are flagged, so a reassuring sentence would be false for most faulty pages. This
    reverses `band()`'s idiom on the same page deliberately: there, silence about a *second
    reading* is a fact about this project; here, silence about *quality* would be a claim about
    the document. `/methodology` carries the shortfall in the same commit — including that an
    engine reading is not scored at all, so an unflagged page is not a judged page.

15. **A reader's report is a report about the reading, and `review_target_vocab` gains
    nothing.** The correctable object is the text, which already has its row and its natural
    key; a new review target would be keyed on a surrogate that changes at every re-score,
    orphaning the report, and `search.PAGE_TABLES` excludes the page tables **by name**, so a
    third page-grain target would put a page-text correction back into the record index's
    signature and rebuild it site-wide. **A human row suppresses the warning**: it copies the
    machine's counts unchanged and means *do not show this*, so nobody has to invent a count
    they did not take.

16. **Held, all four**, and each classified by name in `dump.HELD_TABLES` — `text_quality`,
    `quality_rule`, `text_quality_run`, `lexicon` — with `text_quality` **above `document_text`**
    (children before parents). `dump.scrub` raises `Unsafe` on any table it cannot classify, so
    an unclassified one breaks the nightly snapshot the night the migration lands. Whether a
    23,524-word vocabulary distilled from the record could ever be published is a
    `docs/licensing.md` question, not a migration author's; held answers it for now.

17. **The writer.** A CLI pass scores live text-layer readings that have no live score under the
    live rule's instrument, reading the lexicon blob named by that rule and **refusing to score
    rather than to load** if it is absent; the forward pass scores what it loads, under the same
    rule. ~931k rows against ADR 0022's budget.

**Validation** (`docs/validation-queries.md`). Query 3 is the one this touches: what a page
showed on date D is the display row live on D, the `text_quality` row live on D for the
instrument the `quality_rule` row live on D names — three reads on one clock, which is why
decisions 4 and 3 are shaped as they are.

**And the first of the three cannot be read today, which this record states rather than
assumes.** `document_text_display` is a CURRENT-state view: it filters `superseded_by IS NULL`
and exposes `asserted_at` but no `superseded_at`, so there is no as-of form of it, and
migration 0028 forbids re-deriving its human-over-primary rule against `document_text`. The gap
predates this addendum and belongs to the text pages as they ship today; what is new is that
decisions 4 and 9 make a *published sentence* depend on it. **Owed with the migration**: an
as-of projection of the display rule — one view or one function, in the store, not a second copy
in the web tier — or decision 14's sentence is replayable only to the day it was read.

Queries 1, 2, 4 and 5 read no quality row; nothing derived is published from a score, and the
citator's families do not join it. The operational join
(`citation_reading.text_id = text_quality.text_id`, a re-walk queue of edges read off flagged
pages) is left unbuilt here and is not foreclosed.

## What the earlier drafts got wrong (schema-critic, two passes, 2026-09-17)

Recorded because three of these are errors in the measurement or in a fix, not in the original
design, and because the second pass broke the first pass's own repair.

- **The cut lived in a `class_vocab` class name** (pass 1). That made `confidence_state =
  'measured'` a function of a threshold: moving the cut meant superseding and re-inserting every
  scored row, and every past replay of query 3 answered today's question. Decision 4 replaces it.
- **The lexicon superseding reinstated that same every-row cost** (pass 2) — the repair's own
  defect, and worse than the disease, because the lexicon changes whenever the record grows
  while the cut changes when somebody decides. Decision 3 makes it a second live score.
- **The floor was frozen onto each row** as a stored verdict under a rule that moves (pass 2).
  Decision 7 makes it read-time, so the § claim that a rule change moves no stored score is now
  true of both halves of the rule.
- **`quality_rule` had one clock and no live index** (pass 2): two rules could be in force at
  once, and a back-dated rule could rewrite what the record says a reader saw. Decision 4 fixes
  the clock and the index, and forbids back-dating.
- **The measurement registry cannot hold what decision 12 promised** (pass 2): a band rate fits
  no column and a second row on one date collides on the identity index. One row now, and the
  band rates stay in the research directory.
- **`text_quality_run` named `ocr_run`'s shape**, which is per document and public, for a
  corpus-scoped held row (pass 2). Decision 8 states its own shape and restores `pages_failed`.
- **The review target would have rebuilt the record index** (pass 2): `search.PAGE_TABLES`
  excludes the page tables by name. Decision 15 adds no target and suppresses through a human
  row instead.
- **`good` had two denominators in one document** (pass 1): `hits / word-shaped` in the 18005
  table and `hits / letter-bearing` everywhere else — 0.56 against 0.22, the same page and the
  same reading. Decision 5 pins it; the README is corrected.
- **Garbage recall was 0.92 and is 0.68** (pass 1). The 0.92 came from the 64-page sample, whose
  ≥0.7 cell held 16 pages and no garbage; the 102-page top-up found 1 in 102 up there, standing
  for ~8,500 pages the cut misses. Nothing had been published from it, and decision 12 now keeps
  it out of the store as well.
