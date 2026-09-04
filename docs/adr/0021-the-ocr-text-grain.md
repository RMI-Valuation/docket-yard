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
