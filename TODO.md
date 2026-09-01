# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## Now

- **v2026.08.45 is live** (2026-09-01, navigation Tiers 1–2). Verified on the site: the
  three walled-off weeks show their 91 filings, 1996 is reachable, `/coverage` names
  2026-08 alone for filings and decisions, search leads with captions. A pre-deploy copy of
  the store sits at `/srv/docketyard/pre-v45-backup.sqlite` (296 MB) — delete it once the
  release has held a day; Litestream is the real answer (ADR 0012)
- **26,943 comment attachments unfetched, and the poller will never fetch them** (measured
  2026-08-31: all are `backfill`-mode observations and `poll` asks for `observed_in=
  "forward"`). Cameron's go given 2026-08-31, **throttled and after this release**:
  `fetch attachments --mode backfill` on the instance, resumable, watching disk (21 GB free
  against the pruner's 20 GB floor). ~27k requests to the Board — agree the rate first
- **ADR 0017 stays Proposed.** Acceptance taken 2026-08-31 and **held by Cameron the same
  day**, before it left the branch; § Decision is unamended. Its § Acceptance, held keeps
  the work — what acceptance would decide, the amendments re-checked, and the six things it
  must clear first. Still gates OCR, the citator and the reviewer build
- **A6 decided 2026-08-31, not built**: an AB sub-docket subscription stops folding to its
  family; every other prefix keeps folding. It changes what a subscription means, so it is
  its own change with its own review
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
- **`docs/navigation-review.md`**: Tiers 1–2 shipped. A7 (a series sheet builds 2,628
  entries and renders none) is one decision with the same item in `docs/deferred.md`.
  Tier 3 is a front door — weeks index, docket index by prefix and year, `/parties` as a
  page, the sub-docket → series breadcrumb. **Tier 4 is his** (the masthead, the home
  window's unit, what a series sheet is, place)
- When this list runs short or a decision makes one of them near-term, pull the next item
  from `docs/deferred.md` (review findings and known gaps, dated, with their context)

## Parked

- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
