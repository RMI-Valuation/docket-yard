-- Migration 0019: the quoted date gets the render in its key, and the rebuild that reaches
-- what an ALTER cannot. ADR 0023.
--
-- ADR 0021 D2 put `render_profile` in `document_text`'s key because the render moves the
-- reading: dots.mocr peaks at 200 DPI where 300 exhausts the card, and crop and mask each
-- change its output. Two renders of one page through one engine at one version are DIFFERENT
-- TEXT, so both readings are kept and neither displaces the other.
--
-- ADR 0021 § Consequences named the table that argument does not reach, and this migration
-- closes it. `decision_decided_date_live` keyed on `(document_sha256, date_kind, ordinal,
-- reading_channel, method, method_version)` with no render, so a re-read of the same page at
-- a better DPI produced a row that SUPERSEDED its predecessor. What that destroys is a quoted
-- string — "Decided: October 5, 2017", `printed_text`, which is NOT NULL because `CLAUDE.md`
-- says dates are quoted and never computed. `document_text` would keep both renders while the
-- date extracted from them kept one, one join away.
--
-- WHY NOW, AND WHY THIS IS THE LAST CHEAP MOMENT. Measured on production 2026-09-02:
-- `decision_decided_date` holds 0 rows, and so does `citation` — the citator shipped its
-- schema at migration 0014 and has never run a real load. After the first load this is a
-- table rebuild against live rows: bounded by decision DOCUMENTS (23,716 `decision_record`
-- rows) times the passes over them, which is not the largest thing the citator owns —
-- 0014:320 gives `citation_reading` that title, and it is per document, page and target.
-- Small enough to rebuild and far too dear to rebuild for nothing.
--
-- WHY A REBUILD AND NOT `ADD COLUMN`. The first draft of this migration was an ALTER, and a
-- schema-critic pass (2026-09-02) found what an ALTER can never reach on this table:
--
--   1. `ADD COLUMN` under `NOT NULL` REQUIRES a non-NULL default, so the render column would
--      have carried `DEFAULT 'native'` — and an `ocr` writer that omitted the column would
--      take it silently, stamping a false render on a quoted date. `document_text` gives the
--      same column NO default (0018:177) and fails an omitting writer loudly. SQLite has no
--      `ALTER COLUMN`, so removing that default later is this same rebuild.
--   2. `method` and `method_version` are key columns rendered into `review_action.target_key`
--      and `correction.target_key`, and carried NO `/`-CHECK, so a value holding a `/`
--      renders a key that cannot be parsed back into columns — the defect 0018:174-178 pins
--      for `document_text` — and `ADD COLUMN` cannot add a constraint to a column that
--      already exists. NOT the same value as there: on `document_text` `method` IS the
--      engine, so a HuggingFace id (`rednote-hilab/dots.ocr`) is the live case. HERE `method`
--      is the DATE EXTRACTOR's, and the exposure on it is a `/` in an extractor's own name —
--      `rmi/date-layout` — which is a naming nobody has ruled out. The engine id lands in
--      `reading_method`, which was payload when this was drafted and is a KEY COLUMN as of
--      this migration, so it carries the CHECK too and the HuggingFace case is live here
--      after all. `ADD COLUMN` could have reached none of the three.
--   3. There was no `superseded_at`. ADR 0021 D1 added one to `document_text` so that "what a
--      reader saw on date D" is replayable; widening the live set without it makes that read
--      strictly harder, because rows now sit BESIDE one another and there is often no
--      successor whose `asserted_at` bounds the predecessor.
--
-- Verified rather than assumed, on this machine's SQLite 3.50.4 (production links 3.46.1):
-- `ADD COLUMN` does accept a CHECK, including one referencing another column of the row — and
-- it VALIDATES the rows already in the table and fails the ALTER if any violates. So the
-- window this migration uses is narrower than "cheap": after one contradicting row the ALTER
-- is not costly, it is refused.
--
-- THE ENGINE'S NAME IS IN THE KEY; ITS VERSION IS NOT (ADR 0023 D6, the operator's decision
-- 2026-09-02). 0014 had both as payload on one argument: a re-OCR at a better version must
-- MATCH and supersede rather than doubling the live rows over 1,480 of 9,663 image-only
-- files. That argument is about a VERSION BUMP — one reader improving, so the readings are
-- ordered and the newer wins — and it is preserved here exactly, because
-- `reading_method_version` stays outside the key.
--
-- It does not reach TWO DIFFERENT ENGINES, which have no such ordering and which ADR 0021 D8
-- runs deliberately as the agreement pair. With both payload, dots.mocr and PP-OCRv6 reading
-- one page at one render collided, and whichever was written second silently destroyed the
-- other's `printed_text`. The case that forced this, the operator's question: an engine can
-- read a page BETTER overall and get the date WRONG. No page-level score can order those two
-- readings — every CER this project measures is per page or per tier, and a decided date is
-- one line of about thirty characters — so a disagreement between engines is not a tie to
-- break, it is a FINDING for a person. It is only a finding if both rows survive.
--
-- Recorded precisely, because a second critic pass found the first draft of this header
-- overstated the position it was deferring to: ADR 0018 D3 is about `citation_reading` and
-- decides NOTHING about this table. For THIS table the engine-outside-the-key position lived
-- in 0014:912 and `citator-schema.md` § B point 2 — a migration comment and a proposal
-- document, not an accepted ADR.
--
-- WHAT THIS IS STILL NOT: it does not widen `citation_reading`, whose live key has the same
-- shape and the same exposure. That table is ADR 0018 D3's, it is accepted, and revisiting it
-- is a decision this migration does not take.
--
-- THE RENDERED KEY GAINS TWO SEGMENTS, and this header is the only append-only place a reader
-- of the deployed chain will reach it — migration 0014:968-975 documents the six-segment form
-- and cannot be edited. From this migration forward the rendering is EIGHT segments:
--
--   decision_decided_date
--       '<document_sha256>/<date_kind>/<ordinal>/<reading_channel>/<method>/<method_version>'
--       '/<render_profile>/<reading_method>'
--
-- The last segment is EMPTY for a text-layer or human row, which has no engine — the same
-- empty string the live index coalesces to, so the rendered key and the index agree about
-- what "no engine" is. Eight segments with a trailing empty one still parse by splitting on
-- '/', because none of the other seven may contain one.
--
-- Both forms satisfy the `GLOB '*/*/*/*'` shape checks in `correction` (0014:992) and
-- `review_action` (0015:197), which only count to four and do not validate segments, and
-- `review_action_live` is `UNIQUE (queue, target_table, target_key)` — so a six-segment key
-- and an eight-segment key naming ONE row do not collide, and would be two live review
-- decisions on one item with nothing saying so. `review_action.target_key_version` is the
-- column that distinguishes them; nothing writes either form today (no renderer for this
-- table exists in `src/`), so the obligation lands on the first writer, and ADR 0023 D5 is
-- where it is written down.

