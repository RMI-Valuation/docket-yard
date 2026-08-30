# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- **ADR 0017 (Proposed 2026-08-30)**: the API extractor ships edges at measured class
  confidence; schema-critic's findings folded in. Awaiting Cameron's acceptance with the
  amendment candidates (regex-first docket class; on-page rule; the cite.py verb-gate
  conflict). `target` column settled: what a citator resolves
- **Local candidates batch running** (status <http://10.180.20.12:8765/>; `ssh rmi-lan`):
  scored so far on docket-shaped — Claude 95.6/95.6, qwen3:14b 93.8/93.8, regex+registry
  94.7 with no model, qwen2.5 87.6/90.0. Roles classifier queued behind the batch
  (`benchmark_roles_followup.sh`); score each model as it lands
- **OCR/extraction (M3):** step 2 done 2026-08-29 (~$16); the finding — OCR costs the
  citator nothing measurable, the extractor moves recall 16 points — is in `ocr-plan.md`,
  `extraction-benchmark.md` and ADR 0017. **Ground truth's bound: ranking publishable,
  absolute character accuracy not**
- Keys: rotation closed 2026-08-30; Litestream unaffected. The Anthropic key is revoked
  and its local copy gone; a further extraction run needs a new one
- **Party types (F3's first slice, chosen 2026-08-30)**: design in `docs/party-types.md`
  (vocabulary measured, three method tiers, ground truth before anything ships);
  critic's report folded in (evidence keys, additive vocab, pinned projection). The
  300-party sample is drawn, Wikidata evidence attached (67 links, 10 disagreements),
  and **Cameron's check queue is live**:
  <https://claude.ai/code/artifact/70be297e-340e-4875-b4e3-94a509f6fe7d> — judge, then
  Copy findings back to a session to apply to `docs/research/party-types/labels.csv`
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **ADR 0016** accepted 2026-08-28. `reviewer`/`review_action` drafted into
  `schema-draft.md` § 7 and through schema-critic 2026-08-30 (report folded in: every
  decision writes a human row, attribution of pre-table human rows is a rule not an
  UPDATE, text target keys, no benchmark-label queue). Next: build, after ADR 0017
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
