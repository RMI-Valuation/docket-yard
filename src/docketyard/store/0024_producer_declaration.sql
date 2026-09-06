-- Migration 0024: which producer owns a reading key — ADR 0024 § Owed 1, and D6's registry.
--
-- TWO PRODUCERS WRITE THE SAME READING KEY. The enrichment box runs `extract_text.py` and,
-- under ADR 0024, the instance runs a container doing the same job; both write
-- `text-layer`/`native` readings whose method is `pymupdf`. At two versions they make one
-- document supersede itself on alternate passes, each alternation costing an FTS5 delete and
-- insert per page. D6's answer is that the version is DECLARED once and a contradicting
-- reading is refused at load time.
--
-- THIS TABLE IS NOT SEEDED, and that is migration 0014's rule rather than an omission: "a
-- method version welded into DDL is a version the code then has to match". A producer declares
-- itself on its first run, the declaration is idempotent because a backfill is restartable,
-- and a declaration that CONTRADICTS one already live raises rather than being swallowed —
-- `citator.methods.declare`'s idiom, which D6 names.
--
-- THE PIN MUST BE ABLE TO MOVE, and a first draft made that impossible: it keyed the table
-- `(reading_channel, render_profile)` and raised on every change, so the only way to bump a
-- version was a hand `UPDATE` on a nightly-published table — which erases the prior
-- declaration and rewrites `declared_at`, so a third party's diff cannot tell a re-point from
-- a first declaration. The design REQUIRES the move: D4 counts dispatch attempts per pin "so
-- that a version bump is the reset", and § Consequences says "a `pymupdf` CVE becomes a
-- release rather than a note". Under the first draft the next bump would have refused every
-- forward reading, halted dispatch, and left the stage dead until somebody ran SQL, with
-- nothing in the store recording it (schema-critic, 2026-09-05).
--
-- So the shape is `assertion_method`'s, one table over: a surrogate id, and uniqueness held by
-- a PARTIAL INDEX over the live rows. A re-point is an append plus a retirement — the
-- `store.supersede` idiom every other assertion in this store already uses — and the history
-- stays readable, which is what ADR 0006's event grain asks of anything that changes.
--
-- THE KEY CARRIES THE ROLE. `document_text` displaces a page's live row by (page, ROLE),
-- whatever its reading key, so the flap this table guards against is per role. Measured in
-- `tools/rmi-ai-machine/ocr_wave.py` (2026-09-05): `pp-ocrv6-medium` renders at 150 as
-- primary, second and — for the graphic root — primary again, while `dots.mocr` 1.5 renders at
-- 200 as primary. So each render carries ONE engine today and a two-column key would have
-- fitted by luck; a primary and a second by different engines at the same render is exactly
-- what ADR 0021 D8's agreement design is for, and the two-column key could not hold it. An
-- earlier draft of this header said the OCR channel "renders at 150 and may run several
-- engines", which is measurably wrong in both halves.
--
-- AN UNDECLARED KEY IS UNCONSTRAINED — absence is how this table says "no pin here", the same
-- way an absent `assertion_method` row says "not yet trusted". That is what keeps the OCR wave
-- loadable while the text layer is pinned. IT ALSO MEANS D6 IS INERT UNTIL SOMETHING DECLARES,
-- and nothing does yet: the poller that would read a pin is ADR 0024's own implementation and
-- does not exist. `deferred.md` carries that, and it is the first thing the poller stage owes.
--
-- PUBLIC, and it carries an inline CHECK rather than a foreign key for the reason migration
-- 0018 already recorded on `ocr_run`: `reading_vocab` is HELD, no public table in the shipped
-- store references a held one, and such an FK fails at a third party's `foreign_key_check`
-- rather than at ours. The channel list is therefore duplicated here and cannot be widened
-- without a rebuild — the same bargain `ocr_run` took, for the same reason.
--
-- IT GATES THE POLLER, NOT THE DISPATCH TABLE. Migration 0023's `extraction_dispatch` records
-- the pin it handed off on and carries NO foreign key here: SQLite cannot add one by `ALTER`,
-- so an FK deferred past publication is an FK foreclosed, and the dispatch row is an
-- observation of what the poller was configured with rather than a claim that it was right.

BEGIN TRANSACTION;

CREATE TABLE producer_declaration (
    declaration_id  INTEGER PRIMARY KEY,
    -- the reading key this pin governs. `human` is legal in the channel vocabulary because a
    -- review row needs one (ADR 0018 D3) and is meaningless here — a reviewer is not a
    -- producer — so it is excluded rather than left to convention. The role is in the key
    -- because a page's live reading is displaced per role, which is the flap this guards.
    -- (This comment ships in the CC0 `schema.sql`, so it names no held table.)
    reading_channel TEXT NOT NULL CHECK (reading_channel IN ('text-layer', 'ocr')),
    render_profile  TEXT NOT NULL CHECK (render_profile <> '' AND render_profile NOT GLOB '*/*'),
    reading_role    TEXT NOT NULL CHECK (reading_role IN ('primary', 'second')),
    -- the producer. The no-slash rule every reading key carries, because a review key renders
    -- as `<sha>/<page>/<method>/<version>/<render>` and must parse back — and because a pin
    -- that cannot match any reading is a pin that silently never applies.
    method          TEXT NOT NULL CHECK (method <> '' AND method NOT GLOB '*/*'),
    method_version  TEXT NOT NULL CHECK (method_version <> '' AND method_version NOT GLOB '*/*'),
    -- WHICH producer declared it. This table exists because two of them write the same key, so
    -- a row that cannot say which one spoke cannot show the mistake where the wrong one did.
    -- Nullable: the column ships before any caller, and a NULL here means "not recorded".
    declared_by     TEXT CHECK (declared_by IS NULL OR declared_by <> ''),
    declared_at     TEXT NOT NULL CHECK (declared_at <> ''),
    -- a re-point retires and appends; an un-pin retires with no replacement. Guarded like
    -- `declared_at`: '' is falsy to nothing here and would silently un-pin the key while
    -- satisfying every other constraint.
    retired_at      TEXT CHECK (retired_at IS NULL OR retired_at <> ''),
    superseded_by   INTEGER REFERENCES producer_declaration (declaration_id),
    CHECK (superseded_by IS NULL OR retired_at IS NOT NULL)
);

-- ONE LIVE PIN PER READING KEY, and the history beside it. The partial index is what makes
-- "the pin in force" singular without making the past unwritable (`assertion_method`'s
-- `rank_version` indexes are the same idea with a different axis).
CREATE UNIQUE INDEX producer_declaration_live ON producer_declaration
    (reading_channel, render_profile, reading_role) WHERE retired_at IS NULL;

PRAGMA user_version = 24;

COMMIT;
