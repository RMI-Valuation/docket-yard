-- Migration 0030 — the veto's trigger (migration 0014's owed item 7; ADR 0018 D7 and its
-- addendum of 2026-09-15, PROPOSED).
--
-- 0014 made a `suppress` declaration point at a `citation_resolution` measurement and left two
-- cross-row conditions as prose, "owed with the veto": that the measurement carries a false-veto
-- rate rather than a recall, and that the rows a suppress method writes are `measured`. Both are
-- triggers here, with three the operator added (2026-09-15):
--
--   1. a triple (method, method_version, reading_channel) declared `suppress` in ANY
--      `rank_version` binds its `citation_resolution` rows, which carry no `rank_version`;
--   2. a bound row is `measured`, and its own `score_row_id` names a measurement carrying a
--      non-NULL `false_veto_rate`;
--   3. a declaration's measurement carries `false_veto_rate` and was measured on the
--      declaration's OWN `reading_channel`;
--   4. an UPDATE of `class_measurement` may not withdraw that rate (set it NULL) or re-point the
--      measurement (`measurement_id`, `measured_target`, and a declaration's `reading_channel`)
--      while a declaration or a bound row names it. A changed non-NULL rate is not refused;
--   5. declaring a triple `suppress`, by INSERT or UPDATE, is refused while any row of it, live
--      or superseded, fails 2.
--
-- A NULL `score_row_id` or another stage's measurement on a declaration is left to 0014's CHECKs,
-- which hold whatever `PRAGMA foreign_keys` says; the triggers below gate on the stage so those
-- CHECKs stay the refusal a test can name.
--
-- NOTHING DECLARES A VETO TODAY, so the triggers constrain no existing row. The guard below
-- proves it rather than assuming it: a store holding a violation refuses this migration whole.
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
--                        column reads it), the two `..._not_declared_over_unmeasured_rows`
--                        triggers ON assertion_method and `class_measurement_vetoing_rows_rate_
--                        is_kept`; recreate those and the two triggers ON citation_resolution.
--   assertion_method     drop first: the two triggers ON citation_resolution and the two ON
--                        class_measurement; recreate those and the four ON assertion_method.
--   class_measurement    drop first: the four triggers ON assertion_method and the two ON
--                        citation_resolution; recreate those and the two ON class_measurement.
--
-- THE PRE-CHECK is the guard's two SELECTs below, run bare: on a store where both return no row,
-- this migration applies.
--
-- All three tables are in `dump.HELD_TABLES`, so the snapshot drops these triggers with them.

BEGIN TRANSACTION;

-- ---------------------------------------------------------------------------
-- The guard: no existing row may already break what the triggers will hold
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE m0030_violation (what TEXT);
CREATE TEMP TRIGGER m0030_violation_aborts BEFORE INSERT ON m0030_violation
BEGIN
    SELECT RAISE(ROLLBACK, 'migration 0030: a suppress declaration or a row it binds already breaks the veto trigger; nothing was applied. The guard SELECTs in 0030_veto_trigger.sql name the rows.');
END;

INSERT INTO m0030_violation
SELECT 'declaration'
  FROM assertion_method a
 WHERE a.target_table = 'citation_resolution' AND a.role = 'suppress'
   AND NOT EXISTS (SELECT 1 FROM class_measurement m
                    WHERE m.measurement_id = a.score_row_id
                      AND m.measured_target = 'citation_resolution'
                      AND m.reading_channel = a.reading_channel
                      AND m.false_veto_rate IS NOT NULL);

INSERT INTO m0030_violation
SELECT 'row'
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
-- class_measurement: a veto's rate is not withdrawn or re-pointed (rule 4)
-- ---------------------------------------------------------------------------
CREATE TRIGGER class_measurement_declared_veto_rate_is_kept
BEFORE UPDATE OF measurement_id, measured_target, reading_channel, false_veto_rate
ON class_measurement
WHEN (NEW.false_veto_rate IS NULL
      OR NEW.measurement_id IS NOT OLD.measurement_id
      OR NEW.measured_target IS NOT OLD.measured_target
      OR NEW.reading_channel IS NOT OLD.reading_channel)
 AND EXISTS (SELECT 1 FROM assertion_method a
              WHERE a.target_table = 'citation_resolution' AND a.role = 'suppress'
                AND a.score_row_id = OLD.measurement_id)
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0018 D7: a false-veto rate a suppress declaration names is not withdrawn or re-pointed');
END;

CREATE TRIGGER class_measurement_vetoing_rows_rate_is_kept
BEFORE UPDATE OF measurement_id, measured_target, false_veto_rate
ON class_measurement
WHEN (NEW.false_veto_rate IS NULL
      OR NEW.measurement_id IS NOT OLD.measurement_id
      OR NEW.measured_target IS NOT OLD.measured_target)
 AND EXISTS (SELECT 1 FROM citation_resolution r
              WHERE r.score_row_id = OLD.measurement_id
                AND EXISTS (SELECT 1 FROM assertion_method a
                             WHERE a.target_table = 'citation_resolution' AND a.role = 'suppress'
                               AND a.method = r.method AND a.method_version = r.method_version
                               AND a.reading_channel = r.reading_channel))
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0018 D7: a false-veto rate a row of a suppress method names is not withdrawn or re-pointed');
END;

PRAGMA user_version = 30;

COMMIT;
