-- Migration 0030's pre-check (ADR 0018 addendum of 2026-09-15, the veto's trigger). Run
-- READ-ONLY on production BEFORE the wall, at schema 29: it lists every `suppress` declaration
-- whose measurement is not a false-veto rate on its own channel, and every row of a declared
-- triple not measured on a rate. Any row here aborts the migration whole.
--
-- A SECOND COPY of the guard's two SELECTs in `src/docketyard/store/0030_veto_trigger.sql`,
-- because they run inside the migration. tests/test_citator_veto_trigger.py runs both over one
-- store and requires the same answer; change them together.
SELECT what, id
  FROM (
SELECT 'declaration' AS what, a.method_row_id AS id
  FROM assertion_method a
 WHERE a.target_table = 'citation_resolution' AND a.role = 'suppress'
   AND NOT EXISTS (SELECT 1 FROM class_measurement m
                    WHERE m.measurement_id = a.score_row_id
                      AND m.measured_target = 'citation_resolution'
                      AND m.reading_channel = a.reading_channel
                      AND m.false_veto_rate IS NOT NULL)
UNION ALL
SELECT 'row', r.resolution_id
  FROM citation_resolution r
 WHERE EXISTS (SELECT 1 FROM assertion_method a
                WHERE a.target_table = 'citation_resolution' AND a.role = 'suppress'
                  AND a.method = r.method AND a.method_version = r.method_version
                  AND a.reading_channel = r.reading_channel)
   AND NOT (r.confidence_state = 'measured'
            AND EXISTS (SELECT 1 FROM class_measurement m
                         WHERE m.measurement_id = r.score_row_id
                           AND m.false_veto_rate IS NOT NULL))
  )
 ORDER BY what, id