BEGIN TRANSACTION;

-- SQLite's documented table-rebuild procedure. `db.migrate` already runs every script with
-- `PRAGMA foreign_keys = OFF` and runs `PRAGMA foreign_key_check` after it, which IS that
-- procedure's fence; nothing outside this table references it (only its own `superseded_by`
-- does), so there are no children to strand. `correction` was rebuilt the same way at 0014.
CREATE TABLE decision_decided_date_rebuilt (
    decided_id             INTEGER PRIMARY KEY,
    document_sha256        TEXT NOT NULL REFERENCES document (document_sha256),
    date_kind              TEXT NOT NULL REFERENCES date_kind_vocab (date_kind),
    -- POSITIONAL and parser-assigned, and 0014:913-918 already owes a fix for that. The
    -- render in the key sharpens the debt rather than paying it: two renders that disagree
    -- about how many `Decided:`-shaped lines a degraded page carries assign the same printed
    -- line different ordinals, and the rows are then keyed as two DATE INSTANCES rather than
    -- two readings of one. Inert while none of the sixty prints two lines (ADR 0017), and
    -- named in ADR 0023 § What this record does not decide, so the day one does it is not a
    -- surprise.
    ordinal                INTEGER NOT NULL DEFAULT 0,
    reading_channel        TEXT NOT NULL REFERENCES reading_vocab (reading_channel),
    -- the DATE EXTRACTOR's method, not the OCR engine's — the engine is payload below. The
    -- `/`-CHECKs are what keep the rendered key above parseable back into its columns.
    method                 TEXT NOT NULL CHECK (method <> '' AND method NOT GLOB '*/*'),
    method_version         TEXT NOT NULL
                           CHECK (method_version <> '' AND method_version NOT GLOB '*/*'),
    -- NO DEFAULT, deliberately: a writer that omits the render must fail, not be guessed at.
    render_profile         TEXT NOT NULL
                           CHECK (render_profile <> '' AND render_profile NOT GLOB '*/*'),
    -- IN THE KEY as of 0019 (ADR 0023 D6), where 0014 had it as payload — so it carries the
    -- `/`-CHECK the other key columns carry, and here the HuggingFace case IS the live one:
    -- `rednote-hilab/dots.ocr` is how these engines are published, and an engine id is what
    -- this column holds. The convention is the one `document_text` already takes: store the
    -- engine's short name, `dots.mocr`, and keep the key parseable.
    reading_method         TEXT CHECK (reading_method IS NULL
                                       OR (reading_method <> ''
                                           AND reading_method NOT GLOB '*/*')),
    -- and its VERSION stays payload, OUTSIDE the key: a version bump is one reader improving
    -- and must MATCH and supersede (0014:911-912's argument, which is preserved exactly).
    reading_method_version TEXT,
    printed_text           TEXT NOT NULL,       -- "Decided: October 5, 2017", as printed
    decided_date           TEXT,                -- the ISO reading; NULL when it won't parse
    -- NEW at 0019, and free only while the table is empty. ADR 0021 D4: `document_sha256`
    -- fixes the byte stream, so page order is a property of the BYTES and a page number is
    -- channel-independent — which is what makes it safe to put here at all. It is the typed
    -- half of `source_location`, which held the page inside unconstrained JSON, and three
    -- things want it: a live reading cannot otherwise be joined to the page's text in
    -- `document_text`, a work-level resolution cannot say WHICH decided-date row it matched
    -- (ADR 0007), and 0014:913-918 says the ordinal must eventually be assigned "from
    -- something stable on the page" — which is a page.
    --
    -- NULLABLE, and OUTSIDE the key. Not in the key, because a re-read that paginates
    -- differently would mint a row superseding nothing — the defect `source_location` was
    -- removed from the key for. Not NOT NULL, because no writer exists to be held to it and
    -- a text-layer extractor quoting from a document-level parse would be refused for no
    -- reason; the obligation to set it is ADR 0023 D2's, on the first writer.
    page_no                INTEGER CHECK (page_no IS NULL OR page_no >= 1),
    source_location        TEXT,                -- payload, OUTSIDE the key
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
    -- new at 0019, and the reason the live set may now hold two rows where it held one
    superseded_at          TEXT,
    CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL)),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    CHECK ((reading_method IS NULL) = (reading_method_version IS NULL)),
    -- A BICONDITIONAL, and both halves earn their place.
    --
    -- FORWARD (ADR 0007, which CLAUDE.md lists as non-negotiable: every derived assertion
    -- carries its source and method): the pairing above let an `ocr` row store a quotation as
    -- "read by OCR" with the engine unrecorded — a provenance hole in the one table whose
    -- content IS the quotation, and the analogue of what 0018:239 closes for `document_text`.
    --
    -- BACKWARD, and this one is load-bearing now that `reading_method` is IN the key: without
    -- it, a `text-layer` row naming an engine and one naming none differ in a key column, so
    -- BOTH are live and the key enforces nothing for them. Confirmed by execution, not
    -- reasoning (code review, 2026-09-02): two live text-layer readings of one date, which is
    -- exactly what the coalesce in `decision_decided_date_live` exists to prevent. A page the
    -- publisher typeset was not read by an engine, so naming one is a false provenance as
    -- well as a broken key.
    CHECK ((reading_channel = 'ocr') = (reading_method IS NOT NULL)),
    CHECK ((superseded_by IS NULL) = (superseded_at IS NULL)),
    -- ADR 0021 D3 states the text layer's render as part of the decision; migration 0018 says
    -- an unenforced decision is a comment, and the first draft of this migration was one.
    CHECK (reading_channel <> 'text-layer' OR render_profile = 'native'),
    -- The three encodings of "human" the shipped writer already sets together
    -- (`citator/review.py`: method 'human', channel 'human', state 'human', confidence 1.0),
    -- bound so a model row cannot claim one of them. `method_version` is NOT pinned here, and
    -- that is a departure from `document_text`: `citator.methods.HUMAN_VERSION` is a DATED
    -- convention sitting in FOUR shipped citator keys, and pinning it in this one table alone
    -- would make two conventions where there is now one. ADR 0023 § What this record does
    -- not decide.
    CHECK ((method = 'human') = (reading_channel = 'human')),
    CHECK ((reading_channel = 'human') = (confidence_state = 'human')),
    -- a human read a page, not a DPI. Without this a human quotation records that it was read
    -- off the publisher's text layer at native render, which is a claim nobody made.
    CHECK (reading_channel <> 'human' OR render_profile = 'human'),
    FOREIGN KEY (score_row_id, measured_target)
        REFERENCES class_measurement (measurement_id, measured_target)
);

