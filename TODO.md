# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## Now

- **Migration 0014 is written and uncommitted** — five families plus `citation_key`,
  `assertion_method`, `class_measurement`, `extraction_run`, `decision_decided_date`;
  `correction.target_id` rebuilt to `target_key TEXT`. All eight owed items paid; two
  schema-critic passes triaged. `citation_dryrun.py` reproduces the scorer **in SQL** over
  all 60 decisions: 201 of 225 projected (89.3%), 201 true of 205 shown (98.0%)
- **All three review calls settled by Cameron, 2026-09-01.** The citator tables stay **held
  from the CC0 dump**. ADR 0018 D7's "88.4%" is left as it stands — it describes a
  configuration nothing runs, and the shipping figures in 0014 and `schema-draft.md` carry
  the measured 87.9%. `class_measurement` keeps D8's key exactly; the scorer-version gap is
  in `docs/deferred.md`, not worth widening an accepted key for a spot-in-time number
- **Owed with the pipeline, not the migration**: ingest must insert into `decision_work` on
  `decision_observed`; the review queue and the "not in the record" display must join live
  `citation`, not `citation_resolution` alone; the extractor must not re-assert a key a
  human retracted; the veto's cross-row rules need a trigger the day it stops being inert
  (the within-page span join is inert too — the finder dedupes per page)
- **The comment-attachment drain is RUNNING and healthy** — 16,541 left at 17:11 UTC
  2026-09-01, 0 failed, 26 GB free, due ~02:30 UTC 2026-09-02. `drain.stop` ends it
- **Party types (F3)**: rules v2 at 83.3%, tuned on the sheet it is scored against —
  **a second unseen sample must confirm** before any type ships
- No Anthropic key exists; any Claude-backed run needs a new one from Cameron
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **The extraction pipeline against 0014** — finder, resolver, span judgement and
  `extraction_run`, writing what the dry run writes. The regex class needs no Anthropic key
- **ADR 0016** accepted 2026-08-28; `reviewer`/`review_action` drafted into
  `schema-draft.md` § 7. **Unblocked** — 0017/0018 accepted; `review_action` needs
  `key_version` and the resolution rendering (0018 D1) before `/review` ships
- **OCR of the 13,604 image-only files** (M3's first slice): plan in `docs/ocr-plan.md`,
  ~$700 for the backfill. **Unblocked by 0017/0018**; still needs the Anthropic key
- Deadline engine (C4): decision JSON carries no extracted obligations (verified
  2026-08-26); a hand-checked fixture of 8 for FD 36873 is in
  `../up-ns-merger-tracker/briefs/2026-08-25.md` (read-only). Dates quoted, never computed
- JSON-LD (Cameron, 2026-08-26): none on any page; decide the vocabulary before adding any
- Cameron's idea: cadence switch from the alert email; a signed-link manage page per address
- **ADR 0012 addendum: the blob cache** (S3 the store, the instance a cache; sync + prune)
- **`docs/navigation-review.md`: Tiers 1–3 and A7 are built**, and the home window keeps its
  rolling seven days (Cameron, 2026-09-01). What is left is **Cameron's**: the masthead's
  shape, and whether a place index is ripe
- When this list runs short or a decision makes one of them near-term, pull the next item
  from `docs/deferred.md` (review findings and known gaps, dated, with their context)

## Parked

- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
