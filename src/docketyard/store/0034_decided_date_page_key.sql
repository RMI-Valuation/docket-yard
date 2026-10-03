-- Migration 0034: the decided date gets its page in the key and names the text it read.
-- ADR 0023 addendum of 2026-09-16, accepted 2026-10-03.
--
-- The operator chose on 2026-09-16 to build the decided-date extraction pass, the first writer
-- this table has had. A first writer makes the positional `ordinal` 0019 left open live, and
-- the record says where it lives: measured on the 2026-09-15 restore, 262 decision-carried
-- documents print a `Decided:` line more than once, every one of them on more than one page,
-- and one page prints two. `(document, ordinal)` cannot tell a service copy's repeat on page 9
-- from the original on page 1; `(document, page, ordinal)` can.
--
-- WHAT CHANGES, by the addendum's numbers:
--   1. `page_no` is NOT NULL and IN the live key. 0019 kept it nullable and out of the key on
--      the argument that a re-read paginating differently would mint a row superseding
--      nothing. ADR 0021 D4 answers that: page order is a property of the BYTES, and
--      `document_text` already keys on the page.
--   4. `text_id` names the `document_text` row a machine quotation read. NOT NULL exactly when
--      the row is not a person's, OUTSIDE the live key (0023 D6: a newer reading replaces the
--      older rather than sitting beside it), never updated, and checked against the row it
--      names by the trigger below.
--   5. One live quotation per line per reading: UNIQUE (text_id, date_kind, ordinal).
--  10. `decision_decided_date_one_human` gains the page, and the rendered review key is nine
--      segments: `<sha>/<date_kind>/<page_no>/<ordinal>/<reading_channel>/<method>/
--      <method_version>/<render_profile>/<reading_method or ''>`. Nothing renders it yet.
--
-- WHY A REBUILD. `page_no` becomes NOT NULL and enters a CHECK with `text_id`; SQLite has no
-- ALTER COLUMN, and 0019 records why `ADD COLUMN` is the wrong tool for this table. 0 rows in
-- production and in every store this repository builds, so the copy below copies nothing.
--
-- A STORE THAT HOLDS ROWS IS REFUSED, not guessed at (addendum decision 11). The copy carries
-- `page_no` as NULL for EVERY row, as 0019 did: a 0019 row's `ordinal` counted lines across the
-- document and decision 2 counts them within a page, so even a row that had a page would be
-- carried across with its key reinterpreted (schema-critic, 2026-10-03). Every row fails NOT
-- NULL and the migration rolls back whole. Inventing a page or a text for a quotation would be the computed provenance this table
-- exists to refuse. `data/` is disposable (CLAUDE.md).

BEGIN TRANSACTION;

CREATE TABLE decision_decided_date_rebuilt (
    decided_id             INTEGER PRIMARY KEY,
    document_sha256        TEXT NOT NULL REFERENCES document (document_sha256),
    date_kind              TEXT NOT NULL REFERENCES date_kind_vocab (date_kind),
    -- counts `Decided:` lines within ONE reading of ONE page, from 0 (addendum decision 2)
    ordinal                INTEGER NOT NULL DEFAULT 0,
    reading_channel        TEXT NOT NULL REFERENCES reading_vocab (reading_channel),
    method                 TEXT NOT NULL CHECK (method <> '' AND method NOT GLOB '*/*'),
    method_version         TEXT NOT NULL
                           CHECK (method_version <> '' AND method_version NOT GLOB '*/*'),
    render_profile         TEXT NOT NULL
                           CHECK (render_profile <> '' AND render_profile NOT GLOB '*/*'),
    reading_method         TEXT CHECK (reading_method IS NULL
                                       OR (reading_method <> ''
                                           AND reading_method NOT GLOB '*/*')),
    reading_method_version TEXT,
    printed_text           TEXT NOT NULL,       -- the line as printed
    decided_date           TEXT,                -- the ISO reading; NULL when it won't parse
    -- NOT NULL and in the live key (addendum decision 1)
    page_no                INTEGER NOT NULL CHECK (page_no >= 1),
    -- the `document_text` row a machine quotation read (addendum decision 4)
    text_id                INTEGER REFERENCES document_text (text_id),
    source_location        TEXT,                -- `{"page", "spans"}`, payload
    asserted_from_document TEXT REFERENCES document (document_sha256),
    asserted_from_capture  INTEGER REFERENCES capture (capture_id),
    asserted_at            TEXT NOT NULL,
    confidence             REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    confidence_state       TEXT NOT NULL CHECK (confidence_state IN (
                               'measured', 'human', 'unmeasured', 'not-applicable')),
    measured_target        TEXT CHECK (measured_target IS NULL
                                       OR measured_target = 'decision_decided_date'),
    score_row_id           INTEGER,
    superseded_by          INTEGER REFERENCES decision_decided_date_rebuilt (decided_id),
    superseded_at          TEXT,
    CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL)),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    CHECK ((reading_method IS NULL) = (reading_method_version IS NULL)),
    CHECK ((reading_channel = 'ocr') = (reading_method IS NOT NULL)),
    CHECK ((superseded_by IS NULL) = (superseded_at IS NULL)),
    CHECK (reading_channel <> 'text-layer' OR render_profile = 'native'),
    CHECK ((method = 'human') = (reading_channel = 'human')),
    CHECK ((reading_channel = 'human') = (confidence_state = 'human')),
    CHECK (reading_channel <> 'human' OR render_profile = 'human'),
    -- a machine quotation names its text and a person's does not (addendum decision 4): a
    -- person read the page, and which stored reading they looked at is not what they assert
    CHECK ((reading_channel <> 'human') = (text_id IS NOT NULL)),
    FOREIGN KEY (score_row_id, measured_target)
        REFERENCES class_measurement (measurement_id, measured_target)
);

