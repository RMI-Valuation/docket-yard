# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- Document viewer: frame confirmed rendering by Cameron 2026-08-27. Open: the read-only S3 key
  pair for the web tier and the `sandbox` CSP test (`docs/deferred.md` § Document viewer)
- Backfill complete 2026-08-27: 77,565 documents held; the 41 partial months re-walked and
  recorded `empty` (13:58 UTC), `/coverage` lists none. One legacy `/MPD/` URL 403s (rests
  a week from PR #10)
- Seed wave 2 (after wave 3 tables): most frequent unresolved spans; pre-2020 roads
  (Conrail, SP, BN/ATSF, IC, WC, KCS) and dated successions
- RMI-AI-MACHINE: qwen3:14b step-2 run done 2026-08-26 (60/60, `benchmark/runs/`); text
  layer over the first 9,663 wave 2–3 files done (1,480 image-only — 15%); the full-record
  pull + extraction started 2026-08-27 13:45 UTC in tmux `extract`. Scoring waits on
  Cameron's check of `labels.csv`; the API candidate waits on his go (it spends money)
- Explainers draft (`docs/explainers.md`): Cameron reviews; [?] rows need the Board's
  records staff; then a page per prefix. Whether/how to announce the wedge — his call

## Next

- Citator schema gate, before C2 is chosen: the citation-edge shape against
  `validation-queries.md` (negative treatment, segment history), ADR 0006 and 0007 — a new ADR
  if needed; an unresolvable citation string is data, record the span; re-measure ~22% density
- Deadline engine (C4) evidence: decision JSON carries no extracted obligations (verified
  2026-08-26); F1's "computed next deadline" presupposes it; a hand-checked fixture of 8 dated
  obligations for FD 36873 is in `../up-ns-merger-tracker/briefs/2026-08-25.md` (read-only;
  what else to take from that project: `docs/upns-tracker-inheritance.md`).
  Hard rule: dates quoted, never computed; a reset schedule supersedes (ADR 0006)
- JSON-LD (Cameron, 2026-08-26): none on any page; decide the vocabulary before adding any
- **OCR of the 13,604 image-only files** (M3's first slice): plan in `docs/ocr-plan.md` —
  ground truth the operator checks, engines measured by CER and by docket-number/date errors,
  a review layer (agreement → confidence, registry checks, an operator queue). Four
  decisions at the end of the plan are Cameron's; nothing reads into the store before step 3
- Cameron's idea: cadence switch from the alert email; a signed-link manage page per address
- When this list runs short or a decision makes one of them near-term, pull the next item
  from `docs/deferred.md` (review findings and known gaps, dated, with their context)

## Parked

- Benchmark step 2: 12GB VRAM ⇒ 14B dense / ~30B MoE; disable Qwen3 thinking per request
- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
