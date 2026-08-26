# The party module (M6) — design

> **Status: built 2026-08-26 (migration 0006, `parties/`), shipping in v2026.08.14.** Implements
> ADR 0004 over the record the wedge holds. Schema-critic and code review applied; the split
> rules cut 91% of the two-year record's cells at full confidence and leave the rest whole.
> Party subscriptions are the remaining M6 piece.

## What the record shows today

Measured on the production store, 2026-08-26 (3,614 filings, 1,391 distinct "Filed For"
cells, two years of history):

- The top cells are single railroads spelled consistently: `CSX Transportation, Inc.` (180),
  `Union Pacific Railroad Company` (166), `BNSF Railway Company` (163). The same railroad also
  appears as `CSX Transportation` (16), `CPKC` (19) beside `Canadian Pacific Kansas City
  Limited` (90) and `Canadian Pacific Railway Company dba CPKC` (27).
- **The Board is a filer** (`Surface Transportation Board`, 135): its own notices and orders
  appear in the filings table. It is a party like any other for these purposes; the type
  label never looks at it (methodology page).
- **Lists** take three shapes: `A and B` where B is A's subsidiary (`Norfolk Southern
  Corporation and Norfolk Southern Railway Company`, 66); `A, B` between unrelated parties
  (`Union Pacific Corporation and Union Pacific Railroad Company, Norfolk Southern Corporation
  and Norfolk Southern Railway Company`, 27 — two pairs joined by a comma); and `A, on behalf
  of B…` (`Grand Trunk Corporation, on behalf of itself and its U.S. rail operating
  subsidiaries`, 27+65). The comma is both a list separator and part of a name (`Kansas &
  Oklahoma Railroad, LLC`, `Canadian Pacific Kansas City, Limited`).
- **Repeats**: `Ohio Rail Development Commission, Ohio Rail Development Commission` — the
  Board's cell repeating one party (the sheet already folds these for display).
- **Individuals and firms**: `James Riffin`, `Mullins Law Group PLLC` — a law firm filing in
  its own name, not its client's.
- `d/b/a` and `dba` mark trade names: `Ethanol Products, LLC d/b/a POET Biofuels`.

So the splitting judgement ADR 0004 warned about is real, and it is a judgement: a comma is
ambiguous, "and" joins both subsidiaries and co-filers, and "on behalf of" names a
relationship, not a second filer.

## Schema (the § 3 and § 5 draft, hardened; revised after schema-critic review)

The critic's first finding reshaped this: **splitting and resolving are two assertions
with two provenances and must be two rows**, or "party_id is null until resolved" and
"nothing ever rewrites a party_id" cannot both hold. So a cell becomes spans, and a span
may acquire a link — each supersedable on its own.

```sql
party (party_id PK, founding_key TEXT UNIQUE NOT NULL, created_at)
  -- founding_key: the normalised span the party was minted from; deterministic, so a
  -- rebuild from captures mints the same parties in the same order (see addresses)

party_name (name_id PK, party_id FK, raw_name, norm_name, name_kind,   -- as_filed | legal |
  provenance…, superseded_by)                                          -- mark | trade | display
  -- natural key (party_id, norm_name, name_kind), partial UNIQUE WHERE superseded_by IS NULL

relationship_vocab (rel_type PK, reading, symmetric INTEGER NOT NULL CHECK (symmetric IN (0,1)))
  -- succeeded_by, merged_into, renamed_to (earlier → later, 0); parent_of (parent → sub, 0);
  -- same_as (1). Symmetry is DATA: every traversal unions both directions where symmetric = 1
party_relationship (edge_id PK, from_party, to_party, rel_type FK, effective_date NULL,
  provenance…, superseded_by)
  -- natural key (from_party, to_party, rel_type, COALESCE(effective_date, ''))

filing_party_span (span_id PK, filing_pk FK, raw_text NOT NULL,    -- the WHOLE cell, uncut
  ordinal, span_start, span_end, span_text,                        -- location in the cell
  role CHECK (role IN ('filed_for', 'on_behalf_of')),
  provenance…, superseded_by)
  -- natural key (filing_pk, raw_text, ordinal); a span whose raw_text no longer equals the
  -- filing's current filed_for_raw is superseded by the next split pass (the mirror column
  -- is overwritten on re-observation; the span remembers the cell it cut)

filing_party_link (link_id PK, span_id FK NOT NULL, party_id FK NOT NULL,
  provenance…, superseded_by)
  -- natural key (span_id) among live rows; "unresolved" = no live link, never a NULL

correction (correction_id PK, target_table, target_id, note, provenance…)
  -- the amendment path for human rows (ADR 0007's rule that a model pass never supersedes
  -- a human assertion needs somewhere for the human to say "this one was wrong")