INSERT INTO decision_decided_date_rebuilt
    (decided_id, document_sha256, date_kind, ordinal, reading_channel, method, method_version,
     render_profile, reading_method, reading_method_version, printed_text, decided_date,
     page_no, text_id, source_location, asserted_from_document, asserted_from_capture,
     asserted_at, confidence, confidence_state, measured_target, score_row_id, superseded_by,
     superseded_at)
    SELECT decided_id, document_sha256, date_kind, ordinal, reading_channel, method,
           method_version, render_profile, reading_method, reading_method_version,
           printed_text, decided_date,
           NULL,  -- page_no: refused for every row (see the header), never reinterpreted
           NULL,  -- text_id: no row can be said to have read one
           source_location, asserted_from_document, asserted_from_capture, asserted_at,
           confidence, confidence_state, measured_target, score_row_id, superseded_by,
           superseded_at
      FROM decision_decided_date;

DROP TABLE decision_decided_date;
ALTER TABLE decision_decided_date_rebuilt RENAME TO decision_decided_date;

-- The live key, with the page after the kind (addendum decision 1). `COALESCE` for the reason
-- 0019 measured: SQLite holds NULLs distinct in a unique index.
CREATE UNIQUE INDEX decision_decided_date_live ON decision_decided_date
    (document_sha256, date_kind, page_no, ordinal, reading_channel, method, method_version,
     render_profile, COALESCE(reading_method, ''))
    WHERE superseded_by IS NULL;

CREATE INDEX decision_decided_date_by_date ON decision_decided_date (date_kind, decided_date)
    WHERE superseded_by IS NULL AND decided_date IS NOT NULL;

-- one live human answer per line, now per page (addendum decision 10)
CREATE UNIQUE INDEX decision_decided_date_one_human ON decision_decided_date
    (document_sha256, date_kind, page_no, ordinal)
    WHERE superseded_by IS NULL AND reading_channel = 'human';

-- One live quotation per line per reading (addendum decision 5). The live key cannot say this
-- on its own: two versions of one extractor differ in `method_version`, a key column, so both
-- would be live on one line. The writer retires every live row of its method on a page before
-- it writes, and this index is what refuses a writer that forgot to.
CREATE UNIQUE INDEX decision_decided_date_one_per_line ON decision_decided_date
    (text_id, date_kind, ordinal)
    WHERE superseded_by IS NULL AND text_id IS NOT NULL;

-- 0019's, recreated with the table: a human quotation is superseded only by a human one.
CREATE TRIGGER decision_decided_date_human_row_is_not_a_model_pass_to_supersede
BEFORE UPDATE OF superseded_by ON decision_decided_date
WHEN OLD.confidence_state = 'human'
 AND NEW.superseded_by IS NOT NULL
 AND (SELECT confidence_state FROM decision_decided_date
       WHERE decided_id = NEW.superseded_by) <> 'human'
BEGIN
    SELECT RAISE(ABORT, 'ADR 0017 D5: a human decided date may only be superseded by a human');
END;

-- The quotation and the text it names agree (addendum decision 4): same document, page,
-- channel and render, and on the `ocr` channel the same engine at the same version. A
-- text-layer row keeps `reading_method` NULL under the CHECK above, and its `text_id`
-- recovers the engine. A `text_id` naming another page's text would make the quotation's
-- provenance checkable-looking and false, which is ADR 0026 § Context's indictment.
CREATE TRIGGER decision_decided_date_text_is_its_own
BEFORE INSERT ON decision_decided_date
WHEN NEW.text_id IS NOT NULL
 AND NOT EXISTS (
     SELECT 1 FROM document_text t
      WHERE t.text_id = NEW.text_id
        AND t.document_sha256 = NEW.document_sha256
        AND t.page_no = NEW.page_no
        AND t.reading_channel = NEW.reading_channel
        AND t.render_profile = NEW.render_profile
        AND (NEW.reading_channel <> 'ocr'
             OR (t.method = NEW.reading_method
                 AND t.method_version = NEW.reading_method_version)))
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0023 addendum D4: text_id names another document, page, channel, render or engine');
END;

-- `text_id` is never updated (addendum decision 4): a newer reading is a new row. NOR ARE THE
-- COLUMNS THE TRIGGER ABOVE COMPARED: one UPDATE of `page_no` would leave `text_id` naming
-- another page's text, checked at insert and false after (schema-critic, 2026-10-03).
CREATE TRIGGER decision_decided_date_text_id_is_fixed
BEFORE UPDATE OF text_id, document_sha256, page_no, reading_channel, render_profile,
                 reading_method, reading_method_version ON decision_decided_date
WHEN OLD.text_id IS NOT NEW.text_id
  OR OLD.document_sha256 IS NOT NEW.document_sha256
  OR OLD.page_no IS NOT NEW.page_no
  OR OLD.reading_channel IS NOT NEW.reading_channel
  OR OLD.render_profile IS NOT NEW.render_profile
  OR OLD.reading_method IS NOT NEW.reading_method
  OR OLD.reading_method_version IS NOT NEW.reading_method_version
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0023 addendum D4: a quotation''s text_id and what it was checked against never change');
END;

-- and a retirement's date may not be taken back or moved, 0028's idiom for `citation_reading`:
-- validation query 3 replays "live on D" from this column (schema-critic, 2026-10-03)
CREATE TRIGGER decision_decided_date_superseded_at_is_append_only
BEFORE UPDATE OF superseded_at ON decision_decided_date
WHEN OLD.superseded_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'ADR 0023 addendum: superseded_at is append-only once set');
END;

PRAGMA user_version = 34;

COMMIT;
