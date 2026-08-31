# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- **Environmental comments shipped (v2026.08.42)** — schema 0011–0012, capture, parser,
  wave, sheet row, `/comment/<number>`, search and the canary pair. **Next: the archive
  wave** — >22,000 rows, 1996 →, `backfill --tables comments`, monthly. Watch its
  `id_collisions` count: the address rests on uniqueness measured over 11% of the record,
  and the wave is what tests the rest. **No name is masked** (2026-08-31; the reasoning is
  in 0011's header): nothing published may imply otherwise
- **ADR 0017 (Proposed)**: the batch is complete, so it is decidable. Amendments to fold in
  at acceptance: the docket class ships from regex+registry (95.1%, unbeaten by nine local
  models); the on-page rule joins the resolution pass; the decided date is extracted in the
  same pass or costs a ~$1,335 re-run. **Cameron's acceptance**
- **Party types (F3's first slice)**: design in `docs/party-types.md`, ground truth checked
  (300 parties), rules v2 at 83.3% — but tuned on the sheet it is scored against, so **a
  second unseen sample must confirm** before any type ships. Then the model tier
- No Anthropic key exists; any Claude-backed run needs a new one from Cameron
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **ADR 0016** accepted 2026-08-28; `reviewer`/`review_action` drafted into
  `schema-draft.md` § 7, schema-critic's report folded in. Build after 0017
- Citator schema gate (`docs/citator-gate.md`) is drafted into ADR 0017; still open after
  it: record cites' slice, statutes, the decided date's placement
- **OCR of the 13,604 image-only files** (M3's first slice): plan in `docs/ocr-plan.md`,
  shape measured — Textract bulk + Claude on graphic/tabular/low-confidence, ~$700 for the
  backfill. Nothing reads into the store before ADR 0017 settles what ships
- Deadline engine (C4) evidence: decision JSON carries no extracted obligations (verified
  2026-08-26); a hand-checked fixture of 8 dated obligations for FD 36873 is in
  `../up-ns-merger-tracker/briefs/2026-08-25.md` (read-only; see
  `docs/upns-tracker-inheritance.md`). Dates quoted, never computed (ADR 0006)
- JSON-LD (Cameron, 2026-08-26): none on any page; decide the vocabulary before adding any
- Cameron's idea: cadence switch from the alert email; a signed-link manage page per address
- When this list runs short or a decision makes one of them near-term, pull the next item
  from `docs/deferred.md` (review findings and known gaps, dated, with their context)

## Parked

- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
