-- Validation query 2 — "what has narrowed, distinguished or superseded this work?" —
-- written in full against ADR 0017 and ADR 0018, so that "Q2 is writable against this shape"
-- is a claim anyone can check rather than one both records assert about themselves.
--
-- Written by the schema-critic across passes 5-7 and kept here because the pre-split ADR
-- carried it inline and the split nearly lost it.
--
-- IT RUNS, as of migration 0014 (2026-09-01), against a store at user_version 14. It returns
-- the EMPTY SET, and that is the correct answer on the day the citator ships: every edge in
-- the first slice is `cites`, treatment typing is a later pass, and this query filters on a
-- negative polarity (ADR 0017 D7). An empty result is a measurement; an unparseable query
-- was not, which is why citation_treatment is in that migration against the review's
-- recommendation — see 0014_citations.sql's header for the argument.
--
-- Of the three things writing it exposed, two are settled by that migration:
--   1. SETTLED. cited_docket_id and cited_decision_id are columns on citation_resolution and
--      one `resolve` row asserts the COMPLETE outcome — owed item 3. The family test below
--      reads the docket column and the WHERE keys on the decision column, and they must come
--      off the SAME resolution row, or this query joins one method's work-level answer to
--      another method's docket-level one.
--   2. STILL OPEN, with its cost named. :rank_version is BOUND, not read. Nothing dates which
--      ranking was in force, which is 0018's one deferred item and the reason a past
--      projection is not reconstructible. A `projection_rule` table is an addition any day;
--      what is not recoverable is the interval between the first edge and the day it lands.
--   3. SETTLED AS A STATEMENT, not as code. The projection is a conjunction of three terms
--      (resolution, family, span judgement), and it is stated per family in migration 0014's
--      header — owed item 2 — because it cannot be a view while term 1 binds a version that
--      nothing dates. Reading ADR 0018 decision 7's resolution term alone and stopping there
--      publishes every own-proceeding mention. Measured on the sixty-decision sheet by
--      removing the family branch from the dry-run projection: 210 true of 239 shown =
--      87.9%, against 201 of 205 = 98.0% with both terms. (ADR 0018 D7 states this as
--      "88.4%", which is citator-schema.md's EXTRACTION precision as scored, 220 of 249
--      emitted -- a different configuration, and an erratum for the operator on an accepted
--      record. This header separately read 98.2% for the projection until 2026-09-01, until
--      ADR 0017 D4 retracted that figure for counting registry-unresolvable edges as shown
--      when they reach no page at all.)
--
-- AND IT ASKS THE RARER GRAIN, which nothing said before. `WHERE rd.cited_decision_id =`
-- keys on the WORK. ADR 0018 D9 measures how rare that is: `decision_record.decision_number`
-- is populated for 0 of 23,713 rows, so "docket-level edges are the normal case", and D4's
-- verb gate keeps every `decided <date>` phrase at docket level. So this query stays thin
-- even AFTER the treatment pass runs, and the day-one emptiness has two causes, not one.
-- The docket-grain variant — `WHERE rd.cited_docket_id = :target_docket` — is the one a
-- reader's "cited by" list is actually built from.
--
-- THE SHIPPING PROJECTION IS `docketyard.citator.project`, not this file. This is validation
-- query 2 — a different job, filtering on a negative treatment polarity — written out so the
-- claim "Q2 is writable against this shape" is checkable. The terms they share are pinned
-- equal by a test, because they drifted within a day of being written: the veto sat on the
-- rank-1 row in one and the candidate set in the other.
--
-- The live tables it joins (decision_attachment, decision_record, docket) were verified
-- against src/docketyard/store/0002_filings_decisions.sql.

