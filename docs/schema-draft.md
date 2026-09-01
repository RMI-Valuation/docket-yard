# Schema draft — the paper model

**Status: working draft, not an ADR.** This is the entity schema written to test ADRs 0002–0008
against the five queries in [`validation-queries.md`](validation-queries.md), on paper, before
any pipeline code. DDL is SQL-ish pseudocode: types are indicative, storage engine undecided.
Nothing here is a migration.

This is **revision 2**. Revision 1 was put through an adversarial review against the five
queries and the measured corpus facts; it broke in specific places, recorded in
[§ What broke](#what-broke-in-revision-1) at the bottom. The breaks are the point of the
exercise — each cost a paragraph here instead of an every-row migration later.

Layering, from raw to derived:

1. **Captures** — every response fetched from a source, verbatim.
2. **Documents** — bytes, identified by content hash, plus the layout IR.
3. **Registries** — dockets, parties, places: the stable things assertions point at.
4. **Events** — the append-only record of what happened. Source of truth.
5. **Assertions** — derived claims extracted from documents and captures. Every row carries
   provenance and a supersession pointer. Projections (current docket sheet, current service
   list, a party's display name) are computed, never truth.

---

## 1. Captures

Raw ingest artifacts. This is where the endpoint's silent-failure traps are answered: a capture
records exactly what was asked and what came back, so "the filter actually applied" is a stored,
checkable fact rather than a hope.

```sql
capture (
  capture_id        bigint PK,
  source_system     text,      -- 'stb-ajax', 'stb-service-list', 'federal-register', ...
  endpoint          text,
  request_params    json,      -- includes the search-criteria[i][name]/[value] pairs as sent
  response_sha256   bytea,     -- hash of raw response body (body itself in blob storage)
  http_status       int,
  row_count         int,
  filter_asserted   boolean NOT NULL,  -- ingest positively verified the criteria applied
  ingest_mode       text NOT NULL,     -- 'forward' | 'backfill'  (see alerting, §6)
  captured_at       timestamptz
)
```

`ingest_mode` exists because backfill waves (forced by the 10,000 display cap) insert old
filings with new event ids; without the flag, the first backfill would fire thirty years of
"new filing" alerts at every subscriber.

## 2. Documents (ADR 0002, ADR 0003)

The content hash identifies **bytes** — nothing else. Filings and decisions are different
things from documents (revision 1 conflated them; see [break B1](#what-broke-in-revision-1))
and get their own identity in §5.

```sql
document (
  document_sha256   bytea PK,  -- SHA-256 of the bytes; THE identity (ADR 0002)
  size_bytes        bigint,
  media_type        text,      -- pdf, xlsx, zip, jpg, docx all observed in the wild
  page_count        int NULL,
  first_seen_at     timestamptz
)

-- Containers: .zip attachments are measured in the wild. Members are hashed as documents in
-- their own right, with containment recorded, so an assertion extracted from a spreadsheet
-- inside a zip has a real document to anchor provenance to.
document_member (
  container_sha256  FK document,
  member_sha256     FK document,
  path_in_container text,
  PK (container_sha256, member_sha256, path_in_container)
)

-- STB filing IDs, decision IDs and URLs are attributes, never keys. An errata replacing bytes
-- under a known filing/decision ID shows up as a NEW document row: the replacement chain is
-- typed here, not buried in an event payload, because the citator needs "all versions of this
-- decision" as a join, not a convention.
document_source (
  document_sha256   FK document,
  source_system     text,
  source_url        text,
  stb_filing_id     text NULL,
  stb_decision_id   text NULL,
  supersedes_sha256 FK document NULL,  -- set by the errata detector (document_replaced event)
  capture_id        FK capture,        -- where this association was observed
  observed_at       timestamptz
)
```

Errata-detector caution (paper note, no schema impact): if a source ever *regenerates* rather
than re-serves a file, bytes change while content does not. Before announcing a
`document_replaced` event, compare extracted text, not just hashes.

Layout IR (ADR 0003) — captured at extraction time because it cannot be added later without
re-running OCR over the archive:

```sql
document_page (
  document_sha256   FK document,
  page_no           int,
  had_text_layer    boolean,
  ocr_method        text NULL,     -- null when born-digital
  rotation          int,
  PK (document_sha256, page_no)
)

page_block (
  block_id          bigint PK,
  document_sha256   FK, page_no int,
  bbox              box,           -- x0,y0,x1,y1 in page coordinates
  text              text,
  font_size         numeric NULL,
  font_weight       text NULL,
  block_confidence  numeric        -- 1.0 for text-layer extraction, OCR confidence otherwise
)
```

## 3. Registries

Registries hold **identity only**. Every mutable or judged attribute (a docket's title, a
party's display name, a place's geometry) is either projected from events or asserted with
provenance — a registry column that silently updates is where current-state thinking sneaks
back in ([break B5](#what-broke-in-revision-1)).

### Dockets (ADR 0005)

```sql
docket (
  docket_id         bigint PK,     -- surrogate; the composite below is the identity
  raw_docket        text,          -- the string as the source printed it; parsing is re-runnable
  prefix            text,
  sequence          int,
  sub_sequence      int NULL,      -- Sub-No.
  suffix            text NULL,     -- 'X', ...
  parent_docket_id  FK docket NULL,  -- FD 36873 (Sub-No. 1) -> FD 36873
  UNIQUE NULLS NOT DISTINCT (prefix, sequence, sub_sequence, suffix)
)
```

`NULLS NOT DISTINCT` is load-bearing: under default SQL semantics two `('FD', 36873, NULL,
NULL)` rows insert without error, and almost every docket has null sub-parts — a retried
ingest run would silently mint duplicate dockets and split every referencing row across them.
`raw_docket` is kept because historical docket forms may not decompose cleanly into four
parts; a parse revision is then a re-run, not a loss.

Docket *title* and other mutable attributes arrive as events (`docket_observed`) and are
projected. The dockets table is ingested first (capability sequence step 1): it is the
validation set that keeps extracted citations trustworthy.

### Parties (ADR 0004)

```sql
party (
  party_id          bigint PK      -- identity and nothing else
)

party_name (                       -- every raw surface form, with how we judged it
  party_id          FK party,
  raw_name          text,
  name_kind         text,          -- legal name, reporting mark, colloquial, display choice
  -- provenance + supersession block (§5)
)

party_relationship (               -- the succession graph, one edge per assertion
  from_party        FK party,
  to_party          FK party,
  rel_type          text,          -- FK to relationship_vocab
  effective_date    date NULL,     -- quoted from a source, never computed
  -- provenance + supersession block (§5)
)

relationship_vocab (
  rel_type          text PK,       -- succeeded_by | merged_into | renamed_to | parent_of | ...
  reading           text           -- plain-English direction, e.g. 'from = earlier entity,
)                                  --   to = later entity' — the convention is DATA, not lore
```

**Edge direction is declared, not assumed** ([break Q1a](#what-broke-in-revision-1)): all
temporal-succession edges (`succeeded_by`, `merged_into`, `renamed_to`) are stored **earlier
entity → later entity**; `parent_of` is stored parent → subsidiary. Revision 1 mixed
orientations and its own flagship query traversed half the edges backwards, silently.

A party's display name is a projection over `party_name` rows (latest non-superseded row with
`name_kind = 'display choice'`, falling back to most-recent legal name). Canonicalisation is a
judgement; judgements get provenance.

**Merges are assertions, not updates.** When resolution later concludes party 42 and party 97
are the same entity, that is a new edge (`rel_type = 'same_as'` in the vocabulary), and
queries traverse it — no `UPDATE` ever rewrites a provenance-bearing row's `party_id`
([break A2](#what-broke-in-revision-1)). This is what makes ADR 0004's "resolution can improve
forever without schema change" actually true.

### Places (ADR 0008)

```sql
place (
  place_id          bigint PK,
  place_type        text,          -- city_state | county | station | rail_line | segment | point
  name              text,          -- founding label; refinements are place_name assertions
  parent_place_id   FK place NULL  -- station -> line, city -> county, ...
)

place_geometry (                   -- georeferencing is a derived assertion, so it lives here,
  place_id          FK place,      -- versioned, not as a silently-updated registry column
  geometry          geometry,
  -- provenance + supersession block (§5)
)
```

## 4. Events (ADR 0006) — the source of truth

One append-only ledger. Two timestamps on every row, because "when did the source say this
happened" and "when did we learn it" are different questions and both get asked:

```sql
event (
  event_id          bigint PK,
  event_type        text,          -- FK to event_vocab
  docket_id         FK docket NULL,
  document_sha256   FK document NULL,
  occurred_at       date NULL,     -- the date the source itself states; quoted, never computed
  recorded_at       timestamptz NOT NULL,  -- when ingest observed it
  capture_id        FK capture NULL,  -- null ONLY for human-entered correction events
  supersedes_event_id FK event NULL, -- corrections point at what they supersede, as a column
  payload           json,          -- type-specific detail
  payload_version   int NOT NULL   -- parsers change shape; readers dispatch on this
)

-- A correction that amends a derived assertion (not an event) names its target in a typed
-- row, never in free JSON — otherwise correction propagation is prose, not a join:
correction_target (
  event_id          FK event,      -- the correction event
  target_table      text,          -- 'citation', 'instrument_event', ...
  target_pk         bigint,
  PK (event_id, target_table, target_pk)
)
```

**Date-bound rule, stated once:** `occurred_at` is nullable (sources omit dates). Every
date-bounded query uses `COALESCE(occurred_at, recorded_at::date)` — an undated event surfaces
at its ingest date rather than silently vanishing from every date-filtered result.

Initial event vocabulary (a table, extensible by INSERT):

| event_type | meaning |
| --- | --- |
| `docket_observed` | docket row seen in the dockets table (title, attributes in payload) |
| `filing_observed` | a filing row appeared in the filings table |
| `decision_observed` | a decision row appeared in the decisions table |
| `enviro_comment_observed` | environmental comment row appeared |
| `document_replaced` | new bytes under a known filing/decision ID (errata detection, ADR 0002) |
| `service_list_observed` | a service-list snapshot was taken for a docket |
| `correction` | we corrected our own data; supersedes via the columns above, never overwrites |

Current state — the docket sheet a visitor sees — is a projection over this ledger,
rebuildable from scratch.

## 5. Assertions (ADR 0007) — derived claims

Every table in this section carries the same block, present from row one because retrofitting
it means discarding and regenerating everything:

```sql
-- PROVENANCE + SUPERSESSION COLUMNS, on every assertion table:
  assertion_id            bigint PK,
  asserted_from_document  FK document NULL,   -- exactly one of these two is set...
  asserted_from_capture   FK capture NULL,    -- ...except method='human', where both may be null
  source_location         json,      -- {page, block_id, bbox} for documents; {row} for captures
  method                  text,      -- 'regex-docket-cite', 'human', 'model:<name>', ...
  method_version          text,
  asserted_at             timestamptz,
  confidence              numeric,
  superseded_by           FK <same table> NULL   -- retirement is a pointer, never a DELETE
```

**Re-extraction discipline** ([break A3](#what-broke-in-revision-1)): every assertion table
declares a **natural key** (noted per table below). A higher-`method_version` pass writes new
rows and sets `superseded_by` on the rows it replaces; every projection and every query reads
`WHERE superseded_by IS NULL`. Without this, the first improved extraction pass silently
doubles every citation count and every NITU in the corpus. `method = 'human'` rows are never
superseded by a model pass — amending one requires a `correction` event via
`correction_target`.

### Filings and decisions (the record rows)

STB's tables publish *filings* and *decisions* — rows with zero, one, or several attachments.
Revision 1 gave them no identity and hung party facts directly on document bytes; measured
facts broke that twice (no-attachment filings lost their parties; byte-identical boilerplate
filed in different proceedings cross-contaminated them). The record rows are entities:

```sql
filing (                           -- natural key: (docket_id, stb_filing_id)
  filing_id         bigint PK,
  docket_id         FK docket,
  stb_filing_id     text,          -- attribute of the filing; documents attach to it
  filing_type       text NULL,
  observed_in_event FK event,      -- the filing_observed event that established it
  -- provenance + supersession block
)

filing_document (                  -- zero..n attachments per filing, PDFs preferred as primary
  filing_id         FK filing,
  document_sha256   FK document,
  is_primary        boolean
)

decision_record (                  -- natural key: (docket_id, decision_number)
  decision_id       bigint PK,
  docket_id         FK docket,
  decision_number   text NULL,     -- 'Decision No. 30'
  service_date      date NULL,     -- quoted from the source
  document_sha256   FK document NULL,
  observed_in_event FK event,
  -- provenance + supersession block
)
```

"All versions of Decision No. 30" is now a join: `decision_record` rows plus the
`document_source.supersedes_sha256` chain — not a convention every consumer reinvents.

### Environmental comments (F1's third record row)

The Board publishes three tables per proceeding; the sheet held two. Found 2026-08-31 on
AB 55 (Sub-No. 794X) — 70 records held, 6 environmental comments unheld — and measured the
same day, twice: the endpoint's mechanics, then the rows themselves once the natural key
turned out to depend on them (`stb-data-source.md` § Environmental comments). Structurally
this is a third row of the kind `filing` and `decision_record` already are: a record row
carrying zero-or-more attachments, established by an event. It reuses that shape — with one
deliberate departure, in the key.

```sql
enviro_comment (                    -- natural key: (docket_id, comment_number)
  comment_pk            bigint PK,
  docket_id             FK docket,
  comment_number        text NOT NULL,  -- 'EI-34280', 'EO-3243': printed in the row AND the
                                        -- data-stb-id of its own detail link. The only
                                        -- identity the source corroborates (see below)
  stb_row_ref           text NULL,      -- the 203738 of FD_36873|203738|830758 — kept as a
                                        -- corroborating attribute, never as the key
  date_received_or_sent date NULL,      -- the Board heads this column "Date Received or
                                        -- Sent" and declines to say which; so do we
  submitter_raw         text NULL,      -- as printed (on an EO row, a document title)
  organisation_raw      text NULL,      -- as printed
  location_raw          text NULL,      -- 'Laramie, WY', kept whole and unparsed
  comment_text_printed  text NULL,      -- the commenter's own words; absent on half the rows
  observed_in_event     FK event
)

enviro_comment_attachment (         -- the same shape as filing_/decision_attachment
  comment_pk        FK enviro_comment,
  source_url        text,
  label             text NULL,
  document_sha256   FK document NULL,   -- null until fetched
  UNIQUE (comment_pk, source_url)
)
```

**The record is published as the Board publishes it, and no name is masked** (decided
2026-08-31, after a masking design was drafted and dropped). A commenter filed on a public
docket at a federal agency; that is the public record, and republishing it is what this
project is for. ADR 0011's posture is about the site's **readers** — whose attention we
decline to collect — not about the people who choose to file. So the page, the JSON and the
CC0 snapshot all carry the comment whole: its words, its submitter, its organisation and its
location, exactly as printed.

The design that was dropped, recorded so it is not re-proposed from scratch: a mask over the
submitter column, showing initials while the store kept the name as the Board prints it. It
fails on its own terms, and the measurement is why. The submitter's own name is inside the
comment's own words in **5 of the 76** comments measured for 2026 — `EI-34282` signs off
*"Erin Collins President, Chesterton Town Council"*, and carries no attachment, so that cell
is the only machine-readable copy there is. The name is also inside the attachment the Board
serves, and it will be inside the extracted text when the OCR milestone lands. Masking one
column while three other paths print the name is not a privacy measure but the appearance of
one — and the appearance is worse than nothing, because a reader takes it for a promise.

Consequences to hold to: **nothing published may imply that a name here can be held back**,
and the schema carries no `masked_at` column, no CHECK, no trigger and no redaction pass in
`store/dump.py`. Reinstating any of it is a new migration and a new decision, not the filling
of a gap left open.

**The key departs from filings and decisions because the source forces it.** Both of those key
on the endpoint's own record id, and `observations.py` refuses any row whose printed id cell
disagrees with the middle part of `data-stb-id` — the check that stops a column reorder
mis-filing a record. **No cell of a comment row prints that middle part.** Keying on it would
weld an uncorroborated number into an append-only ledger through `source_key`, where re-keying
is not an `UPDATE` but tens of thousands of fresh events and a ledger of orphans. What the row
does print is the comment number, which is also the `data-stb-id` of its own detail link — so
the key is `(docket_id, comment_number)`, corroborated two ways (the cell text against that
attribute, and the printed docket against the id's first part), with the middle part kept
beside it as `stb_row_ref`. Measured over 150 rows of 2026: never blank, never colliding with
a different middle part, never repeated across dockets. **A row with no comment number is
quarantined and counted, never stored under a synthesised key** — the discipline a dropped row
already gets.

**One comment spans several rows, one per attachment**, exactly as filings do (FD 36854's
`EI-34249` occupies four). The parser folds by (docket, record) and takes the attachment set as
the union of this capture and what the record already holds — reused, not re-derived.

**Every mirrored column must appear in the event payload.** In `observations.py` the payload is
the *only* change detector (`latest_payload_by_key`), and `_upsert_record` writes columns *only*
when the payload changed. So a column mirrored onto the record but missing from the payload is
write-once current state: no history, no change detection, and Q3 quietly wrong for it. The rule
is that every value of `record_columns` resolves through the payload keys, and it is pinned by a
test across every spec — which retro-covers filings and decisions too.

**Two columns are derivations, not quotes, and say so.** `date_received_or_sent` is
`printed_date_to_iso` applied to the cell, with the printed form surviving in
`payload["date_printed"]` as it does for filings; its name matches the Board's own column head,
which declines to say whether the date is a receipt or a sending, so the schema declines too.
`comment_text_printed` is the cell after `markup.clean`, which strips tags and collapses
whitespace — a multi-paragraph comment loses its paragraphing. For the one column whose purpose
is a member of the public's own words, that is worth naming rather than glossing: its provenance
is the capture body at its `payload_version`, and the authoritative text is the attachment. It is
measured **not** truncated (longest 1,549 characters, ending on a complete signature), so it is
the whole comment as far as the table gives it — but the cleaned whole, not the printed whole.

**Everything else is quoted, so the table carries no provenance block.** Like `filing` and
`decision_record`, the remaining columns are cells as the source printed them, and their
provenance is `observed_in_event → capture`. The provenance block belongs to derived claims, and
this milestone derives none.

**No position column — here or anywhere.** A comment states a position in the commenter's own
words. Storing those words verbatim is quotation; a column naming what the position *is* would be
inference, which the record forbids. A stance classification, if ever chosen, is a separate
assertion table with ADR 0007 provenance and a `method` — never a column here, exactly as
`document_party` carries none. The same rule disposes of the `EI`/`EO` split the measurement
found (42 submitted comments to 8 of the Board's own environmental documents on FD 36873, the
latter printing a document title where a submitter belongs): the prefix is *inside*
`comment_number` and needs no column, and typing the row is a derived claim for whoever wants it.

**Location: raw only** (decided 2026-08-31). ADR 0008 requires structured rows so that
georeferencing never costs a re-read of the corpus. That cost does not arise on this column: the
string arrives inside the table row and is stored whole, so parsing it later is a pass over
stored strings — no fetch, no document opened. The `place` registry and `place_mention` therefore
wait for the geography milestone (C3/D2). Two conditions this puts on what follows. First,
`location_raw` is stored **uncut and unparsed**, because it is that pass's whole input — and it
needs to be, since the format varies (`Laramie, WY` and `Towson, Maryland` both occur, so the
state is not reliably a code and splitting it is a judgement, not a split). Second,
**`place_mention` as drafted cannot receive it**: its natural key is
`(document_sha256, source_location, raw_text)`, and a comment's location has no document — it is
printed in a cell, and half these rows carry no attachment at all. That is break B1 recurring a
milestone downstream. The geography milestone must anchor a mention on *exactly one of* a
document or a capture-plus-record, the shape ADR 0007's block already has; cheap to settle now,
while `place_mention` is still paper. **This is a narrowing of ADR 0008's categorical text living
in a working draft, recorded as the operator's decision of 2026-08-31 — not as a draft's own
reading of an accepted record.**

**Submitter: raw text only** (decided 2026-08-31). `submitter_raw` and `organisation_raw` are
stored and shown as the Board prints them, and nothing here mints a `party`. ADR 0015 makes a
party id a permanent public address, never reused or withdrawn, and a milestone whose job is to
capture rows does not open that door for a private individual who commented once. There is a
second, structural reason the decision is right: `party.founding_key` is `NOT NULL UNIQUE`, one
party per normalised span, so two different people who share a name would be silently minted as
one — a false assertion about people, made with no evidence, in a store whose whole discipline is
that resolution is a judgement carrying provenance. Linkage stays available as an **addition**: a
`comment_party_span` / `comment_party_link` pair copying the party module's shape (migration 0006
— copying, not reusing, since `filing_party_span.filing_pk` is `NOT NULL REFERENCES filing`),
resolved against the raw text this table keeps.

**Citations come from the attachment, never from the cell.** `citation` keys on
`citing_document` — bytes. A comment's attachment is a document and is already expressible; the
printed cell is not, and mining edges from it would mean a citation with no citing document.

**Instruments group by document, not by event.** An earlier draft of this section claimed a NITU
lifecycle could later take a comment event into its group with no schema change. That is false as
drafted: `instrument_event`'s natural key is `(instrument_id, kind, document_sha256)`, so a
comment with no attachment — half of them — cannot enter one. Recorded as a cost, not patched
here; widening it belongs to the trail-use milestone.

### Party involvement

```sql
document_party (                   -- natural key: (filing_id, party_raw, role)
  filing_id         FK filing,     -- anchored to the FILING, not the bytes (break B1)
  party_id          FK party NULL, -- null until resolved; resolution is its own re-runnable pass
  raw_text          text NOT NULL, -- the original cell, uncut, always kept
  role              text,          -- filed_for | filed_by | on_behalf_of | served_on
  -- provenance + supersession block
)
```

Multi-party "Filed For" cells (91 of 605 measured) split into one row each at ingest, all
sharing the same `raw_text`. `party_id` is nullable for the same reason it is on
`place_mention` and `service_list_member`: linkage is a judgement that improves; the raw text
is the fact. **No position column exists on this table or any other.** A party's position, if
ever modelled, is an assertion extracted from the document's own words with its own provenance
— never inferred from who filed.

### Citations (ADR 0018) — five assertion families over one natural key

**Revised 2026-09-01 to the shape ADR 0018 accepts.** What stood here before — one `citation`
row carrying `cited_raw`, both resolved FKs and a `treatment` column under a single confidence
and a single provenance block — is superseded in full. Six schema-critic passes found the same
defect in different clothes each time: a value that must be superseded sitting inside a key,
two values sharing one confidence, or a live row nobody could order against another. The
shipping decision and its measured figures are
[ADR 0017](adr/0017-citation-edges-ship-at-measured-confidence.md); the shape is
[ADR 0018](adr/0018-the-citation-assertion-families.md); the argument behind each table is in
[`citator-schema.md`](citator-schema.md).

**One natural key, with no method in it:** `(citing_document, page, target_kind, target_key)`,
carried as **typed columns** on every family — the draft's idiom everywhere else — and rendered
canonically as `<sha256>/<page>/<target_kind>/<target_key>` where a single text key is wanted
(`review_action.target_key`, and `correction.target_key`, which migration 0014 widened from
an integer to text for exactly this — the paper `correction_target` of § 4 is in no migration).
It is **never digested**: the normalisation
has already changed once — the scorer's docket-suffix fix moved the docket-shaped truth from 220
targets to 225 on 2026-08-30 — and under a digest that class of change rewrites every key and
strands every human row. `key_version` makes it a migration somebody can see instead.

The key is stable across a text-layer and an OCR reading of the same bytes, which differ in the
quoted passage (10.8% CER measured) and would otherwise double every edge on re-read.

```sql
citation_key (          -- THE KEY, and nothing else. A key is not an assertion.
  citing_document   FK document,   -- bytes; the fold to the work happens at projection
  page              int,
  target_kind       text,          -- FK target_kind_vocab: 'stb' | 'court' | ...
  target_key        text,          -- the NORMALISED target, never the string as printed
  key_version       text NOT NULL, -- the normaliser that produced target_key
  PK (citing_document, page, target_kind, target_key)
)

citation (              -- the EXTRACTION assertion, keyed on the row above
  <the natural key>,
  -- provenance + supersession block, MINUS source_location: `page` in the key IS the
  -- location. A deliberate departure from § 5's uniform block; do not restore the column
)
```

**The key is a table because the assertion about it must be able to supersede** *(settled at
migration 0014, on the schema-critic's report)*. Every child foreign-keys the four typed
columns, and SQLite will only accept a **non-partial** UNIQUE as a foreign key's parent — so
holding the key on `citation` itself would have forced a full UNIQUE there, and that forbids
three supersessions the accepted records require: a re-extraction at a higher `method_version`
(ADR 0017: "a better extractor supersedes rather than rewrites"), an ownership handover to a
new method, and a retraction with **no successor** — a docket-shaped string that is no
citation at all, which `0009_party_ids_permanent.sql` retires with a `superseded_by` pointing
at its own row. `decision_work` exists for the identical reason one table over.

**Identity only.** `cited_raw` is not here — the string as printed differs between readings, so
on a row keyed stably across them whichever channel inserted first would own it for ever. It
belongs beside the quoted passage it came from, in `citation_reading`. Neither resolved FK is
here, and neither is `treatment`: those are assertions, measured at different rates, by
different methods, at different times.

`target_kind` is in the key, so a misclassification **cannot** be corrected by supersession — a
corrected row would mint a *different* key. It is a **retraction and a fresh assertion**: the new
row is written and the mis-keyed row's `superseded_by` points at it. For that to change anything,
**every projection must join `citation` and require it live**. The resolutions and judgements
anchored on the retracted key still read `superseded_by IS NULL`; a projection reading only those
tables would publish the mis-kinded edge regardless. The join is what makes a retraction bite.

Because the key has no method in it, **one method owns each `(target_kind, target_form)`** — two
extractors emitting the same target on the same page would collide, one row dropped or the edge
counted twice. Ownership is declared on `assertion_method` and fixed at insert time from the
owning method's own declaration, never from a later judgement row. A finding outside its method's
class is counted on `extraction_run`, so "not kept" is an auditable number and not a silent drop.

```sql
citation_reading (      -- + reading_channel. One row per reading of the page.
  <the natural key>,
  reading_channel   text,          -- FK reading_vocab: 'text-layer' | 'ocr' | 'human'
  reading_method    text NULL,     -- the OCR engine, and its version, OUTSIDE the key —
  reading_method_version text NULL,-- else a re-OCR mints a row that supersedes nothing and
                                   -- doubles the live readings (1,480 of 9,663 image-only)
  cited_raw         text NOT NULL, -- the string as THIS reading printed it
  quoted_passage    text NOT NULL, -- what the span test reads
  source_location   json,          -- § 5's block: {page, block_id, bbox}
  -- provenance + supersession block  (OCR text is derived; it supersedes)
)

citation_resolution (   -- + (method, method_version, reading_channel)
  <the natural key>,                -- the channel is in the key, or one rule run over two
  method, method_version,           -- readings of a page collides on the whole key
  reading_channel   text,
  outcome           text NOT NULL, -- FK outcome_vocab: resolved | unresolved | repaired |
                                   -- vetoed. A null docket id otherwise means three things
  cited_docket_id   FK docket NULL,          -- the COMPLETE outcome rides on ONE row: the
  cited_decision_id FK decision_work NULL,   -- family test reads the docket and Q2 keys on
                                             -- the decision, both of the SAME resolution
  -- provenance + supersession block, with confidence NOT NULL + confidence_state
)

citation_judgement (    -- + (judgement, method, method_version, reading_channel)
  <the natural key>,
  judgement         text,          -- FK judgement_vocab: 'kind' | 'target_form' |
                                   -- 'span_names_document'
  method, method_version, reading_channel,
  value             text NOT NULL, -- PAYLOAD, never key. Its domain is judgement_vocab's,
                                   -- or one column holds a boolean and two enumerations
                                   -- untyped — the EAV shape citator-schema.md § B rejects
  -- provenance + supersession block, with confidence NOT NULL + confidence_state
)

citation_treatment (    -- + (method, method_version, reading_channel)
  <the natural key>,               -- what the citing decision DID to the target. Not a
  method, method_version,          -- resolution row: sharing one would force a typing pass
  reading_channel,                 -- to restate the resolution or write NULLs into outcome
  treatment         text NOT NULL, -- FK treatment_vocab
  -- provenance + supersession block, with confidence NOT NULL + confidence_state
)

treatment_vocab (
  treatment         text PK,       -- cites | follows | distinguishes | narrows | overrules |
  polarity          text NOT NULL  -- supersedes | ...
)                                  -- polarity: positive | neutral | negative
```

`kind` and `span_names_document` are measured at different rates (88.1%, and the span test is
what the 98.0% projected precision was measured with), which is why one confidence column on a
parent could never have carried them. A review writes a `human` row in whichever family it
corrects — including `citation_treatment`, or the one column Q2 reads would have no correction
path.

**The registries the families are ordered and scored by:**

```sql
assertion_method (      -- APPEND-ONLY. The single ordering registry for all five families.
  target_table      text NOT NULL, -- 'citation' | 'citation_resolution' | ...
  method, method_version,
  reading_channel   text NULL,     -- NULL exactly on a target_table='citation' ownership row:
                                   -- citation's own key has no channel, so ownership of a
                                   -- class cannot be per-channel either
  role              text NULL,     -- 'suppress' | 'resolve'; NULL on an ownership row, which
  precedence_rank   int NULL,      -- declares WHO MAY WRITE, not who wins — a rank there
                                   -- would be a fake ordering inside the registry that orders
  target_kind       text NULL,     -- the (target_kind, target_form) this method OWNS: the
  target_form       text NULL,     -- one-owner rule of ADR 0018 D1, given a table
  score_row_id      FK class_measurement NULL,  -- REQUIRED when role='suppress': a veto row
                                   -- exists only once its false-veto rate is measured
  rank_version      text NOT NULL  -- a re-rank is a new version, never an UPDATE of rows
)

class_measurement (     -- APPEND-ONLY. The single home for every score, ADR 0018 D8.
  measurement_id    bigint PK,     -- so the pointer from an assertion row is one column
  measured_target   text NOT NULL, -- WHICH STAGE was measured; also scopes `class`'s vocabulary
  class             text NOT NULL, -- FK (measured_target, class) → class_vocab
  extraction_method, extraction_method_version,
  resolution_method text NULL,     -- NULL for a stage that runs before resolution, which is
  resolution_method_version text NULL,  -- why the unique index COALESCEs over these
  reading_channel   text NOT NULL, -- every figure so far is text-layer; OCR is unmeasured
  projection_rule_version text NULL,    -- the span test's version, the family closure's, and
                                        -- rank_version, together — the projection is that
                                        -- product. NULL for a pre-projection stage
  benchmark_date    text NOT NULL, -- re-measuring the same version is an INSERT, not an
  score_file        text NOT NULL, -- UPDATE on a published number
  recall, precision, false_veto_rate    -- the veto carries a RATE, not a confidence
)

extraction_run (        -- one row per (document, method, method_version, reading_channel)
  ...,                  -- a typed outcome AND the out-of-class counts. Nothing else
)                       -- distinguishes READ AND FOUND NOTHING from NOT YET READ.
                        -- Absence is not a measurement.

decision_work (         -- stb_decision_id text PK, AND NOTHING ELSE — attributes here would
)                       -- be current state entering a registry by the back door. Written
                        -- only by ingest from decision_observed; the resolver may reference
                        -- it and never insert. Measured before proposing the PK, because it
                        -- is a one-way door: 1,736 ids carry several decision_record rows
                        -- and NOT ONE of them disagrees.
```

Confidence is `NOT NULL` on every assertion row with a typed `confidence_state`
(`measured | human | unmeasured | not-applicable`) and
`CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL))`. A human review has a
confidence; what it lacks is a *benchmark*. Because unmeasured rows carry `0`, these tables
cannot reuse `0006_parties.sql`'s `CHECK (confidence > 0)` idiom, and **`confidence` is never
selected without `confidence_state`** — the projection is the only supported path to it.

**The projection formula, stated per family, because they do not share one.** For the resolution
family: *if any live `suppress` row exists **for the same reading channel**, no edge; else the
highest-ranked live `resolve` row whose `outcome IN ('resolved','repaired')`.* A flat rank made
every rule-2 repair unreachable, because rule 1 writes a row when it fails and outranks the repair
that exists because it failed. **Treatment and judgement have no `outcome` to restrict on: theirs
is the highest-ranked live row and nothing else.** The predicate
`confidence_state IN ('measured','human')` goes on the **candidate set**, never on the rank-1 row
— there it *deletes* edges, when an unmeasured OCR resolution outranks a measured text-layer one
and takes rank 1.

That term is not the whole projection. **An edge projects only when the resolution term holds AND
one of two family terms does:** the target docket is outside the citing work's family — the
docket, its sub-dockets and its parent, unioned over every docket a consolidated decision is
entered in — **or**, if it is inside, a live `span_names_document` judgement says `true`,
defaulting to **suppress** where nothing has judged it (ADR 0017 D4). Reading the resolution term
alone publishes every own-proceeding mention. The comparison is in migration 0016's § The
figures, with the run that produced it.
(ADR 0018 D7 states this comparison as "88.4%", which is near enough that the difference is
the run rather than the rule. Both figures moved that day when a defect in the scorer's
registry was fixed — it dropped the suffix from 2,711 held dockets, so every finding naming
one scored as unresolvable; migration 0014's header carries the restatement.) The family
closure is **registry data, not application code**; `web/cite.py` computes the same closure for
the lookup page, and the projection may not depend on that being kept in step by hand.

**Projection folds by work** (ADR 0018 D9): "cited by" and every count are distinct
`(citing work, target_kind, cited_docket_id | cited_decision_id)` triples, with the citing work
being `decision_attachment` → `decision_record.stb_decision_id`, falling back to
`COALESCE(stb_decision_id, citing_document)` so an edge mined from a filing folds to itself rather
than being dropped by an inner join. The target half is **typed** because
`decision_record.decision_number` is populated for 0 of 23,713 rows — docket-level edges are the
normal case, and an untyped count would silently mix two grains.

**The decided date is extracted in the same pass**, because doing it later costs a ~$1,335
re-extraction. It is an assertion — `decision_decided_date`, keyed
`(document_sha256, date_kind, ordinal, reading_channel, method, method_version)` with
`printed_text NOT NULL`, since dates are quoted and never computed — and **never a
`decision_record` column** (that table mirrors the latest observation and would destroy the
history) and **never a ledger event** (a decided date is a second clock; a replay would show a
decision existing before it was served).

Unresolved targets are kept, never discarded: the WB25-53 false-positive trap means resolution
*must* validate against the dockets registry, and a failed validation is stored `unresolved` and
projected never — which is what makes "cites `EP 445` (not in the record)" a display that can be
produced, and a review queue that is not empty by construction. Citations to authorities outside
STB (federal courts, USC/CFR) are `target_kind` values whose resolver does not exist yet;
`citation_reading.cited_raw` preserves them. Door left ajar on purpose.

### Place mentions

```sql
place_mention (                    -- natural key: (document_sha256, source_location, raw_text)
  document_sha256   FK document,
  raw_text          text,
  mention_type      text,          -- city_state | county | station | milepost_range | line_name
  place_id          FK place NULL, -- null until resolved; resolution is re-runnable
  line_place_id     FK place NULL, -- for milepost ranges: which line
  milepost_from     numeric NULL,
  milepost_to       numeric NULL,
  -- provenance + supersession block
)
```

Rows exist even when resolution is null (ADR 0008): the map is a rendering problem later, not
an extraction problem later.

### Service lists

```sql
service_list_member (              -- natural key: (observed_in_event, raw_text)
  docket_id         FK docket,
  party_id          FK party NULL, -- null until resolved; raw_text always kept
  raw_text          text NOT NULL,
  observed_in_event FK event,      -- the service_list_observed snapshot this came from
  -- provenance + supersession block
)
```

Membership over time = the sequence of snapshots. Current membership = **members of the
latest snapshot per docket** — not "latest row per party", which would keep removed parties
on the list forever ([break C1](#what-broke-in-revision-1)).

### Instruments (lifecycle grouping)

Query 4 needs "this notice and its whole history" as a unit. An instrument is a derived
grouping — it adds no new grain, it names a thread through the record:

```sql
instrument (                       -- natural key: (docket_id, instrument_type, established_by)
  instrument_id     bigint PK,
  docket_id         FK docket,
  instrument_type   text,          -- NITU | ITU | CITU | ... (controlled vocabulary)
  established_by    FK document,
  UNIQUE (docket_id, instrument_type, established_by),
  -- provenance + supersession block
)

instrument_event (                 -- natural key: (instrument_id, kind, document_sha256)
  instrument_id     FK instrument,
  kind              text,          -- issued | extended | expired | vacated | converted
  effective_date    date,          -- quoted from the document's own words, never computed
  document_sha256   FK document,   -- the document that says so
  -- provenance + supersession block
)
```

## 6. Subscriptions and alerting (the wedge)

```sql
subscription (
  subscription_id   bigint PK,
  subscriber        text,          -- delivery address / account ref
  channel           text,          -- email first; rss, webhook after
  predicate_type    text,          -- docket | party | service_list_party | query | citation
  docket_id         FK docket NULL,
  party_id          FK party NULL,
  query_def         json NULL,
  status            text NOT NULL, -- active | cancelled   (unsubscribing must exist on day one)
  created_at        timestamptz,
  cancelled_at      timestamptz NULL
)

alert_delivery (
  delivery_id       bigint PK,
  subscription_id   FK subscription,
  event_id          FK event,      -- alerts fire off the event ledger, nothing else
  attempt           int NOT NULL,
  status            text,          -- pending | sent | failed
  delivered_at      timestamptz NULL,
  UNIQUE (subscription_id, event_id, attempt)
)
```

**Backfill does not alert.** The alert join takes only events whose capture has
`ingest_mode = 'forward'` — otherwise the first backfill wave (tens of thousands of old
filings with new event ids) crosses every subscriber's high-water mark at once
([break B6](#what-broke-in-revision-1)).

Silent-failure detection (`docs/alerts.md`, stub): because every alert joins a subscription to
an event and every event to a capture, "no alerts since date X" decomposes into "no captures"
(ingest broke) vs "captures but no events" (parser broke) vs "events but no deliveries"
(delivery broke) — each independently monitorable.


## 7. Review (ADR 0016) — SHIPPED at migration 0015, 2026-09-01

Drafted 2026-08-30 and revised the same day on the schema-critic's report; built as drafted.
`src/docketyard/store/0015_review.sql` is what runs, and where it and this section disagree
the migration governs.

A human review is a derived assertion and must carry *who*; reading stays anonymous
(ADR 0011) and addresses stay ciphertext (ADR 0014). Two tables: a registry and an
append-only action log. The first consumers are ADR 0017's queues.

**A QUEUE IS A QUERY, and nothing stores queue items.** `docketyard.citator.review` computes
each one: every live row matching its kind that no live `human` answer already clears. A
stored queue would be a second source of truth kept in step with a registry that MOVES —
waves 2—3 are still adding dockets, so a target that could not resolve last week resolves
this week and leaves the queue on its own. A derived queue notices; a table would hold
yesterday's answer and nobody would know it had.

**The exposure test became a stored judgement, and the projection gained a gate.** Migration
0015 adds `exposed` to `judgement_vocab` (its domain is `boolean`, whose members 0014 already
seeded, so it adds a question and not a type). ADR 0017 D2 says the exposed class "goes to
review; everything else ships unreviewed" — and until 0015 there was no queue, so it shipped
unreviewed too: an `AB 124` with a footnote `2` fused on, resolving confidently to `AB 1242`,
a real but different proceeding, indistinguishable on the page from a clean edge. The
projection now holds such an edge until a live `human` resolution exists for it, which is
§ 7's own mechanism and not a second one: the projection still reads `superseded_by IS NULL`
with no knowledge that a review happened.

That gate reads the `exposed` judgement WITHOUT the `confidence_state IN ('measured','human')`
predicate every other family carries. It suppresses, and a suppressor filtered out of the
candidate set is silently inert — ADR 0018 D7's own argument about the on-page veto, one
table over. The judgement itself is `not-applicable`: it is not a claim about correctness but
a mechanical property of the printed form, and ADR 0017 measures how OFTEN it fires (3 of 225,
3 of 249 emitted), which is a rate and not a precision.

**The figures live in ONE place and are re-derivable**: migration 0016's header carries the
restated table, and `tools/rmi-ai-machine/citation_dryrun.py` regenerates the run it was
measured on. On the sixty decisions the rule projects 206 of 225 and a reader sees 203 until
the three edges the exposure test names have been answered. Quote that header, or better,
run the tool — a figure with no `class_measurement` row behind it is one nobody has
checked.

```sql
reviewer (                         -- a REGISTRY (identity only), not an assertion table
  reviewer_id       bigint PK,     -- permanent, never reused or renumbered (provenance
                                   -- rows point here forever; ADR 0015's discipline)
  email_hash        text NOT NULL UNIQUE,  -- the account key the subscription system uses
  email_enc         bytea NOT NULL,-- ciphertext at rest under the operator-held key (0014);
                                   -- the key-rotation pass MUST cover this table too
  credit_name       text NOT NULL, -- mandatory: there is no anonymous review (ADR 0016)
  counts_public     boolean NOT NULL DEFAULT false,  -- ADR 0016's opt-in, as a column
  granted_at        timestamptz NOT NULL,
  granted_note      text NOT NULL, -- the operator's reason, in words
  revoked_at        timestamptz NULL  -- withdrawal ends new actions; past rows stand
)
-- `credit_name`, `counts_public` and `revoked_at` are OPERATIONAL columns, not provenance:
-- they may change (a re-grant clears revoked_at; a rename is a rename). Append-only
-- applies to review_action, never to this registry. The cost accepted with eyes open:
-- a page archived before a rename showed the old credit name and the store does not
-- reconstruct what was shown — the same current-state debt as a party's display name.

reviewer_token (                   -- magic-link sign-in, ADR 0011's machinery, its own
  token_hash        text PK,       -- table: subscription_token cascades on unsubscribe,
  reviewer_id       FK reviewer,   -- and a reviewer must not lose sign-in by unsubscribing
  expires_at        timestamptz NOT NULL
)

review_action (                    -- APPEND-ONLY: one decision per queue item
  action_id         bigint PK,
  reviewer_id       FK reviewer NOT NULL,
  queue             text NOT NULL, -- FK review_queue_vocab: 'ocr_page' | 'citation_edge' |
                                   -- 'correction' | 'reader_report' — extensible by INSERT
  target_table      text NOT NULL, -- what was reviewed: a typed pair, a join, never prose
  target_key        text NOT NULL, -- the target row's key rendered canonically — a bigint
                                   -- pk as digits, a page as '<sha256>/<page>'; bigint
                                   -- alone cannot name sha256-keyed rows (schema-critic)
  method_version    text NOT NULL, -- the queue's convention version: what evidence was
                                   -- shown and under which rules the decision was made
  decision          text NOT NULL, -- FK review_decision_vocab: accepted | rejected |
                                   -- corrected | escalated
  detail            json,          -- what was decided, typed per queue
  produced_table    text NULL,     -- the human assertion row this action wrote (below);
  produced_key      text NULL,     -- THE authoritative link, written in the same
                                   -- transaction that wrote the row it names
  asserted_at       timestamptz NOT NULL,
  superseded_by     FK review_action NULL  -- a later review supersedes, never overwrites
)
-- UNIQUE (queue, target_table, target_key) WHERE superseded_by IS NULL — "one decision
-- per queue item" as a constraint, not prose; index on reviewer_id for the opt-in counts.
```

**Every decision on a queue whose target has an assertion table writes a `human` row**
(ADR 0017 decision 5 — decision 6 pre-split; schema-critic caught the first draft saying otherwise): an
acceptance writes a human resolution agreeing with the model's; a rejection writes a
human *does-not-resolve* resolution; a correction writes the corrected one. In each case
the new row supersedes the live one and the projection keeps reading `superseded_by IS
NULL` with no knowledge of reviews. Only `escalated` — and queues with no assertion
effect — produce nothing, and the nulls say so. The assertion is inserted first, then the
action naming it, in one transaction; the produced row's ADR 0007 block is `method =
'human'`, its `source_location` keeps ADR 0007's meaning (*where in the source*), and
"who reviewed this?" is the typed join `review_action WHERE produced_table = … AND
produced_key = … AND superseded_by IS NULL` → `reviewer.credit_name`. There is no
backward pointer to disagree with the forward one.

**A human amends a human through the queue.** ADR 0016's "a later review supersedes"
means: the superseding action writes its own human row and, in the same transaction, sets
`superseded_by` on the prior action *and* on the prior action's produced row. § 5's rule
is refined, not broken: a `human` row is never superseded by a **model** pass; a **review
action** (or the operator's `correction` event, outside any queue) is what may supersede
it.

**Attribution of pre-table `human` rows is a rule, not a pass — the operator's decision,
2026-09-01, and a narrowing of ADR 0016 recorded here rather than left implicit.** 0016 says
those rows "**are re-attributed** to the operator's reviewer id when the table exists"; the
table exists as of migration 0015 and nothing was rewritten. Doing it literally would be an
UPDATE on provenance, which is break A2, and a synthetic review action would falsify what
happened — so the rule below stands in its place, the way ADR 0008's narrowing was recorded
on 2026-08-31. The party seed, the joins and the corrections carry `source_location` like
`{"file": "parties/seed.py"}` and no review action. They are not rewritten — an UPDATE on provenance is break A2, and a
synthetic action would falsify what happened. The rule, recorded here once: **a `human`
assertion no live review action names is the operator's** (the operator is the first
`reviewer` row, ADR 0016's "reviewer zero"). "Who says so" for those rows answers through
this rule; their provenance JSON is untouched and their `asserted_at` stays true.

**Queues the store cannot hold, named rather than implied** (schema-critic): a **reader
report** needs a row to queue on — a small `reader_report` table (report text, the page's
typed target, received_at; no identity) is the `/contribute` landing the ocr-plan
promises, and `target_table = 'reader_report'` queues it. **Benchmark labels are not a
store queue**: `labels.csv` is a repo file with no stable row identity; its review is the
git history (the operator's 2026-08-30 check *was* such a review, recorded in
`research/benchmark/README.md` and a commit). The first draft's `benchmark_label` queue
kind is withdrawn. An **OCR page** queues on the planned `document_text` row via the
composite key form above.

**What is never stored** (ADR 0011): nothing about what a reviewer reads; no action row is
written by rendering a queue page; publishing per-reviewer counts requires
`counts_public`. Sign-in tokens are hashed, single-use, and enumerate nothing.

---

## The five queries, on paper

All query sketches assume the standing filters, spelled once: assertions read
`superseded_by IS NULL`; date bounds use `COALESCE(occurred_at, recorded_at::date)`.

### Q1 — Segment history through successor railroads

> Every proceeding touching this line segment since 1996, traversing corporate successors.

```sql
WITH lineage AS (                         -- walk succession BACKWARDS: all edges are old->new,
  SELECT party_id FROM party WHERE party_id = :railroad      -- so predecessors are from_party
  UNION
  SELECT pr.from_party
  FROM party_relationship pr JOIN lineage l ON pr.to_party = l.party_id
  WHERE pr.rel_type IN ('succeeded_by','merged_into','renamed_to','same_as')
    AND pr.superseded_by IS NULL
),
segment_docs AS (                         -- documents mentioning the segment
  SELECT DISTINCT pm.document_sha256
  FROM place_mention pm
  LEFT JOIN place_geometry pg ON pg.place_id = COALESCE(pm.place_id, pm.line_place_id)
                             AND pg.superseded_by IS NULL
  WHERE pm.superseded_by IS NULL
    AND ( ST_Intersects(pg.geometry, :segment_geometry)
       OR (pm.line_place_id = :line AND pm.milepost_from <= :mp_hi
                                    AND pm.milepost_to   >= :mp_lo) )
)
SELECT DISTINCT dk.raw_docket
FROM filing f
JOIN docket dk          ON dk.docket_id = f.docket_id
JOIN filing_document fd ON fd.filing_id = f.filing_id
JOIN segment_docs sd    ON sd.document_sha256 = fd.document_sha256
JOIN document_party dp  ON dp.filing_id = f.filing_id AND dp.superseded_by IS NULL
JOIN event e            ON e.event_id = f.observed_in_event
WHERE f.superseded_by IS NULL
  AND dp.party_id IN (SELECT party_id FROM lineage)
  AND COALESCE(e.occurred_at, e.recorded_at::date) >= '1996-01-01';
```

**Verdict: expressible** — after revision. Revision 1 broke here twice: the succession CTE
traversed `successor_of` edges backwards (fixed by declaring direction in the vocabulary and
normalising succession edges old→new), and `document_party` anchored on bytes lost every
no-attachment filing and cross-contaminated hash-folded boilerplate (fixed by the filing
entity). Remaining honest weakness: answer *quality* depends on place-mention extraction
coverage; the schema expresses the query from day one, the corpus fills in later.

### Q2 — Negative treatment

> What has narrowed, distinguished, or superseded this decision?

**The SQL is on disk, not inline here** — [`citator-query-2.sql`](citator-query-2.sql), written
in full against ADR 0018's five families so that "Q2 is writable against this shape" is a claim
anyone can run rather than one three documents assert about each other. Keeping a sketch here as
well would be two spellings of one query, and the sketch is the one that would rot.

**Verdict: expressible.** The query joins `citation` (live, or a retraction changes nothing),
`citation_reading` (the passage and the raw string, per channel), `citation_resolution` (keyed on
`cited_decision_id`), `citation_judgement` (the span test), `citation_treatment` and
`treatment_vocab` for the negative polarity, plus `assertion_method` for the ordering and the
`decision_attachment` → `decision_record` fold to the work.

Three things it settles that the pre-0018 sketch here could not. It keyed on a single document
hash, which returns half the edges the day an erratum splits a decision across two hashes — the
exact scenario ADR 0002 exists to detect; the work fold answers it. It read one `treatment` column
on the `citation` row, which cannot carry a typing pass and a resolution under one confidence.
And it stopped at `superseded_by IS NULL`, which is not the projection: several resolutions are
live per edge, so a "cited by" count that does not pick one is inflated.

**And it returns nothing on the day the first edges ship**, for two reasons and not one.
ADR 0017 D7 gives the first: every edge in the first slice is `cites`, treatment typing is a
later pass, and this query filters on a negative polarity. The second is the grain — it keys on
`cited_decision_id`, the **work**, and ADR 0018 D9 measures how rare that is:
`decision_record.decision_number` is populated for 0 of 23,713 rows, so docket-level edges are
the normal case and D4's verb gate keeps every `decided <date>` phrase at docket level. So this
query stays thin even after the treatment pass runs, and the docket-grain variant is the one a
reader's "cited by" list is actually built from.
That is stated rather than left for a reader to discover — what ships is "what cites this", at
the projected recall and precision in migration 0016's § The figures, which is the wedge and
is worth shipping. New
treatment types remain vocabulary INSERTs; typing untyped edges remains a higher-`method_version`
pass over kept rows — no re-ingest, no migration.

### Q3 — Point-in-time docket state

> What did this docket look like on 18 August 2026, the day before Decision No. 30?

```sql
WITH family AS (                          -- the docket and its sub-dockets
  SELECT docket_id FROM docket WHERE docket_id = :docket
  UNION
  SELECT d.docket_id FROM docket d JOIN family f ON d.parent_docket_id = f.docket_id
)
SELECT e.*
FROM event e
LEFT JOIN event c ON c.supersedes_event_id = e.event_id      -- corrections joinable, not prose
WHERE e.docket_id IN (SELECT docket_id FROM family)
  AND COALESCE(e.occurred_at, e.recorded_at::date) <= '2026-08-18'
ORDER BY COALESCE(e.occurred_at, e.recorded_at::date), e.event_id;
```

The query's own premise — "the day before Decision No. 30" — resolves through
`decision_record (docket_id, decision_number)`, a typed assertion, not a JSON payload dig.

**Verdict: expressible.** The ledger replays to any date; two timestamps answer both readings
(`occurred_at`: what the record said had happened by then; `recorded_at`: what *we* knew by
then — the honest answer for dates before our ingest began). Revision 1's gaps — corrections
unjoinable, decision numbers only in JSON, sub-dockets omitted — are closed by
`supersedes_event_id` / `correction_target`, `decision_record`, and the family CTE.

### Q4 — Trail-use notice lifecycle

> Every interim trail use notice with its full extension and expiration history.

```sql
SELECT i.instrument_id, dk.raw_docket,
       ie.kind, ie.effective_date, ie.document_sha256,
       ie.method, ie.confidence
FROM instrument i
JOIN docket dk ON dk.docket_id = i.docket_id
JOIN instrument_event ie ON ie.instrument_id = i.instrument_id
WHERE i.instrument_type IN ('NITU','ITU','CITU')
  AND i.superseded_by IS NULL
  AND ie.superseded_by IS NULL
ORDER BY i.instrument_id, ie.effective_date;
```

**Verdict: expressible** — after revision. Revision 1 had no natural keys and no supersession,
so the first improved re-extraction pass would have silently doubled every NITU. Natural keys
plus `superseded_by IS NULL` make re-extraction convergent. Every date is quoted from a named
document with provenance — what makes the output usable where these dates are dispositive
(takings litigation). Multiple notices in one docket are simply multiple instruments.

### Q5 — Service-list membership alert

> Alert me to anything filed in any proceeding where a given railroad appears on the service list.

```sql
WITH latest_snapshot AS (                 -- latest service_list_observed event PER DOCKET
  SELECT DISTINCT ON (e.docket_id) e.docket_id, e.event_id
  FROM event e
  WHERE e.event_type = 'service_list_observed'
  ORDER BY e.docket_id, e.recorded_at DESC
),
current_lists AS (                        -- membership = members of that snapshot, nothing else
  SELECT ls.docket_id, slm.party_id
  FROM latest_snapshot ls
  JOIN service_list_member slm ON slm.observed_in_event = ls.event_id
  WHERE slm.superseded_by IS NULL AND slm.party_id IS NOT NULL
)
SELECT s.subscription_id, e.event_id
FROM subscription s
JOIN current_lists cl ON cl.party_id = s.party_id
JOIN event e   ON e.docket_id = cl.docket_id
JOIN capture c ON c.capture_id = e.capture_id
WHERE s.predicate_type = 'service_list_party' AND s.status = 'active'
  AND e.event_type IN ('filing_observed','decision_observed')
  AND c.ingest_mode = 'forward'           -- backfill never alerts
  AND e.event_id > :last_processed_event;
```

**Verdict: expressible** — and revision 1's projection was wrong on paper: "latest row per
party" keeps removed parties on the list forever, alerting subscribers on dockets the railroad
exited. Membership is defined by the latest *snapshot*, which the snapshot-event design
expresses directly. Unresolved members (`party_id IS NULL`) cannot match a party subscription
— acceptable only because resolution is re-runnable and the coverage page must say so.

---

### The five queries against the environmental-comment rows (2026-08-31)

Checked before any code, per `../CLAUDE.md`, then re-checked after the schema-critic's report
and the row-level measurement it forced. The rows are a third record table, so the exposure is
the same one filings and decisions had: the ledger and the identity, not the columns.

- **Q1 — segment history.** Answerable exactly as before; comments neither help nor hinder it
  today. What could foreclose the geography milestone is not the raw-only decision — a stored
  string re-parses for free — but `place_mention`'s document-keyed natural key, which cannot
  hold a location printed in a cell. Noted in the section above as that milestone's to fix
  while it is still paper.
- **Q2 — negative treatment.** Untouched. Comments produce no citation edges, and the rule
  above ("from the attachment, never from the cell") keeps `citation.citing_document` honest;
  the alternative would have been an edge with no citing document, which the key forbids.
  Migration 0011 also closes the cost this section first recorded: `document_source` gains
  `comment_source_key`, so a citation mined from a comment's attachment traces back to the
  comment record and not merely to bytes and a URL. It holds the docket-qualified spelling,
  not the bare number — its two siblings hold ids unique across the whole source, and a
  comment number is identity only within a docket.
- **Q3 — point-in-time docket state.** The query this design has to satisfy, and it does,
  because
  the comment is an event before it is a row: `enviro_comment_observed` — the type § 4's
  vocabulary already reserved — with `occurred_at` from the date cell, `recorded_at` at ingest,
  and `source_key = <canonical docket>|<comment number>`. The sheet as of 18 August 2026 replays
  with its comments through the same ledger, on the existing `event_dedup` index. **The near
  miss**: the ledger carries only what the payload carries, so a mirrored column left out of the
  payload would have been invisible current state — correct today, unreplayable and
  change-blind forever. Stated as a rule and pinned by a test, above.
  The masking design that was dropped would have cost this query a divergence — a flag with
  no event of its own, so the live store and the snapshot would replay two different
  histories. Dropping it removes that cost rather than accepting it: every column on the
  row is a quoted observation carried by an event, and one replay answers for both copies.
- **Q4 — trail-use lifecycle.** Untouched. An earlier draft of this section claimed comments
  could later join a NITU's instrument group with no schema change; that was wrong —
  `instrument_event` groups by `document_sha256`, and half these rows have no document. The
  claim is withdrawn and the cost recorded where it belongs.
- **Q5 — service-list membership alert.** The alert path is untouched today:
  `alerts/build.py` selects on an explicit `ALERTING_EVENT_TYPES` allowlist, so
  `enviro_comment_observed` alerts nobody until it is named there, and both alert joins filter
  `capture.ingest_mode = 'forward'`. Break B6 proper is closed for the backfill wave provided
  **the wave's captures are labelled `backfill` before it starts**, not after it finishes. Two
  things the allowlist does *not* cover, both recorded here rather than discovered later:
  1. **`document_replaced` is itself an alerting type**, emitted by `capture/documents.py` for
     whatever is in `SPECS`. The day a comments spec joins that dict, an erratum on a comment
     PDF alerts every subscriber to that docket — and `alerts/summary.py` resolves the owner
     through `document_source`'s two id columns, both null for a comment, so the mail would
     read "a record it holds (not identified)" with no link.
  2. **Widening the allowlist is itself a wave.** `build()` advances a subscription's mark to
     the newest event it actually carried, not to the ledger head, so a subscriber on a quiet
     docket still holds an old mark. Adding a new alerting type therefore delivers every event
     of that type above that mark at once — forward-labelled, so `ingest_mode` does not stop it.
     **The rule, recorded beside the allowlist: a new alerting type is added together with a
     mark advance to the ledger head for active subscriptions, or with a floor date.**

**Consumers that assume the record is two tables.** An earlier draft named two; there are at
least eight, and each is widened deliberately by the milestone that wants it rather than
silently here:

| Consumer | What breaks if it is not widened |
| --- | --- |
| `store/dump.py` `PUBLIC_TABLES` | The CC0 snapshot refuses to build (`Unsafe`) the day the migration lands — a failsafe working as designed, and a decision to take deliberately |
| `capture/documents.py` | `_held_sha` unions two attachment tables, and the two spec ternaries write null into both `document_source` id columns for any third spec |
| `ingest/observations.py` | `_HELD_URLS` / `held_url_count`: comment attachments never enter the errata re-check, so ADR 0002's chain does not exist for them — **and the published re-check cycle is computed from that count** |
| `store/coverage.py` | Published coverage counts held and unheld attachments over two tables, so it would understate both |
| `alerts/summary.py` | Reads an event type as "decision, or else filing" |
| `store/0010_search.sql` | ~~`search_doc.kind` is a closed `CHECK`~~ — widened by migration 0012; comments are indexed by their words, submitter, organisation and location |
| `web/sitemaps.py` (ADR 0013) | ~~no permanent address~~ — `/d/<docket>/comment/<number>`, the store's own key spelled out, because the archive wave found two numbers naming two different comments |
| The heartbeat | `last_event` is an unscoped `MAX(recorded_at) FROM event`, so a third table writing to the ledger **masks a filings/decisions parser outage** on that canary. Scope it by event type when the third table starts writing |

## What broke in revision 1

An adversarial review (2026-08-25) attacked revision 1 with the five queries and the measured
corpus facts. Verdicts before repair: Q1 **broke**, Q2–Q4 expressible at a cost, Q5's supplied
projection wrong. What changed, so the reasoning is not lost:

| # | Break | Fix in revision 2 |
| --- | --- | --- |
| B1 | Filings had no identity; party facts hung on document bytes. No-attachment filings (measured) lost their parties entirely; byte-identical boilerplate cross-contaminated dockets | `filing` / `filing_document` / `decision_record`; `document_party` anchors on the filing |
| Q1a | Succession edges had no declared direction; the flagship query traversed half of them backwards, silently | Direction is data (`relationship_vocab.reading`); succession edges normalised old→new |
| A1 | `UNIQUE` over nullable docket parts enforces nothing under default SQL semantics; retried ingest mints duplicate dockets | `NULLS NOT DISTINCT`; `raw_docket` kept for re-parsing |
| A2 | Party merges required `UPDATE` across every provenance-bearing row, falsifying provenance and breaking ADR 0004's "resolution improves forever" promise | `party_id` nullable-until-resolved everywhere; merges are `same_as` edges traversed by queries |
| A3 | Re-extraction at higher method_version doubled every assertion; nothing retired old rows | Natural key per assertion table + `superseded_by` pointer + standing `IS NULL` filter |
| A4 | Event payloads had no schema version; a parser change would poison every replay forever | `payload_version`, readers dispatch on it |
| B2 | No work-level identity for a decision across errata; citator keyed on single hashes | `decision_record` + typed `supersedes_sha256` chain |
| B3 | "Corrections supersede, never overwrite" was prose — no joinable pointer to the corrected event or assertion | `supersedes_event_id` + `correction_target` |
| B5 | `party.canonical_name`, `place.geometry` were derived values hiding in registries with no provenance — current-state thinking returning through the side door | Registries hold identity only; names and geometry are assertion rows |
| B6 | First backfill wave would alert every subscriber on thirty years of old filings | `capture.ingest_mode`; backfill never alerts |
| C1–C6 | Wrong Q5 projection; undefined `polarity`; nullable `occurred_at` silently dropping rows; corrections needing captures; no unsubscribe/retry; zip members unanchored | All fixed above, each where it lives |

## Revision notes as code met the paper (M1–M2, 2026-08-25)

- **`decision_record` keys on the table's own decision id**, not `decision_number`. The
  dockets/decisions tables print a system id (`53210`); "Decision No. 30" is printed inside
  the document and arrives by extraction. `decision_number` stays as a nullable attribute so
  query 3's lookup path exists; the identity is what the source can actually corroborate.
- **`raw_docket` on a parent minted from a sub-docket** is synthesised (`FD_36873_0`) until
  the parent is directly observed, at which point it is corrected; the minting is recorded
  as a `docket_inferred` event carrying the implying record. Same for dockets first seen on
  a filing or decision row.
- **Filings/decisions record rows mirror the latest observation** (type, dates, filed-for
  raw) and point at the event that last shaped them; history stays in the ledger.
- **`filed_for_raw` is stored uncut** on the filing; the party split (ADR 0004) is the party
  module's pass over that raw, and the captures hold the original markup should separators
  ever matter.

## Revision notes as code met the paper (M4, 2026-08-26)

Migration `0004_subscriptions.sql` hardens § 6 under ADR 0011 and the decided delivery
promise (`alerts.md`):

- **`subscription` is (email, docket) with a cadence**, `pass` or `daily`, and a status
  `pending → active`. **There is no cancelled state: unsubscribing deletes the row** and
  everything cascading from it. The schema-critic's review made the case — a retained
  cancelled row is exactly the attention data ADR 0011 forbids, and RFC 8058 needs an
  idempotent answer to an unknown token, not a persistent row. The docket is the family's
  parent, as the sheet folds its sub-dockets; it is nullable with a partial unique index so
  query 5's party / service-list predicates can be added as columns without a rebuild.
- **No backfill is a column, not a convention**: `high_water_event_id`, set to the
  ledger's head in the confirmation transaction, is the floor every alert join applies;
  a `CHECK` refuses an active row without one. The join also filters
  `capture.ingest_mode = 'forward'` and an event-type allowlist — the mark alone would not
  stop a backfill wave ingested *after* confirmation, nor alert on a caption change.
- **Tokens are stored as SHA-256 only** (`subscription_token`), expiring for confirm,
  never-expiring for unsubscribe.
- **`alert` is one email to one address**; `alert_event` records which events it carried
  for which subscription, with `UNIQUE (subscription_id, event_id)` as the at-most-once
  claim. A daily digest across three dockets is one row, so a retry is an attempt on the
  message that actually went out.
- **Lateness is derived, then annotated**: the heartbeat runs off-box and cannot write the
  store, so the alert builder derives an event's lateness from the spacing of the forward
  captures around it, and `alert_event.late_gap_id` points at the operator's
  `coverage_gap` row when one exists. The coverage page lists those rows.
- **`email_suppression`** is consulted by every send from day one, before any bounce path
  feeds it.

## Revision notes as code met the paper (M5, 2026-08-26)

Migration `0005_encrypted_addresses.sql` replaces every `email` column with `email_hash`
(HMAC-SHA256 under the vault key; what uniqueness, suppression and rate limits match on)
and `email_enc` (Fernet ciphertext; what the sender decrypts). `email_suppression` keeps
only the hash. The tables were rebuilt, not altered, and their two test rows dropped —
the one migration in the set that does not carry every row forward, recorded in its
header. The key is held outside the store (`alerts/vault.py`).

## What this draft deliberately does not model

Deadlines and procedural tracks (C4), outcome coding (M5), cross-agency joins (F6) beyond the
`source_system` field on captures, recordations (M4), reference-data time series (D3), and
resolution of citations to non-STB authorities. Each fits as new assertion tables (or new
columns beside preserved raw text) against the same registries and ledger — additions, not
migrations. That is the test they will have to pass when their turn comes.
