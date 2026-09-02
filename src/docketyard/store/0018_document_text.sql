-- Migration 0018: the record's own text — ADR 0021 (the grain) and ADR 0022 (where the bytes
-- live), both Accepted by the operator 2026-09-02. Migration A of the two the operator split
-- the work into; `docs/ocr-migration.md` is the checklist this header discharges.
--
-- NOTHING WRITES TO THESE TABLES YET, as with migration 0014. What ships is the shape, so
-- the first reading has somewhere correct to land. The loader, the pagination pass, the
-- search wiring and the page-grained address are the next pieces of work.
--
-- FOUR NEW TABLES AND NO REBUILD OF ANYTHING SHIPPED. That is the point of the A/B split:
-- `assertion_method` is the table `citator/project.py` reads on every projection, at schema
-- 17 in production, and the citator has never run a real load. Ranking, `route_class` in the
-- registry, the review queue and the `correction` CHECK are all Migration B.
--
-- WHAT IS TO BE READ, measured (`tools/rmi-ai-machine/text_layer_census.py`, 2026-09-02):
-- 15,085 image-only documents holding 247,923 pages, and 59,210 text-layer documents holding
-- 857,012. About 187 hours of routed reading, and ~1.35M rows here.

BEGIN TRANSACTION;

-- ---------------------------------------------------------------------------
-- The vocabularies, declared rather than left as bare strings
-- ---------------------------------------------------------------------------
-- ADR 0022 D3 publishes FOUR of the objects below — `document_pagination`, `ocr_run` and the
-- two vocabularies they need — so their SHAPE is published with them and a third party holds
-- it. SQLite cannot ALTER a CHECK, so an undeclared typed column in a published table is a
-- table rebuild later; a vocabulary is an INSERT. That is the reasoning migration 0014 spent
-- `measured_target_vocab` on, and it applies to every published typed column here.
CREATE TABLE pagination_outcome_vocab (
    outcome TEXT PRIMARY KEY,
    note    TEXT NOT NULL
);
INSERT INTO pagination_outcome_vocab VALUES
    ('paginated',    'the PDF opened and its page count is recorded'),
    ('not-paginable','held bytes that are not a paginated document — zip, xlsx, an image'),
    ('failed',       'the file should have opened and did not; the count is unknown');

CREATE TABLE run_outcome_vocab (
    outcome TEXT PRIMARY KEY,
    note    TEXT NOT NULL
);
-- `extraction_run` uses a bare CHECK for the same three values, and the difference is that
-- `extraction_run` is HELD while `ocr_run` is PUBLIC: what ships in the snapshot's own
-- `schema.sql` cannot be widened without a rebuild.
INSERT INTO run_outcome_vocab VALUES
    ('read',    'the pass ran; pages_read and pages_failed say how far it got'),
    ('failed',  'the pass could not read this document at all'),
    ('skipped', 'the pass declined it — not image-only, or a tier not read in this pass');

-- ADR 0021 D4. The engine does NOT recover the route: PP-OCRv6 medium is the routed reader
-- for BOTH the clean and the graphic tier, whose error profiles are not comparable — one is
-- scored on CER, the other on whether it invented text at all. Every CER the benchmark
-- reports is per tier and `class_measurement` is keyed on class, so the day the assertion
-- gate opens every row must know which class it belongs to. Re-running the router later is
-- not a recovery: `research/ocr-benchmark/README.md` § Step 4 says the router will change.
--
-- HELD, not published: its only referrer is `document_text`, which is held, so publishing it
-- would ship an orphan taxonomy of the held layer's method. (The tiers themselves are public
-- on `/methodology`; this is the table, not the fact.)
CREATE TABLE route_class_vocab (
    route_class TEXT PRIMARY KEY,
    note        TEXT NOT NULL
);
-- 'unrouted' is a MEMBER rather than a null, because § Step 4 measured the router's blank
-- call as unsafe — three of the four pages it called blank were not — and the rule that
-- follows is that "no regions" routes to a reader, never to a skip. A page read without a
-- route says so; it does not say nothing.
INSERT INTO route_class_vocab VALUES
    ('clean',    'typescript or laser print, level, good contrast'),
    ('degraded', 'fax headers, stamps over text, faint or skewed copies'),
    ('graphic',  'maps and exhibits carrying labels rather than prose'),
    ('tabular',  'a true grid; not read in the first pass (ocr-plan.md)'),
    ('blank',    'read as blank, and the reading records that'),
    ('unrouted', 'the router found nothing, so the page went to the default reader');

