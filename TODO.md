# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- Documents backfill (1996 → 2024-07, ~75k files) in tmux `wave3docs`, log `wave3docs.log`:
  one streaming loop since v2026.08.25 (5,000-file batches; the 1.07 GB FD 36500 application
  landed at 34 MB RSS). When it ends: 41 `partial` months to re-walk;
  re-run extraction. Deferred: Range-resume mid-body; hash while streaming; commit per doc
- Seed wave 2 (after wave 3 tables): most frequent unresolved spans; pre-2020 roads
  (Conrail, SP, BN/ATSF, IC, WC, KCS) and dated successions
- RMI-AI-MACHINE: text layer done for wave 1 (`/data/docketyard/text`); re-run after each
  wave from S3. Benchmark step 1: Cameron fills `docs/research/benchmark/labels.csv`
  (guide in its README); step 2 runs once it is in
- Explainers draft (`docs/explainers.md`): Cameron reviews; [?] rows need the Board's
  records staff; then a page per prefix. Whether/how to announce the wedge — his call

## Next

- **Sitemap defect** (2026-08-26): `sitemap-dockets` lists family parents only, 21,807 of
  32,605 rows; the 10,798 sub-dockets are real pages with their own canonical (2,032 carry
  filings; search points at 765 AB 55 subs) while 16,805 empty parents are listed. Fix in
  `sitemaps.py` (subs with their own `lastmod`); say on `/coverage` what the sitemap holds
- `/coverage` says the waves added 54,422 filings / 23,702 decisions; `/stats` holds 53,027 /
  19,829 (wave-added vs held) — label each so the gap is plainly intentional
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
