# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## Now

- **`docketyard.citator` is written and uncommitted** — keys, resolver, span test, loader
  and projection over migration 0014, plus a `citator` CLI verb. Two reviews triaged, the
  serious findings fixed and pinned by tests; `citation_dryrun.py` now runs the SHIPPED code
  and reproduces the scorer over all 60 decisions
- **The figures moved: 91.1% projected / 98.1% precision**, from 89.3%/98.0%.
  `projection_score.printed()` round-tripped each docket row through a non-idempotent
  normaliser, dropping the suffix from **2,711 held dockets**, so every finding naming one
  scored as unresolvable. Fixed both sides, pinned equal. **ADR 0017 § The figures is not
  re-derivable** — that run directory is not in `data/`
- **Two things block the citator from production**, both in `citator/__init__.py`: no
  finder (its `kind` judgement has no vocabulary), and **no review queue** — 0017 D5 routes
  the exposed class and every repair to a human *before* publication, `review_action` is in
  no migration, so an exposed edge projects indistinguishably from a clean one
- **Owed with the pipeline**: ingest writing `decision_work`; the review queue and the "not
  in the record" display joining live `citation`; the veto's trigger the day it stops being
  inert. Twelve smaller findings in `docs/deferred.md`
- **Settled 2026-09-01 (Cameron):** citator held from the CC0 dump; 0018 D7's "88.4%"
  stands (fixed registry measures 88.1%); `class_measurement` keeps D8's key
- **Drain RUNNING, healthy** — 16,541 left 17:11 UTC, 0 failed, due ~02:30 UTC 2026-09-02
- **Party types (F3)**: rules v2 at 83.3%, tuned on the sheet it is scored against —
  **a second unseen sample must confirm** before any type ships
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- No Anthropic key exists; any Claude-backed run needs a new one from Cameron
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **The finder, and the review queue** — the two blockers above. Neither needs a key
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
