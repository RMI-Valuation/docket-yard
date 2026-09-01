-- Migration 0014: the citator's five assertion families, their ordering registry and their
-- measurement registry — ADR 0018, under the shipping decision of ADR 0017, both Accepted
-- by the operator 2026-09-01. docs/schema-draft.md § Citations was revised to this shape
-- first; docs/citator-schema.md carries the argument behind each table.
--
-- NOTHING WRITES TO THESE TABLES YET. The extraction pipeline is the next piece of work.
-- What ships here is the shape, so that the first edge has somewhere correct to land.
--
-- Dry-run through this shape: the sixty-decision benchmark loaded through all four live
-- families and the projection computed in SQL reproduces the Python scorer pair for pair.
-- All 60 decisions had fetched bytes to hang an edge on, so the two sides were compared over
-- the whole sheet and not a subset; `tools/rmi-ai-machine/citation_dryrun.py` reports that
-- count on every run and exits non-zero if the chains disagree on a single pair. Since
-- 2026-09-01 it runs THROUGH `docketyard.citator`, so it checks the shipping code rather
-- than a second implementation that agrees with it today.
--
-- THE FIGURES MOVED ON 2026-09-01, AFTER A DEFECT IN THE SCORER'S REGISTRY, and they are
-- restated here rather than quietly swapped. `projection_score.printed()` built its registry
-- by round-tripping each `docket` row through `norm_target`, which is not idempotent: it
-- reads `AB 1296X` as `AB 1296 (X)` but reads `AB 1296 (X)` as `AB 1296`. So all 2,711 held
-- dockets that carry a suffix and no sub-docket entered the registry WITHOUT their suffix,
-- every finding naming one scored as a registry unresolvable, and the projected figure was
-- measured low. Fixed by building the key from the columns, which is what the shipped
-- `citator.keys.registry_key` does and what a test now pins the two equal on.
--
--   on `data/benchmark/runs-regex/regex-own`, re-derived 2026-09-01:
--     extraction   214 of 225   95.1%
--     resolution   214 of 225   95.1%   (0 registry unresolvables, was 4)
--     PROJECTION   205 of 225   91.1%   (was 201, 89.3%)
--     precision    205 true of 209 shown = 98.1%   (was 201 of 205, 98.0%)
--
-- ADR 0017 § The figures publishes 97.8 / 93.3 / 89.3 and 98.0%, measured on a DIFFERENT
-- run — the finder with its registry filter removed — whose run directory is not in `data/`.
-- Those numbers are therefore NOT RE-DERIVABLE today, and they were measured with the same
-- broken registry. Restating them is the operator's, and it needs that run kept.
--
-- ============================================================================
-- The eight items ADR 0018 § Owed at the migration owes, and where each is paid
-- ============================================================================
--
-- Four the first edge exercises, so none could be deferred:
--
--  1. `measured_target` INSIDE class_measurement's COALESCE unique index, with a scoped
--     `class` vocabulary. Without it, an extraction score and a projection score of the
--     same class, method and channel collide on the whole key and one of two published
--     numbers is lost — which is the "quoting one stage for another" error ADR 0017 made
--     four times, made structural. `class_vocab` is keyed (measured_target, class), so
--     `docket` at the extraction stage and `docket` at the projection stage are declared
--     separately and a class cannot be attached to a stage that never measured it.
--     Every table that POINTS at a measurement also carries `measured_target` and
--     foreign-keys the pair, so a row cannot be stamped from another stage's figure — see
--     § The stage-scoped score pointer.
--
--  2. THE PROJECTION PREDICATE IS STATED PER FAMILY. See § The projection, below. It is
--     stated and not built, because it cannot be a view: the formula binds a rank_version
--     and nothing in this store dates which ranking was in force (ADR 0018's one deferred
--     item). docs/citator-query-2.sql is the executable statement of it, and after this
--     migration it RUNS — empty, but it runs, which is the only check the shape gets.
--
--  3. A `resolve` ROW ASSERTS THE COMPLETE OUTCOME. `citation_resolution` carries
--     `outcome`, `cited_docket_id` AND `cited_decision_id` on one row, rather than moving
--     `cited_decision_id` to a family of its own. Query 2 keys on the decision column and
--     the family test reads the docket column, and they must be the SAME resolution or the
--     query joins one method's work-level answer to another's docket-level one. ADR 0018
--     D4 already makes work resolution a property of the resolving act — "the phrase's own
--     verb gates which column is matched" — so the two columns are one judgement, not two.
--     A split would have needed a second precedence chain and a second projection term for
--     no gain. The CHECKs below make the row's outcome internally consistent.
--
--  4. citation_judgement's NATURAL KEY IS DECLARED, with `value` as payload — see the
--     table. `value`'s domain is declared per judgement and enforced by a composite FK, so
--     the boolean the projection compares (`span_names_document`) cannot be written as an
--     untyped string. That was the EAV objection, answered by a key rather than by prose.
--
-- Three cheap now and a table rebuild later, so taken now:
--
--  5. An `ordinal` in the decided-date key. 55 of 60 decisions print exactly one `Decided:`
--     line and none prints two, so it buys nothing today — and it costs nothing today,
--     while the day a document prints two the key would silently keep one.
--  6. `(target_kind, target_form)` on assertion_method, so ADR 0018 D1's one-owner rule has
--     a table. See § assertion_method for what the index does and does not enforce.
--  7. A home for the veto's false-veto rate: `class_measurement.false_veto_rate`, and
--     `assertion_method.score_row_id` REQUIRED on any `suppress` row and scoped by the
--     stage pair to a `citation_resolution` measurement. That is ADR 0018 D7's "a suppress
--     row exists only once its false-veto rate is measured" as a constraint rather than as
--     a sentence somebody has to remember. WHAT IS STILL PROSE, stated rather than implied:
--     nothing forces that measurement to carry a `false_veto_rate` rather than a recall,
--     and nothing forces the `citation_resolution` rows a suppress method writes to carry
--     `confidence_state = 'measured'` — both are cross-row conditions SQLite can only
--     express with a trigger, and the veto ships inert (ADR 0018 D7: the projection may not
--     reference it until it is measured on both readings), so a trigger for an inert
--     mechanism is not worth its weight. It is owed with the veto, not with this migration.
--
-- One deferred WITH ITS COST NAMED, unchanged: nothing dates `rank_version`, so a
-- projection binds a version rather than reading one. A `projection_rule` table is an
-- addition any day. What is NOT recoverable is which ranking was in force between the first
-- edge and the day it lands.
--
-- ============================================================================
-- citation_treatment IS IN THIS MIGRATION, against the review's recommendation
-- ============================================================================
-- The adversarial review recommended it sit out: it ships empty, it shares a key and a
-- projection rule with citation_judgement, and it is a DROP later rather than a one-way
-- door. Every one of those is true. It is here anyway, for one reason that outweighs them:
-- docs/citator-query-2.sql INNER JOINs citation_treatment and treatment_vocab, and both
-- ADRs cite that file as the proof that Q2 is writable against this shape. Without the
-- table the file cannot be executed at all, and the first migration to make the check
-- possible would ship with the check still impossible. With it, Q2 parses, plans and
-- returns the empty set ADR 0017 D7 says it must on day one — an empty result is a
-- measurement, an unparseable query is not.
-- The same argument that makes it safe to defer makes it free to include: nothing writes
-- it, so nothing depends on its shape being final. If the treatment pass wants a different
-- one, it is a DROP and a CREATE against zero rows.
--
-- ============================================================================
-- § Why citation_key is a table (schema-critic, 2026-09-01)
-- ============================================================================
-- The first draft of this migration put the natural key's four columns on `citation` under
-- a NON-partial UNIQUE, so the children could foreign-key them — SQLite requires a foreign
-- key's parent to be a full UNIQUE, never a partial one. The argument was that a
-- supersession of a citation row always mints a different key, so a key never has two rows.
-- That is true of the misclassification path ADR 0018 D2 describes and FALSE of three
-- others, all of which the accepted records require:
--
--   * re-extraction at a higher method_version — ADR 0017 § Consequences, "a better
--     extractor supersedes rather than rewrites", and schema-draft.md § 5's break A3;
--   * an ownership handover to a new method at a new `rank_version`, which the registry
--     below explicitly permits and which the store would then forbid;
--   * a retraction with NO successor — a docket-shaped string that is not a citation at all
--     (the WB25-53 trap). 0009_party_ids_permanent.sql's idiom for that is a `superseded_by`
--     pointing at its own row, and a non-partial UNIQUE plus an anti-self CHECK forbade it.
--
-- So identity and the assertion about it are separate rows, exactly as `decision_work` is
-- separate from `citation_resolution.cited_decision_id` and for exactly the same reason
-- (citator-schema.md § F: "cited_decision_id keys on a key of no table"). `citation_key` is
-- the key, and nothing else; `citation` is the extraction assertion, keyed on it, with a
-- partial live index and ordinary supersession. Children foreign-key `citation_key` and are
-- unaffected. The projection's obligation is unchanged and undiminished: it must join
-- `citation` and require it live, or a retraction changes nothing (ADR 0018 D2).
--
-- ============================================================================
-- § The projection, stated per family (owed item 2)
-- ============================================================================
-- Every family: only rows with `superseded_by IS NULL`, and the predicate
-- `confidence_state IN ('measured','human')` applied to the CANDIDATE SET — never to the
-- rank-1 row, where it deletes edges instead of filtering them (an unmeasured OCR
-- resolution outranking a measured text-layer one takes rank 1 and the edge vanishes).
--
--   citation_key         the identity. Not an assertion; nothing to order and nothing to
--                        supersede.
--   citation             joined and REQUIRED LIVE by every projection — AND BY EVERY READ
--                        THAT PUBLISHES, which is wider than the projection. The children
--                        foreign-key `citation_key`, not `citation`, so a resolution can
--                        outlive the extraction assertion that produced it. ADR 0017 D2's
--                        "cites EP 445 (not in the record)" display and the unresolved
--                        review queue read `citation_resolution` directly; if they do not
--                        also join live `citation`, a retraction bites the published edge
--                        and not the queue. A retraction
--                        supersedes only this row; the resolutions and judgements anchored
--                        on the retracted key still read superseded_by IS NULL. This join
--                        is what makes a retraction bite. Highest-ranked live row, and in
--                        practice one: a class has one owning method.
--   citation_reading     joined on the resolution's own reading_channel. No ranking: the
--                        channel is in the key, and a re-read supersedes within it.
--                        INVARIANT, because the join is inner and channel-matched: a
--                        resolution on a channel with no live reading row PROJECTS NOTHING.
--                        A `human` resolution must therefore be written together with a
--                        `human` citation_reading carrying the passage the reviewer read.
--   citation_resolution  if any live `suppress` row exists FOR THE SAME READING CHANNEL,
--                        that channel's candidates drop out; of what remains, the
--                        highest-ranked live `resolve` row whose outcome IN
--                        ('resolved','repaired'). The channel match is required because a
--                        veto names the reading it checked. The outcome filter is required
--                        because a flat rank makes every rule-2 repair unreachable: rule 1
--                        writes a row when it FAILS and outranks the repair that exists
--                        because it failed. THE VETO FILTERS THE CANDIDATE SET TOO, for the
--                        same reason the confidence predicate does: applied after the rank
--                        it deletes an edge a second, unvetoed channel could still carry.
--   citation_judgement   THE HIGHEST-RANKED LIVE ROW AND NOTHING ELSE. There is no
--   citation_treatment   `outcome` column on either table to restrict on, and inventing one
--                        would mean writing NULLs into a column whose NULL already means
--                        three things.
--
-- And the resolution term is NOT the whole projection. An edge projects only when the
-- resolution term holds AND one of two family terms does: the target docket is outside the
-- citing work's family (the docket, its sub-dockets and its parent, unioned over every
-- docket a consolidated decision is entered in), OR — if it is inside — a live
-- `span_names_document` judgement says 'true', defaulting to SUPPRESS where nothing has
-- judged it. Measured on the sixty-decision sheet, 2026-09-01: reading the resolution term
-- alone and stopping there shows 214 true of 243 = 88.1%, against 205 of 209 = 98.1% with
-- both terms (re-derived 2026-09-01 with the registry fixed, by removing the family branch
-- from the dry-run projection). ADR 0018 D7 states this comparison as "88.4%", which is
-- near enough to 88.1% that the difference is the run, not the rule — an earlier reading of
-- 87.9% here was an artefact of the same registry defect, and the argument it started was
-- not worth having.
--
-- THE SPAN TERM IS PER PAGE AND THE RULE IS PER WORK, and the two are reconciled by the
-- fold, not by a wider judgement. ADR 0017 D4 makes the test disjunctive over every
-- occurrence of a target in the citing WORK; a judgement row is keyed per page. A page
-- whose span names no document is filtered out, another page's row for the same target
-- survives, and the DISTINCT over the work collapses them — so the disjunction emerges.
-- That is not reasoning alone: the dry run computes the projection this way in SQL and
-- reproduces the scorer's 201/205 pair for pair.
--
-- A target printed SEVERAL TIMES ON ONE PAGE is one row, and the shipping extractor never
-- produces the second occurrence: `benchmark_regex.findings()` carries a per-page `seen`
-- set and emits at most one finding per (page, key). So the within-page count measured over
-- the sixty decisions — 0 of 356 (document, page, target) rows with more than one
-- occurrence — is FORCED BY THE PRODUCER and is not a property of the corpus. Stated that
-- way because the first draft of this header read it as a corpus measurement, in the manner
-- of owed item 5's "none prints two", and it is not one *(corrected 2026-09-01, second
-- schema-critic pass)*.
--
-- What follows for the key: it needs no ordinal, because the producer cannot collide on it.
-- What follows for the span test: the disjunction ADR 0017 D4 requires runs over PAGES, not
-- over occurrences within a page, and `quoted_passage` joins nothing today because there is
-- never more than one quote to join. D4's own worry — "the extractor quotes the FIRST
-- match's line, which is usually the running caption" — therefore remains live WITHIN a
-- page: a page whose caption is the first match and whose body names a document reads as
-- span-false, and another page has to rescue the edge. The published 89.3%/98.0% were
-- measured with that behaviour, so it is a mis-description to fix and not a regression to
-- chase. Fixing it is a change to the finder's `seen` set, never to this key.
--
-- The figures this shape ships at are 91.1% projected recall — 205 of the 225 docket-shaped
-- truth targets on the sixty-decision sheet — and 98.1% precision, which is 205 true of the
-- 209 edges shown and has a different denominator. Both are re-derivable with
-- tools/rmi-ai-machine/projection_score.py. They are the PROJECTION line. The extraction
-- line (97.8%) describes the finder and is never quoted for what a reader sees.

