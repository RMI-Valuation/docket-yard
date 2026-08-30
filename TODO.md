# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- **ADR 0017 (Proposed 2026-08-30)** — the API extractor ships citation edges; local
  does not write them; confidence is the measured precision of an edge's class; the
  registry (rules 1–2) and the ADR 0016 queue sit between model and page. Drafted from the
  checked sheet: docket-shaped targets 95.9%/95.5%, all ten extras self-references, six
  unresolved targets identical to the sheet's. Schema-critic's seven findings are
  folded in (§ Review); next: Cameron's acceptance in a later session. `target` column settled: what a citator
  resolves (68 rows rewritten, truth sets identical)
- **Local candidates batch, started 2026-08-30 ~10:54 CDT on RMI-AI-MACHINE**
  (`benchmark_batch.sh`, log `/data/docketyard/benchmark/batch.log`): qwen3:14b re-run on
  the current prompt, qwen2.5:14b, gemma3:12b, phi4:14b, mistral-nemo:12b, llama3.1:8b,
  qwen3:30b-a3b, gpt-oss:20b. ~2 h each; Tailscale SSH needs Cameron's browser click per session. Score each with `benchmark_score.py` (now reports
  the docket-shaped class); the bar is Claude's 95.9%/95.5% on that class. If one comes
  close, measure regex-first + local role-classifier next (regex+registry alone: 97.3%
  recall, 76.7% precision on docket-shaped, 2026-08-30)
- **OCR/extraction (M3):** step 2 done 2026-08-29 (~$16); the finding — OCR costs the
  citator nothing measurable, the extractor moves recall 16 points — is in `ocr-plan.md`,
  `extraction-benchmark.md` and ADR 0017. **Ground truth's bound: ranking publishable,
  absolute character accuracy not**
- Keys: rotation closed 2026-08-30 — the superseded `docketyard-instance` key is deleted,
  one Active key remains, Litestream unaffected. The Anthropic key is revoked and its local
  copy gone; a further extraction run needs a new one (session spend was ~$16)
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **ADR 0016** accepted 2026-08-28: a reviewer has an identity, reading stays anonymous;
  `/review` for OCR pages, citation edges, labels, corrections. Next: schema-critic on
  `reviewer`/`review_action`, then build
- Citator schema gate (`docs/citator-gate.md`) is drafted into ADR 0017; still open after
  it: record cites' slice, statutes, the decided date's placement
- Deadline engine (C4) evidence: decision JSON carries no extracted obligations (verified
  2026-08-26); a hand-checked fixture of 8 dated obligations for FD 36873 is in
  `../up-ns-merger-tracker/briefs/2026-08-25.md` (read-only; see
  `docs/upns-tracker-inheritance.md`). Dates quoted, never computed (ADR 0006)
- JSON-LD (Cameron, 2026-08-26): none on any page; decide the vocabulary before adding any
- **OCR of the 13,604 image-only files** (M3's first slice): plan in `docs/ocr-plan.md`.
  Shape now measured: Textract bulk + Claude on graphic/tabular/low-confidence, ~$700 for
  the backfill; nothing reads into the store before step 3
- Cameron's idea: cadence switch from the alert email; a signed-link manage page per address
- When this list runs short or a decision makes one of them near-term, pull the next item
  from `docs/deferred.md` (review findings and known gaps, dated, with their context)

## Parked

- Benchmark step 2: 12GB VRAM ⇒ 14B dense / ~30B MoE; disable Qwen3 thinking per request
- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
