# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive. Anything stale in Parked graduates to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- Cameron: review ADR 0012 (deployment topology) and ADR 0013 (permanent URLs)
- M3 deploy (after ADR 0012 accepted): Dockerfile + compose (web, ingest, caddy) + Litestream;
  release-triggered image build; the instance; move the registry from rmi-ai-machine
- Self-host the two fonts (interface.md) before anything ships — the pages fall back to
  system faces today

## Next

- What `total` counts on the filings table (rows vs records): still unmeasured after 36
  agency-wide filings showed one attachment row each; multi-row filings are rarer than the
  design session assumed. The stop rule does not depend on it; revisit when one appears
- M3: docket sheet projection + server-rendered pages at permanent URLs (needs the hosting
  decision to stop being deferred; the projection can be built first)
- Dockerfile + release-triggered image build in CI (with M2, when there is something to run)

## Parked

- Hosting decision (Lightsail instance vs container service) — **trap:** container service
  has no persistent volumes and no cron; SQLite-on-instance is the likely fit. Needs a
  deployment-topology ADR when hosting stops being deferred
- Local-LLM vs API benchmark on a hand-labelled extraction sample — before any backfill pass
  commits to local output (12GB VRAM ⇒ 14B dense / ~30B MoE class). Qwen3 thinks by default
  on Ollama — disable thinking per request for extraction, or it pays for a monologue per row
- OCR pipeline for pre-2000 archive (GPU layout-OCR fits ADR 0003's IR) — backfill era
- Deploy credentials via GitHub OIDC role assumption, never long-lived AWS keys in secrets
- CLA-assistant Action gating outside PRs — when outside interest is real
- Quarterly bulk dumps (capability F5) doubling as production-corpus backups
- Never attach a self-hosted Actions runner to this public repo (fork-PR code execution)
