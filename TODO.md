# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- **Labels (extraction benchmark):** four conventions settled 2026-08-29, applied and
  corrected after review — `target_kind` on every row; 727 citations, 86 captions, 164
  deadlines. The test is document vs proceeding: a prior decision is a citation even in the
  decision's own docket. **Cameron's row check remains** (884 cards) — start with the 20
  whose quote is not in the text (5 are wrong pin cites). Until it is checked **no
  precision figure anywhere is readable** — a citation the drafter missed scores against
  the model. `benchmark_score.py` scores a run against the sheet
- RMI-AI-MACHINE back 2026-08-29 (a power-off, not a fault: `tailscaled` is enabled at boot,
  sleep targets inactive — nothing to harden). qwen2.5vl:7b pulled and scored. Tailscale SSH
  needs a browser check per session — Cameron's click
- **OCR/extraction (M3):** step 2 **done 2026-08-29**, ~$16. Five engines scored; the
  finding is that OCR costs the citator nothing measurable (91.9% of STB edges from
  Textract's OCR vs 89.2% from the publisher's text) while the extractor moves recall 29
  points (qwen3:14b 60.2%, Claude 89.2%). Budget belongs at extraction: ~$260 Textract +
  ~$1,075 Claude batched for the backfill. GPU rental rejected. Written into `ocr-plan.md`
  and `extraction-benchmark.md`. **Ground truth's bound: ranking publishable, absolute
  character accuracy not.** Next: step 3, an ADR recording what ships at what confidence
- Keys: delete the Inactive `docketyard-instance` key (`aws iam delete-access-key`), and
  **revoke the Anthropic key** at `~/.anthropic-key` (it is in this session's transcript;
  session spend ~$16)
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **ADR 0016** accepted 2026-08-28: a reviewer has an identity, reading stays anonymous;
  `/review` for OCR pages, citation edges, labels, corrections. Next: schema-critic on
  `reviewer`/`review_action`, then build
- Citator schema gate, before C2 is chosen: the citation-edge shape against
  `validation-queries.md`, ADR 0006 and 0007 — a new ADR if needed; an unresolvable citation
  string is data, record the span. **Its first four answers are settled** in
  `docs/research/benchmark/README.md`
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
