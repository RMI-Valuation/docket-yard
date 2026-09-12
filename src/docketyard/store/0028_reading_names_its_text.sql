-- Migration 0028 — a citation reading names the text it read (ADR 0026, Accepted 2026-09-12).
--
-- A REBUILD, not an ALTER, and the reasons are ADR 0026 D8's:
--   * `superseded_at` cannot be added by ALTER and then constrained, because this table holds
--     retired rows — see the CHECK that is deliberately ABSENT below;
--   * the declared shape of `source_location` in 0014:668 is `{page, block_id, bbox}`, and
--     SQLite keeps a CREATE TABLE's text verbatim in `sqlite_master`, so only a rebuild can
--     correct it;
--   * `text_id` and the spans must land in ONE pass over the corpus, or the second is another
--     rewrite of the largest citator table — the every-row shape the five validation queries
--     exist to catch.
--
-- NOTHING REFERENCES `citation_reading` BUT ITSELF (0014:680, `superseded_by`), verified across
-- the repository, so this rebuild has no children to cascade — unlike 0019's. The day
-- `citation_occurrence` lands that stops being true, which ADR 0026 § Foreclosed prices.
--
-- THE LIVE KEY DOES NOT MOVE. ADR 0018 D3 stands and ADR 0026 D3 affirms it on a measured
-- price: widening it would be a four-table key change plus a fan-out fix at three join sites
-- (`project.py` and `citator-query-2.sql`'s reading joins, and `review._base`), because those
-- match a reading on `reading_channel` alone while selecting `cited_raw` and `quoted_passage`,
-- which
-- differ per reading so `SELECT DISTINCT` cannot collapse them.
--
-- WHAT IT COSTS: 73,838 live rows plus their retired predecessors are copied. The pass that
-- fills `text_id` and `spans` is a SEPARATE operation and a RE-LOAD, not an UPDATE — the
-- loader retires and re-inserts, because editing a stored assertion is what this project
-- forbids. Both go behind the maintenance wall (ADR 0020): migration 0025 needed none because
-- `citation_resolution` held zero rows, and the inverse holds here.

BEGIN TRANSACTION;

-- ---------------------------------------------------------------------------
-- What a null `text_id` MEANS (ADR 0026 D1)
-- ---------------------------------------------------------------------------
-- A bare nullable pointer would mean three things at once — a benchmark reading with no store
-- row to point at, a row this migration's pass has not reached, and a human row that read no
-- machine text — and because ADR 0026 D8 holds `FINDER_VERSION`, no other column could tell
-- the first two apart. That would leave the staleness predicate with an unknowable
-- denominator. So the reason is a MEMBER, which is `route_class_vocab`'s idiom (0018:82-96,
-- "'unrouted' is a MEMBER rather than a null, because a page read without a route says so;
-- it does not say nothing") and answers 0014:251-252's objection to a null meaning three
-- things.
--
-- HELD, not public: its only referrer is `citation_reading`, which is in `dump.HELD_TABLES`,
-- and a vocabulary left public would ship an orphan taxonomy of the held layer's own method —
-- exactly why `route_class_vocab` is held (0018:99-101).
CREATE TABLE text_ref_vocab (
    text_ref TEXT PRIMARY KEY,
    note     TEXT NOT NULL
);
INSERT INTO text_ref_vocab (text_ref, note) VALUES
    ('store',     'read from a document_text row, named by text_id'),
    ('benchmark', 'read from the benchmark corpus''s page markers; no store row exists'),
    ('human',     'a reviewer''s assertion; it read no machine text (citator/review.py)'),
    ('pre-0026',  'loaded before migration 0028; which reading it read was not recorded');

-- ---------------------------------------------------------------------------
-- citation_reading, rebuilt (ADR 0026 D1, D4, D5, D7)
-- ---------------------------------------------------------------------------
-- Every column of 0014's table, in its order, plus five. The comments 0014 carried are kept
-- where they still hold and corrected where they do not.
CREATE TABLE citation_reading_rebuilt (
    reading_id             INTEGER PRIMARY KEY,
    citing_document        TEXT NOT NULL,
    page                   INTEGER NOT NULL,
    target_kind            TEXT NOT NULL,
    target_key             TEXT NOT NULL,
    reading_channel        TEXT NOT NULL REFERENCES reading_vocab (reading_channel),
    reading_method         TEXT,                -- the OCR engine and its version: payload,
    reading_method_version TEXT,                -- so a re-OCR MATCHES the key and supersedes
    cited_raw              TEXT NOT NULL,       -- the string as THIS reading printed it,
                                                -- and the FIRST occurrence's form only: a
                                                -- per-occurrence raw rides in `spans` below
    quoted_passage         TEXT NOT NULL,       -- what the span test reads
    -- CORRECTED AT 0028 (ADR 0026 D4). 0014 declared `{page, block_id, bbox}` and `load.py`
    -- wrote `{page}` and nothing else; `block_id` and `bbox` are unreachable from this
    -- pipeline, living only in the blob-tier payload `document_text.payload_digest` and
    -- `payload_member` address — which `text_id` below now names, so the path exists and
    -- taking it is a later decision.
    --
    --   JSON: {page, spans: [[start, end, raw], ...]}
    --
    -- The spans index `document_text.text`, NOT `document_text_display.text`: the mask is
    -- length-changing (0020:34), so anything highlighting a citation on the text page must
    -- re-derive against the displayed string. They are NOT parallel to `quoted_passage`'s
    -- `" | "` elements — `find` de-duplicates identical lines and that separator is an
    -- unescaped in-band string — so nothing may zip them. A span verifies as
    -- `" ".join(text[start:end].split()) == raw`, never as plain equality, because
    -- `_target_end` crosses a newline for a wrapped sub-docket while the printed form is
    -- whitespace-collapsed (628 citations, find.py:53-56).
    source_location        TEXT,
    -- ADR 0026 D1. A COLUMN and not a key inside the JSON above, because it is a
    -- RELATIONSHIP: SQLite enforces it, it can be indexed and joined, and `document_text.text`
    -- is immutable per `text_id` (0020:48), so the pointer resolves for ever to the exact
    -- bytes that were read. OUTSIDE the live key, for the reason 0014 removed `source_location`
    -- from a key and 0019 kept `page_no` out of `decision_decided_date`'s: a re-read that
    -- renders or paginates differently would mint a row superseding nothing.
    text_id                INTEGER REFERENCES document_text (text_id),
    text_ref               TEXT NOT NULL REFERENCES text_ref_vocab (text_ref),
    -- ADR 0026 D7. A character offset IS a derived assertion — a claim about where in a text a
    -- string sits — and CLAUDE.md requires every one to carry its own method version. Storing
    -- spans under `method_version` below would name a finder that never emitted them, which is
    -- the false provenance ADR 0017 made four times. The idiom is `document_text`'s
    -- `route_method` (0018:288-289) and `agreement_method` (0018:307-308).
    --
    -- WRITER OBLIGATION, unenforceable: `spans` present if and only if `span_method` present.
    -- `source_location` is unconstrained TEXT and need not be JSON, so SQLite cannot express
    -- the third pairing — stated here the way 0018:296-299 states the `text_sha256` obligation.
    span_method            TEXT,
    span_method_version    TEXT,
    asserted_from_document TEXT REFERENCES document (document_sha256),
    asserted_from_capture  INTEGER REFERENCES capture (capture_id),
    method                 TEXT NOT NULL,
    method_version         TEXT NOT NULL,
    asserted_at            TEXT NOT NULL,
    confidence             REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    confidence_state       TEXT NOT NULL CHECK (confidence_state IN (
                               'measured', 'human', 'unmeasured', 'not-applicable')),
    measured_target        TEXT CHECK (measured_target IS NULL OR measured_target IN (
                               'citation', 'citation_reading')),
    score_row_id           INTEGER,
    superseded_by          INTEGER REFERENCES citation_reading_rebuilt (reading_id),
    -- ADR 0026 D5, and the CHECK that is DELIBERATELY ABSENT.
    --
    -- `document_text` pairs these two with `CHECK ((superseded_by IS NULL) = (superseded_at IS
    -- NULL))` (0018:357) and 0019 copied it. THAT CANNOT BE DONE HERE: this table holds retired
    -- rows, every one with `superseded_by` set and no `superseded_at` to have filled, so the
    -- INSERT below would violate the biconditional on every one of them and the migration
    -- would roll back whole. And the only backfill available is forbidden by 0019:212-217 —
    -- "`superseded_at` has no value to recover for a row already retired, and inventing one is
    -- a computed date in the one table whose whole rule is that nothing is computed."
    --
    -- So the pairing is enforced FORWARD ONLY, by the three triggers below. Legacy retirements
    -- stay honestly undated; nothing retired after this migration can be. This is validation
    -- query 3's fix as much as it is 0019's third defect of an ALTER: "which reading was live
    -- on 18 August" is answerable today only from a successor's `asserted_at`, and a row
    -- retired at itself has no successor and no recovery.
    superseded_at          TEXT,
    CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL)),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    CHECK ((reading_method IS NULL) = (reading_method_version IS NULL)),
    -- the pointer and its reason agree, both ways (ADR 0026 D1)
    CHECK ((text_ref = 'store') = (text_id IS NOT NULL)),
    -- and 'human' is BOUND to the human channel in both directions. 0018:331-339 is this store
    -- having learned it once already: "'human' is encoded FOUR ways and all four are bound. …
    -- An earlier draft bound three and left `reading_channel` free, which is the same hole one
    -- column over." Without these, `text_ref` is a hint rather than a fact — and the staleness
    -- predicate gates on it.
    CHECK (text_ref <> 'human' OR reading_channel = 'human'),
    CHECK (reading_channel <> 'human' OR text_ref = 'human'),
    CHECK ((span_method IS NULL) = (span_method_version IS NULL)),
    FOREIGN KEY (score_row_id, measured_target)
        REFERENCES class_measurement (measurement_id, measured_target),
    FOREIGN KEY (citing_document, page, target_kind, target_key)
        REFERENCES citation_key (citing_document, page, target_kind, target_key)
);

