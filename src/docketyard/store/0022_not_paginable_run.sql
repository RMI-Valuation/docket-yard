-- Migration 0022: `ocr_run` gains the word `document_pagination` has always had.
--
-- THIS CORRECTS A PUBLISHED TABLE THAT SAYS SOMETHING UNTRUE, and it is NOT ADR 0024's to
-- carry — 0024's queue is where it was noticed, not where it comes from. `text/load.py`
-- mapped the extractor's `not-paginable` onto `skipped`, while `run_outcome_vocab`'s
-- published note read "the pass declined it — not image-only, or a tier not read in this
-- pass". Neither clause describes "the bytes are not a paginated document at all", which is
-- what 3,271 rows in production actually mean. That note ships in the CC0 snapshot, so a third
-- party has been reading a description that does not match the rows carrying it.
--
-- THE REASON IS THE PUBLISHED RECORD, NOT THE QUEUE, and an earlier draft of this header
-- claimed otherwise. ADR 0024's predicate is positive — `outcome = 'read'` — so `skipped` and
-- `not-paginable` fail it identically and the new word buys that queue nothing as specified.
-- It buys correctness for the snapshot, which is reason enough on its own (schema-critic,
-- 2026-09-05).
--
-- `pagination_outcome_vocab` HAS HELD `not-paginable` SINCE MIGRATION 0018, for the same
-- judgement about the same bytes. So this is not a new concept; it is a word that exists one
-- table over and was collapsed on the way into this one.
--
-- WHICH TABLE ASSERTS IT. `document_pagination` is the ASSERTION OF RECORD: it carries ADR
-- 0007's whole block — confidence, state, `asserted_at`, supersession, a human-protection
-- trigger and a `review_target_vocab` row. `ocr_run.outcome` is the PASS'S REPORT of what it
-- did, and carries none of that. Two public tables now answer "are these bytes a paginated
-- document?", and this is which one a reader believes. A test asserts they never disagree.
--
-- WHY THE WORD CANNOT STAY OVERLOADED. `not-paginable` is PERMANENT: those bytes will never be
-- a paginated document. `skipped` in its other sense is TRANSIENT — a tier not read in this
-- pass, which the next pass may read — and ADR 0024 § Owed 2's refusal will ship under it.
--
-- THE ROWS ARE NOT REWRITTEN (the operator's decision, 2026-09-05). `ocr_run` has no
-- `superseded_by` and its key ends in `ran_at`, so correcting one would be an in-place UPDATE
-- of shipped assertions with no supersession trail, which this store refuses.
--
-- SO THE BOUNDARY IS A ROW, NOT A SENTENCE. A first draft wrote the history into the
-- vocabulary's own note — which would have shipped "3,271 of them at 2026-09-05" as data to
-- every store, including fresh ones holding no such rows, a false statement published as a
-- definition. It also named `method = 'pymupdf'` at text-layer/native as the discriminator,
-- which is a NECESSARY and not a SUFFICIENT condition: that is exactly the key § Owed 2's
-- transient refusal must also write under, so the discriminator dies on the next change
-- (schema-critic, 2026-09-05). The note below stays universal; the history goes into a
-- `correction` row, conditionally, with the boundary computed from THIS store — `run_id` is a
-- rowid alias preserved across the snapshot's VACUUM, which `ran_at` is not (it is the
-- parser's clock, from a spool header that may predate the load by weeks).
--
-- THE BOUNDARY CARRIES THE CHANNEL AND THE RENDER, not just the outcome and the id. A reading
-- pass may legitimately write `skipped` on the `ocr` channel in the surviving sense — a tier
-- it did not read this pass — so a boundary of `outcome = 'skipped' AND run_id <= N` alone
-- would claim "these bytes are not a paginated document" about rows where that is false, and
-- would inflate both the id and the count. Production holds no such row today (every one of
-- the 3,271 is text-layer/native), which is exactly why it had to be checked rather than
-- assumed (code review, 2026-09-05).

BEGIN TRANSACTION;

INSERT INTO run_outcome_vocab VALUES
    ('not-paginable', 'held bytes that are not a paginated document — zip, xlsx, an image');

-- Universal, and true of a store with no history as much as of production.
UPDATE run_outcome_vocab
   SET note = 'the pass declined it — not image-only, or a tier not read in this pass.'
           || ' Runs written before migration 0022 may also carry not-paginable; where a store'
           || ' holds any, a correction row names the boundary'
 WHERE outcome = 'skipped';

-- The store-specific half, and ONLY where there is something to say: the aggregate over an
-- empty set is one row that `HAVING` drops, so a fresh store gets no correction and no false
-- claim. `correction` is public (migration 0014 rebuilt it with a text key), its CHECK
-- constrains only the citator's natural-keyed tables, and `dump.py` deletes corrections naming
-- HELD tables — `run_outcome_vocab` is public, so this ships with the snapshot it explains.
INSERT INTO correction (target_table, target_key, note, method, method_version, asserted_at)
SELECT 'run_outcome_vocab',
       'skipped',
       'Until migration 0022 the loader recorded the extractor''s not-paginable as skipped.'
       || ' In this store that means: outcome = ''skipped'' AND reading_channel ='
       || ' ''text-layer'' AND render_profile = ''native'' AND run_id <= ' || MAX(run_id)
       || ' says the bytes are not a paginated document, not that a tier went unread.'
       || ' ' || COUNT(*) || ' runs. The channel and render are part of the boundary: that is'
       || ' the extraction path''s key, and a reading pass may write skipped on its own'
       || ' channel in the surviving sense. They are not rewritten — ocr_run has no'
       || ' superseded_by and its key ends in ran_at, so an in-place UPDATE is the only'
       || ' correction it admits and this store refuses those. document_pagination is the'
       || ' assertion of record.',
       'migration-0022',
       'unversioned',
       strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')
  FROM ocr_run
 WHERE outcome = 'skipped' AND reading_channel = 'text-layer' AND render_profile = 'native'
HAVING COUNT(*) > 0;

PRAGMA user_version = 22;

COMMIT;
