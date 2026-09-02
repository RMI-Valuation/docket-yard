# ADR 0021 — The OCR text grain

- **Status:** Proposed
- **Date:** 2026-09-02
- **Reviewed:** schema-critic, 2026-09-02, against the five queries and the shipped store.
  Its Tier 0 and Tier 1 findings are answered in decisions 1, 2, 4, 5, 9, 10 and 11 rather
  than deferred.
- **Split:** where the bytes are written left this record for
  [ADR 0022](0022-where-the-records-text-lives.md) on 2026-09-02, while both were Proposed.
  It changes no column here, and binding a file-copy decision to a 132-hour one would have
  priced them the same.

## Context

**Nothing of the record's text is in the store.** `extract_text.py` writes one JSON file per
document on the enrichment box, `citator.find.findings_document` takes its pages as an
argument, and the store holds captures, the registry, the ledger, the party module and the
citator's five assertion families — and not one word of any document. So `document_text` is
not a table added beside an existing one: it is the first place the record's own text lands,
and its grain is a one-way door in exactly ADR 0003's sense. Reversing it means re-running
the read over the archive.

**What is to be read is counted, not estimated** — a census of the extraction output
(`tools/rmi-ai-machine/text_layer_census.py`, 2026-09-02, with the corrections it forces
recorded in `ocr-plan.md`): **15,085 image-only documents holding 247,923 pages**, against
59,210 text-layer documents holding 857,012. **247,923 is the figure that moves**, because it
is 42% above the ~175,000 every cost in the plan is multiplied by — about 187 hours of routed
reading rather than 132. It is almost entirely the pre-2005 record, the boundary at which
search, the citation graph and the registers all degrade, and it is a lower bound:
`image_only` is a *document*-level flag, so an image page inside an otherwise text-layer
document is counted on the other side.

**The benchmark settled the engines and deliberately unsettled the pipeline**
(`docs/research/ocr-benchmark/README.md` § Steps 3–5, which is authoritative for every
figure). Two of its findings bear on the schema. **No single engine wins** — dots.mocr reads
best overall and perfectly on docket numbers, PP-OCRv6 is the only engine that reads a map
without inventing, and neither detects an unruled table — so the read is routed per page.
And **the router's blank call is unsafe**: three of the four pages it calls blank are not,
so *"no regions" must never mean "skip"*. The tabular route rests on five pages and the
graphic tier on nine, so neither is settled.

**And the render moves the reading.** dots.mocr peaks at 200 DPI — degraded 12.7% to 12.1%,
where 250 overshoots and 300 exhausts the 12 GB card — while PP-OCRv6 is flat from 150 to
300 (§ Step 5). Crop-to-content moves dots.mocr 8.2% to 7.9% and masking gives it its best
clean tier at 2.6%. These are the same engine at the same version producing different text.

So a schema that names one engine per page encodes a routing decision the measurements
refuse to make, and one that omits the render cannot hold two readings the measurements say
differ — both in the one place that cannot be re-run cheaply.

**The paper schema predates all of it.** `docs/schema-draft.md` § 2 drafts

```sql
document_page (document_sha256, page_no, had_text_layer, ocr_method, rotation, PK (…, page_no))
page_block   (block_id, document_sha256, page_no, bbox, text, font_size, …, block_confidence)
```

