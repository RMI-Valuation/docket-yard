# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- **Labels: checked 2026-08-30** — all 884 judged, one row wrong, none missing. Precision
  is readable at last: Claude 64.2% against 89.2% recall on STB edges, qwen3 23.6%/73.5%.
  **One decision open, Cameron's:** 68 rows record a target as `FD 36744 et al.`; does the
  `target` column hold what the page printed or what a citator resolves? Scoring is
  unaffected either way. Then step 3 — the ADR naming what ships, at what confidence, and
  what is left to a human
- RMI-AI-MACHINE back 2026-08-29 (a power-off, not a fault: `tailscaled` is enabled at boot,
  sleep targets inactive — nothing to harden). qwen2.5vl:7b pulled and scored. Tailscale SSH
  needs a browser check per session — Cameron's click
- **OCR/extraction (M3):** step 2 **done 2026-08-29**, ~$16. Five engines scored; the
  finding is that OCR costs the citator nothing measurable (91.9% of STB edges from
  Textract's OCR vs 89.2% from the publisher's text) while the extractor moves recall 16
  points (qwen3:14b 73.5%, Claude 89.2%). Budget belongs at extraction: ~$260 Textract +
  ~$1,075 Claude batched for the backfill. GPU rental rejected. Written into `ocr-plan.md`
  and `extraction-benchmark.md`. **Ground truth's bound: ranking publishable, absolute
  character accuracy not.** Next: step 3, an ADR recording what ships at what confidence
- Keys: rotation closed 2026-08-30 — the superseded `docketyard-instance` key is deleted,
  one Active key remains, Litestream unaffected. The Anthropic key is revoked and its local
  copy gone; a further extraction run needs a new one (session spend was ~$16)
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **ADR 0016** accepted 2026-08-28: a reviewer has an identity, reading stays anonymous;
  `/review` for OCR pages, citation edges, labels, corrections. Next: schema-critic on
  `reviewer`/`review_action`, then build
- Citator schema gate, before C2 is chosen: **`docs/citator-gate.md`** now collects it —
  four conventions settled, two docket-resolution rules from the footnote-fusion defect, and
  what is still open (record cites, statutes, the decided date). Needs an ADR, and
  schema-critic before it is accepted
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