```

`provenance…` is ADR 0007's full block on every assertion table: `asserted_from_capture`,
`source_location`, `method`, `method_version`, `asserted_at`, `confidence`. Partial
indexes on `(filing_pk) WHERE superseded_by IS NULL` and `(party_id) WHERE superseded_by
IS NULL` keep the sheet's queries cheap.

**`party_component`** is one recursive view — a party and everything reachable over live
`same_as` edges in both directions — and the display name, the Parties block, the party
page and the alert join all read it. It is pinned by a test the way `docket_current` is.
The representative of a component is its smallest live `party_id`; the display name is the
representative's latest live `display` row, else its latest `legal`, else its `as_filed`.

Two passes, each re-runnable, each superseding by pointer:

1. **Split** (`split-rules`, v1) cuts a cell into spans. Rules, in order: fold an exact
   repeat; cut on `, on behalf of ` into a `filed_for` span and an `on_behalf_of` span;
   cut on ` and ` only when both sides end in a corporate suffix or match a known name;
   cut on `, ` only when the right side does not start with a suffix token (`LLC`, `Inc.`,
   `Limited`, `L.P.`, …). What the rules cannot cut stays one span at confidence below 1 —
   never silently wrong, never discarded. The fold and the sheet's `display_filed_for`
   become one function.
2. **Resolve** (`resolve-exact`, v1) links a span to a party whose live `party_name` has the
   same `norm_name` (case, punctuation, `Inc`/`Incorporated`, `Co`/`Company`,
   `RR`/`Railroad`; `d/b/a` yields a `trade` alias). **Ambiguous** — the norm matches names
   on two components — makes no link (nondeterminism is worse than a gap). **Minting** a
   new party happens only from a `filed_for` span at split confidence 1: its founding name
   is `as_filed`, not `legal` — the matcher has made no judgement about legal names — and
   the party's confidence inherits from the span. An uncut `A and B` or an `on_behalf_of`
   fragment therefore never becomes a party.

The **seed list** is a versioned file in `src/docketyard/parties/seed.py` (not `data/`,
which is disposable), loaded with `method = 'human'`, `method_version` = the file's version,
`source_location = {file, row}`. `effective_date` on a succession is set only when quoted
from a Board decision the row cites; otherwise null with a note. The operator reviews the
file before it ships; its git history is the audit trail.

## What the sheet shows

A **Parties** block in the rail: the entities on record in this docket, with how many
filings each, from `filing_party` joined through the family. Names are the party's display
name; the raw cell is always one click away on the entry. Nothing about position, side, or
stance (CLAUDE.md rules; interface.md's Parties-view row).

A **filter** on the sheet ("only entries filed for …") and a **browse view**
(`/parties?name=…`) listing the dockets a party appears in with its aliases, successors and
each link's provenance — a convenience, not an address (see the decision below).

## Subscriptions by party

`subscription.party_id` (added nullable; a CHECK that exactly one predicate is set means a
table rebuild, done in the same migration) alerts on any filing whose live link resolves
into the subscribed party's **component** — so a `same_as` edge discovered later widens the
subscription rather than splitting it, and one address subscribed to both halves of a pair
receives an event once (the alert_event uniqueness is per subscription; the digest folds).
Resolve runs before the alert builder in the same pass, so a span that has no link yet is
simply not alerted until it has one; the high-water floor means a late edge never alerts
history. Query 5's *service-list* predicate is **not** in M6: the
Board's search exposes no service-list table, so membership would have to come from
documents (certificates of service) — extraction, and a measurement of the source first.
The coverage page says which predicates exist.

## What is deliberately not in M6

Position or stance extraction (never inferred; a later, document-based method with its own
methodology page); service lists (above); reporting-mark data from external sources beyond
the operator's seed; any UI that ranks parties.

## Decided by the operator (2026-08-26)

1. ~~Party page address is `/p/{id}`~~ — superseded the same day: parties are a facet,
   not an address (the last section).
2. **The Board is shown in the Parties block, labelled as the agency**, and is never
   treated as a litigant in any later work.
3. **The seed list covers Class I carriers and holding companies with marks and recent
   successions, plus Amtrak, the commuter agencies and the major short-line holding
   companies** — on the order of sixty rows, entered with `method = 'operator'` and
   reviewed by the operator before they ship; the list is data in the repository, so its
   history is the audit trail.

## Decided (operator, 2026-08-26): parties are a facet, not an address

The permanence promise (ADR 0013) covers what the Board itself identifies — dockets,
filings, decisions — and the calendar weeks, which are dates. **Parties get no permanent
address.** A party is a way of reading the record: a Parties block on the sheet, a filter
over a sheet's entries, a browse list, a subscription predicate. A party view reachable by
query (`/parties?name=…`) is a convenience the site never offers as a citation and never
promises to keep; ids are internal and may be re-minted on a rebuild; a `same_as` merge is
a better answer to the same query. ADR 0013 records the boundary so it is never assumed.
