# Unified search — design note

> **Status: planning only, 2026-08-26.** The operator's third ask after party pages and the
> contribute page; not started, and not to be started before both are done. The one schema
> touch here (an FTS5 index, migration 0010) goes to the schema-critic before it is built.

## The ask

One box, in the masthead where the docket lookup is now, that takes a docket number, part
of a party's name, or words from a caption, and gets the reader to the right page. `/search`
works without JavaScript; `/suggest` answers as-you-type with captions; nothing about the
reader or the query is stored.

## What is searched

Three kinds of thing, each already an address:

| Kind | Text indexed | Address | Rows today |
| --- | --- | --- | --- |
| Docket family | printed number and its spellings (`FD 36873`, `FD-36873`, `FD_36873`), the caption as the Board prints it, the sub-dockets' captions | `/d/…` (ADR 0013) | 32,604 |
| Party | every live name of the component (all kinds, all members) | `/p/<id>` (ADR 0015) | 10,110 parties, fewer components |
| Decision | id and the Board's summary, when one is printed | `/decision/…` | tens of thousands after wave 3 |

Not indexed: filings (a filing is reached through its docket; its "type" string is not a
search target), document text (no extraction exists yet; the citator is a later decision),
anything derived.

**F4's rule**: a sub-docket never appears as a result on its own. `FD 36873 (Sub-No. 1)`
resolves to the family sheet, which is where the sub-docket's entries are (ADR 0005). A
search for a sub-docket's caption words returns the family, with the sub-docket named in
the snippet.

## Mechanics

- **A docket number is not a search.** `urls.lookup` already turns anything a person types
  into an identity; if it parses and the family exists, `/search` answers **303 to the
  sheet** and never touches the index. That keeps the one fast path the masthead has today.
- **The index** is an FTS5 external-content table (`search_doc(kind, ref, address, title,
  body)`; FTS5 present in the production image, SQLite 3.46) rebuilt by ingest, not the web
  tier — the server stays a reader. Rebuild is a pass at the end of `poll` and after a wave:
  captions and party names change rarely and the whole set is small (tens of MB at most), so
  a full rebuild per pass is simpler than incremental maintenance and is measured, not
  assumed, before choosing otherwise.
- **Tokenizer** `unicode61` with `remove_diacritics 2`; the docket-number spellings are
  written into the body as separate tokens so `36873` alone matches. Prefix queries on the
  last token for `/suggest`.
- **Ranking**: `bm25` with the title column weighted above the body; ties broken by kind
  (docket, party, decision) then by recency of activity for dockets. No popularity signal —
  there is none, by design.
- **`/search?q=`**: an HTML page, at most 50 results, each row = kind, address, the caption
  or name as printed (`as-printed`), and a one-line measured fact (filings and last filing
  for a docket; dockets and filings for a party; docket and date for a decision). Works with
  no script. `Cache-Control: public, max-age=300` like every reader page; no `q` in any log.
  Caddy's console log writes the full URI, query included (the filter in `infra/deploy/
  Caddyfile` deletes address and agent, not the query), so before this ships the filter
  gains `request>uri query delete q` — and `name`, which `/parties` already carries today.
- **`/suggest?q=`**: JSON, at most 8 rows, the same fields, `no-store`. The masthead's script
  renders it as a listbox with proper ARIA; without the script the box is the `/search` form.
  A docket-number prefix answers the parsed identity first.
- **Nothing stored**: no query log, no "popular searches", no per-query counters. The hourly
  traffic counts (if they ship) see `/search` as a route class and nothing more.

## Schema (for the schema-critic)

Migration 0010: `search_doc` (a plain table, one row per indexed thing, rebuilt) and
`search_fts` (FTS5, `content='search_doc'`). Derived, disposable, rebuildable from the store
— it carries no provenance because it asserts nothing; it is an index over assertions that
carry theirs. The `party` rows index every live name of a component under the
representative's address, so a join or unjoin changes the index at the next rebuild and the
address never changes.

## Open

- [ ] Confirm the three kinds; decisions in from the start or added when summaries are
      measured to be useful (many are empty).
- [ ] Whether the masthead box replaces the docket lookup or sits beside it (recommendation:
      replaces it; the number fast path keeps the old behaviour exactly).
- [ ] The `/parties?name=` query string is in Caddy's log today; the filter change above
      is worth making before search, on its own.
