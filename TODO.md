# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive. Anything stale in Parked graduates to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- Cameron: convert RMI-AI-MACHINE per `infra/rmi-ai-machine.md`

## Next

- Registry walk: capture all dockets by prefix slices (`--mode backfill`; capped prefixes
  need sequence sub-slicing); measure a working sort for multi-page stability first
- M2: filings + decisions ingest — documents hashed into blobs, errata detection, filing
  entity per the revised schema draft
- Docket-sheet page mockup (design canvas) before any M3 frontend code — the sheet IS the product
- Dockerfile + release-triggered image build in CI (with M2, when there is something to run)

## Parked

- Hosting decision (Lightsail instance vs container service) — **trap:** container service
  has no persistent volumes and no cron; SQLite-on-instance is the likely fit. Needs a
  deployment-topology ADR when hosting stops being deferred
- Local-LLM vs API benchmark on a hand-labelled extraction sample — before any backfill pass
  commits to local output (12GB VRAM ⇒ 14B dense / ~30B MoE class)
- OCR pipeline for pre-2000 archive (GPU layout-OCR fits ADR 0003's IR) — backfill era
- Deploy credentials via GitHub OIDC role assumption, never long-lived AWS keys in secrets
- CLA-assistant Action gating outside PRs — when outside interest is real
- Quarterly bulk dumps (capability F5) doubling as production-corpus backups
- Never attach a self-hosted Actions runner to this public repo (fork-PR code execution)
