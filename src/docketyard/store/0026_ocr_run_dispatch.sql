-- Migration 0026: a reading names the dispatch it answers (ADR 0024 § Owed 5, settled by the
-- operator 2026-09-11 on schema-critic's report; the ADR's addendum of that date).
--
-- THE GAP. `dispatch.unanswered` asked whether ANY successful text-layer reading of a document
-- was dated after its dispatch. A hand `text load` of a root read on another machine could
-- satisfy that and clear the halt for documents the instance's container never read —
-- a narrowing, not a proof, and the ADR said so.
--
-- THE SHAPE. `ocr_run.dispatch_id` references `extraction_dispatch`. The stage stamps it with
-- the dispatch the container QUOTED in its record (`dispatched_at`, echoed) and checked at
-- admit; a record that quotes none is refused, and a hand load never stamps. The halt becomes
-- a join: a dispatch is answered when a `read` row names it. `extraction_dispatch` gains
-- nothing — it has one writer by construction (`text/dispatch.py`).
--
-- WHAT NULL MEANS: no dispatch of the instance's stage is answered by this row. That is
-- exactly true of every row a hand load writes, and of all 89,019 rows production held when
-- this was decided (measured 2026-09-10) — no dispatch existed before 2026-09-10 23:45:17.
--
-- RETIRED: migration 0023's "`dispatch_id` … nothing may cite it". A reading now cites one.
-- With foreign keys ON, a hand DELETE of an ANSWERED dispatch fails. With them OFF (a sqlite3
-- shell's default) it succeeds, and the damage is QUIET, not loud: `dispatch_id` is a rowid
-- with no AUTOINCREMENT, so deleting the newest cited dispatch lets the next one reuse its
-- integer, and the reading then names ANOTHER document's dispatch with every check passing
-- (schema-critic, 2026-09-11). Do not delete dispatches. The reset D4 designed is the pin
-- bump, and it still works: attempts are counted per pin. ON DELETE SET NULL was refused — it
-- would silently turn a stage reading into what reads as a hand load.
--
-- CORRECTED PREMISE. Migration 0024 and ADR 0024 D6 say SQLite "cannot add a foreign key by
-- ALTER". That is true of an existing column; `ADD COLUMN … REFERENCES` is legal for a new
-- one whose default is NULL, which is what this is. SQLite splices the column's definition
-- into `ocr_run`'s stored CREATE TABLE, which `dump.py` publishes as `schema.sql` — so no
-- comment sits inside the statement.
--
-- READINGS ALREADY LANDED. The stage has been landing readings since 2026-09-10 23:45 with no
-- column to stamp. Left NULL they would say "no stage dispatch answered" — false — so they are
-- stamped HERE, under a rule of the migration's own that is narrower than the loader's and
-- only where it is unambiguous: a text-layer/native run with EXACTLY ONE dispatch of its
-- document, pinned to that run's very method and version, at or before its `ran_at` and no
-- more than 24 hours before it (`dispatch.AUTHORISED_HOURS` = `EXTRACT_RETRY_HOURS` ×
-- (attempts + 1), a constant copied because a migration cannot import one; a test holds the
-- two together). The DEPLOY lands the old container's records first — stop `extract`, let one
-- pass admit and load them, stop `ingest` — so nothing lands unstamped between the last pass
-- and this (infra/deploy/README.md). A `correction` row names the boundary, as migration
-- 0022's does, and counts the rows it could not stamp: these stamps were worked out by the
-- migration; every later one was quoted by the container. A fresh store gets no row.
-- `strftime(…, '-24 hours')` keeps the `T…+00:00` form both tables store; `datetime()` would
-- not compare.

BEGIN TRANSACTION;

ALTER TABLE ocr_run ADD COLUMN dispatch_id INTEGER REFERENCES extraction_dispatch (dispatch_id);

-- the halt's probe, and the parent-side key check on a DELETE, would each scan ocr_run without it
CREATE INDEX ocr_run_by_dispatch ON ocr_run (dispatch_id) WHERE dispatch_id IS NOT NULL;

UPDATE ocr_run
   SET dispatch_id = (
       SELECT x.dispatch_id FROM extraction_dispatch x
        WHERE x.document_sha256 = ocr_run.document_sha256
          AND x.pinned_method = ocr_run.method
          AND x.pinned_method_version = ocr_run.method_version
          AND x.dispatched_at <= ocr_run.ran_at
          AND x.dispatched_at >= strftime('%Y-%m-%dT%H:%M:%S+00:00', ocr_run.ran_at, '-24 hours'))
 WHERE reading_channel = 'text-layer' AND render_profile = 'native'
   AND (SELECT COUNT(*) FROM extraction_dispatch x
         WHERE x.document_sha256 = ocr_run.document_sha256
           AND x.pinned_method = ocr_run.method
           AND x.pinned_method_version = ocr_run.method_version
           AND x.dispatched_at <= ocr_run.ran_at
           AND x.dispatched_at >= strftime('%Y-%m-%dT%H:%M:%S+00:00', ocr_run.ran_at, '-24 hours')
       ) = 1;

INSERT INTO correction (target_table, target_key, note, method, method_version, asserted_at)
SELECT 'ocr_run',
       'dispatch_id',
       'Migration 0026 added dispatch_id after the text stage had already landed readings.'
       || ' In this store the ' || COUNT(*) || ' rows with run_id <= ' || MAX(run_id)
       || ' that carry a dispatch_id were stamped by the migration, not quoted by the'
       || ' container: a text-layer/native run with exactly one dispatch of its document,'
       || ' pinned to that run''s method and version, at or before ran_at and within 24 hours'
       || ' of it. '
       || (SELECT COUNT(*) FROM ocr_run r
            WHERE r.dispatch_id IS NULL
              AND r.reading_channel = 'text-layer' AND r.render_profile = 'native'
              AND EXISTS (SELECT 1 FROM extraction_dispatch x
                           WHERE x.document_sha256 = r.document_sha256
                             AND x.pinned_method = r.method
                             AND x.pinned_method_version = r.method_version))
       || ' rows at a version a dispatch was pinned to were left NULL: no single dispatch'
       || ' could be named. Every later stamp is the dispatch the container quoted, checked'
       || ' when the stage admitted its record.',
       'migration-0026',
       'unversioned',
       strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')
  FROM ocr_run
 WHERE dispatch_id IS NOT NULL
 GROUP BY 1, 2
HAVING COUNT(*) > 0;

PRAGMA user_version = 26;

COMMIT;
