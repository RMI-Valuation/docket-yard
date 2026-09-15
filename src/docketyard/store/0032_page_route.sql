-- Migration 0032 — the router's verdict is its own assertion (ADR 0021 addendum, 2026-09-15).
--
-- The OCR wave's router classified every page of 27,269 image-only documents and wrote the
-- verdict to `route/<xx>/<sha>.json`. The store kept it only on OCR readings
-- (`document_text.route_class`, ADR 0021 D4), so the 26,245 `tabular` pages no engine read have
-- a blank text-layer primary and nothing else, and the text page says "Read as blank." where
-- `ocr-plan.md` decision 3 promised "scanned; contains a table we have not read"
-- (`deferred.md`, 2026-09-15). `docketyard text route` fills this table; nothing here reads a
-- file.
--
-- PAGE GRAIN, ONE LIVE ROW PER PAGE, SUPERSEDED RATHER THAN UPDATED — `document_pagination`'s
-- idioms (0018:152-223), copied: the confidence block with 'measured' unreachable through
-- `confidence_state_vocab`, the supersession pair, the bound "human" encodings and the trigger
-- that keeps a model pass off a human row.
--
-- TWO CLOCKS, NEVER ONE (schema-critic, 2026-09-15). `asserted_at` is the STORE's: when this row
-- entered the record, as `document_text.asserted_at` is, so that it and `superseded_at` replay
-- what a page showed on a date (validation query 3). `routed_at` is the ROUTER's own clock, from
-- the file; it orders two verdicts for staleness and is never read as a record date. One shape,
-- UTC to the second, so that ordering the strings orders the instants. The CHECK is
-- `(routed_at IS NULL AND method = 'human') OR routed_at GLOB '<that shape>'`: a person's row may
-- be NULL (a correction names no router run) or carry the shape, and nothing else; every other
-- row must carry the shape, since GLOB on NULL is NULL and fails. The pass always writes it, and
-- decides a human row before any comparison reads the date. Settled while the table is empty,
-- because later it is a rebuild.
--
-- `render_profile` is the render the router saw (the file's `dpi`, e.g. '150'): a verdict at
-- another render is another verdict, as a reading at another render is (ADR 0021 D2).
--
-- A PAGE THE ROUTER FAILED ON HAS NO ROW. The wave writes such a page as `unrouted` with an
-- `error`, which is a record of a failure, not a verdict; the pass counts it and writes nothing.
--
-- `document_text.route_class` IS NOT BACK-FILLED FROM HERE, and never is: on a reading it is the
-- class the page was READ under, which a later router verdict does not change.
--
-- HELD (`dump.HELD_TABLES`, beside `route_class_vocab`): its class vocabulary is held, and it is
-- provenance of the held text layer. No `review_target_vocab` row yet — nothing corrects a route.
--
-- No comments inside the parentheses below: SQLite keeps a CREATE TABLE's text verbatim, and
-- 0018:148-151's rule is that prose there ships wherever the DDL does.

BEGIN TRANSACTION;

CREATE TABLE page_route (
    route_id         INTEGER PRIMARY KEY,
    document_sha256  TEXT NOT NULL REFERENCES document (document_sha256),
    page_no          INTEGER NOT NULL CHECK (page_no >= 1),
    route_class      TEXT NOT NULL REFERENCES route_class_vocab (route_class),
    method           TEXT NOT NULL CHECK (method <> ''),
    method_version   TEXT NOT NULL CHECK (method_version <> ''),
    render_profile   TEXT NOT NULL CHECK (render_profile <> ''),
    region_count     INTEGER CHECK (region_count IS NULL OR region_count >= 0),
    note             TEXT,
    confidence       REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    confidence_state TEXT NOT NULL REFERENCES confidence_state_vocab (confidence_state),
    measured_target  TEXT CHECK (measured_target IS NULL OR measured_target = 'page_route'),
    score_row_id     INTEGER,
    routed_at        TEXT,
    asserted_at      TEXT NOT NULL CHECK (asserted_at <> ''),
    superseded_by    INTEGER REFERENCES page_route (route_id),
    superseded_at    TEXT,
    CHECK ((superseded_by IS NULL) = (superseded_at IS NULL)),
    CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL)),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    CHECK ((method = 'human') = (confidence_state = 'human')),
    CHECK ((routed_at IS NULL AND method = 'human') OR routed_at GLOB
        '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00')
);

-- One live verdict per page, whatever router gave it: a second router is a supersession, not a
-- second live answer (the page's display reads exactly one).
CREATE UNIQUE INDEX page_route_live
    ON page_route (document_sha256, page_no) WHERE superseded_by IS NULL;

-- 0018:215-223's rule, for 0018's reason: a routine re-route must not retire a person's verdict.
CREATE TRIGGER page_route_human_row_is_not_a_model_pass_to_supersede
BEFORE UPDATE OF superseded_by ON page_route
WHEN OLD.confidence_state = 'human'
 AND NEW.superseded_by IS NOT NULL
 AND (SELECT confidence_state FROM page_route WHERE route_id = NEW.superseded_by) <> 'human'
BEGIN
    SELECT RAISE(ABORT, 'ADR 0007: a human page route may only be superseded by a human');
END;

-- Nothing the row asserts changes in place: a different class, router, version or render is a new
-- row, and the page, both clocks, the region count and the note are held with it.
CREATE TRIGGER page_route_assertion_is_immutable
BEFORE UPDATE OF document_sha256, page_no, route_class, method, method_version, render_profile,
                 region_count, note, routed_at, asserted_at
ON page_route
WHEN NEW.document_sha256 IS NOT OLD.document_sha256
  OR NEW.page_no IS NOT OLD.page_no
  OR NEW.route_class IS NOT OLD.route_class
  OR NEW.method IS NOT OLD.method
  OR NEW.method_version IS NOT OLD.method_version
  OR NEW.render_profile IS NOT OLD.render_profile
  OR NEW.region_count IS NOT OLD.region_count
  OR NEW.note IS NOT OLD.note
  OR NEW.routed_at IS NOT OLD.routed_at
  OR NEW.asserted_at IS NOT OLD.asserted_at
BEGIN
    SELECT RAISE(ABORT, 'ADR 0021 addendum: a page route is superseded, never edited');
END;

PRAGMA user_version = 32;

COMMIT;
