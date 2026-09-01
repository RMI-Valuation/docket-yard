# Unified search — design note

> **Status: built 2026-08-26** (migration 0010, `store/search.py`, `/search`, `/suggest`),
> after the party pages and the contribute page. The schema-critic reviewed 0010 before
> commit (its findings — the snapshot, decision duplicates, the sheet's counts, unparsed
> families, AB-family sub-dockets, the join/unjoin window — are all folded in below).
>
> **Revised 2026-08-31** (migration 0013, `INDEX_FORMAT` 3): a result row now prints the
> row's own caption and a highlighted snippet of what matched. The words were always in the
> index; the template rendered three of the six fields it was handed
> (`navigation-review.md` § B).

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
| Environmental comment | number, the commenter's own words as printed, submitter, organisation and location | `/d/<docket>/comment/<number>` (ADR 0013) | 34,255 after the archive wave |

Every comment is indexed, not only those carrying words: half the rows print `--` for the
text (measured 2026-08-31), and their submitter, organisation and location are terms nothing
else in the index holds. A placeholder is never a term. The words are the commenter's own,
quoted; a hit asserts nothing about them, and the page it resolves to says so.

**The placeholder tuple is `--` and nothing else, measured after the wave.** `--` accounts
for 22,553 of the short `location_raw` cells and 21,941 of the short `organisation_raw`
ones; every other short spelling that looked like a placeholder is somebody's own typing —
`Unknown` 124, `Various` 74, `N/A`/`NA`/`n.a.` 15, `None` 17 across all three columns,
230 rows in 34,257. Those are what the Board printed and what a person filled in, so they
are indexed like any other cell rather than swallowed: a cell that says `Unknown` is an
assertion, an empty cell is an absence, and the index must not turn the first into the
second.

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
  2026-08-26 store; 96,225 on 2026-08-31, the comment wave having added a third of it), so a
  full rebuild is simpler than incremental maintenance. It runs only
  when a signature of the record's newest ids has moved (`search_meta`), derives every row
  on reads first, and writes in one short transaction; the CLI's join/unjoin rebuild too.
  Measured on the production copy: the first version took 227 s (correlated subqueries);
  the one-pass version is what shipped.

  **How long a rebuild takes, and how long it locks.** Measured on the instance
  2026-08-31, against a `VACUUM INTO` snapshot of the production store at **96,225 rows**
  (a third of them comment bodies, the longest text the index carries):

  | | |
  | --- | --- |
  | Deriving every row, on reads | **22.4 s** — no lock held |
  | The write transaction | **5.6 s** — the write lock is held for this and only this |
  | …of which the FTS re-tokenise | 4.5 s (delete 0.3 s, insert 0.6 s, commit 0.3 s) |
  | Whole `search rebuild` | **24.1 s** |

  Earlier figures — 40 s while a wave ran, 32 s for 61,959 on the v2026.08.42 deploy — are
  whole-command wall times, and `docs/deferred.md` read them as lock time. **They are not.**
  `rebuild()` derives everything on reads first and writes in one short transaction, exactly
  as this note has always claimed, so the window in which another writer can collide is the
  5.6 s, comfortably inside the 30 s `_connect_rw` waits. A concurrent `/subscribe` waits
  about five seconds in the worst case; it does not fail. At this record's growth — roughly
  250 documents a month — the lock window would have to grow more than fivefold before the
  waiter's timeout became the binding constraint.

  The derive is the part worth watching, and it is the part that costs nothing to anyone:
  it holds no lock, and a reader searching during it sees the previous index.
- **Tokenizer** `unicode61` with `remove_diacritics 2`; the docket-number spellings are
  written into the body as separate tokens so `36873` alone matches. Prefix queries on the
  last token for `/suggest`.
- **Ranking**: `bm25` with the title column weighted above the body; ties broken by kind
  then title, the kinds ordering as they sort (comment, decision, docket, party). No
  recency and no popularity signal. A result row shows kind, the title as printed, and one
  measured fact (the sheet's own counts for a docket; distinct dockets and filings across
  the component for a party; docket and service date for a decision; docket and the date
  the Board printed for a comment — "dated", never "received", because the Board's own
  column declines to say which).
- **`/search?q=`**: an HTML page, at most 50 results, each row = kind, address, the caption
  or name as printed (`as-printed`) with the identifier beside it, a one-line measured fact
  (filings and last filing for a docket; dockets and filings for a party; docket and date
  for a decision or a comment), and — where it says something the caption does not — a
  snippet of the body with the matched words marked.

  **The caption is a column, not the title.** `title` is weighted 8.0 against the body's 1.0
  in the bm25 ranking and is where a docket's number and its spellings live; moving a
  caption into it would re-rank every query so that caption words outweighed the number a
  reader typed. `search_doc.caption` (migration 0013) is not in the FTS table at all — its
  words are already indexed in `body`, and indexing them twice would double-count them.

  **The snippet is marked with control characters, never with tags.** `body` holds the
  Board's printed text and the words environmental commenters wrote — external input,
  34,257 rows of it — so `snippet()` is asked for ``/``, and the web tier escapes
  the whole string before substituting `<mark>`. The only markup that can reach the page is
  markup `search.py` put there. `/suggest` carries the caption and NOT the snippet: control
  characters do not belong in a JSON answer.

  A snippet is dropped when it would only repeat the caption printed beside it, and when it
  carries no mark at all — FTS5 returns the leading text of a column it found no match in,
  and leading text is not a reason. A comment's title is its number with no noun in front of it: `EI` rows are
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
the empty index knows it is stale. Migration 0013 added `search_doc.caption`, a plain
`ALTER TABLE`: `search_fts` is external-content and names its columns (`title`, `body`), so
a column it does not name is invisible to it and neither the index nor its shadow tables are
touched. Nothing clears the signature there either — `INDEX_FORMAT` is part of it, and
bumping it to 3 is what makes the next pass rebuild the content and fill the column in.
Migration 0010, as it stands after both: `search_doc` (a
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
