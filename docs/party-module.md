# The party module (M6) — design

> **Status: draft for review, 2026-08-26.** Implements ADR 0004 over the record the wedge
> already holds. Schema-critic review and operator sign-off precede any migration; the
> resolution method is versioned from day one (ADR 0007).

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

## Schema (the § 3 and § 5 draft, hardened)

```sql
party (party_id INTEGER PRIMARY KEY, created_at TEXT NOT NULL)

party_name (                       -- every surface form, with the judgement that linked it
  party_id, raw_name, name_kind,   -- legal | mark | colloquial | trade | display
  method, method_version, confidence, asserted_at, superseded_by
)

party_relationship (from_party, to_party, rel_type, effective_date, provenance…)
relationship_vocab (rel_type PK, reading)   -- succeeded_by, merged_into, renamed_to,
                                            -- parent_of, same_as, on_behalf_of

filing_party (                     -- one row per party named in a cell; the split
  filing_pk, ordinal, raw_text,    -- raw_text = the WHOLE cell, always; ordinal = position
  span_text,                       -- the piece this row is about, as cut
  party_id NULL,                   -- null until resolved
  role,                            -- filed_for | on_behalf_of
  method, method_version, confidence, asserted_at, superseded_by
)
```

Two passes, each re-runnable and each leaving its predecessor's rows in place under
supersession (ADR 0007):

1. **Split** (`split-rules`, v1): cut a cell into spans. Rules, in order: fold an exact
   repeat; cut on `, on behalf of ` into a `filed_for` span and an `on_behalf_of` span;
   cut on ` and ` only when both sides end in a corporate suffix or a known name; cut on
   `, ` only when the right side does not start with a suffix token (`LLC`, `Inc.`,
   `Limited`, `L.P.`, …). Everything the rules cannot cut stays one span with confidence
   below 1 — never silently wrong, never discarded.
2. **Resolve** (`resolve-exact`, v1): a span matches a `party_name` row by normalised form
   (case, punctuation, `Inc`/`Incorporated`, `Co`/`Company`, `RR`/`Railroad`, `d/b/a`
   split into a trade-name alias). No match creates a new party with the span as its
   legal name at confidence 1 — *the span is the fact*; the resolution that it equals an
   existing party is the judgement. Later, better methods add `same_as` edges; nothing
   rewrites a `party_id`.

A **seed list** of the Class I carriers and their holding companies, marks and recent
successions (CP + KCS → CPKC, 2023) is hand-entered with `method = 'operator'` — the
succession graph starts from what the operator knows, with provenance saying so.

## What the sheet shows

A **Parties** block in the rail: the entities on record in this docket, with how many
filings each, from `filing_party` joined through the family. Names are the party's display
name; the raw cell is always one click away on the entry. Nothing about position, side, or
stance (CLAUDE.md rules; interface.md's Parties-view row).

A **party page** at a permanent address — proposed `/p/{party_id}` — listing the dockets a
party appears in and its aliases and successors, with every link's provenance. That is a
new address class and needs an ADR 0013 addendum; ids are the store's own integers, which
are stable only if never re-minted (they are not).

## Subscriptions by party

`subscription.party_id` becomes non-null for a `party` predicate: alert on any filing in any
docket where this party files. Query 5's *service-list* predicate is **not** in M6: the
Board's search exposes no service-list table, so membership would have to come from
documents (certificates of service) — extraction, and a measurement of the source first.
The coverage page says which predicates exist.

## What is deliberately not in M6

Position or stance extraction (never inferred; a later, document-based method with its own
methodology page); service lists (above); reporting-mark data from external sources beyond
the operator's seed; any UI that ranks parties.

## Open questions for the operator

1. Party page address: `/p/{id}` (opaque, stable) or a slug from the display name (readable,
   but a rename breaks it)? Recommendation: `/p/{id}`, with the name in the page title.
2. The Board as a party: show it in the Parties block (it is a filer of record) or fold it
   out as "the Board" with its own treatment? Recommendation: show it, labelled as the
   agency, never counted as a litigant in any later stance work.
3. Seed list scope: Class I holding companies + operating railroads + marks (about 20
   rows), or also the Amtrak/commuter and largest short-line holding companies?