BEGIN TRANSACTION;

-- ---------------------------------------------------------------------------
-- Vocabularies. Closed sets the two records decided; everything else is an INSERT.
-- ---------------------------------------------------------------------------

CREATE TABLE target_kind_vocab (
    target_kind TEXT PRIMARY KEY                -- WHAT is cited, and it is in the key
);
INSERT INTO target_kind_vocab VALUES ('stb'), ('court');

CREATE TABLE reading_vocab (
    reading_channel TEXT PRIMARY KEY
);
-- 'human' exists because the channel is in every key below and a human row must carry
-- something legal (ADR 0018 D3).
INSERT INTO reading_vocab VALUES ('text-layer'), ('ocr'), ('human');

CREATE TABLE outcome_vocab (
    outcome TEXT PRIMARY KEY
);
-- Typed, because a null docket id otherwise means three things at once: not tried, tried
-- and failed, and tried and vetoed. 'repaired' is rule 2 — the raw fails, exactly one
-- trailing-digit-stripped reading resolves, and the printed number has five digits — and
-- it is a distinct method at lower confidence, never a rewrite of the raw.
INSERT INTO outcome_vocab VALUES ('resolved'), ('unresolved'), ('repaired'), ('vetoed');

-- `polarity` is the column validation query 2's whole answer turns on, and it is NOT one of
-- the three things `projection_rule_version` names. Re-classifying `narrows` would silently
-- restate every published Q2 answer. Recorded as a cost, not patched: the table is empty,
-- no treatment row exists, and versioning a vocabulary nothing writes to would be shape
-- without a purpose. It is owed with the treatment pass.
CREATE TABLE treatment_vocab (
    treatment TEXT PRIMARY KEY,
    polarity  TEXT NOT NULL CHECK (polarity IN ('positive', 'neutral', 'negative'))
);
-- Every edge in the first slice is 'cites'; the typing pass is later, which is one of the
-- reasons validation query 2 returns nothing on the day this ships.
INSERT INTO treatment_vocab VALUES
    ('cites',          'neutral'),
    ('follows',        'positive'),
    ('distinguishes',  'negative'),
    ('narrows',        'negative'),
    ('overrules',      'negative'),
    ('supersedes',     'negative');

