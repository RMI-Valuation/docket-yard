-- Migration 0031 — a page the pass failed says why (ADR 0024 § Owed 2, addendum 2026-09-15,
-- Proposed; the operator's defaults of 2026-09-15, reworked on two schema-critic passes).
--
-- `ocr_run.pages_failed` has counted the pages a pass attempted and did not read since 0018;
-- the reasons lived only in the fleet queue's `job.error`. This is the row per failed page,
-- under its run, with a reason from a vocabulary, the classifier that chose it, and — only
-- where the reason has one — a measurement in a closed shape.
--
-- A RECORD OF AN ACTION, like `citation_reading_retirement` (0029) and NOT an ADR 0007
-- assertion: it says what the pass did with the page, not what the page says, so it carries no
-- confidence block. Its provenance is its run's (method, version, render, `ran_at`) and the
-- classifier's (`classifier`, `classifier_version`), because the reason is derived from a
-- producer's words by code that can change.
--
-- `page_owned` IS THE VOCABULARY'S, NOT THE ROW'S, AND IT STATES OWNERSHIP ONLY. A page-owned
-- failure is the page's own; a failure that is not the page's is transient. NEITHER IS
-- PERMANENT: a document re-read for another reason reads every page again. A page-owned failure
-- at key K stands only while no live `document_text` row at K exists on that page — the join is
-- ocr_page_failure → ocr_run → document_text on sha, page_no, method, method_version,
-- render_profile, reading_channel, `superseded_by IS NULL`, matching by KEY and not by reading
-- role. `document_text` is held, so the reconciliation is the store's, not the snapshot's.
--
-- `detail` IS NEVER FREE TEXT. It is kept only when it matches the closed shape its reason
-- defines (`ocr_wave.DETAIL_SHAPES`, re-checked by `text/load.py`), and is NULL otherwise: an
-- exception's text can carry a path or a host into a snapshot that cannot be withdrawn. The
-- shape is not a CHECK — SQLite has no regular expressions — so the bound below is length only.
--
-- WHAT IS NOT WRITTEN HERE: a whole-document size refusal (`text/queue.py`) stays counted and
-- is not a page failure — no run exists for it to hang under (ADR 0024 § Owed 2).
--
-- PUBLIC (`dump.PUBLIC_TABLES`) with `ocr_run`; both tables' referents are public, so the
-- snapshot's `schema.sql` names nothing it drops. No prose inside the parentheses below: SQLite
-- keeps table DDL verbatim and the snapshot publishes it (0018's note).
--
-- ADDITIVE: two new tables and their triggers, no rebuild and no backfill, so not behind the
-- wall. The 134 failures already in the fleet queue are a separate one-off load
-- (`docs/deferred.md` § From the schema critic on migration 0031).

BEGIN TRANSACTION;

CREATE TABLE page_failure_reason_vocab (
    reason     TEXT PRIMARY KEY,
    page_owned INTEGER NOT NULL CHECK (page_owned IN (0, 1)),
    note       TEXT NOT NULL
);
INSERT INTO page_failure_reason_vocab (reason, page_owned, note) VALUES
    ('cut-answer', 1,
     'the engine stopped before its answer was complete; the page''s own; a document re-read'
     || ' for another reason reads it again'),
    ('oversize', 1,
     'the page is larger than the pass''s bound at its render; the page''s own; a document'
     || ' re-read for another reason reads it again'),
    ('render', 1,
     'the document opened and this page would not rasterise; the page''s own; a document'
     || ' re-read for another reason reads it again'),
    ('timeout', 1,
     'the engine did not answer in time while it was otherwise healthy; the page''s own; a'
     || ' document re-read for another reason reads it again'),
    ('operator-page', 1,
     'an operator judged the fault to be the page''s own; a document re-read for another reason'
     || ' reads it again'),
    ('server', 0,
     'the engine''s server failed while reading the page; transient'),
    ('document-bytes', 0,
     'the document''s bytes were missing or would not open where the page was read; transient'),
    ('lease-expired', 0,
     'the reader holding the page stopped answering on its last attempt; transient'),
    ('operator', 0,
     'an operator stopped the page for a reason that is not the page''s; transient'),
    ('unclassified', 0,
     'the producer recorded no known reason; transient');

CREATE TABLE ocr_page_failure (
    run_id             INTEGER NOT NULL REFERENCES ocr_run (run_id),
    page_no            INTEGER NOT NULL CHECK (page_no >= 1),
    reason             TEXT NOT NULL REFERENCES page_failure_reason_vocab (reason),
    detail             TEXT CHECK (detail IS NULL OR (detail <> '' AND length(detail) <= 500)),
    classifier         TEXT NOT NULL CHECK (classifier <> '' AND length(classifier) <= 64
                                            AND classifier NOT GLOB '*/*'),
    classifier_version TEXT NOT NULL CHECK (classifier_version <> ''
                                            AND length(classifier_version) <= 64
                                            AND classifier_version NOT GLOB '*/*'),
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
-- text layer's runs count 0, so they can carry none. NOT GUARDED: a later UPDATE of the run's
-- `pages_failed` or `outcome` under existing rows (docs/deferred.md).
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