-- ---------------------------------------------------------------------------
-- document_pagination — how many pages the bytes have (ADR 0021 D4)
-- ---------------------------------------------------------------------------
-- One row per document, not per page. The per-page table the paper schema drafted would be
-- ~1.10M rows and ~400 MB of measured row budget, to hold a `rotation` column no code reads
-- and a `had_text_layer` flag the extraction pass already computes per document.
--
-- BOTH VALUES ARE DERIVED, so both carry provenance: extractors disagree about a page
-- carrying three junk characters, which is exactly what `had_text_layer` decides.
--
-- IT SUPERSEDES RATHER THAN UPDATING. A re-pagination as an UPDATE would be current state in
-- a table the snapshot publishes, and `page_count` is the DENOMINATOR of the coverage
-- arithmetic — unread pages are `page_count` minus readings — so a mutable count would move
-- a published number with nothing recording that it moved.
--
-- OWED TO THE OPERATOR, not fixed here because it departs from what ADR 0021 D4 enumerates:
-- this is a PUBLISHED derived claim carrying no `confidence`/`confidence_state`, where
-- `CLAUDE.md`'s non-negotiable names confidence explicitly and every citator family carries
-- it. It also has no `review_target_vocab` row, so a published page count has no human
-- correction path on the day it ships while page TEXT does. Both are shape changes to a
-- published table, so they are cheap now and a rebuild later.
CREATE TABLE document_pagination (
    pagination_id   INTEGER PRIMARY KEY,
    document_sha256 TEXT NOT NULL REFERENCES document (document_sha256),
    outcome         TEXT NOT NULL REFERENCES pagination_outcome_vocab (outcome),
    page_count      INTEGER,
    had_text_layer  INTEGER CHECK (had_text_layer IN (0, 1)),
    method          TEXT NOT NULL CHECK (method <> ''),
    method_version  TEXT NOT NULL CHECK (method_version <> ''),
    asserted_at     TEXT NOT NULL,
    superseded_by   INTEGER REFERENCES document_pagination (pagination_id),
    superseded_at   TEXT,
    -- A count and a text-layer answer exist exactly when the file opened. These weld both
    -- values to ONE pass under one `method`, which is true of today's extractor — the census
    -- reads pages, chars and image_only from a single JSON — and would refuse a count-only
    -- pagination pass. Named because it is a real forward constraint, not an oversight.
    CHECK ((outcome = 'paginated') = (page_count IS NOT NULL)),
    CHECK ((outcome = 'paginated') = (had_text_layer IS NOT NULL)),
    CHECK (page_count IS NULL OR page_count >= 0),
    CHECK ((superseded_by IS NULL) = (superseded_at IS NULL))
);
CREATE UNIQUE INDEX document_pagination_live
    ON document_pagination (document_sha256) WHERE superseded_by IS NULL;