-- A judgement declares its value domain, or one `value` column holds a boolean and two
-- enumerations untyped — the EAV shape docs/citator-schema.md § B rejects a whole document
-- over, and it would leave the projection comparing a boolean as a string.
CREATE TABLE judgement_vocab (
    judgement    TEXT PRIMARY KEY,
    value_domain TEXT NOT NULL,
    UNIQUE (judgement, value_domain)            -- so citation_judgement can FK the pair
);
INSERT INTO judgement_vocab VALUES
    ('span_names_document', 'boolean'),
    ('target_form',         'target_form'),
    ('kind',                'kind');

CREATE TABLE judgement_value_vocab (
    value_domain TEXT NOT NULL,
    value        TEXT NOT NULL,
    PRIMARY KEY (value_domain, value)
);
-- 'docket' is the only form with an owner today: ADR 0017 D1 ships the docket-shaped class
-- from regex-docket-cite and buys the API model for the rest, which is not in this slice.
-- The 'kind' domain is DELIBERATELY EMPTY: the typing pass has not decided its values, and
-- an empty domain means no `kind` judgement can be written until it does. That is the
-- point of declaring a domain rather than a column type.
INSERT INTO judgement_value_vocab VALUES
    ('boolean',     'true'),
    ('boolean',     'false'),
    ('target_form', 'docket');

CREATE TABLE date_kind_vocab (
    date_kind TEXT PRIMARY KEY
);
INSERT INTO date_kind_vocab VALUES ('decided'), ('effective');

-- ---------------------------------------------------------------------------
-- The measurement registry (ADR 0018 D8) — the single home for every score
-- ---------------------------------------------------------------------------

CREATE TABLE measured_target_vocab (
    measured_target TEXT PRIMARY KEY            -- WHICH STAGE a figure is true of
);
INSERT INTO measured_target_vocab VALUES
    ('citation'),                               -- extraction: the finder saw it
    -- the reading is here because ADR 0017 D3 names the day it will be measured: OCR ships
    -- "stored and unprojected UNTIL SOMEBODY MEASURES IT". SQLite cannot alter a CHECK, and
    -- citation_reading is the largest table here, so the stage is declared now and its
    -- class_vocab left empty — no row can claim 'measured' until somebody scores it
    ('citation_reading'),
    ('citation_resolution'),                    -- and the registry resolved it
    ('citation_judgement'),
    ('citation_treatment'),
    ('decision_decided_date'),
    ('projection');                             -- and a reader sees it

CREATE TABLE class_vocab (
    measured_target TEXT NOT NULL REFERENCES measured_target_vocab (measured_target),
    class           TEXT NOT NULL,
    PRIMARY KEY (measured_target, class)        -- owed item 1: the class vocabulary is
);                                              -- SCOPED, so a class cannot be attached to
                                                -- a stage that never measured it
-- Only classes something has actually measured. 'decision_decided_date' has a stage and no
-- class, deliberately, the same way the 'kind' judgement has a domain and no members: until
-- somebody scores it, no row of that table can claim `confidence_state = 'measured'`.
INSERT INTO class_vocab VALUES
    ('citation',            'docket'),
    ('citation_resolution', 'docket'),
    ('citation_resolution', 'on-page-veto'),    -- the veto's own class; its figure is a
                                                -- false-veto RATE, not a confidence
    ('citation_judgement',  'span_names_document'),
    ('projection',          'docket');

