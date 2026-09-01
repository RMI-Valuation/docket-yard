"""The projection: which stored edges a reader is shown, and nothing else.

ADR 0018 D7 states the rule per family, and this is its ONE implementation. It was three —
`docs/citator-query-2.sql`, the dry run's own copy, and whatever a page would have grown —
and each drifted from the others within a day of being written: the veto sat on the rank-1
row in one and the candidate set in another, and the confidence predicate reached the parent
in neither. `docs/citator-query-2.sql` stays on disk as validation query 2 written out,
which is a different job (it filters on a negative treatment polarity); the terms it shares
with this file are the ones a test pins together.

The formula, per family, because they do not share one:

  citation_key         identity. Not an assertion; nothing to order, nothing to supersede.
  citation             joined AND REQUIRED LIVE. A retraction supersedes only this row; the
                       resolutions and judgements anchored on the retracted key still read
                       superseded_by IS NULL, so this join is what makes a retraction bite.
  citation_reading     joined on the resolution's own channel, live, and measured or human
                       like every other family. INNER, which is an invariant on the writer:
                       a `human` resolution must be written with a `human` reading carrying
                       the passage the reviewer read, or it projects nothing.
  citation_resolution  a live `suppress` row FOR THE SAME CHANNEL whose outcome is 'vetoed'
                       drops that channel's candidates; of what remains, the highest-ranked
                       live `resolve` row whose outcome is 'resolved' or 'repaired'.
  citation_judgement   the highest-ranked live row and nothing else. No outcome to restrict
                       on, and inventing one would mean NULLs in a column whose NULL already
                       means three things.

And the resolution term is not the whole projection. An edge projects only when it holds AND
one of two family terms does: the target docket is OUTSIDE the citing work's family, or —
inside — a live `span_names_document` judgement says 'true', defaulting to suppress. Reading
the resolution term alone shows 214 true of 243 = 88.1%, against 205 of 209 = 98.1% with
both (measured 2026-09-01 on the sixty-decision sheet, after the scorer's registry defect
was fixed — see migration 0014's header).

`:rank_version` is BOUND, not read. Nothing dates which ranking was in force — ADR 0018's
one accepted deferral — so a past projection is not reconstructible, and that cost is named
rather than hidden behind a default.
"""

from docketyard.citator.methods import RANK_VERSION