WITH rank_res AS (                       -- 0018 D7: the ordering registry, append-only
  SELECT method, method_version, reading_channel, role, precedence_rank
  FROM assertion_method
  WHERE target_table = 'citation_resolution' AND rank_version = :rank_version
),
res_cand AS (                            -- 0018 D7: the predicate goes on the CANDIDATE SET
  SELECT r.*, rr.role, rr.precedence_rank
  FROM citation_resolution r
  JOIN rank_res rr ON rr.method          = r.method
                  AND rr.method_version  = r.method_version
                  AND rr.reading_channel = r.reading_channel
  WHERE r.superseded_by IS NULL
    AND r.confidence_state IN ('measured', 'human')
),
suppressed AS (                          -- 0018 D7: same channel, or a text-layer extraction
  SELECT DISTINCT citing_document, page, target_kind, target_key, reading_channel
  FROM res_cand                          -- would be vetoed by an OCR check
  -- BOTH terms. `role` says the method is a suppressor; `outcome` says THIS target was
  -- actually vetoed. On role alone, a veto pass that records every target it checked and
  -- CLEARED -- the auditable way to write one, and the way every other family writes --
  -- would suppress everything it looked at. (Added 2026-09-01, second schema-critic pass;
  -- `vetoed` was in outcome_vocab and read by nothing.)
  WHERE role = 'suppress' AND outcome = 'vetoed'
),
resolved AS (
  SELECT * FROM (
    SELECT rc.*, ROW_NUMBER() OVER (
             PARTITION BY rc.citing_document, rc.page, rc.target_kind, rc.target_key
             ORDER BY rc.precedence_rank) AS rn
    FROM res_cand rc
    WHERE rc.role = 'resolve' AND rc.outcome IN ('resolved', 'repaired')
      -- 0018 D7: THE VETO FILTERS THE CANDIDATE SET, like every other term. It sat on the
      -- rank-1 row until 2026-09-01, which is the shape D7 retired for the confidence
      -- predicate and retired here for the same reason: after the rank it DELETES an edge
      -- that a second, unvetoed channel could still carry, and a veto on a losing channel
      -- is silently ignored. The channel match stays — a veto names the reading it checked.
      --
      -- Every name on both sides must be qualified: unqualified columns bind to the INNER
      -- scope, so `s.citing_document = citing_document` reads as `s.x = s.x` and the NOT
      -- EXISTS is false for every row the moment `suppressed` holds anything at all. One
      -- veto would have emptied the entire result. (Found by the multi-agent review,
      -- 2026-09-01, in the file both ADRs cite as proof this query runs.)
      AND NOT EXISTS (SELECT 1 FROM suppressed s
                       WHERE s.citing_document = rc.citing_document
                         AND s.page            = rc.page
                         AND s.target_kind     = rc.target_kind
                         AND s.target_key      = rc.target_key
                         AND s.reading_channel = rc.reading_channel)
  ) ranked
  WHERE ranked.rn = 1
),
citing_work AS (                         -- 0018 D9: fold to the work, COALESCE so a filing
  SELECT r.citing_document,              -- folds to itself rather than being dropped
         COALESCE(dr.stb_decision_id, r.citing_document) AS citing_work_id
  FROM (SELECT DISTINCT citing_document FROM resolved) r
  LEFT JOIN decision_attachment da ON da.document_sha256 = r.citing_document
  LEFT JOIN decision_record     dr ON dr.decision_pk     = da.decision_pk
),
treat AS (                               -- 0018 D7: no outcome term for this family
  SELECT * FROM (
    SELECT t.*, ROW_NUMBER() OVER (
             PARTITION BY t.citing_document, t.page, t.target_kind, t.target_key
             ORDER BY am.precedence_rank) AS rn
    FROM citation_treatment t
    JOIN assertion_method am ON am.target_table    = 'citation_treatment'
                            AND am.method          = t.method
                            AND am.method_version  = t.method_version
                            AND am.reading_channel = t.reading_channel
                            AND am.rank_version    = :rank_version
    WHERE t.superseded_by IS NULL AND t.confidence_state IN ('measured', 'human')
  ) WHERE rn = 1
),
exposed AS (                             -- 0017 D2 / migration 0015: the exposure gate
  -- READ WITHOUT the confidence predicate: this judgement SUPPRESSES, and a suppressor
  -- filtered out of the candidate set is silently inert (0018 D7, on the on-page veto).
  SELECT DISTINCT citing_document, page, target_kind, target_key
  FROM citation_judgement
  WHERE judgement = 'exposed' AND value = 'true' AND superseded_by IS NULL
),
reviewed AS (                            -- a human has since answered on this key
  SELECT DISTINCT citing_document, page, target_kind, target_key
  FROM citation_resolution
  WHERE confidence_state = 'human' AND superseded_by IS NULL
),
refused AS (                             -- and a human NO stands against every later pass
  SELECT DISTINCT citing_document, page, target_kind, target_key
  FROM citation_resolution
  WHERE confidence_state = 'human' AND superseded_by IS NULL
    AND outcome NOT IN ('resolved', 'repaired')
),
span AS (                                -- 0017 D4 / 0018 D5: the stored span judgement
  SELECT * FROM (
    SELECT j.citing_document, j.page, j.target_kind, j.target_key, j.value,
           ROW_NUMBER() OVER (
             PARTITION BY j.citing_document, j.page, j.target_kind, j.target_key
             ORDER BY am.precedence_rank) AS rn
    FROM citation_judgement j
    JOIN assertion_method am ON am.target_table    = 'citation_judgement'
                            AND am.method          = j.method
                            AND am.method_version  = j.method_version
                            AND am.reading_channel = j.reading_channel
                            AND am.rank_version    = :rank_version
    WHERE j.judgement = 'span_names_document' AND j.superseded_by IS NULL
      AND j.confidence_state IN ('measured', 'human')
  ) WHERE rn = 1
),
family AS (                              -- 0017 D4: self + sub-dockets + parent, unioned over
  -- NOTE: keyed on stb_decision_id, while citing_work_id COALESCEs to a raw sha256 for a
  -- filing-mined edge -- so for those the EXISTS below is always false and every filing
  -- self-mention projects. 0018 D9 explicitly provides for filing edges, so this needs the
  -- filing branch below before extraction moves beyond decisions.
  SELECT dr.stb_decision_id, dr.docket_id FROM decision_record dr   -- every member docket
  UNION
  SELECT dr.stb_decision_id, ch.docket_id
    FROM decision_record dr JOIN docket ch ON ch.parent_docket_id = dr.docket_id
  UNION
  SELECT dr.stb_decision_id, pa.docket_id
    FROM decision_record dr JOIN docket me ON me.docket_id = dr.docket_id
                            JOIN docket pa ON pa.docket_id = me.parent_docket_id
)
SELECT DISTINCT
       cw.citing_work_id, t.treatment, tv.polarity,
       rd.confidence, rd.confidence_state, rd.score_row_id,
       rd.method, rd.method_version, rd.reading_channel,
       rg.cited_raw, rg.quoted_passage, rg.source_location, rd.page
