-- Migration 0030 — the veto's trigger (migration 0014's owed item 7; ADR 0018 D7 and its
-- addendum of 2026-09-15, PROPOSED).
--
-- 0014 made a `suppress` declaration point at a `citation_resolution` measurement and left two
-- cross-row conditions as prose, "owed with the veto": that the measurement carries a false-veto
-- rate rather than a recall, and that the rows a suppress method writes are `measured`. Both are
-- triggers here, with the rules the operator added (2026-09-15) and the schema critic's:
--
--   1. a triple (method, method_version, reading_channel) declared `suppress` in ANY
--      `rank_version` binds its `citation_resolution` rows, which carry no `rank_version`;
--   2. a bound row is `measured`, and its own `score_row_id` names a measurement carrying a
--      non-NULL `false_veto_rate`;
--   3. a declaration's measurement carries `false_veto_rate` and was measured on the
--      declaration's OWN `reading_channel`;
--   4. a measurement is never changed or removed; a re-score is a new row (ADR 0018 D8, which
--      nothing held until now). Every UPDATE and DELETE of `class_measurement` is refused, and so
--      is an INSERT that would collide with a row on either unique key — `measurement_id` or
--      `class_measurement_identity` (0014) — because `INSERT OR REPLACE` deletes the row it
--      collides with WITHOUT firing a DELETE trigger, so the INSERT is where it is caught. A
--      plain duplicate card therefore fails with this trigger's message, not "UNIQUE constraint";
--   5. declaring a triple `suppress`, by INSERT or UPDATE, is refused while any row of it, live
--      or superseded, fails 2.
--
-- So a triple once declared `suppress`, or one that ever wrote a non-conforming row, is escaped
-- only by a new `method_version`.
--
-- A NULL `score_row_id` or another stage's measurement on a declaration is left to 0014's CHECKs,
-- which hold whatever `PRAGMA foreign_keys` says; the triggers below gate on the stage so those
-- CHECKs stay the refusal a test can name.
--
-- NOTHING DECLARES A VETO TODAY, and nothing updates, deletes or replaces a measurement (the
-- repository searched 2026-09-15). The guard below proves the first rather than assuming it: a
-- store holding a violation refuses this migration whole. Its two SELECTs, run bare, name the
-- rows; `infra/deploy/0030-precheck.sql` is a copy for production before the wall, and
-- tests/test_citator_veto_trigger.py requires the two to agree.
--
-- ONE LITERAL PER RAISE. Production's SQLite (Debian 13's 3.46.1) refuses a message built with
-- `||` as a syntax error (migration 0029, 2026-09-13).
--
-- A REBUILD OF ANY OF THE THREE TABLES MUST DROP AND RECREATE WHAT NAMES THEM. 0028's procedure
-- (create, copy, DROP, RENAME) fails at the RENAME while a view or another table's trigger names
-- the table in its body (0029's header, tested on 3.46.1), and the DROP takes the table's own
-- triggers with it. So, besides each table's indexes:
--
--   citation_resolution  drop first: the view `citation_reading_residue` (0029, whose `decided`
--                        column reads it) and the two `assertion_method_veto_is_not_declared_
--                        over_unmeasured_rows*` triggers; recreate those and the two
--                        `citation_resolution_veto_row_is_measured_on_a_rate*` triggers.
--   assertion_method     drop first: the two `citation_resolution_veto_row_*` triggers; recreate
--                        those and the four `assertion_method_veto_*` triggers.
--   class_measurement    drop first: the four `assertion_method_veto_*` and the two
--                        `citation_resolution_veto_row_*` triggers; recreate those, and the three
--                        `class_measurement_*` append-only triggers AFTER the copy.
--
-- A FUTURE COLUMN BACKFILL on `class_measurement` (an ALTER ADD then an UPDATE) must drop the
-- three `class_measurement_*` triggers and recreate them inside its own transaction, or use the
-- rebuild procedure above: the UPDATE is otherwise refused.
--
-- All three tables are in `dump.HELD_TABLES`, so the snapshot drops these triggers with them.

BEGIN TRANSACTION;

-- ---------------------------------------------------------------------------
-- The guard: no existing row may already break what the triggers will hold
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE m0030_violation (what TEXT, id INTEGER);
CREATE TEMP TRIGGER m0030_violation_aborts BEFORE INSERT ON m0030_violation
BEGIN
    SELECT RAISE(ROLLBACK, 'migration 0030: a suppress declaration or a row it binds already breaks the veto trigger; nothing was applied. infra/deploy/0030-precheck.sql names the rows.');
END;

INSERT INTO m0030_violation
SELECT 'declaration', a.method_row_id
  FROM assertion_method a
 WHERE a.target_table = 'citation_resolution' AND a.role = 'suppress'
   AND NOT EXISTS (SELECT 1 FROM class_measurement m
                    WHERE m.measurement_id = a.score_row_id
                      AND m.measured_target = 'citation_resolution'
                      AND m.reading_channel = a.reading_channel
                      AND m.false_veto_rate IS NOT NULL);

INSERT INTO m0030_violation
SELECT 'row', r.resolution_id
  FROM citation_resolution r
 WHERE EXISTS (SELECT 1 FROM assertion_method a
                WHERE a.target_table = 'citation_resolution' AND a.role = 'suppress'
                  AND a.method = r.method AND a.method_version = r.method_version
                  AND a.reading_channel = r.reading_channel)
   AND NOT (r.confidence_state = 'measured'
            AND EXISTS (SELECT 1 FROM class_measurement m
                         WHERE m.measurement_id = r.score_row_id
                           AND m.false_veto_rate IS NOT NULL));

-- dropped before COMMIT, as 0029's are: the migrating connection is handed to the app
DROP TRIGGER temp.m0030_violation_aborts;
DROP TABLE temp.m0030_violation;

-- ---------------------------------------------------------------------------
-- assertion_method: a declaration is measured on a rate, on its own channel (rule 3)
-- ---------------------------------------------------------------------------
CREATE TRIGGER assertion_method_veto_is_measured_on_its_own_channel
BEFORE INSERT ON assertion_method
WHEN NEW.target_table = 'citation_resolution' AND NEW.role = 'suppress'
 AND NEW.score_row_id IS NOT NULL AND NEW.measured_target = 'citation_resolution'
 AND NOT EXISTS (SELECT 1 FROM class_measurement m
                  WHERE m.measurement_id = NEW.score_row_id
                    AND m.measured_target = 'citation_resolution'
                    AND m.reading_channel = NEW.reading_channel
                    AND m.false_veto_rate IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0018 D7: a suppress declaration names a false-veto rate measured on its own reading channel');
END;

CREATE TRIGGER assertion_method_veto_is_measured_on_its_own_channel_on_update
BEFORE UPDATE OF target_table, role, reading_channel, measured_target, score_row_id
ON assertion_method
WHEN NEW.target_table = 'citation_resolution' AND NEW.role = 'suppress'
 AND NEW.score_row_id IS NOT NULL AND NEW.measured_target = 'citation_resolution'
 AND NOT EXISTS (SELECT 1 FROM class_measurement m
                  WHERE m.measurement_id = NEW.score_row_id
                    AND m.measured_target = 'citation_resolution'
                    AND m.reading_channel = NEW.reading_channel
                    AND m.false_veto_rate IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0018 D7: a suppress declaration names a false-veto rate measured on its own reading channel');
END;

-- ---------------------------------------------------------------------------
-- assertion_method: no declaration over rows that do not conform (rule 5)
-- ---------------------------------------------------------------------------
CREATE TRIGGER assertion_method_veto_is_not_declared_over_unmeasured_rows
BEFORE INSERT ON assertion_method
WHEN NEW.target_table = 'citation_resolution' AND NEW.role = 'suppress'
 AND EXISTS (SELECT 1 FROM citation_resolution r
              WHERE r.method = NEW.method AND r.method_version = NEW.method_version
                AND r.reading_channel = NEW.reading_channel
                AND NOT (r.confidence_state = 'measured'
                         AND EXISTS (SELECT 1 FROM class_measurement m
                                      WHERE m.measurement_id = r.score_row_id
                                        AND m.false_veto_rate IS NOT NULL)))
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0018 D7: a triple is not declared suppress while any of its rows lacks a measured false-veto rate');
END;

CREATE TRIGGER assertion_method_veto_is_not_declared_over_unmeasured_rows_on_update
BEFORE UPDATE OF target_table, method, method_version, reading_channel, role
ON assertion_method
WHEN NEW.target_table = 'citation_resolution' AND NEW.role = 'suppress'
 AND EXISTS (SELECT 1 FROM citation_resolution r
              WHERE r.method = NEW.method AND r.method_version = NEW.method_version
                AND r.reading_channel = NEW.reading_channel
                AND NOT (r.confidence_state = 'measured'
                         AND EXISTS (SELECT 1 FROM class_measurement m
                                      WHERE m.measurement_id = r.score_row_id
                                        AND m.false_veto_rate IS NOT NULL)))
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0018 D7: a triple is not declared suppress while any of its rows lacks a measured false-veto rate');
END;

-- ---------------------------------------------------------------------------
-- citation_resolution: a bound row is measured on a rate (rules 1 and 2)
-- ---------------------------------------------------------------------------
CREATE TRIGGER citation_resolution_veto_row_is_measured_on_a_rate
BEFORE INSERT ON citation_resolution
WHEN EXISTS (SELECT 1 FROM assertion_method a
              WHERE a.target_table = 'citation_resolution' AND a.role = 'suppress'
                AND a.method = NEW.method AND a.method_version = NEW.method_version
                AND a.reading_channel = NEW.reading_channel)
 AND NOT (NEW.confidence_state = 'measured'
          AND EXISTS (SELECT 1 FROM class_measurement m
                       WHERE m.measurement_id = NEW.score_row_id
                         AND m.false_veto_rate IS NOT NULL))
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0018 D7: a row of a suppress method is measured and names a false-veto rate');
END;

CREATE TRIGGER citation_resolution_veto_row_is_measured_on_a_rate_on_update
BEFORE UPDATE OF method, method_version, reading_channel, confidence_state, score_row_id
ON citation_resolution
WHEN EXISTS (SELECT 1 FROM assertion_method a
              WHERE a.target_table = 'citation_resolution' AND a.role = 'suppress'
                AND a.method = NEW.method AND a.method_version = NEW.method_version
                AND a.reading_channel = NEW.reading_channel)
 AND NOT (NEW.confidence_state = 'measured'
          AND EXISTS (SELECT 1 FROM class_measurement m
                       WHERE m.measurement_id = NEW.score_row_id
                         AND m.false_veto_rate IS NOT NULL))
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0018 D7: a row of a suppress method is measured and names a false-veto rate');
END;

-- ---------------------------------------------------------------------------
-- class_measurement: append-only (rule 4; ADR 0018 D8)
-- ---------------------------------------------------------------------------
CREATE TRIGGER class_measurement_is_never_updated
BEFORE UPDATE ON class_measurement
BEGIN
    SELECT RAISE(ABORT, 'ADR 0018 D8: a measurement is append-only; a re-score is a new row');
END;

CREATE TRIGGER class_measurement_is_never_deleted
BEFORE DELETE ON class_measurement
BEGIN
    SELECT RAISE(ABORT, 'ADR 0018 D8: a measurement is append-only; a re-score is a new row');
END;

CREATE TRIGGER class_measurement_is_never_replaced
BEFORE INSERT ON class_measurement
WHEN EXISTS (SELECT 1 FROM class_measurement m WHERE m.measurement_id = NEW.measurement_id)
  OR EXISTS (SELECT 1 FROM class_measurement m
              WHERE m.measured_target = NEW.measured_target
                AND m.class = NEW.class
                AND m.extraction_method = NEW.extraction_method
                AND m.extraction_method_version = NEW.extraction_method_version
                AND COALESCE(m.resolution_method, '') = COALESCE(NEW.resolution_method, '')
                AND COALESCE(m.resolution_method_version, '')
                    = COALESCE(NEW.resolution_method_version, '')
                AND m.reading_channel = NEW.reading_channel
                AND COALESCE(m.projection_rule_version, '')
                    = COALESCE(NEW.projection_rule_version, '')
                AND m.benchmark_date = NEW.benchmark_date)
BEGIN
    SELECT RAISE(ABORT, 'ADR 0018 D8: a measurement is append-only; a re-score is a new row');
END;

PRAGMA user_version = 30;

COMMIT;
