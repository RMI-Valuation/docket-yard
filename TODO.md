# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive. Anything stale in Parked graduates to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- M4: first real subscription confirmed 2026-08-26 (Cameron, FD 36873, as-it-happens);
  watch the first alert land, then delete this line
- SES bounce/complaint feedback path (SNS topic → `email_suppression`) before any real
  volume; until then the SES reputation dashboard is checked by hand
- `hello@docketyard.org`: Cameron enabling Cloudflare Email Routing → camrex@; send a test
  once done (the about page already names it)
- `docketyard gap open/close` so a recorded outage has a `coverage_gap` row for the
  coverage page and the late-delivery marking to cite
- DMARC `p=quarantine` is now set on docketyard.org (2026-08-26) — any other sender on the
  domain must be DKIM-aligned or its mail will be quarantined; Cameron to confirm none exists
- Credentials ADR follow-up: Lightsail has no instance profile, so the first deploy runs on
  a bucket-scoped IAM user's keys; decide EC2 t4g / Roles Anywhere / accept (ADR 0012 gap)

## Next

- What `total` counts on the filings table (rows vs records): still unmeasured after 36
  agency-wide filings showed one attachment row each; multi-row filings are rarer than the
  design session assumed. The stop rule does not depend on it; revisit when one appears
- Blobs to S3 is a host `aws s3 sync` timer, not the in-process S3 store ADR 0012 describes;
  fine at this volume, revisit when the instance disk or a second consumer makes it matter
- Errata detection is built but unscheduled: nothing in production re-fetches known
  documents. Needs a last-checked column (schema change) so a refresh pass can walk the
  corpus oldest-checked first under a per-pass limit
- Poller bookkeeping for permanently-bad items (a capture whose ingest raises, a 404
  attachment) — retried and re-logged every pass; an attempt counter is a schema change
- Off-box heartbeat for the poller (M4 alerts.md): nothing pages anyone yet if `ingest` dies

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