`ocr_method` is singular — one engine per page, current state, updated in place by a re-run.
The review layer the operator required on 2026-08-28 (*"as accurate as possible, with a
review layer"*) needs the opposite: **two engines' readings of one page have to coexist**,
because their agreement is the confidence signal. The drafted shape cannot hold the plan the
operator chose.

**And most of the machinery already exists.** Migration 0014 built `assertion_method` (who
may write, who wins, at which version), `class_measurement` (every published figure, scoped
to the stage it measured), `extraction_run` (a pass with a typed outcome, because *absence is
not a measurement*) and `reading_vocab`, typed `text-layer | ocr | human`. Migration 0015
built `reviewer`, `review_action` and its typed targets, and defined a queue as **a query**:
every live row of a kind that no live review action names. And ADR 0017 D3 already says a
class nobody has scored is `unmeasured` and **projects nothing** — *"which is why OCR, at
10.8% CER, ships stored and unprojected until somebody measures it"*. The question this
record answers is not what to build; it is what not to build a second time.

## Decision

1. **The grain is one row per reading of one page.** `document_text`, append-only, with a
   natural key of `(document_sha256, page_no, method, method_version, render_profile)` and a
   surrogate `text_id` used only by pointers. Not one row per page, and not one per
   document. Two engines' readings of a page are two rows that sit beside each other; a
   re-run at a new version or a new render lands beside the old rather than on it. The
   plan's agreement-as-confidence is then a query over rows rather than a decision taken
   before anything is written.

   **A human row's key is pinned**: `method = 'human'`, `method_version = 'unversioned'`,
   `render_profile = 'human'`. The shipped convention for a human assertion is
   `citator.methods.HUMAN_VERSION`, a *dated* queue-convention version — and carried into
   this key it would put two live human rows on one page the day that date changes, and a
   third if two reviewers worked from different renders. The version of what a reviewer was
   shown belongs in `review_action.method_version`, which is the row that records it.

   **The natural key is a partial unique index over live rows, not a table-wide one**, and
   the record says so rather than leaving it to the migration: a table-wide `UNIQUE` forbids
   the retraction of decision 10 and the self-pointer of owed item 8, which are the two
   things `superseded_by` exists for. Migration 0014 § Why `citation_key` is a table
   enumerates the same reasons.

   **The surrogate exists because every downstream assertion needs to name the reading, not
   just the document.** ADR 0007's provenance block as shipped carries
   `asserted_from_document` and a JSON `source_location`; a `place_mention` or a
   `citation_reading` derived from an OCR'd page could name the bytes it came from and not
   *which reading of them*. Validation queries 1 and 5 both run through that join, so
   without the pointer the gate of decision 8 sits on the mention's confidence state with
   nothing structurally connecting it to the reading's. Anything extracted from a page
   carries `text_id` in its `source_location`.

2. **The render is in the key, not in a convention.** `render_profile` names the DPI and the
   preprocessing chain (`150` today; `200`, `200+mask` if the operator takes them). Measured
   fact forces this: 150-DPI and 200-DPI dots.mocr readings of one page are different text
   from one engine at one version, so under a key without the render they collide, and the
   second read either overwrites the first or is dropped. Folding the render into
   `method_version` by convention would work until somebody wrote the convention down
   differently — the failure mode ADR 0018 D7 names about `web/cite.py`, where two things
   kept in step by hand drift. One column, before a single row exists.

   **A second reading for agreement is therefore a different method by construction.** An
   identical re-run at the same method, version and render is not evidence — it is a repeat,
   and it supersedes rather than sitting beside. (Several of these engines are sampling
   decoders and may not be exactly reproducible; that is a reason to record the run, not a
   reason to store two readings under one key.)

3. **The text layer is a reading, in the same table**, at `reading_channel = 'text-layer'`
   with the extractor and its version as the method and a `render_profile` of `native`. Not
   a second table and not a branch on `media_type`. One table means the citator, the search
   index and the viewer have one join; it means "which pages of the record have been read,
   and how?" is a query rather than an inference from the file's type; and it is the shape
   ADR 0018 D3 already assumes, since the channel is in every citation reading's key.

4. **`page_no` is a function of the document's identity, and `document_page` is kept to say
   so.** `document_sha256` fixes the byte stream, which fixes the PDF's page order; so the
   page number is a property of the bytes and not of a reading, and both passes take the
   order the PDF gives, 1-based. This matters because `citation_key`'s primary key is
   `(citing_document, page, target_kind, target_key)` and migration 0014 states plainly that
   *`page` in the key IS the location*: a channel-dependent page number would mint two keys
   for one edge and leave ADR 0018 D7's rank — the text layer outranks OCR — nothing to
   compare.

   `document_page (document_sha256, page_no, had_text_layer, rotation)` is therefore
   **retained** and stripped of `ocr_method`. It is the referent `citation_key.page` has
   never had; it is what makes an **unread** page countable at all (an unread page has no
   `document_text` row, so without it the coverage promise cannot be kept); and it is what
   separates "this page has no text layer" from "the text-layer pass has not run here". A
   file with no pagination — `media_type` records `zip` and `xlsx` among the held bytes —
   gets no `document_page` rows and therefore no readings. **This costs a pagination pass
   over every held PDF** — a row for a document nobody has read is the whole point — and
   `had_text_layer` is itself a derived assertion carrying a method, a version and a
   timestamp, or it breaks ADR 0007 on arrival.

5. **An empty reading is a row; a failed read is not.** A page an engine correctly reads as
   blank writes a `document_text` row with empty text. A page whose read failed — the OOM at
   300 DPI is a measured example — writes no text row and is recorded in an `ocr_run` row
   modelled on `extraction_run`: one row per `(document, method, method_version,
   reading_channel, render_profile)` with a typed outcome and pages read — **and, unlike
   `extraction_run`, it appends rather than replacing on a re-run.** That table's own header
   records the cost of replacing: a `failed` attempt overwritten by a later `read` leaves no
   retry history, *"so no published coverage number may be derived from this table"*. The
   coverage page reads exactly this, so the semantics have to differ. **This is not a
   detail; it is a mistake already made once and paid for.** The benchmark's runner treated
   empty output as an error and dropped the page, so it penalised precisely the safest
   behaviour — Tesseract lost two of its nine graphic pages, the two where it correctly
   emitted nothing, while an engine that invents prose about a map kept all nine (§ Step 3,
   fixed 2026-09-01). ADR 0018 D10 states the same rule from the other side: *nothing else
   distinguishes read and found nothing from not yet read; absence is not a measurement.*

6. **Layout is captured as the engine's own payload, and block identity is defined now.**
   The payload is kept whole as a blob, recorded in a table with `document`'s discipline
   (digest, size, first seen) so a pruned payload is a visible fact and not a dangling hash;
   `document_text` carries its digest. **No block table ships with this migration** — ADR
   0003's argument is that layout cannot be added later without re-running OCR over the
   archive, and keeping the payload satisfies exactly that, while a block table today would
   have to invent one vocabulary across engines that genuinely disagree: dots.mocr returns
   HTML with `rowspan`/`colspan`, PP-OCRv6 returns line boxes, PP-DocLayoutV3 returns
   regions with no text in them at all.

   **But `block_id` must be deterministic from the payload**, because
   `citation_reading.source_location` is documented as `{page, block_id, bbox}` and ADR
   0003's validation resolves an edge's provenance to page, block and bbox. A block id
   minted by a later projection would strand every `source_location` written before it. The
   id is a function of the payload digest and the engine's own index path, so projecting
   blocks twice yields the same ids.

   **And this narrows ADR 0003, which is recorded rather than left implicit** — the form
   `schema-draft.md` uses for ADR 0016's narrowing and ADR 0008's. 0003 decides the IR holds
   bounding boxes, font size and weight, and per-block confidence. For a scan nothing is
   lost: no OCR payload carries a font. For a **born-digital** page font size and weight are
   extractable and no engine payload holds them, so keeping the payload does *not* satisfy
   0003 for that channel. The text-layer pass therefore keeps its own extractor output as its
   payload, or that half of 0003 is dropped knowingly. It is not dropped silently here.

7. **What the engine reported and what the pipeline concluded are different columns.** The
   engine's self-reported confidence is stored verbatim, is uncomparable across engines, and
   **is never shown to a reader as a number**. What governs display is `confidence_state` —
   `measured | human | unmeasured | not-applicable`, the vocabulary `citation` already uses —
   with the state as the predicate and the number inert beside it. Agreement between two
   readings is a *rule with a version*, and it is stored — in `text_agreement`, a table
   nothing owns today and which the review queue cannot find a flagged page without. It is
   not a number an engine gave itself.

8. **Nothing published until something is measured.** `document_text` joins
   `measured_target_vocab`; its `class_vocab` rows are **left empty**, so no row can claim
   `confidence_state = 'measured'` until a class is scored against operator-checked ground
   truth. Until then the text is stored and unprojected: not searched, not extracted from
   for a published edge, and the sheet says *"scanned; not yet read"* rather than showing
   text that may be wrong. This is ADR 0017 D3's discipline applied to the stage it names,
   and it is what lets the migration ship before the second unseen sample exists.

9. **The route is its own table, and an empty detection routes to a reader.** `page_route`
   is keyed `(document_sha256, page_no, method, method_version)` and holds the routed class
   with the same provenance block; it is not a `document_text` row. Three reasons, and the
   third is the one that decides it: a router returns no text, so folding it in would make
   `document_text.text` nullable and force every reader to exclude routers by method name;
   `reading_vocab` is a closed three-member set whose domain is shared by six shipped
   columns, so adding `'structure'` to it would let a `citation_resolution` claim a channel
   that reads nothing; and a route has no winner to pick, so it needs none of the ranking
   machinery `document_text` needs. **A page with no detected regions is unrouted, not
   blank**, and an unrouted page is read by the default engine — the benchmark's one unsafe
   finding, written into the store's shape rather than left to the pipeline's memory.

    **A route has no winner but it does have a live row**, which is not the same claim and
    the first draft ran them together. `method` and `method_version` are in the key, so a
    router upgrade puts a second row beside the first and decision 11 then ranks readers by a
    value that would not be single-valued. `page_route` therefore carries `superseded_by` and
    a live partial index like every other assertion here: the newest declared router's row is
    the live one, and a re-route is an insert that supersedes. And the render belongs in its
    key too, by decision 2's own argument — region detection at 150 DPI is not region
    detection at 300.

10. **The winner is chosen by rank, and a human correction does not supersede the engines.**
    Migration 0015's rule is that a review writes a `human` row which *supersedes the live
    one* — and that is forced there by an index, not by principle: `citation_live` carries no
    method, so two live rows on one key are illegal. **`document_text`'s key carries the
    method, so nothing forces it here** — and doing it anyway would take both engine readings
    non-live on exactly the pages a human touched, which are the flagged pages, which are the
    ones whose agreement evidence is worth keeping. So `superseded_by` on this table means
    one thing only: *this same reading was re-run or retracted*. Which live reading a reader
    sees is `assertion_method`'s answer.

    **But rank must be pinned for `human`, or the rule the store used to enforce is left to
    data entry.** `citation` protects it with a trigger because its live key carries no
    method; dropping supersession here drops that protection and replaces it with nothing, so
    a mis-declared registry row — or a bumped `RANK_VERSION` constant in `methods.py` — could
    rank an engine above a human correction on some route class and silently stop it being
    what a reader sees. `ocr-plan.md` states the rule independently of migration 0015 (*"a
    human correction... supersedes the engines' readings, and is never overwritten by a
    re-run"*), so it is not migration 0015's to trade away. The rebuild therefore carries
    `CHECK (NOT (target_table = 'document_text' AND method = 'human') OR precedence_rank =
    0)`, mirroring the human resolver at rank 0 that `citator.methods` already declares.

11. **`assertion_method` ranks per route class, not globally.** Its shipped rank index is
    unique on `(rank_version, target_table, precedence_rank)` — across channels — and a
    single global rank per method cannot express what the benchmark measured: dots.mocr wins
    the degraded tier, PP-OCRv6 wins graphic pages, and the tabular route is unsettled. So
    the rebuild decision 12 already pays adds `route_class` and ranks within it. The
    alternative — rank the channels only (`human` > `text-layer` > `ocr`) and let the route
    row name the engine — puts the routing policy back in code, which is what ADR 0018 D7
    spent a registry to avoid.

    **The index is `UNIQUE (rank_version, target_table, COALESCE(route_class, ''),
    precedence_rank)`, and the COALESCE is the whole point.** SQLite treats NULLs as distinct
    in a unique index, so adding a nullable column to `assertion_method_rank` would leave the
    five citation tables — where `route_class` is null — with no rank uniqueness at all, which
    is the non-determinism migration 0014 built that index to forbid. `route_class` gets a
    vocabulary table with `'unrouted'` as a member rather than a null, the rebuilt `CASE`
    requires it null for every target but `document_text`, and `citator.methods.declare`
    writes a fixed column list into this table, so it moves in the same commit.

12. **Reuse the registries, and pay for two rebuilds rather than one.**
    - **`assertion_method`**: its `target_table` is a hard `CHECK` over five citation tables
      and SQLite cannot alter a CHECK, so the table is rebuilt — reproducing its three
      partial indexes and its `CASE` check, with an explicit `WHEN 'document_text'` branch
      rather than letting it fall to the `ELSE`, and with `route_class` from decision 11.
    - **`correction`**: its CHECK lists the seven natural-keyed tables that must carry a
      slash-rendered key. `document_text` is not among them, so a correction naming it could
      carry a bare integer — the exact defect that rebuild existed to stop. It is added, in
      the same transaction, with its rendering written down beside the others.
    - **`review_action`** gains `document_text` as a **natural**-keyed target with the key
      `<sha256>/<page_no>/<method>/<method_version>/<render_profile>`. Five segments passes
      the GLOB, which requires at least four; the precedent is `decision_decided_date`, which
      renders six. `/` is forbidden in `method`, `method_version` and `render_profile` by
      CHECK, or a HuggingFace-style method id (`rednote-hilab/dots.ocr`) renders a key that
      cannot be parsed back to its columns. This also corrects `schema-draft.md` § 7, which
      specifies a page as `<sha256>/<page>` — two segments, which the shipped GLOB rejects.
      **`target_key_version` is the literal `'verbatim'`**: the column is `NOT NULL` and
      documented as the normaliser that rendered the key, and this key has no normaliser —
      every segment is copied. A declared sentinel says that; an empty string is forbidden and
      a borrowed `key_version` would be a lie.
    - **The queue is page-grained even though the key is reading-grained.** A page is flagged
      because two readings disagree; a review action names one of them; and a queue is *every
      live row that no live review action names*, so the sibling reading would be re-served
      for ever. The queue query therefore excludes a page with any live action on any of its
      readings. That is a query rule, not a schema change, and it is written here because
      otherwise it is invented later or not at all.
    - `class_measurement` holds the OCR figures when they exist, stage-scoped like every
      other figure. `reviewer` is the identity, ADR 0016 unchanged.

13. **`document_page.ocr_method` and `page_block` are withdrawn from the paper schema by
    this record**; the rest of `document_page` is kept by decision 4.

## Not decided here, and deliberately

Which engine reads which tier; whether the degraded tier renders at 200 DPI; HunyuanOCR-1.5's
licence, the only free route to the table gap, which bars the EU, UK and South Korea and
forbids using its outputs to improve any model; the weekly review budget; and whether a
trusted contributor may sit at the queue. **All five are the operator's** and all five are
recorded in `ocr-plan.md` § Decisions. The DPI choice reaches this record only as a value in
`render_profile`, which is decision 2's purpose: the operator's open questions change rows,
not columns.

## Consequences

**What becomes easy.** Two engines read the same page and disagree without either being
wrong in the store, and the disagreement stays visible after a human has ruled on it. A
re-run at a better engine, or at a better render, is an insert. A human correction has a
home, an author and a review action naming it on the day the table ships. The router's
answers are auditable against the second sample instead of being a decision already taken.
Coverage counts read, flagged and unread as a query over `document_page` and `document_text`,
with failures typed in `ocr_run` rather than looking like absence.

**What becomes hard, or costs.**

- **The store grows, and how much is ADR 0022's question, not this one's.** The rows alone
  are ~800k–1.1M across both channels, carrying ~380 B of keys, digests, methods and
  timestamps each before any text. ADR 0022 decides which of them keep their bytes in the
  replicated file — and answers "nearly all", at the price of a resize. What this record
  fixes is that the row carries the digest and the provenance either way, so that decision
  stays a file copy.
- **Full-text search over page text is a step change.** `search_doc.kind` is a hard
  `CHECK IN ('docket','party','decision','comment')` with an `INTEGER ref`, and the index is
  rebuilt
  whole whenever the record changes — which stops being viable at this scale whatever the
  engine. Page-grained search is a third rebuild plus an FTS rebuild; ADR 0022 D4 settles how
  the index is declared and leaves the rebuild open.
- **Two readings a page doubles the read** as well as the rows: the routed pipeline is 2.71 s
  a page, so agreement roughly doubles the ~187 hours the census's page count implies. Worth
  measuring before it is assumed.
- **Two shipped tables are rebuilt**, one of which the citator reads on every projection, at
  schema 17 in production.

- **Decision 2's argument does not reach `citation_reading`, and this record does not fix
  it.** That table's live index is `(key, reading_channel)` and its reading method is payload
  by ADR 0018 D3, so a re-render at a better DPI produces an `ocr` reading that *supersedes*
  the earlier one: the evidence `document_text` keeps is destroyed one join over, and which
  render produced the surviving `cited_raw` is recoverable only through the `text_id`
  pointer. Widening that key is ADR 0018's to revisit. Until it is, the pipeline's rule is
  that a re-render does not re-extract without a new method version.

**What this forecloses.** A store where one page has one text. Any pipeline that decides its
engine once, globally. And the shape where a re-run improves the record by overwriting it —
which would have made the 90-page benchmark unrepeatable against the store it fed.

## Validation

Checked against `docs/validation-queries.md` before proposing, as ADRs 0002–0008 were, and
re-checked after the schema-critic pass that produced decisions 1, 2, 4, 5, 9, 10 and 11.

- **Q1 (segment history through successors)** reads `place_mention`, derived from document
  text and absent for the pre-2005 record today. This record gives it a source with
  provenance that names the *reading* (decision 1's `text_id`), so the gate of decision 8 is
  structural rather than a coincidence of two confidence states agreeing.
- **Q2 (negative treatment)** is the citator's and joins `document_text` nowhere; the channel
  rank in `assertion_method` already works. Decision 4 is what keeps it working — one edge,
  one `citation_key` row, whichever channel read it.
- **Q3 (point-in-time docket state)** needs `asserted_at` and `superseded_at` on every
  reading, and gets both (decision 1 is append-only; the ADR 0007 block is required, not
  implied). **It is still not fully answered, and this record does not claim otherwise**:
  the winner among live rows is `assertion_method`'s, and nothing dates `rank_version` —
  the deferral migration 0014 already records. Q3 answers "which readings existed as at D",
  not "which one a reader was shown", until that is paid.
- **Q4 (trail-use lifecycle)** reads events and the registry and is unaffected **today** —
  but only because no NITU date is yet quoted from a page. The pre-2005 notices are exactly
  the image-only set, so the day one is quoted, Q4 joins through decision 1's pointer like
  Q1.
- **Q5 (service-list membership alert)** inherits Q1 exactly: a source with provenance, held
  out of the alert until measured. Decision 8 is what stops an unmeasured OCR reading of a
  service list from firing an alert — a public promise made on an unmeasured number.

## Owed at the migration

**The checklist lives in [`../ocr-migration.md`](../ocr-migration.md)** — sixteen items
across two forced table rebuilds, six vocabulary changes, three tables that have no home yet,
two passes, the infrastructure that breaks on deploy day, and schema-critic before the tables
exist. It is held there so that accepting this record means accepting thirteen decisions
rather than sixty lines of mechanics, and it becomes the migration's header comment when the
migration is written, which is where migrations 0014 and 0015 keep theirs.

Three of its items are consequences of decisions above rather than mechanics, so they are
stated where they belong: the pinned human key in decision 1, the pagination pass in decision
4, and `text_agreement` in decision 7.

## Cost of reversing

**The grain (decisions 1–5): expensive.** Not a migration — a re-read. The routed pipeline is
2.71 s a page over the **247,923 pages** the census counted, so changing what a row means
costs about **187 hours** of box time and the operator's re-checking. That is why this is an
ADR and not a schema note, and it is why the render is in the key: a column added before the
first row is free, and the same column added after the backfill is the whole backfill.

**Layout as a payload (decision 6): cheap, and chosen because it is.** The payloads are kept
and block ids are reproducible from them, so a block table can be projected at any later date
without re-reading a page. Shipping a block schema now and finding it cannot hold the next
engine's output is the expensive direction.

**The registry reuse (decisions 10–12): moderate.** Two table rebuilds, paid once whether now
or later.

**Where the bytes live: not this record's cost.** ADR 0022 carries it, and carries it
because it is cheap — the row holds the digest either way, so a tier is a copy and a
re-point.

**`superseded_at` (Q3): free to take now, a migration to add later** — which is the argument
for taking it.

---

*Proposed, not accepted. Accept only after this decision has been checked against
`../validation-queries.md`.*
