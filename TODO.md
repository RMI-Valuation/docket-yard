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
  whose quote is not in the text (5 are wrong pin cites). No scorer yet: it must compare
  *sets* of (decision, target), scoring each `target_kind` apart
- RMI-AI-MACHINE **offline on the tailnet since ~2026-08-29 06:00** (the workstation is not on
  its LAN) — Cameron fixes it physically; then OCR step 2, and check `systemctl is-enabled
  tailscaled`, `journalctl -b -1 -e`, mask the sleep targets
- **OCR (M3 slice):** step 1 accepted 2026-08-29. Step 2 **cloud half done 2026-08-29**
  without the box: Textract and Claude Sonnet 5 over the 90 pages (`ocr_run.py` gained both
  engines; Textract records per-word confidence). Claude leads on every tier; Textract is
  within a point on clean pages at 1/11th the cost, and is redundant-preprocessed — greyscale
  and 1-bit score identically. Local engines still unrun (box down). **Note the ground
  truth's own bound: ranking may be published, absolute character accuracy may not**
- Delete the Inactive `docketyard-instance` key after a clean day (`aws iam delete-access-key`);
  Cameron stores both new secrets from the session scratchpad
- **Revoke the Anthropic API key** pasted 2026-08-29 (it is in this session's transcript);
  it lives at `~/.anthropic-key`. Cost so far ~$5. Next: OCR→citation compound measurement
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