_TERMS = """
WITH rank_res AS (
  SELECT method, method_version, reading_channel, role, precedence_rank
  FROM assertion_method
  WHERE target_table = 'citation_resolution' AND rank_version = :rank_version
),
res_cand AS (                            -- the predicate goes on the CANDIDATE SET, never
  SELECT r.*, rr.role, rr.precedence_rank -- on the rank-1 row, where it DELETES edges
  FROM citation_resolution r
  JOIN rank_res rr ON rr.method          = r.method
                  AND rr.method_version  = r.method_version
                  AND rr.reading_channel = r.reading_channel
  WHERE r.superseded_by IS NULL
    AND r.confidence_state IN ('measured', 'human')
),
suppressed AS (                          -- BOTH terms: `role` says the method is a
  SELECT DISTINCT citing_document, page, target_kind, target_key, reading_channel
  FROM res_cand                          -- suppressor, `outcome` says THIS target was
  WHERE role = 'suppress' AND outcome = 'vetoed'   -- actually vetoed rather than cleared
),
resolved AS (
  SELECT * FROM (
    SELECT rc.*, ROW_NUMBER() OVER (
             PARTITION BY rc.citing_document, rc.page, rc.target_kind, rc.target_key
             ORDER BY rc.precedence_rank) AS rn
    FROM res_cand rc
    WHERE rc.role = 'resolve' AND rc.outcome IN ('resolved', 'repaired')
      -- every name qualified: unqualified columns bind to the INNER scope, so
      -- `s.citing_document = citing_document` reads as `s.x = s.x` and one veto empties
      -- the whole result (found by the multi-agent review, 2026-09-01)
      AND NOT EXISTS (SELECT 1 FROM suppressed s
                       WHERE s.citing_document = rc.citing_document
                         AND s.page            = rc.page
                         AND s.target_kind     = rc.target_kind
                         AND s.target_key      = rc.target_key
                         AND s.reading_channel = rc.reading_channel)
  ) ranked
  WHERE ranked.rn = 1
),
citing_work AS (                         -- ADR 0018 D9: fold to the WORK, COALESCE so an
  SELECT r.citing_document,              -- edge mined from a filing folds to itself rather
         COALESCE(dr.stb_decision_id, r.citing_document) AS citing_work_id
  FROM (SELECT DISTINCT citing_document FROM resolved) r  -- than being dropped by an inner
  LEFT JOIN decision_attachment da ON da.document_sha256 = r.citing_document   -- join
  LEFT JOIN decision_record     dr ON dr.decision_pk     = da.decision_pk
),
span AS (
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
family AS (                              -- ADR 0017 D4: self, sub-dockets and parent, over
  SELECT dr.stb_decision_id, dr.docket_id FROM decision_record dr   -- every docket a
  UNION                                                             -- consolidated decision
  SELECT dr.stb_decision_id, ch.docket_id                           -- is entered in
    FROM decision_record dr JOIN docket ch ON ch.parent_docket_id = dr.docket_id
  UNION
  SELECT dr.stb_decision_id, pa.docket_id
    FROM decision_record dr JOIN docket me ON me.docket_id = dr.docket_id
                            JOIN docket pa ON pa.docket_id = me.parent_docket_id
)
SELECT DISTINCT cw.citing_work_id, rd.target_kind, rd.target_key,
       rd.cited_docket_id, rd.cited_decision_id,
       rd.confidence, rd.confidence_state, rd.score_row_id,
       rd.method, rd.method_version, rd.reading_channel,
       rg.cited_raw, rg.quoted_passage, rd.page
FROM resolved rd
JOIN citation c         ON (c.citing_document, c.page, c.target_kind, c.target_key)
                         = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
                       AND c.superseded_by IS NULL
                       AND c.confidence_state IN ('measured', 'human')
JOIN citing_work cw     ON cw.citing_document = rd.citing_document
JOIN citation_reading rg ON (rg.citing_document, rg.page, rg.target_kind, rg.target_key)
                          = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
                        AND rg.reading_channel = rd.reading_channel
                        AND rg.superseded_by IS NULL
                        AND rg.confidence_state IN ('measured', 'human')
LEFT JOIN span sp ON (sp.citing_document, sp.page, sp.target_kind, sp.target_key)
                   = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
WHERE NOT (EXISTS (SELECT 1 FROM family f
                    WHERE f.stb_decision_id = cw.citing_work_id
                      AND f.docket_id       = rd.cited_docket_id)
           AND COALESCE(sp.value, 'false') <> 'true')
"""

PROJECTION = _TERMS
CITED_BY_DOCKET = f"{_TERMS}  AND rd.cited_docket_id = :target_docket"
CITED_BY_WORK = f"{_TERMS}  AND rd.cited_decision_id = :target_work"


def projected(con, *, rank_version: str = RANK_VERSION):
    """Every edge a reader may be shown. The only supported path to `confidence`, which is
    never selected without `confidence_state` (ADR 0018 D8)."""
    return con.execute(PROJECTION, {"rank_version": rank_version}).fetchall()


def cited_by(
    con,
    *,
    docket_id: int | None = None,
    work_id: str | None = None,
    rank_version: str = RANK_VERSION,
):
    """What cites this proceeding, or this work.

    THE DOCKET GRAIN IS THE NORMAL ONE, and a caller should reach for it first:
    `decision_record.decision_number` is populated for 0 of 23,713 rows and ADR 0018 D4's
    verb gate keeps every `decided <date>` phrase at docket level, so a work-grain question
    answers thin. Both are offered because a public "cited by" count must not silently mix
    two grains (ADR 0018 D9).
    """
    if (docket_id is None) == (work_id is None):
        raise ValueError("cited_by takes exactly one of docket_id or work_id")
    if docket_id is not None:
        return con.execute(
            CITED_BY_DOCKET, {"rank_version": rank_version, "target_docket": docket_id}
        ).fetchall()
    return con.execute(
        CITED_BY_WORK, {"rank_version": rank_version, "target_work": work_id}
    ).fetchall()
