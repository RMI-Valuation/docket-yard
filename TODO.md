# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## Now

- **The review gate holds** (migration 0015): the exposure test is a stored judgement and an
  exposed edge waits for a human. Five held on the benchmark
- **The figures: 94.7% projected / 97.7% precision by the rule, 93.3% to a reader.** Three
  causes, separated in 0016's header: the scorer's registry dropped the suffix from 2,711
  dockets; the finder now joins every occurrence on a page, not the first; and precision
  FELL, which is the honest trade for finding more
- **The finder ships too** (migration 0016 seeds `kind`; `citator/find.py`). The whole chain
  is now shipping code, and `citation_dryrun.py` regenerates the run it is measured on, so
  ADR 0017's table is re-derivable at last. **The figures moved again and every line has its
  own reason** — migration 0016's header is the one to quote
- **`/review` and magic-link sign-in ship** (migration 0017). The one cookie this server
  sets, scoped to `/review` so no read page can become identity-linked, and no page view
  counted. `/privacy` and `/contribute` say so. **Nothing now blocks the citator from
  production** — what remains is the operator's call on when to run the first real load
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

- **The finder, and `/review` + sign-in** — the two blockers above. Neither needs a key
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
