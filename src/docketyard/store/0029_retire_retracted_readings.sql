-- Migration 0029 — a retraction retires the key's readings too (ADR 0018 addendum, Accepted
-- 2026-09-13).
--
-- `citator load` retracted a key by retiring its `citation` alone (ADR 0018 D2), and the key's
-- readings stayed live with nothing to hang on. v2026.09.15's re-load left 903 of them; no finder
-- emits those keys again, so no pass can replace them. They project nothing (every consumer joins
-- a live `citation`), but they trip `load.SharedPage` and sit for ever in ADR 0026's `pre-0026`
-- count. From here a retraction retires them, and this migration retires the ones already there.
--
-- NOT A HELD-BACK EDIT. A retired reading's columns are untouched except the pointer and the
-- date, set in one statement as migration 0028's triggers require; what did it, and why, is a
-- ROW of its own below.
--
-- `citation_reading` STOPS BEING REFERENCED ONLY BY ITSELF (0028:13-15 relied on that): the
-- retirement row is its child, and `citation`'s, so a later rebuild of either must carry it.
--
-- AND A REBUILD OF EITHER MUST DROP WHAT NAMES THEM FIRST. The view `citation_reading_residue`
-- and the retirement triggers below name `citation_reading` and `citation` in their bodies, and
-- 0028's procedure (create, copy, DROP, RENAME) FAILS at the RENAME with them in place — tested on
-- 3.46.1: "error in view …: no such table". Drop the view and those triggers before the DROP, and
-- recreate them after the RENAME; tests/test_citator_reading_retirement.py runs the procedure.

BEGIN TRANSACTION;

-- ---------------------------------------------------------------------------
-- Why a reading was retired: a vocabulary, so a second reason is a row and not a rebuild
-- ---------------------------------------------------------------------------
CREATE TABLE retirement_reason_vocab (
    reason TEXT PRIMARY KEY,
    note   TEXT NOT NULL
);
INSERT INTO retirement_reason_vocab (reason, note) VALUES
    ('retracted-key',
     'the key''s citation was retracted by a finder that no longer emits it; the method named is'
     || ' the pass or migration that retired the reading');

-- ---------------------------------------------------------------------------
-- The retirement row (ADR 0018 addendum, decision 2)
-- ---------------------------------------------------------------------------
-- A RECORD OF AN ACTION, like `review_action`, and NOT an ADR 0007 assertion: it claims nothing
-- about the document, so it carries no confidence and no source. The operator's decision.
--
-- Keyed by `reading_id` because a reading is retired once: `superseded_at` is append-only
-- (0028:269-274). A surrogate id and not a natural key, against ADR 0018 D1's "never a surrogate",
-- because what is named is one ROW of a key's history, not the key.
CREATE TABLE citation_reading_retirement (
    reading_id     INTEGER PRIMARY KEY REFERENCES citation_reading (reading_id),
    -- the retraction: the key's `citation` row with the highest id, retired at itself or pointed
    -- at another key (the triggers below hold it to that)
    citation_id    INTEGER NOT NULL REFERENCES citation (citation_id),
    reason         TEXT NOT NULL REFERENCES retirement_reason_vocab (reason),
    method         TEXT NOT NULL CHECK (method <> ''),
    method_version TEXT NOT NULL CHECK (method_version <> ''),
    -- equal to the reading's `superseded_at`, which the first trigger enforces: the date is
    -- stored twice, and nothing else would hold the copies together
    retired_at     TEXT NOT NULL CHECK (retired_at <> '')
);

CREATE TRIGGER citation_reading_retirement_names_a_retired_reading
BEFORE INSERT ON citation_reading_retirement
WHEN NOT EXISTS (SELECT 1 FROM citation_reading r
                  WHERE r.reading_id = NEW.reading_id
                    AND r.superseded_by IS NOT NULL
                    AND r.superseded_at = NEW.retired_at)
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0018 addendum: a retirement row names a retired reading, dated as the reading is');
END;