CREATE TABLE class_measurement (
    measurement_id            INTEGER PRIMARY KEY,   -- so the pointer from an assertion row
                                                     -- is ONE column, ADR 0018 D8
    measured_target           TEXT NOT NULL,
    class                     TEXT NOT NULL,
    extraction_method         TEXT NOT NULL CHECK (extraction_method <> ''),
    extraction_method_version TEXT NOT NULL CHECK (extraction_method_version <> ''),
    -- NULL for a stage that runs BEFORE resolution. This is why the identity index below
    -- has to COALESCE: SQLite UNIQUE treats NULLs as distinct, so without it two extraction
    -- measurements of one class on one day would both be legal. The empty string is
    -- forbidden alongside, or it collides with the NULL the COALESCE maps to.
    resolution_method         TEXT CHECK (resolution_method <> ''),
    resolution_method_version TEXT CHECK (resolution_method_version <> ''),
    reading_channel           TEXT NOT NULL REFERENCES reading_vocab (reading_channel),
    -- names three things together — the span test's version, the family closure's version
    -- and rank_version — because the projection is that product. NULL before projection.
    projection_rule_version   TEXT CHECK (projection_rule_version <> ''),
    benchmark_date            TEXT NOT NULL CHECK (benchmark_date <> ''),
    score_file                TEXT NOT NULL,    -- re-measuring one version is an INSERT,
                                                -- never an UPDATE of a published number
    truth_count               INTEGER,
    found_count               INTEGER,
    shown_count               INTEGER,
    recall                    REAL CHECK (recall IS NULL OR (recall >= 0 AND recall <= 1)),
    precision                 REAL
                              CHECK (precision IS NULL OR (precision >= 0 AND precision <= 1)),
    -- the on-page veto carries a RATE, not a confidence: the 15 failures of 977 were ALL
    -- false vetoes, at 1.5%, on born-digital text only and unmeasured for OCR
    false_veto_rate           REAL
                              CHECK (false_veto_rate IS NULL
                                     OR (false_veto_rate >= 0 AND false_veto_rate <= 1)),
    measured_at               TEXT NOT NULL,
    -- a row that measures nothing is not a measurement
    CHECK (recall IS NOT NULL OR precision IS NOT NULL OR false_veto_rate IS NOT NULL),
    -- a projection figure without the rule it is a property of is the error both records
    -- were corrected for: a figure may only be published with its rule named beside it
    CHECK (measured_target <> 'projection' OR projection_rule_version IS NOT NULL),
    CHECK ((resolution_method IS NULL) = (resolution_method_version IS NULL)),
    FOREIGN KEY (measured_target, class) REFERENCES class_vocab (measured_target, class),
    -- § The stage-scoped score pointer: measurement_id is already unique, and declaring the
    -- PAIR unique is what lets every assertion table foreign-key (score_row_id,
    -- measured_target) together. Without it a row could be stamped from another stage's
    -- figure — 98.0% displayed beside an extraction — which is the error ADR 0017 made four
    -- times, in the one table built to stop it.
    UNIQUE (measurement_id, measured_target)
);
-- Owed item 1. `measured_target` is the FIRST column for a reason: without it in the index
-- an extraction score and a projection score of the same class collide.
--
-- `score_file` is deliberately NOT in this index: a path is not a version.
--
-- BUT THE COLLISION THIS LEAVES IS A REAL ONE, and it is named rather than argued away. The
-- key is exactly the one ADR 0018 D8 states, and it has no scorer version and no evaluation
-- set in it — so a SCORER FIX at unchanged pipeline versions on the same day cannot be
-- inserted. That is not hypothetical: it is the 98.2% → 98.0% correction of 2026-09-01, and
-- ADR 0017 § The exposure test measures two populations (225 truth, 249 emitted) on one day.
-- The recovery available today is a new `benchmark_date`, which falsifies the column.
-- Widening the key is an ALTER plus a reindex, cheap now and cheap later — and it would
-- depart from a key an accepted record names, so it was the operator's. DECLINED
-- 2026-09-01, on grounds worth recording: these figures are a spot in time and move as the
-- registry grows through waves 2-3, so a re-measurement lands on a new `benchmark_date`
-- anyway and the same-day collision is rare. In `docs/deferred.md`; pull it in if the
-- scorer ever changes twice in one day. `class_measurement` is also the one derived table
-- in this migration with no `method`/`method_version` of its own, which is the same gap
-- seen from ADR 0007's side.
CREATE UNIQUE INDEX class_measurement_identity ON class_measurement (
    measured_target, class,
    extraction_method, extraction_method_version,
    COALESCE(resolution_method, ''), COALESCE(resolution_method_version, ''),
    reading_channel, COALESCE(projection_rule_version, ''), benchmark_date
);

