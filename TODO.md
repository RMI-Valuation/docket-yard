# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive. Anything stale in Parked graduates to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- Watch the first real alert land (Cameron, FD 36873, as-it-happens, confirmed 2026-08-26
  on the encrypted store); then delete this line
- Cameron: copy `DY_EMAIL_KEY` from `~/.docketyard-prod.env` into the password manager,
  then delete that file and `~/.docketyard-instance-key.json`
- Cameron: confirm no other sender uses docketyard.org — DMARC is `p=quarantine`
  (2026-08-26), so unaligned mail from the domain is quarantined
- Decide what comes after the wedge (capability map, not assumed) and whether/how to
  announce; both are the operator's calls

## Next

- `docketyard gap open/close` so a recorded outage has a `coverage_gap` row for the
  coverage page and the late-delivery marking to cite (today: nothing writes that table)
- Key rotation pass for `DY_EMAIL_KEY` (decrypt under old, seal under new, all three
  tables) — unwritten; ADR 0014 records it as the known gap
- Credentials ADR follow-up: Lightsail has no instance profile, so production runs on a
  bucket-scoped IAM user's keys; decide EC2 t4g / Roles Anywhere / accept (ADR 0012 gap)
- Errata detection is built but unscheduled: nothing in production re-fetches known
  documents. Needs a last-checked column (schema change) so a refresh pass can walk the
  corpus oldest-checked first under a per-pass limit
- Poller bookkeeping for permanently-bad items (a capture whose ingest raises, a 404
  attachment) — retried and re-logged every pass; an attempt counter is a schema change
- `docketyard status` should count suppressions and subscriptions (operator-only numbers)
- What `total` counts on the filings table (rows vs records): still unmeasured; multi-row
  filings are rare. The stop rule does not depend on it; revisit when one appears
- Blobs to S3 is a host `aws s3 sync` timer, not the in-process S3 store ADR 0012 describes;
  fine at this volume, revisit when the instance disk or a second consumer makes it matter

## Parked

- Local-LLM vs API benchmark on a hand-labelled extraction sample — before any backfill pass
  commits to local output (12GB VRAM ⇒ 14B dense / ~30B MoE class). Qwen3 thinks by default
  on Ollama — disable thinking per request for extraction, or it pays for a monologue per row
- OCR pipeline for pre-2000 archive (GPU layout-OCR fits ADR 0003's IR) — backfill era
- A key held off the box (KMS) so the instance decrypts addresses only at send time — the
  forward step ADR 0014 leaves open
- Deploy credentials via GitHub OIDC role assumption if CI ever touches AWS (today it only
  pushes to ghcr)
- CLA-assistant Action gating outside PRs — when outside interest is real
- Quarterly bulk dumps (capability F5) doubling as production-corpus backups
- Never attach a self-hosted Actions runner to this public repo (fork-PR code execution)