-- 0 rows in production and in every store this repository builds, so this copies nothing.
-- It is written out anyway because a store that DOES hold rows must migrate or refuse, and
-- refusing is the right answer here: `superseded_at` has no value to recover for a row
-- already retired, and inventing one is a computed date in the one table whose whole rule is
-- that nothing is computed. Such a store fails the biconditional CHECK above and the
-- migration rolls back whole. `data/` is disposable (CLAUDE.md); production is not affected.
INSERT INTO decision_decided_date_rebuilt
    (decided_id, document_sha256, date_kind, ordinal, reading_channel, method, method_version,
     render_profile, reading_method, reading_method_version, printed_text, decided_date,
     page_no, source_location, asserted_from_document, asserted_from_capture, asserted_at,
     confidence, confidence_state, measured_target, score_row_id, superseded_by, superseded_at)
    SELECT decided_id, document_sha256, date_kind, ordinal, reading_channel, method,
           method_version,
           -- A CASE AND NOT A BARE 'native', which would stamp the text layer's render on an
           -- `ocr` row that never had one — the same silent falsehood this migration refuses
           -- `ADD COLUMN … DEFAULT 'native'` for, committed by the backfill instead (code
           -- review, 2026-09-02; reproduced on a schema-18 store holding one ocr row). A
           -- text-layer row's render IS native (ADR 0021 D3) and is the only one recoverable;
           -- anything else yields NULL and is refused by NOT NULL, which is the same stance
           -- this migration takes on `superseded_at` and for the same reason.
           CASE WHEN reading_channel = 'text-layer' THEN 'native' END,
           reading_method, reading_method_version, printed_text, decided_date,
           NULL,  -- page_no: the column did not exist, so no row can be said to have one
           source_location,
           asserted_from_document, asserted_from_capture, asserted_at, confidence,
           confidence_state, measured_target, score_row_id, superseded_by, NULL
      FROM decision_decided_date;