-- A CASE for `text_ref` AND NOT A BARE 'pre-0026', which is 0019's lesson at :225-231: a bare
-- constant would stamp 'pre-0026' on a human row and break the binding CHECK above, and a
-- DEFAULT would let a NEW row silently claim to predate this migration. A human reading's
-- `text_ref` IS 'human' — it read no machine text, by construction (`review.py:481-499` writes
-- channel 'human' and no pointer). Everything else predates the pass and says so.
--
-- `text_id` is NULL for every copied row and `text_ref` never 'store', so the pairing CHECK
-- holds throughout. `superseded_at` is NULL for every row including the retired ones, which is
-- what the absent biconditional is for.
INSERT INTO citation_reading_rebuilt
    (reading_id, citing_document, page, target_kind, target_key, reading_channel,
     reading_method, reading_method_version, cited_raw, quoted_passage, source_location,
     text_id, text_ref, span_method, span_method_version, asserted_from_document,
     asserted_from_capture, method, method_version, asserted_at, confidence, confidence_state,
     measured_target, score_row_id, superseded_by, superseded_at)
    SELECT reading_id, citing_document, page, target_kind, target_key, reading_channel,
           reading_method, reading_method_version, cited_raw, quoted_passage, source_location,
           NULL,
           CASE WHEN reading_channel = 'human' THEN 'human' ELSE 'pre-0026' END,
           NULL, NULL,
           asserted_from_document, asserted_from_capture, method, method_version, asserted_at,
           confidence, confidence_state, measured_target, score_row_id, superseded_by, NULL
      FROM citation_reading;