CREATE TRIGGER citation_reading_retirement_names_the_retraction
BEFORE INSERT ON citation_reading_retirement
WHEN NOT EXISTS (
    SELECT 1
      FROM citation_reading r
      JOIN citation c ON c.citation_id = NEW.citation_id
     WHERE r.reading_id = NEW.reading_id
       AND c.citing_document = r.citing_document AND c.page = r.page
       AND c.target_kind = r.target_kind AND c.target_key = r.target_key
       AND c.citation_id = (SELECT MAX(x.citation_id) FROM citation x
                             WHERE x.citing_document = r.citing_document AND x.page = r.page
                               AND x.target_kind = r.target_kind
                               AND x.target_key = r.target_key)
       AND c.superseded_by IS NOT NULL
       AND (c.superseded_by = c.citation_id
            OR EXISTS (SELECT 1 FROM citation s
                        WHERE s.citation_id = c.superseded_by
                          AND NOT (s.citing_document = c.citing_document AND s.page = c.page
                                   AND s.target_kind = c.target_kind
                                   AND s.target_key = c.target_key)))
       AND NOT EXISTS (SELECT 1 FROM citation l
                        WHERE l.citing_document = r.citing_document AND l.page = r.page
                          AND l.target_kind = r.target_kind AND l.target_key = r.target_key
                          AND l.superseded_by IS NULL))
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0018 addendum: a retirement row names its key''s retraction, and no live citation');
END;

-- append-only, 0009:18-26's idiom
CREATE TRIGGER citation_reading_retirement_is_never_updated
BEFORE UPDATE ON citation_reading_retirement
BEGIN
    SELECT RAISE(ABORT, 'ADR 0018 addendum: a retirement row is append-only');
END;

CREATE TRIGGER citation_reading_retirement_is_never_deleted
BEFORE DELETE ON citation_reading_retirement
BEGIN
    SELECT RAISE(ABORT, 'ADR 0018 addendum: a retirement row is append-only');
END;

-- ---------------------------------------------------------------------------
-- THE RULE, ONCE (ADR 0018 addendum, decision 1)
-- ---------------------------------------------------------------------------
-- A live machine reading whose key holds no live `citation`, with the retraction it answers to,
-- where its pointer goes, and whether a person has decided the key. `citator load` reads it
-- filtered to its document; this migration reads it once below. Empty after either.
--
-- THE POINTER FOLLOWS THE SUCCESSOR'S KEY, NOT ITS ROW: the retraction points at the sub-docket
-- row that pass wrote, and a later load may have replaced that row on the same key (all 768 such
-- successors on production, 2026-09-13). The successor key's live reading on the reading's OWN
-- channel — at most one, by `citation_reading_live` — or the reading itself.
--
-- `decided` is `load._decided`'s two tests. The review key is rendered here as `keys.render`
-- renders it; tests/test_citator_reading_retirement.py pins the two together.
--
-- A SECOND COPY OF THIS SELECT lives in `infra/deploy/0029-precheck.sql`, because the runbook
-- runs it on production before this migration exists there. The same test runs both.
--
-- HELD (`dump.HELD_VIEWS`): it reads only held tables.
CREATE VIEW citation_reading_residue AS
SELECT r.reading_id,
       r.citing_document,
       r.page,
       r.target_kind,
       r.target_key,
       r.reading_channel,
       t.citation_id,
       COALESCE(
           (SELECT sr.reading_id
              FROM citation s
              JOIN citation_reading sr
                ON sr.citing_document = s.citing_document AND sr.page = s.page
               AND sr.target_kind = s.target_kind AND sr.target_key = s.target_key
               AND sr.reading_channel = r.reading_channel AND sr.superseded_by IS NULL
             WHERE s.citation_id = t.superseded_by AND s.citation_id <> t.citation_id),
           r.reading_id) AS pointer,
       (EXISTS (SELECT 1 FROM citation_resolution h
                 WHERE h.citing_document = r.citing_document AND h.page = r.page
                   AND h.target_kind = r.target_kind AND h.target_key = r.target_key
                   AND h.superseded_by IS NULL AND h.confidence_state = 'human')
        OR EXISTS (SELECT 1 FROM review_action a
                    WHERE a.target_table = 'citation_resolution' AND a.superseded_by IS NULL
                      AND a.target_key = r.citing_document || '/' || r.page || '/'
                                         || r.target_kind || '/' || r.target_key)) AS decided
  FROM citation_reading r
  JOIN citation t
    ON t.citation_id = (SELECT MAX(x.citation_id) FROM citation x
                         WHERE x.citing_document = r.citing_document AND x.page = r.page
                           AND x.target_kind = r.target_kind AND x.target_key = r.target_key)
 WHERE r.superseded_by IS NULL
   AND r.reading_channel <> 'human'
   AND t.superseded_by IS NOT NULL
   AND (t.superseded_by = t.citation_id
        OR EXISTS (SELECT 1 FROM citation o
                    WHERE o.citation_id = t.superseded_by
                      AND NOT (o.citing_document = t.citing_document AND o.page = t.page
                               AND o.target_kind = t.target_kind
                               AND o.target_key = t.target_key)))
   AND NOT EXISTS (SELECT 1 FROM citation l
                    WHERE l.citing_document = r.citing_document AND l.page = r.page
                      AND l.target_kind = r.target_kind AND l.target_key = r.target_key
                      AND l.superseded_by IS NULL);
