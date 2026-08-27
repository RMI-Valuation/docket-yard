# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- **Document viewer, PR #10** (branch `document-viewer`, 2026-08-27): reviews answered; CI →
  merge → v2026.08.31 → deploy with the new `Caddyfile` (a `/document/*` handle block) and
  `compose.yaml` (`DY_S3_BUCKET` in the web env) → verify `/document/<sha>.pdf` (200, 206,
  304) and `/filing/<id>/view` from outside → `docs/milestones.md`. **Cameron, in a
  browser:** does the frame render (Chrome, Firefox, a phone)? Then decide the two key
  questions in `docs/deferred.md` § Document viewer (a read-only key pair for the web tier)
- Backfill: documents done 2026-08-27 (77,565 held; one legacy `/MPD/` URL 403s). The 41
  `partial` months (1996–2000) are **proven empty** by neighbour-window reconciliation
  (`stb-data-source.md` § Measured 2026-08-27); the walker now proves that itself. After
  v2026.08.30 deploys, re-walk 1996–2000 so they record `empty` and `/coverage` drops them
- Seed wave 2 (after wave 3 tables): most frequent unresolved spans; pre-2020 roads
  (Conrail, SP, BN/ATSF, IC, WC, KCS) and dated successions
- RMI-AI-MACHINE: qwen3:14b step-2 run done 2026-08-26 (60/60, `benchmark/runs/`); text
  layer over the first 9,663 wave 2–3 files done (1,480 image-only — 15%); the full-record
  pull + extraction started 2026-08-27 13:45 UTC in tmux `extract`. Scoring waits on
  Cameron's check of `labels.csv`; the API candidate waits on his go (it spends money)
- Explainers draft (`docs/explainers.md`): Cameron reviews; [?] rows need the Board's
  records staff; then a page per prefix. Whether/how to announce the wedge — his call

## Next

- F5's unfinished edge (no decision needed): `/api`, a human page for `/openapi.json` (what,
  licence, stability, rate expectations, an example, links); `/llms.txt` from the trust pages' source
- Citator schema gate, before C2 is chosen: the citation-edge shape against
  `validation-queries.md` (negative treatment, segment history), ADR 0006 and 0007 — a new ADR
  if needed; an unresolvable citation string is data, record the span; re-measure ~22% density
- Deadline engine (C4) evidence: decision JSON carries no extracted obligations (verified
  2026-08-26); F1's "computed next deadline" presupposes it; a hand-checked fixture of 8 dated
  obligations for FD 36873 is in `../up-ns-merger-tracker/briefs/2026-08-25.md` (read-only;
  what else to take from that project: `docs/upns-tracker-inheritance.md`).
  Hard rule: dates quoted, never computed; a reset schedule supersedes (ADR 0006)
- JSON-LD (Cameron, 2026-08-26): none on any page; decide the vocabulary before adding any
- Cameron's idea: cadence switch from the alert email; a signed-link manage page per address
- When this list runs short or a decision makes one of them near-term, pull the next item
  from `docs/deferred.md` (review findings and known gaps, dated, with their context)

## Parked

- Benchmark step 2: 12GB VRAM ⇒ 14B dense / ~30B MoE; disable Qwen3 thinking per request
- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
