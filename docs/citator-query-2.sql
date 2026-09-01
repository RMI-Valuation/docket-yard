-- Validation query 2 — "what has narrowed, distinguished or superseded this work?" —
-- written in full against ADR 0017 and ADR 0018, so that "Q2 is writable against this shape"
-- is a claim anyone can check rather than one both records assert about themselves.
--
-- Written by the schema-critic across passes 5-7 and kept here because the pre-split ADR
-- carried it inline and the split nearly lost it. NOT executable today: no citator table is
-- in any migration. The live tables it joins (decision_attachment, decision_record, docket)
-- are real and were verified against src/docketyard/store/0002_filings_decisions.sql.
--
-- Three things writing it exposed, all recorded in ADR 0018's "owed at the migration":
--   1. cited_docket_id / cited_decision_id are used by the WHERE and are not yet declared
--      as columns anywhere — that is owed item 3, and it is the column this query keys on.
--   2. :rank_version is BOUND, not read. Nothing dates which ranking was in force, which is
--      0018's one deferred item and the reason a past projection is not reconstructible.
--   3. The projection is a conjunction of three terms (resolution, family, span judgement).
--      Reading ADR 0018 decision 7's resolution term alone and stopping there publishes every
--      own-proceeding mention: 88.4% instead of 98.2%.

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
  FROM res_cand WHERE role = 'suppress'  -- would be vetoed by an OCR check
),
resolved AS (
  SELECT * FROM (
    SELECT rc.*, ROW_NUMBER() OVER (
             PARTITION BY rc.citing_document, rc.page, rc.target_kind, rc.target_key
             ORDER BY rc.precedence_rank) AS rn
    FROM res_cand rc
    WHERE rc.role = 'resolve' AND rc.outcome IN ('resolved', 'repaired')
  ) ranked
  WHERE ranked.rn = 1
    -- every name on both sides must be qualified: unqualified columns bind to the INNER
    -- scope, so `s.citing_document = citing_document` reads as `s.x = s.x` and the NOT
    -- EXISTS is false for every row the moment `suppressed` holds anything at all. One
    -- veto would have emptied the entire result. (Found by the multi-agent review,
    -- 2026-09-01, in the file both ADRs cite as proof this query runs.)
    AND NOT EXISTS (SELECT 1 FROM suppressed s
                     WHERE s.citing_document = ranked.citing_document
                       AND s.page            = ranked.page
                       AND s.target_kind     = ranked.target_kind
                       AND s.target_key      = ranked.target_key
                       AND s.reading_channel = ranked.reading_channel)
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
JOIN citing_work cw     ON cw.citing_document = rd.citing_document
JOIN treat t            ON (t.citing_document, t.page, t.target_kind, t.target_key)
                         = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
JOIN treatment_vocab tv ON tv.treatment = t.treatment
JOIN citation_reading rg ON (rg.citing_document, rg.page, rg.target_kind, rg.target_key)
                          = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
                        AND rg.reading_channel = rd.reading_channel
                        AND rg.superseded_by IS NULL
LEFT JOIN span sp ON (sp.citing_document, sp.page, sp.target_kind, sp.target_key)
                   = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
WHERE rd.cited_decision_id = :target_work
  AND tv.polarity = 'negative'
  -- 0017 D4: inside the family, an edge projects ONLY on a live span judgement saying true.
  -- COALESCE is the stated default: absent judgement = suppress.
  AND NOT (EXISTS (SELECT 1 FROM family f
                    WHERE f.stb_decision_id = cw.citing_work_id
                      AND f.docket_id       = rd.cited_docket_id)
           AND COALESCE(sp.value, 'false') <> 'true');
