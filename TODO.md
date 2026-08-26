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
- Seed wave 2 (after wave 3 tables land): pull the most frequent unresolved spans; extend
  the seed with the pre-2020 roads (Conrail, SP, BN/ATSF, IC, WC, KCS) and dated successions
- RMI-AI-MACHINE: text layer (benchmark step 0) done 2026-08-26 for wave 1's files —
  4,273 PDFs in 4 min, 2 image-only, 0 failed (`/data/docketyard/text`); re-run after each
  wave lands, pulling from S3. Step 1 sample drawn 2026-08-26: Cameron fills
  `docs/research/benchmark/labels.csv` (guide in its README); step 2 runs once it is in
- Whether/how to announce the wedge — the operator's call
- Explainers draft (`docs/explainers.md`): Cameron reviews; [?] rows need the Board's records
  staff; then a page per prefix

## Next

- Cameron's asks (2026-08-26), in the order agreed: (1) ADR 0015 → Accepted next session, then
  `/p/<id>` with dockets shown as number + caption + filings + last filing (also on
  `/parties`), 301 for folded ids, `docketyard parties join`; (2) `/contribute` draft — ideas
  → Issues (add an idea template), code → repo + CLA, money → hello@ for now, saying what it
  pays for and buys nothing; entity question in `licensing.md` before any formal channel;
  (3) one search box: docket number, party name or caption words, FTS5 index, `/suggest`
  as-you-type showing captions, `/search` works without JS, nothing stored; (4) traffic as
  hourly counts only (route class, status, bytes, latency, bot/not) — no identifier ever;
  needs one privacy sentence Cameron signs off
- FD 36873 sheet is 1.1 MB / 907 entries (79 KB wired): measure on a low-end phone first
- Enriched layer into the snapshot/JSON after the attorney review (`licensing.md` § Open):
  remove `dump.HELD_TABLES`, restore the Parties block, bump `JSON_SHAPE`, announce on `/data`
- M8 deferrals: dead webhook endpoints self-suppress after N failures; per-pass delivery
  budget; one delivery loop over a channel object; TTL-cache feeds on the ledger head
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
- ADR 0012 addendum recording the blob cache design (sync + prune) once wave 3 proves it

## Parked

- Benchmark step 2: 12GB VRAM ⇒ 14B dense / ~30B MoE; disable Qwen3 thinking per request
- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: share one month walker and family fold between `home.py`/`stats.py`;
  index `filing(filed_date)` at the next migration