-- ---------------------------------------------------------------------------
-- text_payload — the engine's own output, kept whole (ADR 0021 D6, ADR 0022 D2)
-- ---------------------------------------------------------------------------
-- Declared before `document_text` because that table references it.
--
-- The bytes live in the blob tier under `blobs/<dg[:2]>/<dg>`, immutable and addressed by
-- their OWN digest: the sync runs `--size-only` on the stated ground that blobs never
-- change, and the prune deletes a local file when S3 holds an object of that key without
-- comparing digests — so a mutable bundle can be silently replaced by a stale one.
--
-- `payload_kind` names the format, because ADR 0021 D6 makes `block_id` a deterministic
-- function of the payload digest and the engine's own index path — and that function's
-- domain is the payload's SHAPE. Without the column it is resolvable only by convention from
-- `document_text.method`, which is the kind of hand-kept correspondence ADR 0018 D7 names as
-- the `web/cite.py` failure mode.
CREATE TABLE text_payload (
    payload_digest TEXT PRIMARY KEY,
    payload_kind   TEXT NOT NULL CHECK (payload_kind <> ''),
    size_bytes     INTEGER NOT NULL CHECK (size_bytes >= 0),
    media_type     TEXT,
    first_seen_at  TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- document_text — one row per READING of one page (ADR 0021 D1)
-- ---------------------------------------------------------------------------
-- The key carries `render_profile` because the render moves the reading: dots.mocr peaks at
-- 200 DPI where 300 exhausts the card, and crop and mask each change its output. Two renders
-- of one page through one engine at one version are DIFFERENT TEXT, so without the column
-- they collide and the second read overwrites the first or is dropped.
--
-- A HUMAN ROW'S KEY IS PINNED: method 'human', method_version 'unversioned', render_profile
-- 'human', channel 'human'. The shipped convention for a human assertion is
-- `citator.methods.HUMAN_VERSION`, a DATED queue-convention version — carried into this key
-- it would put two live human rows on one page the day that date changes. What a reviewer
-- was SHOWN belongs in `review_action.method_version`.
--
-- `engine_confidence` is NULLABLE and is NOT ADR 0007's `confidence`. A text-layer row and a
-- human row have no engine number at all, and a NOT NULL column would make them invent one —
-- the same overloading the empty-text rule refuses below.
--
-- `agreement_distance` is the operand of the confidence band a reader sees, and it ships HERE
-- rather than with Migration B's `text_agreement` table: a decision and the thing it is
-- computed from ship together, or the decision is a promise with nothing behind it. It names
-- the reading it is a distance FROM, because a distance whose second operand is unidentified
-- is an ADR 0007 gap — and the primary it was measured against is superseded routinely.
--
-- IT IS BOUNDED BY THE NORMALISATION, and the constraint pins which one:
-- `tools/rmi-ai-machine/ocr_agreement.py` divides the edit distance by `max(len(a), len(b))`,
-- which is mathematically <= 1. `ocr_score.rate()` divides by `len(truth)` and stays in range
-- only because it clamps. A loader that picked the second would be refused here, correctly.
CREATE TABLE document_text (
    text_id                   INTEGER PRIMARY KEY,
    document_sha256           TEXT NOT NULL REFERENCES document (document_sha256),
    page_no                   INTEGER NOT NULL CHECK (page_no >= 1),
    method                    TEXT NOT NULL CHECK (method <> '' AND method NOT GLOB '*/*'),
    method_version            TEXT NOT NULL
                              CHECK (method_version <> '' AND method_version NOT GLOB '*/*'),
    render_profile            TEXT NOT NULL
                              CHECK (render_profile <> '' AND render_profile NOT GLOB '*/*'),
    reading_channel           TEXT NOT NULL REFERENCES reading_vocab (reading_channel),
    reading_role              TEXT NOT NULL CHECK (reading_role IN ('primary','second','human')),
    route_class               TEXT REFERENCES route_class_vocab (route_class),
    route_method              TEXT,
    route_method_version      TEXT,
    -- EMPTY IS A READING, NOT AN ABSENCE. A page an engine correctly reads as blank writes a
    -- row with '' here. The benchmark's runner treated empty output as an error and dropped
    -- the page, penalising the safest behaviour: Tesseract lost the two graphic pages it
    -- correctly emitted nothing for, while an engine that invents prose about a map kept all
    -- nine. A failed read writes NO row and is counted in `ocr_run`.
    text                      TEXT NOT NULL,
    -- WRITER OBLIGATION, unenforceable in SQLite: this is the digest OF `text`, and it is
    -- what a loader compares to decide whether a re-read changed anything. A wrong digest
    -- silently suppresses a supersession.
    text_sha256               TEXT NOT NULL,
    engine_confidence         REAL
                              CHECK (engine_confidence IS NULL
                                     OR (engine_confidence >= 0 AND engine_confidence <= 1)),
    agreement_distance        REAL
                              CHECK (agreement_distance IS NULL
                                     OR (agreement_distance >= 0 AND agreement_distance <= 1)),
    agreement_against         INTEGER REFERENCES document_text (text_id),
    agreement_method          TEXT,
    agreement_method_version  TEXT,
    payload_digest            TEXT REFERENCES text_payload (payload_digest),
    payload_member            TEXT,
    -- ADR 0007's block. `confidence` follows `citation`'s idiom: NOT NULL, unmeasured rows
    -- carry 0, and the STATE is the predicate while the number is inert beside it.
    confidence                REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    confidence_state          TEXT NOT NULL CHECK (confidence_state IN (
                                  'measured', 'human', 'unmeasured', 'not-applicable')),
    measured_target           TEXT CHECK (measured_target IS NULL
                                          OR measured_target = 'document_text'),
    score_row_id              INTEGER,
    asserted_from_document    TEXT REFERENCES document (document_sha256),
    asserted_at               TEXT NOT NULL,
    superseded_by             INTEGER REFERENCES document_text (text_id),
    superseded_at             TEXT,
    -- ADR 0021 D7's gate, as a constraint rather than a convention: 'measured' demands a
    -- `class_measurement` row, whose (measured_target, class) must exist in `class_vocab` —
    -- and `class_vocab` is left EMPTY for this stage below, so no row can claim it until
    -- somebody scores a class. ADR 0017 D3, unchanged.
    CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL)),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    FOREIGN KEY (score_row_id, measured_target)
        REFERENCES class_measurement (measurement_id, measured_target),
    -- "human" is encoded FOUR ways and all four are bound. Unbound, a model row written with
    -- reading_role 'human' would win the display below and be unprotected by the trigger,
    -- which fires on confidence_state as `citation`'s does. An earlier draft bound three and
    -- left `reading_channel` free, which is the same hole one column over.
    CHECK ((method = 'human') = (reading_role = 'human')),
    CHECK ((reading_role = 'human') = (confidence_state = 'human')),
    CHECK ((reading_role = 'human') = (reading_channel = 'human')),
    CHECK (reading_role <> 'human'
           OR (method_version = 'unversioned' AND render_profile = 'human')),
    -- ADR 0021 D3 states the text layer's render as part of the decision; an unenforced
    -- decision is a comment.
    CHECK (reading_channel <> 'text-layer' OR render_profile = 'native'),
    -- ADR 0021 D4: every OCR reading knows the class it was routed as, or the day the gate
    -- opens there is nothing to stamp it from and the router's answer exists nowhere.
    CHECK (reading_channel <> 'ocr' OR route_class IS NOT NULL),
    -- the agreement quadruple travels together, and only a second reading carries it
    CHECK ((agreement_distance IS NULL) = (agreement_method IS NULL)),
    CHECK ((agreement_method IS NULL) = (agreement_method_version IS NULL)),
    CHECK ((agreement_distance IS NULL) = (agreement_against IS NULL)),
    CHECK (agreement_distance IS NULL OR reading_role = 'second'),
    -- an engine's own number belongs to an engine
    CHECK (engine_confidence IS NULL OR reading_channel = 'ocr'),
    -- a route class is an assertion too, so it names who said so
    CHECK ((route_class IS NULL) = (route_method IS NULL)),
    CHECK ((route_method IS NULL) = (route_method_version IS NULL)),
    CHECK ((payload_digest IS NULL) = (payload_member IS NULL)),
    CHECK ((superseded_by IS NULL) = (superseded_at IS NULL))
);

