# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. Anything stale in Parked
graduates to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- Webhook live test: a throwaway webhook.site endpoint follows FD 36873; after its next
  forward entry, verify the signed delivery (token in session notes), then unsubscribe
- Backfill pipeline on the instance, queued in tmux (2026-08-26): `wave2` documents
  (2020–2024-07, tables done) → `wave3` tables (1996–2019) → `wave3docs` (150–250 GB through
  the 58 GB cache; prune keeps ≥20 GB free). Logs `/srv/docketyard/wave*.log`. When each
  ends: check `partial` months and the coverage line; then re-run extraction on RMI-AI-MACHINE
- Seed wave 2 (after wave 3 tables land): 1996–2019 names roads that no longer exist —
  Conrail and its 1999 split, SP/UP, BN/ATSF, IC/CN, WC, KCS pre-CPKC. Pull the most
  frequent unresolved spans, extend the seed with those roads and dated successions
- Party resolution: a `docketyard parties join` command (human same_as edges) once real
  spelling pairs accumulate in the poll log's `ambiguous`/`left` counts
- RMI-AI-MACHINE: text layer (benchmark step 0) done 2026-08-26 for wave 1's files —
  4,273 PDFs in 4 min, 2 image-only, 0 failed (`/data/docketyard/text`); re-run after each
  wave lands, pulling from S3. Step 1 sample drawn 2026-08-26: Cameron fills
  `docs/research/benchmark/labels.csv` (guide in its README); step 2 runs once it is in
- Whether/how to announce the wedge — the operator's call
- Explainers draft (`docs/explainers.md`): Cameron reviews; [?] rows need one email to the
  Board's records staff before publishing; then a page per prefix

## Next

- Enriched layer into the snapshot/JSON after the attorney review (`licensing.md` § Open):
  remove `dump.HELD_TABLES`, restore the Parties block, bump `JSON_SHAPE`, announce on `/data`
- M8 review deferrals: a dead webhook endpoint should suppress itself after N consecutive
  failed alerts; a per-pass wall-clock budget for webhook delivery; `deliver` and
  `deliver_webhooks` want one loop over a channel object and one alert envelope; feeds
  run ~400 statements per request behind the cache header — TTL-cache on the ledger head
- `docketyard gap open/close` so a recorded outage has a `coverage_gap` row for the
  coverage page and the late-delivery marking to cite (today: nothing writes that table)
- Key rotation pass for `DY_EMAIL_KEY` (decrypt under old, seal under new; four sealed
  columns across three tables since 0008 — `subscription.secret_enc` is the fourth;
  tables) — unwritten; ADR 0014 records it as the known gap
- Credentials ADR follow-up: Lightsail has no instance profile, so production runs on a
  bucket-scoped IAM user's keys; decide EC2 t4g / Roles Anywhere / accept (ADR 0012 gap)
- Errata re-check is built but unscheduled: needs a last-checked column (schema change) so
  a refresh pass walks the corpus oldest-checked first under a per-pass limit
- Poller bookkeeping for permanently-bad items (ingest raises, 404 attachment): an attempt
  counter is a schema change; today they are retried and re-logged every pass
- What `total` counts on the filings table (rows vs records): unmeasured; the stop rule
  does not depend on it
- ADR 0012 addendum recording the blob cache design (sync + prune) once wave 3 proves it

## Parked

- Benchmark step 2 notes: 12GB VRAM ⇒ 14B dense / ~30B MoE class; Qwen3 thinks by default
  on Ollama — disable thinking per request for extraction, or it pays for a monologue per row
- A key held off the box (KMS) so the instance decrypts addresses only at send time — the
  forward step ADR 0014 leaves open
- Stats review deferrals (2026-08-26): `home.py` and `stats.py` each carry a month walker and
  the docket-family fold — share one helper; add an index on `filing(filed_date)` when a
  migration is next cut (the year and week queries range-scan without it)
