# Search, built out — design note

> **Status: proposed 2026-09-17**, on branch `search-v2`. Revises `search.md`, which stays
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
| Decisions | 23,726 | 19,846: those with a printed summary |
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

## The index (migration 0034)

Numbered 0034: 0033 is claimed by the decided-dates addendum on `decided-date-grain`;
whichever lands second renumbers. All three tables are derived and disposable, rebuilt by
ingest; the migration clears `search_meta`'s signature, not its row (0012's reasoning).
`INDEX_FORMAT` goes to 4.

### `search_doc`, rebuilt

Rebuilt as 0012 rebuilt it, the kind CHECK admitting `filing`:

- **Filing rows**, one per filing id. Body: the Board's type, the Filed For text as printed,
  the filing id, the printed docket(s). Title `Filing <id>`.
- **Every decision**, summary or not, with its **type in the body**, so a decision without
  a summary is found by typing its type and not only through the filter. The prose that says
  search covers "decision summaries" (`search.html`, `search.md`) is revised with it.
- No filter columns: those are the placements'.

### `search_place`, new

One row per (index row, proceeding), deduplicated per proceeding:

| Column | |
| --- | --- |
| `doc_id` | the `search_doc` row |
| `group_docket_id` | the proceeding by the sheet rule. **An id, not a path**: an unparseable docket has no path and must not become one shared empty group. The display path is computed at read; the address parameter for "N more in this proceeding" is the path (ADR 0013) |
| `prefix` | the docket's prefix |
| `date_kind`, `date` | `filed`, `served` or `dated` (the Board's "received or sent" column, which declines to say which), and that entry's printed date, ISO. `served` is `service_date`, never the derived decided date of the 0033 branch. NULL for a docket |
| `type_kind`, `type` | `filing` or `decision`, and the type as that entry prints it |

Indexed `(doc_id)`, `(group_docket_id)`, `(prefix, date)`, `(type_kind, type)`, created
after the inserts inside the rebuild's transaction. A docket row places itself; a party has
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
  index rows, ≈160,000 placements and ≈110,000 map rows to the WAL Litestream ships. Measured
  on the restore in production's image before build: the whole rebuild, the write lock
  (0012's was 5.6 s at 96,225 rows, most of it the FTS re-tokenise, which grows with tokens;
  filing bodies are short), and that the fleet's page loader waits on busy rather than fails.

## Query plan, and what it costs

### Records

Two phases, because grouping needs every match and weighted `bm25` defeats FTS5's internal
ordering, evaluating the whole select list — snippet included — for every matching row
(`search.md`). First `(doc_id, rank)` for all matches, joined to placements, filtered,
grouped; then snippets only for the items displayed. Measured on the rebuilt index before
the query layer is fixed, with the broadest words over comment bodies.

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
  matching rowids are read unranked, joined to placements and filtered under a **time budget**
  (a SQLite progress handler); the pages that survive are then ranked, or sorted by date. A
  query that exhausts the budget is answered from records only, with the page side marked
  "too broad to filter: add words or narrow the filter" — never a partial sample presented
  as the answer. By the figures above scaled 3x, filtered `abandonment` and `railroad` would
  exceed a 1.5 s budget on production, so the budget is set from a measurement on the
  instance, not from this table.

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
rank a page by, and nothing to bound the walk), sorted newest.

The address carries every parameter, so a filtered search is a link. Caddy drops the whole
query string from its log (`search.md`); the new parameters inherit that.

## Surfaces

- **`/search`**: the box; a filter bar, one "Filters" line on a phone; the party strip;
  proceedings, each with up to three matched items (caption or number, then decisions,
  filings, comments, pages) and "N more matches in this proceeding"; sort; paging;
  `?view=documents` for the flat list. Works without script.
- **`/suggest`**, **MCP**: unchanged (§ What else reads the index).
- **Wording**: "proceeding" is defined once, on `/search`'s help: the sheet rule. MCP's
  `count_filings` answer names its own unit, docket numbers.

## Build order

1. This note, critic-reviewed and decided; commit.
2. Migration 0034, the rebuild, the signature, `DERIVED_TABLES`; tests; measured on the
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
