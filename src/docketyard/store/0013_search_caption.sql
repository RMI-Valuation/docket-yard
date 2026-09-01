-- Migration 0013: a search row learns its own name.
--
-- 86,069 of 96,225 index rows (89.4%) have an identifier-only title, and 29,542 of 31,979
-- docket rows (92.4%) carry the Board's caption in `body` — which the results template has
-- never printed (navigation-review.md § B). `FD 30101` was published as "FD 30101 — 0
-- filings" while "NORFOLK AND WESTERN RY CO.-ABANDONMENT EXEMPTION-WYOMING,WV" sat one
-- field away in the same tuple.
--
-- The caption is a COLUMN OF ITS OWN and not a change to `title`, deliberately. `title` is
-- weighted 8.0 against the body's 1.0 in the bm25 ranking, and it is where a docket's
-- number and its spellings live; moving a caption into it would re-rank every query in the
-- record so that caption words outweighed the number a reader typed. `caption` is not in
-- the FTS table at all: the words it holds are already indexed in `body`, so indexing them
-- twice would double-count them in the ranking of the rows that have one.
--
-- search_fts is external-content over search_doc and names its columns (title, body); a
-- column the FTS table does not name is invisible to it, so neither the index nor its
-- shadow tables are touched here and no FTS rebuild is needed for the schema's sake.
-- `INDEX_FORMAT` is bumped to 3 in the same release, which changes `signature()` and makes
-- the next ingest pass rebuild the content — that is what fills this column in.
--
-- Derived and disposable like the rest of the index: nothing here is a record, and
-- `docketyard search rebuild` remakes every row from the store.

BEGIN TRANSACTION;

ALTER TABLE search_doc ADD COLUMN caption TEXT NOT NULL DEFAULT '';

PRAGMA user_version = 13;

COMMIT;
