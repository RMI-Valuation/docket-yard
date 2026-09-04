-- Migration 0021: which record carries a document, answered by index.
--
-- `search.search_pages` (2026-09-04) asks it for every page hit — twenty a query, on an
-- unauthenticated page — and the only indexes on the two attachment tables lead with the
-- record's key (migration 0002: `UNIQUE (filing_pk, source_url)` and its decision twin),
-- so each ask was a scan of the whole table, twice for a decision's document. The two
-- indexes below are the inverse of the join the sheet and the viewer already make.
-- `filing_attachment` and `decision_attachment` are public in the CC0 snapshot, so this DDL
-- ships in the snapshot's published `schema.sql` (dump.py); an index asserts nothing.
BEGIN TRANSACTION;

CREATE INDEX filing_attachment_by_document ON filing_attachment (document_sha256);
CREATE INDEX decision_attachment_by_document ON decision_attachment (document_sha256);

PRAGMA user_version = 21;

COMMIT;