-- The natural key, over LIVE rows only. Not a table-wide UNIQUE: that would forbid the
-- retraction and self-pointer idioms `superseded_by` exists for (0009's, via 0014).
CREATE UNIQUE INDEX document_text_live ON document_text
    (document_sha256, page_no, method, method_version, render_profile)
    WHERE superseded_by IS NULL;

-- ADR 0021 D9, and this is the pair that makes the display an ANSWER rather than a rule with
-- no tie-break. `method_version` and `render_profile` are in the natural key PRECISELY so a
-- re-run inserts rather than collides — so without these two indexes the first re-run leaves
-- two live primaries, and a born-digital page that is also OCR'd has two by construction,
-- since the text-layer row is a primary too. With them, a re-run MUST supersede the outgoing
-- primary, and `superseded_at` then makes "what a reader saw on date D" replayable.
--
-- WRITER OBLIGATIONS, because this is an idiom the project has not used. Supersession here is
-- CROSS-KEY: the incoming row has a different natural key from the row it displaces, so
-- nothing in the index will remind the writer — the insert simply fails.
--   1. ALL THREE STEPS GO IN ONE TRANSACTION (0014's rule, for 0014's reason): retire the
--      outgoing primary at ITSELF, insert the replacement, repoint the retired row. A crash
--      between the first and the third leaves a self-pointer that cannot be told apart from
--      a deliberate retirement with no successor.
--   2. `superseded_at` IS SET IN THE SAME STATEMENT as `superseded_by`, or the CHECK above
--      refuses it. `citator.load._retire` as shipped writes only `superseded_by`, so it is
--      NOT reusable here unmodified — `docs/ocr-migration.md` item 13 is corrected to say so.
--
-- `document_text_one_human` is redundant as a CONSTRAINT — the pinned human key plus
-- `document_text_live` already permit only one live human row per page — and is kept as an
-- INDEX, because it is the exact match for the display view's NOT EXISTS below. Removing it
-- turns the FTS rebuild into a nested scan over ~1.1M rows.
CREATE UNIQUE INDEX document_text_one_primary ON document_text (document_sha256, page_no)
    WHERE superseded_by IS NULL AND reading_role = 'primary';
CREATE UNIQUE INDEX document_text_one_human ON document_text (document_sha256, page_no)
    WHERE superseded_by IS NULL AND reading_role = 'human';

-- (document_sha256, page_no), not document_sha256 alone: the viewer reads a document's live
-- readings in page order, and the narrower index would be ~1.35M entries serving nothing the
-- pair does not serve better.
CREATE INDEX document_text_by_document ON document_text (document_sha256, page_no)
    WHERE superseded_by IS NULL;

-- The same rule `citation` carries, for the same reason and in the same idiom. A human row
-- retired at ITSELF still passes: in a BEFORE UPDATE the subquery reads the pre-update row,
-- so the target is the human row and the guard is satisfied.
CREATE TRIGGER document_text_human_row_is_not_a_model_pass_to_supersede
BEFORE UPDATE OF superseded_by ON document_text
WHEN OLD.confidence_state = 'human'
 AND NEW.superseded_by IS NOT NULL
 AND (SELECT confidence_state FROM document_text WHERE text_id = NEW.superseded_by) <> 'human'
BEGIN
    SELECT RAISE(ABORT, 'ADR 0021 D9: a human reading may only be superseded by a human one');
END;

-- ---------------------------------------------------------------------------
-- ocr_run — the pass, and the pages it did NOT read (ADR 0021 D5)
-- ---------------------------------------------------------------------------
-- `ran_at` IS IN THE KEY, and that is the difference from `extraction_run`, which replaces on
-- a re-run and whose own header therefore forbids deriving a published coverage number from
-- it. This one appends; the coverage read takes the latest.
--
-- `pages_failed` exists because the measured failure is PARTIAL: the 300-DPI OOM died nine
-- pages into a document. Without the count nothing distinguishes those pages from pages never
-- attempted, which is ADR 0018 D10's rule — absence is not a measurement — one level down
-- from where the empty-text rule enforces it.
--
-- `reading_channel` is a CHECK and not a foreign key, which is the one place this migration
-- departs from the house idiom, deliberately: `ocr_run` is PUBLIC and `reading_vocab` is
-- HELD, so an FK would leave the snapshot's own `schema.sql` naming a table it does not
-- contain. No PUBLIC table in the shipped store has ever referenced a HELD one; this would
-- have been the first, and it fails at a third party's `foreign_key_check` rather than here.
--
-- NOT CONSTRAINED, and named instead: `outcome = 'failed'` with `pages_failed = 0` is legal,
-- because a file that will not open fails before page 1 and legitimately has none.
CREATE TABLE ocr_run (
    run_id          INTEGER PRIMARY KEY,
    document_sha256 TEXT NOT NULL REFERENCES document (document_sha256),
    method          TEXT NOT NULL,
    method_version  TEXT NOT NULL,
    reading_channel TEXT NOT NULL CHECK (reading_channel IN ('text-layer', 'ocr', 'human')),
    render_profile  TEXT NOT NULL,
    outcome         TEXT NOT NULL REFERENCES run_outcome_vocab (outcome),
    pages_read      INTEGER NOT NULL DEFAULT 0 CHECK (pages_read >= 0),
    pages_failed    INTEGER NOT NULL DEFAULT 0 CHECK (pages_failed >= 0),
    note            TEXT,
    ran_at          TEXT NOT NULL,
    UNIQUE (document_sha256, method, method_version, reading_channel, render_profile, ran_at)
);

-- ---------------------------------------------------------------------------
-- The assertion gate, declared and left shut (ADR 0021 D7 / ADR 0017 D3)
-- ---------------------------------------------------------------------------
-- The stage is declared so a figure has somewhere to go; `class_vocab` is left EMPTY on
-- purpose, exactly as `citation_reading`'s was, so no row of this table can claim
-- `confidence_state = 'measured'` until somebody scores a class against checked ground truth.
--
-- KNOWN GAP, recorded rather than worked around: `class_measurement` carries `recall`,
-- `precision` and `false_veto_rate`, and this stage's figures are CER and WER. The gate
-- cannot be OPENED through the shipped table. Nothing here publishes an assertion, so it does
-- not block; it is Migration B's to solve, and it must not be solved by storing a CER in
-- `precision` — `methods.stamp` reads that column as a precision and says so.
INSERT INTO measured_target_vocab VALUES ('document_text');

-- A human correction needs an author on the day the table ships. `review_action` foreign-keys
-- (target_table, target_keyed) to this vocabulary, so without the row there is nowhere to
-- record who wrote a correction or under which convention. The key renders as
-- `<sha256>/<page_no>/<method>/<method_version>/<render_profile>` — five segments, which
-- satisfies `review_action`'s GLOB of at least four, and the no-`/` CHECKs above are what
-- keep it parseable back into its columns.
--
-- THIS IS NOT THE QUEUE. `review_queue_vocab` and everything in `citator/review.py` are
-- Migration B, after the flag rate measured in § Step 6 has reshaped them. Note the halves
-- ship apart: a page-text correction becomes WRITABLE here while `search.signature()`'s split
-- (`ocr-migration.md` item 11) is still owed, so nothing must write one until it lands.
INSERT INTO review_target_vocab VALUES ('document_text', 'natural');

-- ---------------------------------------------------------------------------
-- What a reader sees, and what search indexes (ADR 0021 D9, ADR 0022 D4)
-- ---------------------------------------------------------------------------
-- The view IS the display rule, so its version belongs in the page index's signature: a
-- change here silently changes what search matched. Nothing dates which version was in force
-- on a given day — the same deferral migration 0014 records for `rank_version`.
--
-- IT CARRIES NO `agreement_distance`, deliberately. The band a reader sees comes from the
-- live `second` reading of the page; this view selects only `primary` and `human` rows, so
-- the column would be NULL on every row of it and a consumer would render "no band" always —
-- which under ADR 0021 D8 is itself a claim, and a false one. The band is a separate read
-- against `(document_sha256, page_no, reading_role = 'second', superseded_by IS NULL)`.
CREATE VIEW document_text_display AS
SELECT t.text_id, t.document_sha256, t.page_no, t.reading_channel, t.reading_role,
       t.route_class, t.method, t.method_version, t.render_profile,
       t.text, t.confidence_state, t.asserted_at
  FROM document_text t
 WHERE t.superseded_by IS NULL
   AND t.reading_role IN ('primary', 'human')
   AND NOT (t.reading_role = 'primary'
            AND EXISTS (SELECT 1 FROM document_text h
                         WHERE h.document_sha256 = t.document_sha256
                           AND h.page_no = t.page_no
                           AND h.reading_role = 'human'
                           AND h.superseded_by IS NULL));

-- External content over the VIEW. VERIFIED ON THE SQLITE PRODUCTION LINKS, not only the
-- development one: MATCH, `snippet()`, `'rebuild'` and `'delete'` all work through a view on
-- **3.46.1** in the production image, where this machine runs 3.50.4. The two differ, and
-- ADR 0022 D4 rests on this working, so `tests/test_document_text_schema.py` exercises it
-- wherever the code runs rather than trusting a note.
--
-- Measured on 443 real pages: external content with no prefix
-- index costs 0.44x the text, where a plain fts5() keeps a SECOND COPY at 1.71x and the
-- shipped `search_fts` configuration (external AND prefix) costs 0.95x. The prefix index
-- earns its place on docket numbers and party names; it does not earn it over page prose, and
-- dropping it is a QUERY-SURFACE choice — prefix queries still work, falling back to a
-- vocabulary scan.
--
-- NOT JOINED TO `search()`. `search.py`'s own comments record that its `bm25()` in ORDER BY
-- defeats FTS5's internal ordering and evaluates the select list for every matching row
-- before LIMIT — the shape of the 2026-09-02 fault, which must not be handed a million more
-- rows. No OCR text reaches /search, /suggest or `web/mcp.py`'s `_search` until `search.Hit`
-- can carry the label, the band and the scan link.
--
-- THE LOADER'S OBLIGATIONS, because external content never syncs itself and the non-obvious
-- half is not the writes to this table:
--   1. `'delete'` needs the OLD TEXT AS INDEXED. Once a row is superseded it has left the
--      view, so the view cannot supply it — but `document_text` is append-only and `text` is
--      immutable, so `SELECT text FROM document_text WHERE text_id = ?` always can.
--   2. A ROW LEAVES AND RE-ENTERS THIS VIEW WITH NO WRITE TO THAT ROW. Inserting a live
--      `human` row for a page silently removes that page's `primary` through the NOT EXISTS
--      above; retiring the human row silently returns it. Neither event touches the primary,
--      so a trigger on the primary would never fire. On every human insert the loader must
--      also issue `'delete'` for the primary's text_id and its stored text, and re-insert it
--      on retirement — or the index matches a human correction AND the engine text it
--      corrects, which is the exact failure the view exists to prevent.
CREATE VIRTUAL TABLE page_fts USING fts5 (
    text,
    content = 'document_text_display',
    content_rowid = 'text_id',
    tokenize = "unicode61 remove_diacritics 2"
);

-- Its own build row, because `search_meta` keys the record index's build on 'built' and two
-- indexes sharing one signature means either rebuilds the other. Owed with the search wiring:
-- `web/app.py`'s ETag validator reads the 'built' row alone, so a page-index rebuild will not
-- invalidate a cached page until it reads this one too.
INSERT INTO search_meta (key, signature, build, built_at)
VALUES ('page_built', '', 0, '1970-01-01T00:00:00+00:00');

PRAGMA user_version = 18;

COMMIT;
