-- Migration 0031 — a page the pass failed says why (ADR 0024 § Owed 2, addendum 2026-09-15,
-- Proposed; the operator's defaults of 2026-09-15).
--
-- `ocr_run.pages_failed` has counted the pages a pass attempted and did not read since 0018;
-- the reasons lived only in the fleet queue's `job.error`. This is the row per failed page,
-- under its run, with a reason from a vocabulary and the producer's own words beside it.
--
-- A RECORD OF AN ACTION, like `citation_reading_retirement` (0029) and NOT an ADR 0007
-- assertion: it says what the pass did with the page, not what the page says, so it carries no
-- confidence block. Its provenance is its run's: method, version, render and `ran_at`.
--
-- `page_owned` IS THE VOCABULARY'S, NOT THE ROW'S. A page-owned failure (a cut answer, an
-- oversize sheet) is final at the run's key — method, version, render — and a new key resets
-- it; a failure that is not the page's (the server, the bytes, a lease) is transient, and the
-- page is owed a re-read at the same key.
--
-- WHAT IS NOT WRITTEN HERE: a whole-document size refusal (`text/queue.py`) stays counted and
-- is not a page failure — no run exists for it to hang under (ADR 0024 § Owed 2).
--
-- PUBLIC (`dump.PUBLIC_TABLES`) with `ocr_run`, the detail included; both tables' referents are
-- public, so the snapshot's `schema.sql` names nothing it drops. No prose inside the
-- parentheses below: SQLite keeps table DDL verbatim and the snapshot publishes it (0018's note).
--
-- ADDITIVE: two new tables and their triggers, no rebuild and no backfill, so not behind the
-- wall. The 134 failures already in the fleet queue are a separate one-off load.

BEGIN TRANSACTION;

CREATE TABLE page_failure_reason_vocab (
    reason     TEXT PRIMARY KEY,
    page_owned INTEGER NOT NULL CHECK (page_owned IN (0, 1)),
    note       TEXT NOT NULL
);
INSERT INTO page_failure_reason_vocab (reason, page_owned, note) VALUES
    ('cut-answer', 1,
     'the engine stopped before its answer was complete; final at the run''s key'),
    ('oversize', 1,
     'the page is larger than the pass''s bound at its render; final at the run''s key'),
    ('render', 1,
     'the document opened and this page would not rasterise; final at the run''s key'),
    ('timeout', 1,
     'the engine did not answer in time while it was otherwise healthy; final at the run''s key'),
    ('operator-page', 1,
     'an operator judged the fault to be the page''s own; final at the run''s key'),
    ('server', 0,
     'the engine''s server failed while reading the page; transient'),
    ('document-bytes', 0,
     'the document''s bytes were missing or would not open where the page was read; transient'),
    ('lease-expired', 0,
     'the reader holding the page stopped answering on its last attempt; transient'),
    ('operator', 0,
     'an operator stopped the page for a reason that is not the page''s; transient'),
    ('unclassified', 0,
     'the producer recorded no known reason; the detail carries its words; transient');

CREATE TABLE ocr_page_failure (
    run_id  INTEGER NOT NULL REFERENCES ocr_run (run_id),
    page_no INTEGER NOT NULL CHECK (page_no >= 1),
    reason  TEXT NOT NULL REFERENCES page_failure_reason_vocab (reason),
    detail  TEXT CHECK (detail IS NULL OR (detail <> '' AND length(detail) <= 500)),
    PRIMARY KEY (run_id, page_no)
);

-- A failed page belongs to a pass that attempted pages: `read` (some pages read, some not) or
-- `failed` (none read). `skipped` and `not-paginable` attempted none. A run that does not exist
-- is refused here too, so the rule holds with foreign keys off.
CREATE TRIGGER ocr_page_failure_names_a_run_that_attempted_pages
BEFORE INSERT ON ocr_page_failure
WHEN NOT EXISTS (SELECT 1 FROM ocr_run r
                  WHERE r.run_id = NEW.run_id AND r.outcome IN ('read', 'failed'))
BEGIN
    SELECT RAISE(ABORT, 'ADR 0024 Owed 2: a page failure names a read or failed run');
END;

-- Never more rows than the run counted. The loader writes exactly `pages_failed` rows or none;
-- fewer is a run whose producer gave no list, which is every run before this migration. The
-- text layer's runs count 0, so they can carry none.
CREATE TRIGGER ocr_page_failure_within_the_runs_count
BEFORE INSERT ON ocr_page_failure
WHEN (SELECT COUNT(*) FROM ocr_page_failure f WHERE f.run_id = NEW.run_id)
     >= (SELECT r.pages_failed FROM ocr_run r WHERE r.run_id = NEW.run_id)
BEGIN
    SELECT RAISE(ABORT, 'ADR 0024 Owed 2: a run carries no more page failures than it counted');
END;

-- append-only, 0029's idiom
CREATE TRIGGER ocr_page_failure_is_never_updated
BEFORE UPDATE ON ocr_page_failure
BEGIN
    SELECT RAISE(ABORT, 'ADR 0024 Owed 2: a page failure is append-only');
END;

CREATE TRIGGER ocr_page_failure_is_never_deleted
BEFORE DELETE ON ocr_page_failure
BEGIN
    SELECT RAISE(ABORT, 'ADR 0024 Owed 2: a page failure is append-only');
END;

PRAGMA user_version = 31;

COMMIT;