-- ---------------------------------------------------------------------------
-- § assertion_method — the single ordering registry for all five families
-- ---------------------------------------------------------------------------
-- APPEND-ONLY. Several assertions are live per edge, so "the live one" is singular only
-- against an order — and an order stored per row records a POLICY where the row should
-- record an OBSERVATION, making a re-rank an UPDATE of every row.
--
-- A row here is one of three things, and the CHECK below says which:
--   an OWNERSHIP row   (target_table = 'citation')          declares WHO MAY WRITE a class
--   a READING row      (target_table = 'citation_reading')  declares a reading method
--   a RANKING row      (the three ranked families)          declares WHO WINS
--
-- An ownership row carries no reading_channel, because the citation key carries none: a
-- text-layer and an OCR reading of one page produce ONE key, so ownership of a class cannot
-- be per-channel either. It carries no rank, because a rank there would be a fake ordering
-- inside the registry whose whole job is ordering.
--
-- `role` is required only where the projection READS one — the resolution family, whose
-- formula has a suppress term. Judgement and treatment rank and nothing else (see § The
-- projection), so forcing a role on them would invite a judgement method declared
-- 'suppress', which means nothing and would then demand a false-veto rate.
--
-- NO ROWS ARE SEEDED. A method declares itself at run time (ADR 0018 D1: "fixed at insert
-- time from the owning method's own declaration"), and seeding a method version here would
-- weld it into DDL that the code then has to match.
CREATE TABLE assertion_method (
    method_row_id   INTEGER PRIMARY KEY,
    target_table    TEXT NOT NULL CHECK (target_table IN (
                        'citation', 'citation_reading', 'citation_resolution',
                        'citation_judgement', 'citation_treatment')),
    method          TEXT NOT NULL,
    method_version  TEXT NOT NULL,
    reading_channel TEXT REFERENCES reading_vocab (reading_channel),
    role            TEXT CHECK (role IN ('suppress', 'resolve')),
    precedence_rank INTEGER,
    -- owed item 6: the one-owner rule of ADR 0018 D1, given a table
    target_kind     TEXT REFERENCES target_kind_vocab (target_kind),
    target_form     TEXT CHECK (target_form <> ''),
    -- owed item 7: ADR 0018 D7's "a suppress row exists only once its false-veto rate is
    -- measured". Absence of the registry row is how the record says "not yet trusted"; this
    -- stops the row existing before the number does, and the stage pair stops it pointing
    -- at a measurement of some other stage.
    measured_target TEXT CHECK (measured_target IS NULL
                                OR measured_target = 'citation_resolution'),
    score_row_id    INTEGER,
    rank_version    TEXT NOT NULL,              -- a re-rank is a new version, never an
    declared_at     TEXT NOT NULL,              -- UPDATE of the rows already written
    CHECK (
        CASE target_table
            WHEN 'citation' THEN
                target_kind IS NOT NULL AND target_form IS NOT NULL
                AND reading_channel IS NULL AND role IS NULL AND precedence_rank IS NULL
            WHEN 'citation_reading' THEN
                target_kind IS NULL AND target_form IS NULL
                AND reading_channel IS NOT NULL AND role IS NULL AND precedence_rank IS NULL
            WHEN 'citation_resolution' THEN
                target_kind IS NULL AND target_form IS NULL
                AND reading_channel IS NOT NULL AND role IS NOT NULL
                AND precedence_rank IS NOT NULL
            ELSE                                -- judgement and treatment: rank, no role
                target_kind IS NULL AND target_form IS NULL
                AND reading_channel IS NOT NULL AND role IS NULL
                AND precedence_rank IS NOT NULL
        END
    ),
    CHECK (COALESCE(role, '') <> 'suppress' OR score_row_id IS NOT NULL),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    FOREIGN KEY (score_row_id, measured_target)
        REFERENCES class_measurement (measurement_id, measured_target)
);
-- Owed item 6, enforced: one method owns each (target_kind, target_form) within a ranking
-- version. Two extractors emitting the same target on the same page would otherwise
-- collide, and the citation key has no method in it to separate them.
--
-- WHAT THIS INDEX DOES NOT ENFORCE, stated rather than implied: `target_form` has no
-- vocabulary FK. The forms live in judgement_value_vocab under the 'target_form' domain,
-- and SQLite cannot foreign-key a pair one half of which is a constant. A form misspelt on
-- an ownership row therefore owns nothing — the extractor looks up its own class, finds no
-- owner row and must refuse to insert. That is an insert-time failure and not a silent one,
-- which is the property that matters; a second vocabulary table kept in step by hand is the
-- failure mode ADR 0018 D7 names about web/cite.py, and would be worse.
CREATE UNIQUE INDEX assertion_method_one_owner
    ON assertion_method (rank_version, target_kind, target_form)
    WHERE target_table = 'citation';
-- The class columns are in the identity index too. Without them one method could declare
-- ownership of exactly ONE class per version — while ADR 0017 D1 buys the API model for
-- four (reporter cites, date-named decisions, court citations, dated obligations), so the
-- index paying owed item 6 would have been defeated by the index beside it.
CREATE UNIQUE INDEX assertion_method_identity
    ON assertion_method (rank_version, target_table, method, method_version,
                         COALESCE(reading_channel, ''),
                         COALESCE(target_kind, ''), COALESCE(target_form, ''));
-- "The highest-ranked live row" is singular only if the ranks are. Two methods sharing a
-- rank in one version make the projected edge non-deterministic across runs and across
-- SQLite releases — and the projection orders by this column alone.
CREATE UNIQUE INDEX assertion_method_rank
    ON assertion_method (rank_version, target_table, precedence_rank)
    WHERE precedence_rank IS NOT NULL;

-- ---------------------------------------------------------------------------
-- decision_work — the key cited_decision_id resolves against (citator-schema.md § F)
-- ---------------------------------------------------------------------------
-- stb_decision_id AND NOTHING ELSE. An attribute here would be current state entering a
-- registry by the back door. Written only by ingest from decision_observed and rebuildable
-- from the ledger; the resolver may reference it and must never insert into it.
--
-- Measured before proposing the primary key, because it is a one-way door: 1,736
-- stb_decision_ids carry more than one decision_record row and NOT ONE of them disagrees on
-- SERVICE DATE. Consolidation, not collision. (ADR 0018 D9's phrasing adds "or decision
-- number"; that half is vacuous, because the same record measures `decision_number` as
-- populated for 0 of 23,713 rows, and agreement on a column nobody has filled is not
-- evidence. The service-date half stands on its own and is what the key rests on.)
CREATE TABLE decision_work (
    stb_decision_id TEXT PRIMARY KEY
);
-- The rebuild from the ledger's own projection, so the registry is usable from row one.
-- INGEST MUST KEEP THIS IN STEP: a decision served after this migration and never added
-- here fails the resolver's foreign key. Nothing resolves yet, so nothing breaks today —
-- it is in TODO.md, owed with the pipeline.
INSERT INTO decision_work (stb_decision_id)
    SELECT DISTINCT stb_decision_id FROM decision_record;

-- ---------------------------------------------------------------------------
-- citation_key — the natural key of ADR 0018 D1, and nothing else
-- ---------------------------------------------------------------------------
-- (citing_document, page, target_kind, target_key), carried as typed columns. It is stable
-- across a text-layer and an OCR reading of the same bytes, which differ in the quoted
-- passage (10.8% CER) and would otherwise double every edge on re-read.
--
-- Every anchor is these four columns, rendered canonically as
-- '<sha256>/<page>/<target_kind>/<target_key>' where one string is wanted
-- (review_action.target_key, correction.target_key). NEVER a digest: the normalisation has
-- already changed once — the scorer's docket-suffix fix moved the docket-shaped truth from
-- 220 targets to 225 on 2026-08-30 — and under a digest that class of change rewrites every
-- key and strands every human row. `key_version` makes it a change somebody can see.
--
-- No provenance block: a key is not an assertion. What was asserted about it, by whom and
-- at what confidence, is `citation` below. See § Why citation_key is a table.
CREATE TABLE citation_key (
    citing_document TEXT NOT NULL REFERENCES document (document_sha256),
    page            INTEGER NOT NULL,
    target_kind     TEXT NOT NULL REFERENCES target_kind_vocab (target_kind),
    target_key      TEXT NOT NULL,              -- the NORMALISED target, never as printed
    key_version     TEXT NOT NULL,              -- the normaliser that produced target_key
    first_seen_at   TEXT NOT NULL,
    PRIMARY KEY (citing_document, page, target_kind, target_key)
);

-- ---------------------------------------------------------------------------
-- Family 1 — citation: the EXTRACTION assertion (ADR 0018 D2)
-- ---------------------------------------------------------------------------
-- NOT HERE, and neither is an accident:
--   cited_raw        the string as printed differs between readings, so on a row keyed
--                    stably across them whichever channel inserted first would own it for
--                    ever. It lives in citation_reading beside the passage it came from.
--   source_location  `page` in the key IS the location. A deliberate departure from
--                    schema-draft.md § 5's uniform block; do not restore the column.
--   treatment        a later pass's reading of the citing sentence, with its own method.
--   the resolved FKs a different assertion, measured at a different rate.
--
-- `target_kind` is in the key, so a misclassification cannot be corrected by supersession —
-- a corrected row mints a DIFFERENT key. It is a RETRACTION AND A FRESH ASSERTION: the new
-- row is written and the mis-keyed row's `superseded_by` points at it. A supersession
-- pointing at the row's OWN id is 0009_party_ids_permanent.sql's idiom for retired with no
-- successor, which is what a docket-shaped string that is not a citation at all needs.
--
-- The surrogate is used ONLY by that pointer. Every anchor is the four typed columns.
--
-- THE ORDER OF A SUPERSESSION IS FORCED by the partial live index, and it is the order
-- 0006_parties.sql's re-split already uses: retire the old row by pointing it at ITSELF,
-- insert the replacement, then repoint the retired row at the new id. Inserting first fails,
-- because for that instant two rows on one key would be live. ALL THREE STEPS GO IN ONE
-- TRANSACTION: a crash between the first and the third leaves a self-pointer that cannot be
-- told apart from a deliberate retirement with no successor.
--
-- AND A RETRACTION IS NOT SELF-DEFENDING, which is a writer obligation and not a constraint.
-- Retiring the last live row leaves the key with none, and the partial index then permits
-- the next extraction pass to insert a fresh one — undoing the retraction of a docket-shaped
-- string that is no citation at all. Two things stand in front of that: the trigger below,
-- which stops a model row superseding a human one, and the pipeline's own rule, owed with
-- it, that it must not re-assert a key whose last live row was retired by a human. The
-- `correction` row is the durable record of WHY; nothing joins it yet.
CREATE TABLE citation (
    citation_id            INTEGER PRIMARY KEY,
    citing_document        TEXT NOT NULL,
    page                   INTEGER NOT NULL,
    target_kind            TEXT NOT NULL,
    target_key             TEXT NOT NULL,
    asserted_from_document TEXT REFERENCES document (document_sha256),
    asserted_from_capture  INTEGER REFERENCES capture (capture_id),
    method                 TEXT NOT NULL,
    method_version         TEXT NOT NULL,
    asserted_at            TEXT NOT NULL,
    -- `confidence >= 0`, NOT 0006_parties.sql's `> 0`: ADR 0018 D8 has unmeasured rows
    -- carry 0, and the state is the predicate while the number is inert. confidence is
    -- never selected without confidence_state.
    confidence             REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    confidence_state       TEXT NOT NULL CHECK (confidence_state IN (
                               'measured', 'human', 'unmeasured', 'not-applicable')),
    measured_target        TEXT CHECK (measured_target IS NULL OR measured_target = 'citation'),
    score_row_id           INTEGER,
    superseded_by          INTEGER REFERENCES citation (citation_id),
    CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL)),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    FOREIGN KEY (score_row_id, measured_target)
        REFERENCES class_measurement (measurement_id, measured_target),
    FOREIGN KEY (citing_document, page, target_kind, target_key)
        REFERENCES citation_key (citing_document, page, target_kind, target_key)
);
CREATE UNIQUE INDEX citation_live ON citation
    (citing_document, page, target_kind, target_key)
    WHERE superseded_by IS NULL;
