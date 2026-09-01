-- Migration 0015: a reviewer has an identity, and the exposed class stops publishing itself.
-- ADR 0016 (Accepted 2026-08-28), whose tables `docs/schema-draft.md` § 7 drafted and the
-- schema-critic revised the same day. Under it sits ADR 0017 D5's queue and D2's promise
-- that the exposed class "goes to review; everything else ships unreviewed".
--
-- WHAT THIS UNBLOCKS, and why it could not wait. Migration 0014 shipped the citation
-- families; `docketyard.citator` fills them. Between them they compute the exposed class —
-- `AB 124` with a footnote `2` fused on, resolving CONFIDENTLY to `AB 1242`, a different
-- proceeding — and then published it beside a clean edge, because the queue it was supposed
-- to go to did not exist. ADR 0017's exposure test exists to decide what reaches a page
-- without a person looking; until this migration, the answer was everything.
--
-- ============================================================================
-- § The queue is a QUERY, not a table
-- ============================================================================
-- Nothing here holds queue items. A queue is every live row matching its kind that no live
-- review action names, computed when it is asked for: `docketyard.citator.review`. A stored
-- queue would be a second source of truth that has to be kept in step with the registry —
-- and the registry MOVES, because waves 2-3 are still adding dockets and a target that was
-- unresolvable last week resolves this week. A derived queue picks that up; a table would
-- hold yesterday's answer and nobody would know.
--
-- ============================================================================
-- § How a review changes what is published, WITHOUT the projection knowing about reviews
-- ============================================================================
-- `schema-draft.md` § 7's rule: every decision on a queue whose target has an assertion
-- table writes a `human` row in that table — an acceptance writes a human resolution
-- agreeing with the model's, a rejection writes a human does-not-resolve, a correction
-- writes the corrected one. The new row supersedes the live one, and the projection keeps
-- reading `superseded_by IS NULL` with no knowledge that a review happened.
--
-- So the projection gains exactly ONE term, and it is a gate rather than a lookup: an edge
-- whose live `exposed` judgement says `true` projects only once a `human` resolution exists
-- for it. That is ADR 0017 D2 in SQL. It reads the judgement WITHOUT the
-- `confidence_state IN ('measured','human')` predicate every other family carries, and that
-- is deliberate: this judgement SUPPRESSES, and a suppressor filtered out of the candidate
-- set is silently inert — the defect ADR 0018 D7 records against the on-page veto, one
-- table over. A suppressor is evaluated by its existence, never by its rank.
--
-- `exposed` is written `unmeasured`: ADR 0017 measures how OFTEN it fires — 3 of 225, and
-- 3 of 249 emitted — which is a rate and not a precision, so `class_measurement` has nothing
-- for it to point at. `unmeasured` rather than `not-applicable` because a precision IS
-- measurable, and the queue this migration builds is the instrument that would produce it;
-- "nobody has scored it yet" is the truer state, and the one the span test's `false` rows
-- already carry. It also carries its OWN method and version, never the resolver's: the
-- exposure test is a distinct rule whose membership ADR 0017 reconsidered between 3, 5 and
-- 14 before settling on 3.
--
-- AND THE GATE IS A FOURTH THING `projection_rule_version` NAMES. ADR 0018 D8 lists three —
-- the span test, the family closure, `rank_version`. `methods.PROJECTION_RULE` gains
-- `gate=exposed@<version>` here, because a measurement taken before this migration and one
-- taken after would otherwise carry the same version with different numbers, and
-- `class_measurement_identity` would collide them on one benchmark_date.
--
-- WHAT A READER SEES CHANGES, and it is a function of review backlog. The rule projects
-- 205 of 225 (91.1%) on the sixty-decision benchmark; a reader sees 202 (89.8%) until the
-- three edges ADR 0017 § The exposure test names — `AB 1014`, `AB 1071`, `AB 1242` — have
-- been answered. Migration 0014's header states 91.1% and could not know this; both are
-- true of different questions, and this is where the second one is written down.

BEGIN TRANSACTION;

