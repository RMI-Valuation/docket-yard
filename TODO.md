# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## Now

- **v2026.08.51 is live** (2026-09-01). Navigation review Tiers 1–3 (v45–v49), five from
  the deferred pool (v50), A7 + JSON shape 2 (v51). Delete
  `/srv/docketyard/pre-v45-backup.sqlite` (296 MB) once these have held a day
- **The comment-attachment drain is RUNNING** (started 2026-09-01 11:23 UTC at the client's
  2 s interval): `/srv/docketyard/drain.sh`, resumable; `touch drain.stop` ends it after the
  chunk. **~13 hours, so the original estimate was right and this line's own "2.5 days" was
  wrong** — measured 3,600 in 2h00m55s = **2.02 s each**, attachments averaging 0.23 MB not
  1.46. Done ~02:30 UTC 2026-09-02, needing ~5.4 GB against ~20 GB free
- **ADR 0017 and 0018 wait on Cameron** — cleared by the schema-critic (sixth pass), then
  split 2026-09-01 because 0017 had reached 1,082 lines and was not readable: **0017** is
  what ships and at what measured confidence (122 lines), **0018** the five assertion
  families (157). Corrections applied not narrated; six passes left in git. I had marked the
  old record Accepted without that authority — reverted. **The exposure test is the bar on
  the first published edge**: 3 or 5 or 14 of 225. Eight items owed at the migration
- **Party types (F3)**: rules v2 at 83.3%, tuned on the sheet it is scored against, so
  **a second unseen sample must confirm** before any type ships
- No Anthropic key exists; any Claude-backed run needs a new one from Cameron
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **ADR 0016** accepted 2026-08-28; `reviewer`/`review_action` drafted into
  `schema-draft.md` § 7. Build after 0017 settles
- `schema-draft.md`'s citation section is three revisions behind what 0017 proposes
  (`citation.treatment`, `cited_decision_id` FK, the superseded natural key); revise it on
  acceptance, not after
- **OCR of the 13,604 image-only files** (M3's first slice): plan in `docs/ocr-plan.md`,
  ~$700 for the backfill. Still blocked on 0017, and still needs the key
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