CREATE INDEX citation_by_document ON citation (citing_document) WHERE superseded_by IS NULL;
-- ADR 0017 D5 and schema-draft.md § 5: a review writes a `human` row, and A MODEL PASS MAY
-- NEVER SUPERSEDE ONE. That rule is prose on every other assertion table in this project,
-- and it is a trigger HERE because `citation` is the only family whose live key carries no
-- method — so the supersession order above does not merely permit a re-extraction to
-- displace a human row, it REQUIRES it before the new row can be inserted. The index shape
-- pushes against the rule, so the rule needs teeth. RAISE(ABORT) is the idiom
-- 0009_party_ids_permanent.sql already uses for a constraint SQLite cannot express.
-- A human row retired at itself still passes: the row it points at is its own, and human.
CREATE TRIGGER citation_human_row_is_not_a_model_pass_to_supersede
BEFORE UPDATE OF superseded_by ON citation
WHEN OLD.confidence_state = 'human'
 AND NEW.superseded_by IS NOT NULL
 AND (SELECT confidence_state FROM citation WHERE citation_id = NEW.superseded_by) <> 'human'
BEGIN
    SELECT RAISE(ABORT, 'ADR 0017 D5: a human citation row may only be superseded by a human row');
END;

-- ---------------------------------------------------------------------------
-- Family 2 — citation_reading: one row per reading of the page (ADR 0018 D3)
-- ---------------------------------------------------------------------------
-- The reading METHOD and its version are payload OUTSIDE the key. Inside it, a re-OCR at a
-- better engine would mint a row that supersedes nothing and doubles the live readings —
-- over a measured 1,480 of 9,663 image-only files, so not a corner case.
--
-- `quoted_passage` holds EVERY occurrence of the target on the page, joined: the span test
-- reads this column, and it is what the published precision was measured against.
CREATE TABLE citation_reading (
    reading_id             INTEGER PRIMARY KEY,
    citing_document        TEXT NOT NULL,
    page                   INTEGER NOT NULL,
    target_kind            TEXT NOT NULL,
    target_key             TEXT NOT NULL,
    reading_channel        TEXT NOT NULL REFERENCES reading_vocab (reading_channel),
    reading_method         TEXT,                -- the OCR engine and its version: payload,
    reading_method_version TEXT,                -- so a re-OCR MATCHES the key and supersedes
    cited_raw              TEXT NOT NULL,       -- the string as THIS reading printed it
    quoted_passage         TEXT NOT NULL,       -- what the span test reads
    source_location        TEXT,                -- JSON: {page, block_id, bbox}
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
    superseded_by          INTEGER REFERENCES citation_reading (reading_id),
    CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL)),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    CHECK ((reading_method IS NULL) = (reading_method_version IS NULL)),
    FOREIGN KEY (score_row_id, measured_target)
        REFERENCES class_measurement (measurement_id, measured_target),
    FOREIGN KEY (citing_document, page, target_kind, target_key)
        REFERENCES citation_key (citing_document, page, target_kind, target_key)
);
CREATE UNIQUE INDEX citation_reading_live ON citation_reading
    (citing_document, page, target_kind, target_key, reading_channel)
    WHERE superseded_by IS NULL;

-- ---------------------------------------------------------------------------
-- Family 3 — citation_resolution (ADR 0018 D4), and owed item 3
-- ---------------------------------------------------------------------------
-- Keyed on the natural key plus (method, method_version, reading_channel). WITHOUT THE
-- CHANNEL, one rule run over two readings of a page collides on the whole primary key.
--
-- A row is never discarded for failing to resolve: an unresolved target is stored
-- unresolved and never projected, which is what makes "cites EP 445 (not in the record)" a
-- display that can be produced and a review queue that is not empty by construction.
CREATE TABLE citation_resolution (
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
    -- 'projection' is NOT permitted here, and the asymmetry with citation_judgement below
    -- is the whole point: the span test's own figure IS the projection's, while a
    -- resolution's is not. This is the one path by which a row could display 98.0% beside a
    -- resolution — the error ADR 0017 made four times, in the table built to stop it.
    measured_target        TEXT CHECK (measured_target IS NULL
                                       OR measured_target = 'citation_resolution'),
    score_row_id           INTEGER,
    superseded_by          INTEGER REFERENCES citation_resolution (resolution_id),
    CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL)),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    -- the outcome and the columns must agree, or `outcome` is decoration
    CHECK ((outcome IN ('resolved', 'repaired')) = (cited_docket_id IS NOT NULL)),
    -- a work is always inside a docket; a decision id without one is not a resolution
    CHECK (cited_decision_id IS NULL OR cited_docket_id IS NOT NULL),
    FOREIGN KEY (score_row_id, measured_target)
        REFERENCES class_measurement (measurement_id, measured_target),
    FOREIGN KEY (citing_document, page, target_kind, target_key)
        REFERENCES citation_key (citing_document, page, target_kind, target_key)
);
CREATE UNIQUE INDEX citation_resolution_live ON citation_resolution
    (citing_document, page, target_kind, target_key, method, method_version, reading_channel)
    WHERE superseded_by IS NULL;
