-- Migration 0027: which comment carries a document, answered by index — migration 0021's
-- third table.
--
-- A comment's attachment was given a text address on 2026-09-11 (the operator's decision:
-- its text is shown as a filing's is), so `search.search_pages` now asks this table for
-- every page hit no filing or decision carries. Its only index leads with the comment's key
-- (migration 0011: `UNIQUE (comment_pk, source_url)`), so each ask would be a scan of the
-- whole table. `enviro_comment_attachment` is public in the CC0 snapshot, so this DDL ships
-- in the snapshot's published `schema.sql` (dump.py); an index asserts nothing.
BEGIN TRANSACTION;

CREATE INDEX enviro_comment_attachment_by_document
    ON enviro_comment_attachment (document_sha256);

PRAGMA user_version = 27;

COMMIT;