FROM resolved rd
-- 0018 D2: the parent MUST be joined and MUST be live, or a retracted target_kind changes
-- nothing -- its resolutions still read superseded_by IS NULL and the mis-kinded edge
-- still projects. This join is what makes a retraction effective.
JOIN citation c         ON (c.citing_document, c.page, c.target_kind, c.target_key)
                         = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
                       AND c.superseded_by IS NULL
                       -- the predicate is stated for EVERY family (0018 D7), and this join
                       -- omitted it until 2026-09-01: an unmeasured extraction must reach no
                       -- page, exactly as an unmeasured resolution does
                       AND c.confidence_state IN ('measured', 'human')
JOIN citing_work cw     ON cw.citing_document = rd.citing_document
JOIN treat t            ON (t.citing_document, t.page, t.target_kind, t.target_key)
                         = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
JOIN treatment_vocab tv ON tv.treatment = t.treatment
-- INNER and channel-matched, which is an INVARIANT on the writer rather than an accident:
-- a resolution on a channel with no live reading row projects NOTHING. A `human` resolution
-- — the whole reason `reading_vocab` carries 'human' — must be written together with a
-- `human` citation_reading carrying the passage the reviewer actually read.
JOIN citation_reading rg ON (rg.citing_document, rg.page, rg.target_kind, rg.target_key)
                          = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
                        AND rg.reading_channel = rd.reading_channel
                        AND rg.superseded_by IS NULL
                        AND rg.confidence_state IN ('measured', 'human')
LEFT JOIN span sp ON (sp.citing_document, sp.page, sp.target_kind, sp.target_key)
                   = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
WHERE rd.cited_decision_id = :target_work
  AND tv.polarity = 'negative'
  -- 0017 D4: inside the family, an edge projects ONLY on a live span judgement saying true.
  -- COALESCE is the stated default: absent judgement = suppress.
  AND NOT (EXISTS (SELECT 1 FROM family f
                    WHERE f.stb_decision_id = cw.citing_work_id
                      AND f.docket_id       = rd.cited_docket_id)
           AND COALESCE(sp.value, 'false') <> 'true')
  -- 0017 D2 / migration 0015: the exposed class goes to review, and reaches no page until a
  -- human has answered on the key. A rejection then stands against every later pass.
  AND NOT (EXISTS (SELECT 1 FROM exposed x
                    WHERE x.citing_document = rd.citing_document AND x.page = rd.page
                      AND x.target_kind = rd.target_kind AND x.target_key = rd.target_key)
           AND NOT EXISTS (SELECT 1 FROM reviewed h
                            WHERE h.citing_document = rd.citing_document AND h.page = rd.page
                              AND h.target_kind = rd.target_kind
                              AND h.target_key = rd.target_key))
  AND NOT EXISTS (SELECT 1 FROM refused n
                   WHERE n.citing_document = rd.citing_document AND n.page = rd.page
                     AND n.target_kind = rd.target_kind AND n.target_key = rd.target_key);
