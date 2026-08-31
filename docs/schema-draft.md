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

### Citations (typed edges)

```sql
citation (                         -- natural key: (citing_document, cited_raw, source_location)
  citing_document   FK document,
  cited_raw         text,          -- the string as it appeared, always kept
  cited_docket_id   FK docket NULL,     -- resolved & validated against the dockets registry
  cited_decision_id FK decision_record NULL,  -- resolved to the decision, not one hash of it
  treatment         text,          -- FK to treatment_vocab; defaults to untyped 'cites'
  -- provenance + supersession block
)

treatment_vocab (
  treatment         text PK,       -- cites | follows | distinguishes | narrows | overrules |
  polarity          text           -- supersedes | ...
)                                  -- polarity: positive | neutral | negative
```

Unresolved citations keep `cited_raw` with null FKs — the WB25-53 false-positive trap means
resolution *must* validate against the dockets registry, and a failed validation is stored as
unresolved, not discarded. Treatment typing is a later, higher-`method_version` pass over the
same rows. Citations to authorities outside STB (federal courts, USC/CFR) are not yet
resolvable — `cited_raw` preserves them, and an external-authority target column is a later
*addition*, not a migration. Door left ajar on purpose.

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


## 7. Review (ADR 0016) — drafted 2026-08-30; revised the same day on schema-critic's report

A human review is a derived assertion and must carry *who*; reading stays anonymous
(ADR 0011) and addresses stay ciphertext (ADR 0014). Two tables: a registry and an
append-only action log. The first consumers are ADR 0017's queues.

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
(ADR 0017 decision 6 — schema-critic caught the first draft saying otherwise): an
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

**Attribution of pre-table `human` rows is a rule, not a pass.** The party seed, the
joins and the corrections carry `source_location` like `{"file": "parties/seed.py"}` and
no review action. They are not rewritten — an UPDATE on provenance is break A2, and a
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

```sql
SELECT c.treatment, c.citing_document, c.confidence,
       c.method, c.method_version, c.source_location    -- provenance rides along per edge
FROM citation c
JOIN treatment_vocab tv ON tv.treatment = c.treatment
WHERE c.cited_decision_id = :decision_id      -- the decision, not one hash of one version
  AND tv.polarity = 'negative'
  AND c.superseded_by IS NULL;
```

**Verdict: expressible** — after revision. Revision 1 keyed the query on a single document
hash, which returns half the edges the day an erratum splits the decision across two hashes —
the exact scenario ADR 0002 exists to detect. `decision_record` gives the citator a
work-level target; `document_source.supersedes_sha256` keeps the version chain typed. New
treatment types are vocabulary INSERTs; typing untyped `cites` edges is a
higher-`method_version` pass over kept rows — no re-ingest, no migration.

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