-- the "cited by" read: every live resolution naming this work, then this docket
CREATE INDEX citation_resolution_by_decision ON citation_resolution (cited_decision_id)
    WHERE superseded_by IS NULL AND cited_decision_id IS NOT NULL;
CREATE INDEX citation_resolution_by_docket ON citation_resolution (cited_docket_id)
    WHERE superseded_by IS NULL AND cited_docket_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Family 4 — citation_judgement (ADR 0018 D5), and owed item 4
-- ---------------------------------------------------------------------------
-- What is JUDGED rather than identified. Keyed on the natural key plus
-- (judgement, method, method_version, reading_channel), WITH `value` AS PAYLOAD — owed
-- item 4. `judgement` is in the key and `value` is not, because a re-judgement of the same
-- question must MATCH the key and supersede; a value in the key would mint a second live
-- row saying the opposite.
--
-- The three judgements are measured at different rates — 88.1% for `kind`, and the span
-- test is what the 98.0% projected precision was measured with — which is why one
-- confidence column on a parent row could never have carried them. The span test's own
-- pointer is a 'projection' measurement for that reason: 98.0% is a property of the PAIR,
-- extractor plus this rule, and there is no other figure that is the span test's.
--
-- THAT EXCEPTION IS SOUND IN ONE DIRECTION ONLY, and the limit is stated rather than left
-- to be discovered. 98.0% is the precision of what the pair SHOWS, so it speaks for a
-- judgement whose value is 'true'. A 'false' judgement — the one that suppresses an edge —
-- is not measured by it at all, and stamping it with 98.0% quotes the pair for a decision
-- the pair does not make. `class_vocab` already declares ('citation_judgement',
-- 'span_names_document') and nothing has written a measurement to it: the classifier's own
-- home exists and is empty, and it is owed the day the classifier is scored on its own.
CREATE TABLE citation_judgement (
    judgement_id           INTEGER PRIMARY KEY,
    citing_document        TEXT NOT NULL,
    page                   INTEGER NOT NULL,
    target_kind            TEXT NOT NULL,
    target_key             TEXT NOT NULL,
    judgement              TEXT NOT NULL,
    value_domain           TEXT NOT NULL,       -- copied from judgement_vocab so the pair
    value                  TEXT NOT NULL,       -- below can be foreign-keyed: this is what
                                                -- stops the projection's boolean being
                                                -- written as an untyped string
    method                 TEXT NOT NULL,
    method_version         TEXT NOT NULL,
    reading_channel        TEXT NOT NULL REFERENCES reading_vocab (reading_channel),
    asserted_from_document TEXT REFERENCES document (document_sha256),
    asserted_from_capture  INTEGER REFERENCES capture (capture_id),
    source_location        TEXT,
    asserted_at            TEXT NOT NULL,
    confidence             REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    confidence_state       TEXT NOT NULL CHECK (confidence_state IN (
                               'measured', 'human', 'unmeasured', 'not-applicable')),
    measured_target        TEXT CHECK (measured_target IS NULL OR measured_target IN (
                               'citation_judgement', 'projection')),
    score_row_id           INTEGER,
    superseded_by          INTEGER REFERENCES citation_judgement (judgement_id),
    CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL)),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    FOREIGN KEY (score_row_id, measured_target)
        REFERENCES class_measurement (measurement_id, measured_target),
    FOREIGN KEY (judgement, value_domain)
        REFERENCES judgement_vocab (judgement, value_domain),
    FOREIGN KEY (value_domain, value)
        REFERENCES judgement_value_vocab (value_domain, value),
    FOREIGN KEY (citing_document, page, target_kind, target_key)
        REFERENCES citation_key (citing_document, page, target_kind, target_key)
);
CREATE UNIQUE INDEX citation_judgement_live ON citation_judgement
    (citing_document, page, target_kind, target_key, judgement,
     method, method_version, reading_channel)
    WHERE superseded_by IS NULL;
-- the projection reads exactly one judgement per edge and reads it by name
CREATE INDEX citation_judgement_by_name ON citation_judgement
    (judgement, citing_document, page, target_kind, target_key)
    WHERE superseded_by IS NULL;

-- ---------------------------------------------------------------------------
-- Family 5 — citation_treatment (ADR 0018 D6). SHIPS EMPTY; see the header.
-- ---------------------------------------------------------------------------
-- Not a resolution row: putting treatment there would force the typing pass to restate the
-- resolution or write NULLs into `outcome`, whose NULL already means three things. A review
-- may write a `human` treatment row, or the one column query 2 reads has no correction path.
CREATE TABLE citation_treatment (
    treatment_id           INTEGER PRIMARY KEY,
    citing_document        TEXT NOT NULL,
    page                   INTEGER NOT NULL,
    target_kind            TEXT NOT NULL,
    target_key             TEXT NOT NULL,
    method                 TEXT NOT NULL,
    method_version         TEXT NOT NULL,
    reading_channel        TEXT NOT NULL REFERENCES reading_vocab (reading_channel),
    treatment              TEXT NOT NULL REFERENCES treatment_vocab (treatment),
    asserted_from_document TEXT REFERENCES document (document_sha256),
    asserted_from_capture  INTEGER REFERENCES capture (capture_id),
    source_location        TEXT,
    asserted_at            TEXT NOT NULL,
    confidence             REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    confidence_state       TEXT NOT NULL CHECK (confidence_state IN (
                               'measured', 'human', 'unmeasured', 'not-applicable')),
    measured_target        TEXT CHECK (measured_target IS NULL
                                       OR measured_target = 'citation_treatment'),
    score_row_id           INTEGER,
    superseded_by          INTEGER REFERENCES citation_treatment (treatment_id),
    CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL)),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    FOREIGN KEY (score_row_id, measured_target)
        REFERENCES class_measurement (measurement_id, measured_target),
    FOREIGN KEY (citing_document, page, target_kind, target_key)
        REFERENCES citation_key (citing_document, page, target_kind, target_key)
);
CREATE UNIQUE INDEX citation_treatment_live ON citation_treatment
    (citing_document, page, target_kind, target_key, method, method_version, reading_channel)
    WHERE superseded_by IS NULL;