DROP TABLE citation_reading;
ALTER TABLE citation_reading_rebuilt RENAME TO citation_reading;

-- UNCHANGED from 0014, and recreated because the rebuild dropped it with the table. ADR 0026
-- D3: the live key does not move, so every existing join survives byte for byte — which is
-- what keeps validation query 2's answer set identical.
CREATE UNIQUE INDEX citation_reading_live ON citation_reading
    (citing_document, page, target_kind, target_key, reading_channel)
    WHERE superseded_by IS NULL;

-- WHAT ADR 0026 D2 BUYS, AND WHY IT GETS NO INDEX. A live reading whose text is no longer what
-- the record SHOWS is a re-walk trigger — the passage may still be right, but it is unverified:
--
--   SELECT * FROM citation_reading r
--    WHERE r.superseded_by IS NULL AND r.text_ref = 'store'
--      AND NOT EXISTS (SELECT 1 FROM document_text_display v WHERE v.text_id = r.text_id)
--
-- The predicate is against `document_text_display`, NOT against the pointer's `superseded_by`,
-- because a live `human` text row removes a primary from that view WITHOUT superseding it
-- (0018:556-558) — the one sequence no re-load can repair, so a `superseded_by` test would miss
-- exactly the case that matters.
--
-- NO INDEX IS CREATED FOR IT, and a first draft of this migration created one before measuring.
-- `EXPLAIN QUERY PLAN` on a production copy: the sweep takes `SCAN r USING INDEX
-- citation_reading_live`, an inner `SEARCH t USING INTEGER PRIMARY KEY (rowid=?)` and the view's
-- own `SEARCH h USING INDEX document_text_one_human` — which is the pair ADR 0026 D2 credits.
-- A `(text_id)` index is not used at all, because nothing in that WHERE implies `text_id IS NOT
-- NULL`; and `text_ref = 'store'` is the wrong thing to index because the re-load makes EVERY
-- live row 'store', so it selects all of them. TIMED on the same copy at that worst case:
-- **0.02 s over all 73,838 live rows.** CLAUDE.md: volume is modest, do not over-engineer.
--
-- IT RUNS FROM A CONNECTION THAT HAS CALLED `display.register` (`store/db.py:81`), never from
-- the `sqlite3` CLI: `document_text_display.text` is `dy_display_text(t.text)` (0020:34), a
-- Python-registered function, and SQLite resolves function names at prepare time over the whole
-- view body — so selecting only `v.text_id` does not save you. Do NOT inline the view's two
-- terms against `document_text` instead; a second copy of the display rule in the store is the
-- `web/cite.py` failure 0018:508-511 names. (The RENAME above needs no such connection:
-- verified by execution, a bare `sqlite3.connect` + `db.migrate` applies 27 -> 28 and rewrites
-- the self-reference, because a rename re-parses the view body without calling its functions.)