-- ---------------------------------------------------------------------------
-- reviewer — a REGISTRY (identity only), never an assertion table
-- ---------------------------------------------------------------------------
-- The account is the one ADR 0011 already defines: an email address, address ciphertext at
-- rest under the operator-held key (ADR 0014), plus a grant the operator gives by hand and
-- can withdraw. No self-service, no password, no profile beyond a credit name.
--
-- `credit_name` is NOT NULL because THERE IS NO ANONYMOUS REVIEW (the operator's amendment
-- on acceptance, 2026-08-28): a reviewer chooses how they are shown, but is always shown. A
-- review is an assertion into the record, and an assertion has an author.
--
-- These columns are OPERATIONAL, not provenance: a re-grant clears `revoked_at`, a rename is
-- a rename. Append-only applies to `review_action`, never here. The cost, accepted with eyes
-- open: a page archived before a rename showed the old credit name and the store does not
-- reconstruct what was shown — the same current-state debt a party's display name carries.
CREATE TABLE reviewer (
    reviewer_id   INTEGER PRIMARY KEY,        -- permanent, never reused or renumbered:
                                              -- provenance points here for ever (ADR 0015's
                                              -- discipline for party ids, same reason)
    email_hash    TEXT NOT NULL UNIQUE,       -- HMAC-SHA256 of the normalised address, as
    email_enc     TEXT NOT NULL,              -- 0005; the key-rotation pass MUST cover this
    credit_name   TEXT NOT NULL CHECK (credit_name <> ''),
    counts_public INTEGER NOT NULL DEFAULT 0 CHECK (counts_public IN (0, 1)),
    granted_at    TEXT NOT NULL,
    granted_note  TEXT NOT NULL,              -- the operator's reason, in words
    revoked_at    TEXT                        -- withdrawal ends NEW actions; past rows stand
);

-- Its own table, and not a row on `subscription_token`: that one cascades on unsubscribe,
-- and a reviewer must not lose sign-in by unsubscribing from an alert.
CREATE TABLE reviewer_token (
    token_hash TEXT PRIMARY KEY,              -- hashed, single-use, enumerating nothing
    reviewer_id INTEGER NOT NULL REFERENCES reviewer (reviewer_id),
    expires_at TEXT NOT NULL,
    issued_at  TEXT NOT NULL,
    used_at    TEXT
);
CREATE INDEX reviewer_token_by_reviewer ON reviewer_token (reviewer_id);

-- ---------------------------------------------------------------------------
-- The vocabularies
-- ---------------------------------------------------------------------------
CREATE TABLE review_queue_vocab (
    queue TEXT PRIMARY KEY,
    note  TEXT NOT NULL
);
-- Only queues whose target exists today. `schema-draft.md` § 7 names two more and why they
-- are not here: a READER REPORT needs a `reader_report` row to queue on, which is the
-- `/contribute` landing the OCR plan promises and no table yet; and BENCHMARK LABELS are
-- not a store queue at all — `labels.csv` is a repo file with no stable row identity, and
-- its review is the git history. That kind was withdrawn rather than seeded empty.
INSERT INTO review_queue_vocab VALUES
    ('citation_exposed',    'a docket number a fused footnote marker could explain'),
    ('citation_unresolved', 'a real edge the registry cannot resolve (ADR 0017 D2)'),
    ('citation_repaired',   'a rule-2 repair: the raw failed and a stripped reading resolved'),
    ('correction',          'a reader or the operator says a stored row is wrong');

CREATE TABLE review_decision_vocab (
    decision TEXT PRIMARY KEY,
    note     TEXT NOT NULL
);
INSERT INTO review_decision_vocab VALUES
    ('accepted',  'the stored assertion is right; a human row now says so'),
    ('rejected',  'it is wrong; a human row says it does not resolve'),
    ('corrected', 'it is wrong and the human row carries the right answer'),
    ('escalated', 'not decidable here — the only decision that produces NO assertion');

-- ---------------------------------------------------------------------------
-- review_action — APPEND-ONLY: one decision per queue item
-- ---------------------------------------------------------------------------
-- `target_key` is the row reviewed, rendered canonically, and `produced_key` is the row the
-- action WROTE. They are different columns because they are different rows, and
-- `citator-schema.md` § D records the first draft naming the wrong one: pointing
-- `produced_key` at the citation would break § 7's authoritative join to
-- `reviewer.credit_name`.
--
-- `target_key_version` is the normaliser that rendered `target_key` (ADR 0018 D1). Without
-- it a re-normalisation strands every human row — which is the exact failure the natural key
-- was kept readable to prevent, and the reason a digest was refused. A key rendered under
-- one version and read under another must be visibly, not silently, different.
--
-- `method_version` is the QUEUE's convention version: what evidence was shown and under
-- which rules the decision was made. A reviewer who saw less than today's reviewer saw
-- decided a different question.
-- A typed target, because `target_table` is the other half of every key this table names.
-- Untyped, `'citation_resolutions'` (one letter) escapes the GLOB below AND escapes
-- `review_action_live`'s de-duplication against the correctly spelled rows — two live
-- decisions on one item, and nothing says so. Migration 0014 solved the same problem with
-- `measured_target_vocab`; this is cheap now and a table rebuild later.
CREATE TABLE review_target_vocab (
    target_table TEXT PRIMARY KEY,
    keyed        TEXT NOT NULL CHECK (keyed IN ('natural', 'surrogate')),
    UNIQUE (target_table, keyed)               -- so review_action can FK the pair
);
INSERT INTO review_target_vocab VALUES
    ('citation', 'natural'),
    ('citation_reading', 'natural'),
    ('citation_resolution', 'natural'),
    ('citation_judgement', 'natural'),
    ('citation_treatment', 'natural'),
    ('decision_decided_date', 'natural'),
    ('party_relationship', 'surrogate');

