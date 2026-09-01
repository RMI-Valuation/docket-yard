# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## Now

- **v2026.08.49 is live** (2026-09-01). The navigation review is built through Tier 3:
  Tiers 1–2 (v45), A6 (v46), weeks index and breadcrumb (v47), `/parties` (v48), `/dockets`
  (v49). All verified on the site. A pre-deploy copy of the store sits at
  `/srv/docketyard/pre-v45-backup.sqlite` (296 MB) — delete it once these have held a day
- **26,943 comment attachments unfetched, and the poller will never fetch them** (measured
  2026-08-31: all are `backfill`-mode observations and `poll` asks for `observed_in=
  "forward"`). Cameron's go given 2026-08-31, **throttled and after this release**:
  `fetch attachments --mode backfill` on the instance, resumable, watching disk (21 GB free
  against the pruner's 20 GB floor). ~27k requests to the Board — agree the rate first
- **ADR 0017 stays Proposed.** Acceptance taken 2026-08-31 and **held by Cameron the same
  day**, before it left the branch; § Decision is unamended. Its § Acceptance, held keeps
  the work — what acceptance would decide, the amendments re-checked, and the six things it
  must clear first. Still gates OCR, the citator and the reviewer build
- **`/d/AB-55/sub/794X.json` still answers with the whole family** while its page and feed
  now cover the one line (code review, v2026.08.46). Changing it alters what an existing
  consumer receives: a `shape_version` decision, and **Cameron's** — `docs/deferred.md`
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
- **`docs/navigation-review.md`: Tiers 1–3 are built.** What is left is **Cameron's**:
  Tier 4 (the masthead's shape, whether the home window becomes the calendar week, what a
  series sheet is, whether a place index is ripe) and A7 — a series sheet builds 2,628
  entries and renders none, one decision with the same item in `docs/deferred.md`
- When this list runs short or a decision makes one of them near-term, pull the next item
  from `docs/deferred.md` (review findings and known gaps, dated, with their context)

## Parked

- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