DROP TABLE decision_decided_date;
ALTER TABLE decision_decided_date_rebuilt RENAME TO decision_decided_date;

-- The live key gains the render, so a 200-DPI re-read sits BESIDE the 150-DPI one rather than
-- replacing it, and the projection then has two quotations to choose between rather than one
-- that quietly changed. `docs/citator-schema.md` § B's pick rule — "prefer the text-layer
-- reading, else the OCR reading whose own confidence is higher" — cannot break the new tie:
-- that `confidence` is inert by this project's own rule. A replacement is OWED, not decided:
-- ADR 0023 § The pick rule states what it must satisfy and explicitly declines to pick one.
-- Nothing may publish a single decided date until it is decided, and nothing can today.
-- `COALESCE(reading_method, '')` AND NOT THE BARE COLUMN, which is a trap this migration hit
-- and verified rather than reasoned about. SQLite holds NULLs DISTINCT in a unique index, so
-- with the bare column two text-layer rows — whose engine is NULL, there being no engine —
-- would BOTH be live on one key and the index would enforce nothing for them. Measured on
-- 3.50.4: bare column accepts the second NULL row, the expression refuses it, and two named
-- engines stay live under both. Expression indexes are 3.9+; production links 3.46.1.
CREATE UNIQUE INDEX decision_decided_date_live ON decision_decided_date
    (document_sha256, date_kind, ordinal, reading_channel, method, method_version,
     render_profile, COALESCE(reading_method, ''))
    WHERE superseded_by IS NULL;
