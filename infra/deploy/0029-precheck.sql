-- Migration 0029's pre-check (ADR 0018 addendum, decision 3). Run READ-ONLY on production
-- BEFORE the wall, at schema 28: it lists every reading the migration would retire and, with
-- `decided = 1`, any key a person has decided — which would abort the migration whole.
--
-- A SECOND COPY of `citation_reading_residue`'s SELECT in
-- `src/docketyard/store/0029_retire_retracted_readings.sql`, because that view does not exist
-- until the migration runs. tests/test_citator_reading_retirement.py runs both over one store
-- and requires the same answer; change them together.
SELECT citing_document || '/' || page || '/' || target_kind || '/' || target_key AS key,
       reading_channel,
       citation_id,
       pointer,
       decided
  FROM (
SELECT r.reading_id,
       r.citing_document,
       r.page,
       r.target_kind,
       r.target_key,
       r.reading_channel,
       t.citation_id,
       COALESCE(
           (SELECT sr.reading_id
              FROM citation s
              JOIN citation_reading sr
                ON sr.citing_document = s.citing_document AND sr.page = s.page
               AND sr.target_kind = s.target_kind AND sr.target_key = s.target_key
               AND sr.reading_channel = r.reading_channel AND sr.superseded_by IS NULL
             WHERE s.citation_id = t.superseded_by AND s.citation_id <> t.citation_id),
           r.reading_id) AS pointer,
       (EXISTS (SELECT 1 FROM citation_resolution h
                 WHERE h.citing_document = r.citing_document AND h.page = r.page
                   AND h.target_kind = r.target_kind AND h.target_key = r.target_key
                   AND h.superseded_by IS NULL AND h.confidence_state = 'human')
        OR EXISTS (SELECT 1 FROM review_action a
                    WHERE a.target_table = 'citation_resolution' AND a.superseded_by IS NULL
                      AND a.target_key = r.citing_document || '/' || r.page || '/'
                                         || r.target_kind || '/' || r.target_key)) AS decided
  FROM citation_reading r
  JOIN citation t
    ON t.citation_id = (SELECT MAX(x.citation_id) FROM citation x
                         WHERE x.citing_document = r.citing_document AND x.page = r.page
                           AND x.target_kind = r.target_kind AND x.target_key = r.target_key)
 WHERE r.superseded_by IS NULL
   AND r.reading_channel <> 'human'
   AND t.superseded_by IS NOT NULL
   AND (t.superseded_by = t.citation_id
        OR EXISTS (SELECT 1 FROM citation o
                    WHERE o.citation_id = t.superseded_by
                      AND NOT (o.citing_document = t.citing_document AND o.page = t.page
                               AND o.target_kind = t.target_kind
                               AND o.target_key = t.target_key)))
   AND NOT EXISTS (SELECT 1 FROM citation l
                    WHERE l.citing_document = r.citing_document AND l.page = r.page
                      AND l.target_kind = r.target_kind AND l.target_key = r.target_key
                      AND l.superseded_by IS NULL)
  )
 ORDER BY key, reading_channel
