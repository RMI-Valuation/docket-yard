# Search, built out — design note

> **Status: built 2026-09-17 on branch `search-v2`** (migration 0033, `store/finder.py`,
> `/search`), reviews and the rehearsal owed before release. Revises `search.md`, which stays
> the account of what shipped until this lands. The operator chose the shape as four
> answers, and three more after the schema-critic's pass (§ Decided by the operator). Costs
> were measured the same day on a restore of production taken that morning
> (`data/rehearse-0925`, SQLite 3.50 locally; production runs 3.46 on a slower instance,
> about 3x on the page index by `search.md`'s 2026-09-04 figures).

## Decided by the operator (2026-09-17)

1. **Results are grouped by proceeding.** One result per proceeding, the matching filings,
   decisions, comments and pages under it; a flat list of documents stays available.
2. **Four filters**, each a control and a parameter in the address: docket type (prefix),
   date range, what to search (kinds), and the Board's filing or decision type.
3. **Filings become records the index finds**: their Board type and Filed For text.
4. **Best match or newest first, with paging and a total.**
5. **A proceeding follows the sheet rule** (F4): a sub-docket with a caption of its own is
   its own result; one repeating its parent's caption is the family. MCP's `count_filings`
   keeps counting docket numbers, and says so.
6. **A date filter admits a proceeding only through dated items** in range. A caption-only
   match is left out, and the filter says what dates filter.
7. **Newest among what was examined, labelled.** When a word matches more pages than are
   examined, the page side is sorted among those and the page says so; records are always
   complete.

Unchanged: a docket number or citation is the fast path to its sheet; `/suggest` and MCP's
`search_the_record` keep today's kinds and shape; nothing typed is stored or logged; a page
hit carries who read it, the band and the scan (ADR 0021 D7).

## What the record holds to search (2026-09-17 restore)

| | Rows | Indexed today |
| --- | --- | --- |
| Dockets (`docket_current`) | 32,631 | 31,987 rows (families, and sub-dockets with a caption of their own) |
| Filings | 54,822 (58,388 attachments) | **none**, only their pages' text |
| Decisions | 23,726 rows, 19,846 ids | 19,846: those with a printed summary, which is every id |
| Environmental comments | 34,414 | 34,297 |
| Parties | — | 10,234 components |
| Pages of text (`page_fts`) | 1,357,843 | all |

Vocabularies: **122 filing types**, **12 decision types**, the Board's strings; one string,
`Notice`, is both. No record lacks a type. Filed For is filled on every filing.

## Placement: a record belongs to every proceeding it was entered in

The record holds a filing, a decision or a comment as one row per docket it was entered in
(`filing` is UNIQUE on `(docket_id, stb_filing_id)`, 0002). Today's index folds them to one
row per id under the docket nearest the parent — harmless while search neither grouped nor
filtered. Measured:

| | In more than one docket | In more than one family | Copies that disagree |
| --- | --- | --- | --- |
| Filings | 680 | 573 (70 across prefixes) | 0 (type, date, Filed For) |
| Decisions | 1,737 | 1,432 | 2 (type or served date) |
| Documents | — | 2,171 held in more than one family | — |

Folded, a joint FD/NOR filing would be missed by `prefix=NOR`, its pages would show under
both proceedings and the filing under one, and the family would be chosen by the lowest
pk (the fold's ordering ties across families). So an item is **found once and placed in
every proceeding it was entered in**: one FTS row per record id, and one placement row per
docket entry carrying that entry's own cells. Grouping, filters, totals and "N more" read
placements, and pages reach proceedings through the same placements.

## The index (migration 0033)

Numbered 0033 on this branch, because `MIGRATIONS` must be contiguous; the decided-dates
addendum on `decided-date-grain` claims 0033 too, and whichever lands second renumbers.
All three tables are derived and disposable, rebuilt by ingest; the migration clears
`search_meta`'s signature, not its row (0012's reasoning). `INDEX_FORMAT` goes to 4.

### `search_doc`, rebuilt

Rebuilt as 0012 rebuilt it, the kind CHECK admitting `filing`:

- **Filing rows**, one per filing id. Body: the Board's type, the Filed For text as printed,
  the filing id, the printed docket(s). Title `Filing <id>`.
- **Every decision**, summary or not, with its **type in the body**, so a type is found by
  word as well as by filter. Every decision id on the restore prints a summary, so this adds
  no rows today; it keeps one that ever prints none findable. The prose that says search
  covers "decision summaries" (`search.html`, `search.md`) is revised with it.
- No filter columns: those are the placements'.

### `search_place`, new

One row per (index row, proceeding), deduplicated per proceeding:

| Column | |
| --- | --- |
| `doc_id` | the `search_doc` row |
| `group_docket_id` | the proceeding by the sheet rule. **An id, not a path**: an unparseable docket has no path and must not become one shared empty group. The display path is computed at read; the address parameter for "N more in this proceeding" is the path (ADR 0013) |
| `prefix` | the docket's prefix |
| `date_kind`, `date` | `filed`, `served` or `dated` (the Board's "received or sent" column, which declines to say which), and that entry's printed date, ISO. `served` is `service_date`, never the derived decided date of `decided-date-grain`. NULL for a docket |
| `type_kind`, `type` | `filing` or `decision`, and the type as that entry prints it |

Indexed `(doc_id)`, `(group_docket_id)`, `(prefix, date)`, `(type_kind, type)`, by the
migration; the rebuild inserts with them in place (dropping and recreating them inside the
write is a measurement not yet taken). CHECKs tie a date's kind to the record's kind, hold
dates to ISO form and types to trimmed, non-placeholder strings. A docket row places itself; a party has
no placement.

**The cells mirror the latest observation**, as the record tables do (0002). Nothing reads
them as history; validation queries 3 and 4 stay on the ledger.

### `search_document`, new

`(document_sha256, doc_id)`, one row per attachment owner, about 110,000. With every filing,
decision and comment in the index, a page reaches its proceedings and filter cells through
its owner's placements.

- A page shown under a proceeding **links the record of that placement**, not today's
  earliest-filed rule, so the evidence under B never opens A's filing.
- A page counts **once per proceeding**, deduplicated on (proceeding, `text_id`): a filing
  entered in a docket and its folded sub-docket is two attachment rows in one group.
- Identical bytes filed in several proceedings count in each, and the page says so beside
  the count — the concern about boilerplate across dockets that validation query 1's repair
  record raised.

The page index (`page_fts`) is **not** changed.

### Freshness

A first fetch moves nothing `search.signature()` reads: the capture sets the attachment's
hash and writes `document_source`, with no event. The page index is kept current row by row,
so a new document's pages would match with no map row until an unrelated event. The
signature gains `MAX(rowid)` of `document_source` and the count of attachments holding a
hash; a page without a map row is counted apart from drift, as `dropped` is today.

### What else reads the index

- **`/suggest` and MCP** call `search()`. It takes the kinds to search, and they pass
  today's, so fifty thousand Filed For bodies do not enter a per-keystroke prefix query or
  change an assistant's answers. MCP parity is a separate decision for the operator.
- **The snapshot**: `search_place` and `search_document` join `dump.DERIVED_TABLES`, or the
  nightly dump refuses the unclassified tables; `tests/test_data.py` pins the set.
- **The rebuild** runs whenever the signature moves, most polls, and now writes ≈150,000
  index rows, ≈160,000 placements and ≈110,000 map rows to the WAL Litestream ships. To be
  measured in production's image on the instance at the rehearsal: the whole rebuild, the write lock
  (0012's was 5.6 s at 96,225 rows, most of it the FTS re-tokenise, which grows with tokens;
  filing bodies are short), and that the fleet's page loader waits on busy rather than fails.

### Measured (build step 2)

Migration 0033 and a forced rebuild on a copy of the restore, locally (SQLite 3.50):

| | |
| --- | --- |
| Rows | 149,749 index rows (53,385 filings), 144,927 placements, 104,689 document owners |
| Deriving, on reads | parties 6.4 s (unchanged), filings 0.4 s, placements 0.4 s, the rest 0.5 s |
| The write lock | **2.8 s**, of which the FTS rebuild 1.0 s and the commit 0.5 s |
| Whole rebuild | 11.7 s; the migration itself 25 s from schema 29 (30-33) |

The instance is slower (0012's lock was 5.6 s there at 96,225 rows against a local figure
not taken); the rehearsal in production's image measures it before release.

### Rehearsed (2026-09-17)

In v2026.09.26's image (SQLite 3.46.1) on this workstation, against the 2026-09-17 restore
copied into a Docker volume (`data/rehearse-0925/rehearse_search.py`, log beside it). All
checks passed:

| | |
| --- | --- |
| Migration 29 -> 33 | 28.2 s; foreign keys clean, row counts unchanged, `quick_check` ok |
| After 0033, before the rebuild | `search.ready()` false: `/search` says it is rebuilding |
| Rebuild | 11.0 s, **write lock 2.2 s**; 53,385 filings, 144,927 placements, 104,689 owners |
| `/search`, ordinary | 16-156 ms (Tazewell County 96, Tehachapi 79, a type browse 16) |
| `/search`, broad | `railroad` 430 ms; `the` 836 ms; `abandonment` over AB 1,005 ms |
| `/search`, broadest filtered | `the` over FD 1,595 ms, page text left out and said |
| Unchanged | a docket number opens its sheet; `/suggest` 5 ms; MCP search keeps its kinds |

Not yet measured on the instance itself, whose disk and CPU are slower than this workstation's
(`search.md` puts the page index about 3x slower there). The budget holds the worst case to
about 1.6 s whatever the machine; what the instance changes is how many broad filtered searches
reach it and leave the page text out.

### What the reviews changed (2026-09-17)

`/code-review` (high), the ingest specialist and a second schema-critic pass on the built code:

- **The rebuild reads one snapshot.** Its derivation is several queries and a records wave
  writes beside the poller; read at different moments, a decision committed between two of
  them was a `KeyError` and a rebuild could be stamped older than its rows. The signature and
  every derived row are read inside one read transaction, and the write runs under
  `batches.under_lock`, as the text loader's does, since Litestream's checkpoint wants the
  same lock.
- **An index not yet built says so.** Migration 0033 empties the record index, and until the
  first rebuild `/search` answered every query "nothing" with a 200. `search.ready()` compares
  the built signature's format; `/search` says the index is being rebuilt. The deploy runs the
  rebuild in the window regardless (`infra/deploy/README.md`).
- **One rule for what is a proceeding.** `_docket_docs` reads `proceedings()` to decide which
  sub-dockets are rows, so the two cannot disagree (they did for an unparseable parent).
- **A page links the file on the copy that carries it**, and the text page picks a record's
  copy with the id as last tiebreak; **within one proceeding every page is seen**, not the
  record-wide best 5,000; **placements hold types as the body does** (trimmed, placeholders
  dropped); **owners are ordered**, so which record a page links cannot vary between runs.
- On the page: a flat list whose only matches are captions says so; a page past the last says
  so; within one proceeding, the 200-match cap is said; more than 20 values of a filter are
  said as such; a `page` that is not a number is the first page, not a 422.

Checked on the restore and clean today: no document mapped only through a non-headline copy,
no placement date differing from the printed fact, no placeholder types, no group without a
docket row, no sub-docket with a missing parent. Recorded, not changed: a family's header
counts the family sheet's filings (1,982 captioned sub-dockets with filings are their own
proceedings), and an evidence row prints the headline copy's date, which differs from a
placement's for 2 decisions entered in several dockets.

## Query plan, and what it costs

### Records

Two phases, because grouping needs every match and weighted `bm25` defeats FTS5's internal
ordering, evaluating the whole select list — snippet included — for every matching row
(`search.md`). First `(doc_id, bm25)` for all matches, materialised, then joined to placements,
filtered, grouped; snippets only for the items displayed, one FTS lookup each.

**Every placement column in a filter is written `+p.col`.** Without it SQLite probed
placements through the `(prefix, date)` index once per matched record: `railroad` over AB
since 2020 took 2,640 ms; reached by `doc_id`, 7 ms. Measured on the rebuilt restore:

| Query | Records matching | All, grouped | AB and 2020 on, grouped |
| --- | --- | --- | --- |
| `abandonment` | 5,379 | 7 ms | 1 ms |
| `railroad` | 26,206 | 22 ms | 7 ms |
| `the` | 28,252 | 27 ms | 7 ms |

The record side needs no bound.

### Pages

Measured on the restore, ranked, then grouped through a document map:

| Query | Pages matching | Rank the best 5,000 | Group them | Every page, filtered to AB and 2020 on |
| --- | --- | --- | --- | --- |
| `"tazewell county"` | 140 | 1 ms | 1 ms | — |
| `tehachapi` | 157 | 0 ms | 1 ms | — |
| `abandonment` | 126,802 | 82 ms | 31 ms | 480 ms |
| `railroad` | 496,612 | 324 ms | 27 ms | 1,161 ms |
| `the` | not counted | 963 ms | 26 ms | 1,947 ms |

Grouping is cheap; ranking is the cost, and it grows with the pages a word matches. **`web`
is one uvicorn worker**, so a search that runs for seconds stalls every reader for those
seconds. The page side is bounded, and says when it was:

- **Unfiltered**: rank the best **5,000** matching pages (`PAGE_WINDOW`) and group them. When
  the word matched more, the proceeding count from pages is "at least N", and under Newest the
  order is labelled as among the pages examined (decision 7).
- **Filtered**: the filter must see every matching page, so rank cannot come first — FTS5
  ranks every match before returning a row, and an interrupted ranking returns nothing. The
  matching rowids are read unranked (`the`: 1,047,892 in 283 ms). Up to `DIRECT_MATCHES`
  (20,000) they are joined to their owners' placements and filtered; above it, the pages the
  filter admits are gathered from placements first and the matches intersected with them,
  which is what makes a broad word affordable (`the` over AB since 2020: 2,117 ms joined,
  about 310 ms intersected; over every FD docket, 413 ms to gather 846,113 admitted pages).
  Pages that survive a filter are not ranked: within the page tier a proceeding is ordered by
  how many of its pages matched.
- **Both paths run under a time budget** (`PAGE_BUDGET`, 1.5 s; a SQLite progress handler).
  A query that exhausts it is answered from records only, and the page says the text was left
  out because the words match too many pages — never a partial sample presented as the
  answer. Locally only `the` exhausts it; production's instance is about 3x slower on the page
  index, so the budget is measured there during the rehearsal before it is fixed.

`PAGE_WINDOW` and the budget are published on `/search`'s help and here, as `PAGE_LIMIT` is
today.

### Totals, paging, sort

- 20 proceedings a page. Totals are exact when every match was grouped, "at least N" when the
  window cut the page side.
- **Best match**: by the strongest kind of evidence, then rank within it — a caption or
  number, then a decision, filing or comment, then page text only. Ranks from the two FTS
  indexes are never compared; bm25 scores from different indexes are not on one scale.
- **Newest**: by the latest date among the proceeding's matched, placed items; undated items
  sort last.

## Filters

| Parameter | Meaning | Applies to |
| --- | --- | --- |
| `prefix=AB` (repeatable) | the placement's docket prefix | every kind but party |
| `from=2020-01-01`, `to=` | the placement's printed date in range, inclusive: filed, served or dated | filings, decisions, comments, and pages through their document's placements. **Not** captions (decision 6): the control says "dates filter filings, decisions, comments and pages" |
| `in=captions,filings,decisions,comments,text,parties` | the kinds searched; default all | — |
| `ftype=` and `dtype=` (repeatable) | the Board's filing type or decision type, exact, keyed by kind because `Notice` is both | filings or decisions, and pages whose document has a placement of that type |

Dates are compared as ISO strings; nothing is computed. Types are chosen from lists drawn
from the store. A filter that names something parties do not have (a prefix, dates, a type)
drops the party strip.

**An empty query with a filter is a browse**: records only, never pages (there is nothing to
rank a page by, and nothing to bound the walk), newest first whatever the order asked, since
nothing was matched to rank.

The address carries every parameter, so a filtered search is a link. Caddy drops the whole
query string from its log (`search.md`); the new parameters inherit that.

## Surfaces

- **`/search`**: the box; a filter bar in `<details>`, one line on a phone; the party strip;
  proceedings, each with up to three matched items (decisions, filings, comments, pages) and
  "N more matches in this proceeding", which is the same search with `docket=` and shows every
  match there; sort; paging (`page`, at most 500); `view=documents` for the flat list, each
  match once. Every parameter is checked against what the store holds (prefixes and types
  from the placements, ISO dates, at most 20 values a filter), and a value it does not hold is
  dropped and said. A filtered search is never the docket-number redirect. Works without
  script.
- **`/suggest`** and **MCP** keep `search.search()` and today's kinds. Two changes reach them
  anyway: a family's row carries its own caption alone (below), and MCP's snippet treats every
  printed docket number as the record's own spelling, since a decision's body now names every
  docket it was entered in.
- **A family's row carries its own caption and number, not its sub-dockets' captions.** With
  results grouped, the old body made every word of a line abandonment find its whole series a
  second time: `Tazewell County` returned AB 290 (Sub-No. 222X) and then AB 6 and AB 167
  through captions already indexed as rows of their own. A sub-docket that is not a row
  repeats its parent's caption, so the family loses no word. `/suggest` and MCP now return the
  sub-docket for such a word, not the sub-docket and its family.
- **Wording**: "proceeding" is defined once, on `/search`'s help: the sheet rule. MCP's
  `count_filings` answer names its own unit, docket numbers.

## Build order

Steps 1-5 done 2026-09-17 on `search-v2`; tests 1,021.

1. This note, critic-reviewed and decided; commit.
2. Migration 0033, the rebuild, the signature, `DERIVED_TABLES`; tests; measured on the
   restore in production's image (rebuild, lock window, the loader waiting). Schema-critic on
   the migration.
3. The query layer: placements, filters, the window and budget, two-phase records, grouping,
   sort, paging; tests over the fixture store; measured on the restore, and the budget set on
   the instance.
4. `/search`: the filter bar, grouped results, the flat view, phone layout.
5. Docs: `search.md` folded in, `/search` help, `/api`.
6. `/code-review`, the ingest specialist on the rebuild, `/security-review` (new parameters
   from the public); PR with Copilot and Codex; rehearse; release behind the wall (it rebuilds
   the index, `infra/deploy/README.md`).