-- unchanged from 0014, and recreated because the rebuild dropped it with the table: the
-- docket calendar reads the date, which is one of the three reasons it is typed. It now
-- yields one document on two dates where the renders disagree — the same owed pick rule,
-- and the calendar is the second consumer that will need it.
CREATE INDEX decision_decided_date_by_date ON decision_decided_date (date_kind, decided_date)
    WHERE superseded_by IS NULL AND decided_date IS NOT NULL;

-- ADR 0023 D4, second half. The live key above cannot make the HUMAN set single-valued,
-- because `citator.methods.HUMAN_VERSION` is a DATED string sitting in `method_version` — so
-- the day it changes, a second human correction of one date is a second LIVE row, and the
-- display has two human answers and no rule. `document_text` escapes this by pinning human
-- rows to `unversioned`; this table cannot, because the same dated convention is in FOUR
-- shipped citator keys and pinning one of them makes two conventions where there is one.
--
-- So the index does the work the pinned key does there, and leaves `HUMAN_VERSION` alone.
-- It is the analogue of `document_text_one_human` (0018:284) and, like it, is what lets a
-- display rule say "the human row" and mean exactly one thing.
CREATE UNIQUE INDEX decision_decided_date_one_human ON decision_decided_date
    (document_sha256, date_kind, ordinal)
    WHERE superseded_by IS NULL AND reading_channel = 'human';

-- The rule `citation` carries at 0014:639 and `document_text` at 0018, in the same idiom and
-- for a sharper reason: what this table holds is a QUOTATION. A human row retired at ITSELF
-- still passes — in a BEFORE UPDATE the subquery reads the pre-update row, so the target is
-- the human row and the guard is satisfied.
CREATE TRIGGER decision_decided_date_human_row_is_not_a_model_pass_to_supersede
BEFORE UPDATE OF superseded_by ON decision_decided_date
WHEN OLD.confidence_state = 'human'
 AND NEW.superseded_by IS NOT NULL
 AND (SELECT confidence_state FROM decision_decided_date
       WHERE decided_id = NEW.superseded_by) <> 'human'
BEGIN
    SELECT RAISE(ABORT, 'ADR 0017 D5: a human decided date may only be superseded by a human');
END;

-- WRITER OBLIGATIONS, in the same terms migration 0018 states them for `document_text`:
--   1. Supersession here is CROSS-KEY — the incoming row has a different natural key from the
--      row it displaces, so the index will not remind the writer; the insert simply fails.
--      All three steps go in ONE transaction: retire the outgoing row at ITSELF, insert the
--      replacement, repoint the retired row.
--   2. `superseded_at` IS SET IN THE SAME STATEMENT as `superseded_by`, or the CHECK above
--      refuses it. `citator.load._retire` as shipped writes ONLY `superseded_by`, so it is
--      NOT reusable against this table unmodified — and neither is the generic
--      `_supersede_if_changed` that calls it. Nothing writes here today; the first writer
--      inherits this.

PRAGMA user_version = 19;

COMMIT;
