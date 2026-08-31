# Unified search — design note

> **Status: built 2026-08-26** (migration 0010, `store/search.py`, `/search`, `/suggest`),
> after the party pages and the contribute page. The schema-critic reviewed 0010 before
> commit (its findings — the snapshot, decision duplicates, the sheet's counts, unparsed
> families, AB-family sub-dockets, the join/unjoin window — are all folded in below).

## The ask

One box, in the masthead where the docket lookup is now, that takes a docket number, part
of a party's name, or words from a caption, and gets the reader to the right page. `/search`
works without JavaScript; `/suggest` answers as-you-type with captions; nothing about the
reader or the query is stored.

## What is searched

Four kinds of thing, each already an address:

| Kind | Text indexed | Address | Rows today |
| --- | --- | --- | --- |
| Docket family | printed number and its spellings (`FD 36873`, `FD-36873`, `FD_36873`), the caption as the Board prints it, the sub-dockets' captions | `/d/…` (ADR 0013) | 32,604 |
| Party | every live name of the component (all kinds, all members) | `/p/<id>` (ADR 0015) | 10,110 parties, fewer components |
| Decision | id and the Board's summary, when one is printed | `/decision/…` | tens of thousands after wave 3 |
| Environmental comment | number, the commenter's own words as printed, submitter, organisation and location | `/comment/<number>` (ADR 0013) | 22,000+ after the archive wave |

Every comment is indexed, not only those carrying words: half the rows print `--` for the
text (measured 2026-08-31), and their submitter, organisation and location are terms nothing
else in the index holds. A placeholder is never a term. The words are the commenter's own,
quoted; a hit asserts nothing about them, and the page it resolves to says so.

Not indexed: filings (a filing is reached through its docket; its "type" string is not a
search target), document text (no extraction exists yet; the citator is a later decision),
anything derived.

**F4's rule**: a sub-docket's entries live on the family sheet (ADR 0005), so a hit on a
sub-docket resolves there. A sub-docket whose caption differs from its parent's is indexed
as its own row at its own address (`/d/AB-55/sub/785X` → the family sheet with the
sub-docket printed), so the thousand line abandonments under AB 55 are each findable;
one whose caption repeats the parent's folds into the family row.

## Mechanics

- **A docket number is not a search.** `urls.lookup` already turns anything a person types
  into an identity; if it parses and the family exists, `/search` answers **303 to the
  sheet** and never touches the index. That keeps the one fast path the masthead has today.
- **The index** is an FTS5 external-content table (`search_doc(kind, ref, address, title,
  body)`; FTS5 present in the production image, SQLite 3.46) rebuilt by ingest, not the web
  tier — the server stays a reader. Rebuild is a pass at the end of `poll` and after a wave:
  captions and party names change rarely and the whole set is small (55,000 rows on the
  2026-08-26 store), so a full rebuild is simpler than incremental maintenance. It runs only
  when a signature of the record's newest ids has moved (`search_meta`), derives every row
  on reads first, and writes in one short transaction; the CLI's join/unjoin rebuild too.
  Measured on the production copy: the first version took 227 s (correlated subqueries);
  the one-pass version is what shipped.
- **Tokenizer** `unicode61` with `remove_diacritics 2`; the docket-number spellings are
  written into the body as separate tokens so `36873` alone matches. Prefix queries on the
  last token for `/suggest`.
- **Ranking**: `bm25` with the title column weighted above the body; ties broken by kind
  then title, the kinds ordering as they sort (comment, decision, docket, party). No
  recency and no popularity signal. A result row shows kind, the title as printed, and one
  measured fact (the sheet's own counts for a docket; distinct dockets and filings across
  the component for a party; docket and service date for a decision; docket and the date
  the Board printed for a comment — "dated", never "received", because the Board's own
  column declines to say which) — no snippet.
- **`/search?q=`**: an HTML page, at most 50 results, each row = kind, address, the caption
  or name as printed (`as-printed`), and a one-line measured fact (filings and last filing
  for a docket; dockets and filings for a party; docket and date for a decision or a
  comment). A comment's title is its number with no noun in front of it: `EI` rows are
  submitted comments and `EO` rows are the Board's own environmental documents, and the
  record declines to type the row (migration 0011). Works with
  no script. A result page is `no-store` and `noindex` (its address carries what was
  typed); the bare `/search` page is cached and in the sitemap like any page. No query in
  any log: Caddy's filter now drops the whole query string from the logged URI, whatever
  its parameter is called, and the Referer header (a same-origin click would carry the
  search page's URL). `/privacy` says so.
- **`/suggest?q=`**: JSON, at most 8 rows, the same fields, `no-store`. The masthead's script
  renders it as a listbox with proper ARIA; without the script the box is the `/search` form.
  A docket-number prefix answers the parsed identity first.
- **Nothing stored**: no query log, no "popular searches", no per-query counters. The hourly
  traffic counts (if they ship) see `/search` as a route class and nothing more.

## Schema (for the schema-critic)

Migration 0012 rebuilt `search_doc` to admit `comment` — SQLite cannot alter a CHECK — and
cleared `search_meta`'s signature (not its row, so the ETag's build counter carries on) so
the empty index knows it is stale. Migration 0010, as it stands after that: `search_doc` (a
plain table, one row per indexed thing, rebuilt) and
`search_fts` (FTS5, `content='search_doc'`). Derived, disposable, rebuildable from the store
— it carries no provenance because it asserts nothing; it is an index over assertions that
carry theirs. The `party` rows index every live name of a component under the
representative's address, so a join or unjoin changes the index at the next rebuild and the
address never changes.

## Open

- [x] Three kinds from the start (23,706 decisions carry a printed summary).
- [x] The masthead box replaces the docket lookup; `/d?q=` still resolves a number and
      sends anything else to `/search`.
- [x] Caddy's log filter (query string and Referer) shipped first, on its own.
- [ ] Whether a party's "N filings in D dockets" is a derived claim that wants provenance,
      or a count like the sheet's (treated as the latter, as `/p/<id>` already does).
