-- Migration 0025: the work class exists, so a work-level answer can be scored — and a
-- resolution row says which class it was stamped from.
--
-- ONE ROW IN A VOCABULARY, and everything else about the first half is in the loader.
-- Migration 0014 keyed `class_vocab` on (measured_target, class) so "a class cannot be
-- attached to a stage that never measured it", and seeded it with the classes something had
-- actually measured. `('citation_resolution', 'work')` was not among them: `resolve` did not
-- reach a document until 2026-09-05, and nothing had scored one on 2026-09-10 either. Its
-- absence is what `project.cited_by(work_id=...)` refuses on — a class nobody has scored is
-- unmeasured and projects nothing (ADR 0017 D3) — and that refusal is not weakened here.
--
-- WHAT THIS ROW DOES AND DOES NOT DO. It makes a work measurement WRITABLE. It does not make
-- one, and `class_measurement` still holds none: the gate `project.py` enforces is on a live
-- resolution actually stamped FROM a work measurement, which one INSERT into a vocabulary
-- cannot satisfy. So the work grain stays shut on the day this applies, exactly as it was the
-- day before, and opens when the sixty-decision sheet's work column is checked and declared
-- (`docs/runbook.md` § Blocker 4, the operator's decision of 2026-09-10).
--
-- WHY THE VOCABULARY MOVES BEFORE THE MEASUREMENT EXISTS, rather than with it. The card is
-- declared by `citator declare`, which runs on the instance against the deployed build: a
-- measurement whose class the store does not admit fails on a foreign key at the moment the
-- operator is declaring it, and the fix would then be a deploy. The vocabulary is the cheap
-- half and it ships first. This is migration 0014's own sequencing — it shipped the citator
-- block empty and let the code fill it — and the safety is that an empty class is inert.
--
-- WHY 'projection' GAINS NO 'work' ROW. Not because the work grain is shown somewhere other
-- than the projection — `CITED_BY_WORK` IS the projection, `_TERMS` plus one predicate, and an
-- earlier draft of this header said otherwise (schema-critic, 2026-09-10). The ground is that
-- nothing would be stamped from such a class: the loader writes the ('projection', 'docket')
-- measurement onto span judgements and onto nothing else, so a work row at the projection
-- stage would be shape with no writer and a figure with no rows — which is the condition ADR
-- 0017 § Consequences records the cost of. The day a work-level projection is measured on its
-- own, it is one more row here.
--
-- AND THE ROW SAYS WHICH CLASS IT CARRIES (the operator's decision, 2026-09-10, on the schema
-- critic's report). Until now `citation_resolution` foreign-keyed `(score_row_id,
-- measured_target)`, and BOTH classes of a resolution measurement satisfy that pair
-- identically — so nothing in the STORE stopped a docket-only row being stamped from the work
-- figure, or the reverse. Only Python did. That was tolerable while one class existed and is
-- not now, because the two are measured by different instruments over different populations
-- (the scorer comparing sets; the operator judging claims one at a time), so neither figure
-- bounds the other and a row asserting MORE can carry a higher confidence than the row beside
-- it asserting less. The class belongs where a row can be read without a join.
--
-- A COMPOSITE FOREIGN KEY IS A TABLE CONSTRAINT, so this is a rebuild and not an `ALTER` —
-- migration 0019's idiom, and the reason it is taken TODAY: every citator table holds zero
-- rows in production (measured 2026-09-10), so the copy below moves nothing there, and after
-- the first load this would be a rebuild of the largest table in the citator.
-- `citation_resolution` is in `dump.HELD_TABLES`, so no published shape moves and
-- `JSON_SHAPE` does not bump.
--
-- Nothing else changes: every other CHECK, key and index is carried across verbatim, and the
-- eight other tables that foreign-key `(measurement_id, measured_target)` keep doing so —
-- each carries one class and has nothing to disambiguate.

BEGIN TRANSACTION;

INSERT INTO class_vocab VALUES
    ('citation_resolution', 'work');

-- The parent key for the triple. `measurement_id` is already the primary key, so this index
-- adds no constraint the table did not have — it exists because SQLite requires a unique
-- index over exactly the referenced columns before it will accept the foreign key below.
CREATE UNIQUE INDEX class_measurement_classed
    ON class_measurement (measurement_id, measured_target, class);

CREATE TABLE citation_resolution_rebuilt (
    resolution_id          INTEGER PRIMARY KEY,
    citing_document        TEXT NOT NULL,
    page                   INTEGER NOT NULL,
    target_kind            TEXT NOT NULL,
    target_key             TEXT NOT NULL,
    method                 TEXT NOT NULL,
    method_version         TEXT NOT NULL,
    reading_channel        TEXT NOT NULL REFERENCES reading_vocab (reading_channel),
    outcome                TEXT NOT NULL REFERENCES outcome_vocab (outcome),
    -- OWED ITEM 3: one resolve row asserts the COMPLETE outcome. The family test reads the
    -- docket column and query 2 keys on the decision column, and they must come off the
    -- SAME resolution or the query joins one method's work-level answer to another's
    -- docket-level one. A citation resolves to a work only when the text names a document
    -- and exactly one stb_decision_id in that docket matches; the phrase's own verb gates
    -- which column is matched ('served <date>' matches service_date; 'decided <date>'
    -- matches nothing until a decided-date assertion exists, and stays at docket level).
    cited_docket_id        INTEGER REFERENCES docket (docket_id),
    cited_decision_id      TEXT REFERENCES decision_work (stb_decision_id),
    asserted_from_document TEXT REFERENCES document (document_sha256),
    asserted_from_capture  INTEGER REFERENCES capture (capture_id),
    source_location        TEXT,
    asserted_at            TEXT NOT NULL,
    confidence             REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    confidence_state       TEXT NOT NULL CHECK (confidence_state IN (
                               'measured', 'human', 'unmeasured', 'not-applicable')),
    -- 'projection' is NOT permitted here, and the asymmetry with citation_judgement is the
    -- whole point: the span test's own figure IS the projection's, while a resolution's is
    -- not. This is the one path by which a row could display 98.0% beside a resolution —
    -- the error ADR 0017 made four times, in the table built to stop it.
    measured_target        TEXT CHECK (measured_target IS NULL
                                       OR measured_target = 'citation_resolution'),
    -- WHICH CLASS OF THAT STAGE. 'docket' where the row names a proceeding, 'work' where it
    -- also names a document; NULL exactly when nothing stamped it. The vocabulary is not
    -- restated in a CHECK: the foreign key below reaches `class_measurement`, which reaches
    -- `class_vocab`, so the legal values stay the ones something has actually measured.
    measured_class         TEXT,
    score_row_id           INTEGER,
    superseded_by          INTEGER REFERENCES citation_resolution_rebuilt (resolution_id),
    CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL)),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    -- all three move together, or the triple below is satisfied by an accident
    CHECK ((score_row_id IS NULL) = (measured_class IS NULL)),
    -- the outcome and the columns must agree, or `outcome` is decoration
    CHECK ((outcome IN ('resolved', 'repaired')) = (cited_docket_id IS NOT NULL)),
    -- a work is always inside a docket; a decision id without one is not a resolution
    CHECK (cited_decision_id IS NULL OR cited_docket_id IS NOT NULL),
    -- A ROW THAT NAMES NO DOCUMENT CANNOT CARRY THE WORK FIGURE. That is the half of the
    -- rule a foreign key cannot state, and it is the direction that would overclaim. The
    -- other half — that a row naming a document IS work-stamped — is deliberately not a
    -- constraint: it is false for every row loaded before the work class was scored, and
    -- those rows are legitimate and stay readable (`project.unstamped_work_rows` counts
    -- them so the gap is a number rather than a silence).
    CHECK (measured_class <> 'work' OR cited_decision_id IS NOT NULL),
    FOREIGN KEY (score_row_id, measured_target, measured_class)
        REFERENCES class_measurement (measurement_id, measured_target, class),
    FOREIGN KEY (citing_document, page, target_kind, target_key)
        REFERENCES citation_key (citing_document, page, target_kind, target_key)
);

-- The class of every row already stamped, read from the measurement it points at. Before this
-- migration one class existed, so the answer is 'docket' wherever anything is stamped at all;
-- it is written as a join rather than as a literal so the migration states the rule instead
-- of assuming the history.
INSERT INTO citation_resolution_rebuilt (
    resolution_id, citing_document, page, target_kind, target_key, method, method_version,
    reading_channel, outcome, cited_docket_id, cited_decision_id, asserted_from_document,
    asserted_from_capture, source_location, asserted_at, confidence, confidence_state,
    measured_target, measured_class, score_row_id, superseded_by)
SELECT r.resolution_id, r.citing_document, r.page, r.target_kind, r.target_key, r.method,
       r.method_version, r.reading_channel, r.outcome, r.cited_docket_id, r.cited_decision_id,
       r.asserted_from_document, r.asserted_from_capture, r.source_location, r.asserted_at,
       r.confidence, r.confidence_state, r.measured_target, m.class, r.score_row_id,
       r.superseded_by
FROM citation_resolution r
LEFT JOIN class_measurement m ON m.measurement_id  = r.score_row_id
                             AND m.measured_target = r.measured_target;

DROP TABLE citation_resolution;
ALTER TABLE citation_resolution_rebuilt RENAME TO citation_resolution;

CREATE UNIQUE INDEX citation_resolution_live ON citation_resolution
    (citing_document, page, target_kind, target_key, method, method_version, reading_channel)
    WHERE superseded_by IS NULL;
-- the "cited by" read: every live resolution naming this work, then this docket
CREATE INDEX citation_resolution_by_decision ON citation_resolution (cited_decision_id)
    WHERE superseded_by IS NULL AND cited_decision_id IS NOT NULL;
CREATE INDEX citation_resolution_by_docket ON citation_resolution (cited_docket_id)
    WHERE superseded_by IS NULL AND cited_docket_id IS NOT NULL;

PRAGMA user_version = 25;

COMMIT;