-- The clause on `t.superseded_by` repeats the retirement trigger's own test (schema-critic,
-- 2026-09-13): without it a row this view lists could be one the trigger refuses, and a
-- RAISE(ABORT) mid-script undoes one statement, not the migration. Unreachable today — every
-- same-key repoint goes to a newer, higher id — and now a misfit stays visible here instead.

-- ---------------------------------------------------------------------------
-- The readings already stranded (ADR 0018 addendum, decision 3)
-- ---------------------------------------------------------------------------
-- ONE INSTANT, in `db.utcnow()`'s form. SQLite's `datetime('now')` writes a space where the
-- loader writes `T` and is re-read per statement, so it would neither sort beside the loader's
-- dates nor be one date across the two writes below. That instant is when the store retired
-- these readings, NOT when v2026.09.15 retracted their keys, which nothing recorded.
CREATE TEMP TABLE m0029_now AS
    SELECT strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now') AS at;

-- A KEY A PERSON DECIDED ABORTS THE WHOLE MIGRATION (the operator's decision). Production's SQLite
-- (Debian 13's 3.46.1) cannot build a RAISE message from a value, which arrived in 3.47.0, so the
-- message is fixed and the runbook's pre-check names the key. It fires before any retirement is
-- written; RAISE(ROLLBACK) also undoes the vocabulary row, the table and the view above: tested
-- on 3.46.1 to leave no table and `user_version` unchanged.
CREATE TEMP TABLE m0029_decided (reading_id INTEGER);
CREATE TEMP TRIGGER m0029_decided_aborts BEFORE INSERT ON m0029_decided
BEGIN
    SELECT RAISE(ROLLBACK,
        'migration 0029: a person has decided a key among the readings it would retire;'
        || ' nothing was applied. infra/deploy/0029-precheck.sql names the key.');
END;
INSERT INTO m0029_decided SELECT reading_id FROM citation_reading_residue WHERE decided;

-- A SNAPSHOT, read once: the UPDATE below evaluates its subqueries row by row after earlier rows
-- have changed, so reading the view there could send one row's pointer by another's half-done
-- update. No foreign keys on it: `db.migrate` runs `foreign_key_check` after the script.
CREATE TEMP TABLE m0029_residue AS
    SELECT reading_id, citation_id, pointer FROM citation_reading_residue;

UPDATE citation_reading
   SET superseded_by = (SELECT m.pointer FROM temp.m0029_residue m
                         WHERE m.reading_id = citation_reading.reading_id),
       superseded_at = (SELECT at FROM temp.m0029_now)
 WHERE reading_id IN (SELECT reading_id FROM temp.m0029_residue);

INSERT INTO citation_reading_retirement
    (reading_id, citation_id, reason, method, method_version, retired_at)
SELECT m.reading_id, m.citation_id, 'retracted-key', 'migration',
       '0029_retire_retracted_readings', n.at
  FROM temp.m0029_residue m, temp.m0029_now n;

-- DROPPED BEFORE COMMIT: `db.connect` hands this connection to the app, and a temporary object
-- lives as long as the connection — tested on 3.46.1 to survive a successful script otherwise.
DROP TRIGGER temp.m0029_decided_aborts;
DROP TABLE temp.m0029_decided;
DROP TABLE temp.m0029_residue;
DROP TABLE temp.m0029_now;

PRAGMA user_version = 29;

COMMIT;