-- ADR 0026 D5, forward only. Three triggers and not one, because `BEFORE UPDATE OF
-- superseded_by` guards one edge of three.
--
-- Checked against all three steps of `supersede.retire`'s idiom: a BEFORE UPDATE trigger's
-- `NEW.*` holds the post-update value of EVERY column, so `SET superseded_by = ?,
-- superseded_at = ?` in one statement passes, and the third step's bare repoint
-- (`citator/load.py`, `UPDATE … SET superseded_by = ?`) passes because `NEW.superseded_at`
-- reads what step one already wrote.
CREATE TRIGGER citation_reading_retirement_is_dated
BEFORE UPDATE OF superseded_by ON citation_reading
-- BOTH directions, which a first draft got half right. A pointer with no date is the case D5
-- names; a row UN-retired while keeping its date is the fourth edge, and it would leave a row
-- live and dated-retired at once — the state `document_text`'s biconditional (0018:357) forbids
-- outright and a forward-only trigger set must forbid deliberately. No shipped writer clears
-- `superseded_by`, so this half is latent, which is exactly when it is cheap to close.
WHEN (NEW.superseded_by IS NOT NULL AND NEW.superseded_at IS NULL)
  OR (NEW.superseded_by IS NULL AND NEW.superseded_at IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT,
        'ADR 0026 D5: superseded_by and superseded_at are set and cleared together');
END;

CREATE TRIGGER citation_reading_inserted_retirement_is_dated
BEFORE INSERT ON citation_reading
WHEN NEW.superseded_by IS NOT NULL AND NEW.superseded_at IS NULL
BEGIN
    SELECT RAISE(ABORT, 'ADR 0026 D5: a row inserted already retired must carry superseded_at');
END;

-- and a retirement's date may not be taken back OR MOVED. The WHEN tests only `OLD`, so it
-- catches a clearing and a backdating alike — a first draft added `AND NEW.superseded_at IS
-- NULL` and so permitted `SET superseded_at = '2020-01-01'` on an already-dated row while its
-- message said "append-only", which is `0019:193-194`'s defect: an unenforced decision is a
-- comment. `document_text_text_is_immutable` (0020:48) fires on ANY update of its column and
-- this is its analogue, so it does the same.
CREATE TRIGGER citation_reading_superseded_at_is_append_only
BEFORE UPDATE OF superseded_at ON citation_reading
WHEN OLD.superseded_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'ADR 0026 D5: superseded_at is append-only once set (0020:48s idiom)');
END;

PRAGMA user_version = 28;

COMMIT;