-- ---------------------------------------------------------------------------
-- extraction_run (ADR 0018 D10) — absence is not a measurement
-- ---------------------------------------------------------------------------
-- One row per (document, method, method_version, reading_channel). The channel is in the
-- key from the start, because a text-layer pass and an OCR pass over one document at one
-- method version otherwise collide — and re-keying later touches one row per document per
-- method across 75,000-125,000 documents.
--
-- The out-of-class counts are what make ADR 0018 D1's promise true: a finding outside its
-- method's class is COUNTED, so "not kept" is an auditable number and never a silent drop.
-- Nothing else distinguishes READ AND FOUND NOTHING from NOT YET READ.
--
-- Not an assertion table: it records a pass, so a re-run at the same version REPLACES the
-- row rather than superseding it. That is the key ADR 0018 D10 names, and its cost is
-- named too: a `failed` attempt overwritten by a later `read` leaves no retry history, so
-- no published coverage number may be derived from this table without adding one.
CREATE TABLE extraction_run (
    run_id               INTEGER PRIMARY KEY,
    document_sha256      TEXT NOT NULL REFERENCES document (document_sha256),
    method               TEXT NOT NULL,
    method_version       TEXT NOT NULL,
    reading_channel      TEXT NOT NULL REFERENCES reading_vocab (reading_channel),
    outcome              TEXT NOT NULL CHECK (outcome IN ('read', 'failed', 'skipped')),
    pages_read           INTEGER NOT NULL DEFAULT 0,
    targets_emitted      INTEGER NOT NULL DEFAULT 0,
    targets_out_of_class INTEGER NOT NULL DEFAULT 0,
    note                 TEXT,
    ran_at               TEXT NOT NULL,
    UNIQUE (document_sha256, method, method_version, reading_channel)
);

-- ---------------------------------------------------------------------------
-- decision_decided_date (citator-schema.md § B), and owed item 5
-- ---------------------------------------------------------------------------
-- Extracted in the SAME pass as citations, because doing it later costs a ~$1,335 re-run:
-- 55 of 60 decisions print a `Decided:` line, none prints two, and 34 of 52 differ from the
-- service date, so this record and a paper copy disagree today with nothing explaining why.
--
-- NEVER a decision_record column (that table mirrors the latest observation and would
-- destroy the history) and NEVER a ledger event (a decided date is a second clock; a replay
-- would show a decision existing before it was served). Those two fences are the grain
-- constraint, not a detail.
--
-- `printed_text` is NOT NULL because dates are quoted, never computed. The five documents
-- that print no line get NO ROW; the pass that read them is recorded in extraction_run,
-- which is what separates "read, and there is no printed decided date" from "not yet read".
--
-- OWED ITEM 5: `ordinal` is in the key. None of the sixty prints two lines, so it buys
-- nothing today and costs nothing today — and the day one does, the key would otherwise
-- keep one silently. `source_location` is NOT in the key (a layout-parser change would mint
-- a row that supersedes nothing) and the OCR engine is NOT in the key (a re-OCR must match
-- and supersede) — both are payload, which is what ADR 0007 requires of them.
--
-- The ordinal is POSITIONAL and parser-assigned, so if a layout change ever reordered two
-- `Decided:` lines the same printed line would mint a row that supersedes nothing — the
-- defect source_location-in-the-key was removed for. Inert while none prints two; the day
-- one does, the ordinal must be assigned from something stable on the page, not from
-- reading order.
CREATE TABLE decision_decided_date (
    decided_id             INTEGER PRIMARY KEY,
    document_sha256        TEXT NOT NULL REFERENCES document (document_sha256),
    date_kind              TEXT NOT NULL REFERENCES date_kind_vocab (date_kind),
    ordinal                INTEGER NOT NULL DEFAULT 0,
    reading_channel        TEXT NOT NULL REFERENCES reading_vocab (reading_channel),
    method                 TEXT NOT NULL,
    method_version         TEXT NOT NULL,
    reading_method         TEXT,                -- payload, OUTSIDE the key
    reading_method_version TEXT,
    printed_text           TEXT NOT NULL,       -- "Decided: October 5, 2017", as printed
    decided_date           TEXT,                -- the ISO reading; NULL when it won't parse
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
    superseded_by          INTEGER REFERENCES decision_decided_date (decided_id),
    CHECK ((confidence_state = 'measured') = (score_row_id IS NOT NULL)),
    CHECK ((score_row_id IS NULL) = (measured_target IS NULL)),
    CHECK ((reading_method IS NULL) = (reading_method_version IS NULL)),
    FOREIGN KEY (score_row_id, measured_target)
        REFERENCES class_measurement (measurement_id, measured_target)
);
CREATE UNIQUE INDEX decision_decided_date_live ON decision_decided_date
    (document_sha256, date_kind, ordinal, reading_channel, method, method_version)
    WHERE superseded_by IS NULL;
-- the docket calendar reads the date, which is one of the three reasons it is typed
CREATE INDEX decision_decided_date_by_date ON decision_decided_date (date_kind, decided_date)
    WHERE superseded_by IS NULL AND decided_date IS NOT NULL;

-- ---------------------------------------------------------------------------
-- correction gains a text key — ADR 0018 § Cost of reversing, the one live table touched
-- ---------------------------------------------------------------------------
-- `target_id INTEGER NOT NULL` (migration 0006, widened at 0009) cannot address a
-- natural-keyed citation row. SQLite can only change a column's type and name by rebuilding
-- the table, so it is done here, while the table holds nothing that has to survive a
-- mistake — 0 rows in production, measured 2026-09-01.
--
-- The key is rendered the way ADR 0016's review_action.target_key is rendered, and for the
-- same reason: an integer pk as digits, a natural-keyed row as its columns joined by '/'.
-- One convention, two tables, so a correction and the review that prompted it name the same
-- string.
--
-- THE RENDERINGS, written down because two writers would otherwise invent two and the
-- corrections would not join:
--   citation and its four families
--       '<citing_document>/<page>/<target_kind>/<target_key>'
--   citation_key                 the same string; the key is the same key
--   decision_decided_date
--       '<document_sha256>/<date_kind>/<ordinal>/<reading_channel>/<method>/<method_version>'
-- Both satisfy the GLOB below, which only counts slashes.
--
-- The GLOB is a SHAPE check and nothing more: it requires at least four slash-separated
-- segments, which is what rejects the bare integer pk this rebuild exists to stop. It does
-- not validate the segments, and `*` matches empty strings and slashes, so '///' passes.
-- Validating the sha256, the page and the vocabulary belongs to the writer.
CREATE TABLE correction_rebuilt (
    correction_id   INTEGER PRIMARY KEY,
    target_table    TEXT NOT NULL,
    target_key      TEXT NOT NULL CHECK (target_key <> ''),
    note            TEXT NOT NULL,
    method          TEXT NOT NULL DEFAULT 'human',
    asserted_at     TEXT NOT NULL,
    method_version  TEXT NOT NULL DEFAULT 'unversioned',
    source_location TEXT,
    -- every natural-keyed table this migration adds: a correction that names a surrogate
    -- id instead is a correction nobody can follow back to the row it amends
    CHECK (target_table NOT IN ('citation', 'citation_key', 'citation_reading',
                                'citation_resolution', 'citation_judgement',
                                'citation_treatment', 'decision_decided_date')
           OR target_key GLOB '*/*/*/*')
);
INSERT INTO correction_rebuilt
    (correction_id, target_table, target_key, note, method, asserted_at,
     method_version, source_location)
    SELECT correction_id, target_table, CAST(target_id AS TEXT), note, method, asserted_at,
           method_version, source_location
      FROM correction;
DROP TABLE correction;
ALTER TABLE correction_rebuilt RENAME TO correction;

PRAGMA user_version = 14;

COMMIT;