CREATE TABLE review_action (
    action_id          INTEGER PRIMARY KEY,
    reviewer_id        INTEGER NOT NULL REFERENCES reviewer (reviewer_id),
    queue              TEXT NOT NULL REFERENCES review_queue_vocab (queue),
    target_table       TEXT NOT NULL,
    -- copied from the vocabulary so the CHECK below can read it: SQLite forbids a subquery
    -- in a CHECK, and the composite FK is how migration 0014 types `citation_judgement`'s
    -- value domain for exactly the same reason
    target_keyed       TEXT NOT NULL,
    target_key         TEXT NOT NULL CHECK (target_key <> ''),
    target_key_version TEXT NOT NULL,
    method_version     TEXT NOT NULL,
    decision           TEXT NOT NULL REFERENCES review_decision_vocab (decision),
    detail             TEXT,                  -- JSON, typed per queue
    -- THE AUTHORITATIVE LINK, written in the same transaction as the row it names. There is
    -- no backward pointer from the assertion, because two pointers can disagree and one
    -- cannot.
    produced_table     TEXT,
    produced_key       TEXT,
    asserted_at        TEXT NOT NULL,
    superseded_by      INTEGER REFERENCES review_action (action_id),
    -- An IMPLICATION, not a biconditional: `escalated` decides nothing, so it must produce
    -- nothing. The reverse is deliberately NOT asserted, because `schema-draft.md` § 7 also
    -- names QUEUES WITH NO ASSERTION EFFECT — a reader report is the one it works out — and
    -- a biconditional would force every such decision to be mislabelled `escalated`, or the
    -- table to be rebuilt once it holds provenance ADR 0016 says must stay.
    CHECK (decision <> 'escalated' OR produced_table IS NULL),
    CHECK ((produced_table IS NULL) = (produced_key IS NULL)),
    -- a natural-keyed target is named by its key, never by a surrogate id. The GLOB is a
    -- SHAPE check — at least four slash-separated segments — and `review_target_vocab.keyed`
    -- is what says which tables it applies to, so a new target declares its own shape
    CHECK (target_keyed = 'surrogate' OR target_key GLOB '*/*/*/*'),
    FOREIGN KEY (target_table, target_keyed)
        REFERENCES review_target_vocab (target_table, keyed)
);
-- One live decision per (queue, target). A later review supersedes; it does not sit beside.
CREATE UNIQUE INDEX review_action_live ON review_action (queue, target_table, target_key)
    WHERE superseded_by IS NULL;
-- the queue's own read: what has already been decided, so it can be excluded
CREATE INDEX review_action_by_target ON review_action (target_table, target_key)
    WHERE superseded_by IS NULL;
CREATE INDEX review_action_by_reviewer ON review_action (reviewer_id, asserted_at);
-- § 7's authoritative join: "who reviewed this?" reads produced_table + produced_key
CREATE INDEX review_action_by_produced ON review_action (produced_table, produced_key)
    WHERE superseded_by IS NULL AND produced_key IS NOT NULL;

-- ---------------------------------------------------------------------------
-- The exposure test becomes a stored judgement
-- ---------------------------------------------------------------------------
-- Migration 0014 declared `judgement_vocab` extensible by INSERT and this is the first one.
-- It is a judgement rather than a column for the same reason the span test is (ADR 0017 D4):
-- it decides what a published edge IS, so it carries its own method, version and provenance
-- and is never a predicate computed inside a view.
--
-- The domain is `boolean`, whose two members migration 0014 already seeded — so this INSERT
-- adds a question, not a type.
INSERT INTO judgement_vocab VALUES ('exposed', 'boolean');

PRAGMA user_version = 15;

COMMIT;
