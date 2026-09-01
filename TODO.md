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
- **ADR 0017 stays Proposed, declined twice by the schema-critic and corrected twice**
  (`revive-0017`). Pass 2's D1–D14 are all addressed in d532566: the registry split so no
  stamp is ever rewritten, precedence moved to the method registry, `citation_reading` +
  `reading_channel` in the resolution key, `citation_treatment` as treatment's one home,
  `human` as its own confidence state. Recall is **97.8%**, not 95.1% — the benchmark
  filtered inside the finder and decision 1 no longer does (5ba275a); the six recovered
  targets are all real edges. Third pass running. **The one open blocker is the exposure
  test**, which has no single definition and yields 3, 5 or 14 of 225. **Cameron's**:
  whether to accept once the critic clears it
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
