# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. Anything stale in Parked
graduates to `ROADMAP.md` or dies. Hard line cap enforced
by pre-commit: when it fires, prune.

## Now

- Documents backfill (1996 → 2024-07, ~75k files) in tmux `wave3docs`, log `wave3docs.log`:
  one streaming loop since v2026.08.25 (5,000-file batches); confirm the 1.07 GB FD 36500
  application landed in the blob store and S3. Then: 41 `partial` months to re-walk;
  re-run extraction. Deferred: Range-resume mid-body; hash while streaming; commit per doc
- Seed wave 2 (after wave 3 tables): most frequent unresolved spans; pre-2020 roads
  (Conrail, SP, BN/ATSF, IC, WC, KCS) and dated successions
- RMI-AI-MACHINE: text layer done for wave 1 (`/data/docketyard/text`); re-run after each
  wave from S3. Benchmark step 1: Cameron fills `docs/research/benchmark/labels.csv`
  (guide in its README); step 2 runs once it is in
- Whether/how to announce the wedge — the operator's call
- Explainers draft (`docs/explainers.md`): Cameron reviews; [?] rows need the Board's
  records staff; then a page per prefix

## Next

- Cameron's asks (2026-08-26), in the order agreed, each started only when he says so:
  (2) `/contribute` draft for his review — ideas → Issues (add an idea template), code →
  repo + CLA, money → hello@ for now, saying what it pays for and buys nothing; entity
  question in `licensing.md` before any formal channel; (3) one search box: docket number,
  party name or caption words, FTS5 index, `/suggest` as-you-type showing captions,
  `/search` works without JS, nothing stored; (4) traffic as hourly counts only (route
  class, status, bytes, latency, bot/not) — no identifier ever; bring him the one privacy
  sentence to sign first
- External review 2026-08-26: `/coverage` says the waves added 54,422 filings / 3,297
  decisions, `/stats` holds 53,018 / 2,815 — reconcile or label each so the gap is plainly
  intentional; FD 36873 sheet is 1.1 MB / 908 entries unpaginated — measure DOM cost on a
  low-end phone before changing anything
- M10 deferrals: an address following two ids later joined gets each filing twice per pass;
  the follow form after a 301 follows the representative (a later split narrows it);
  `--cite` is free text; `search()`/`Components.members()` costs — re-measure after wave 3
- Enriched layer into the snapshot/JSON after the attorney review (`licensing.md` § Open):
  remove `dump.HELD_TABLES`, restore the Parties block, bump `JSON_SHAPE`, announce on `/data`
- M8 deferrals: dead webhook endpoints self-suppress after N failures; per-pass delivery
  budget; one delivery loop over a channel object; TTL-cache feeds on the ledger head
- `docketyard gap open/close` so a recorded outage has a `coverage_gap` row for the
  coverage page and the late-delivery marking to cite (today: nothing writes that table)
- Key rotation pass for `DY_EMAIL_KEY` (decrypt under old, seal under new; four sealed
  columns across three tables since 0008) — unwritten; ADR 0014 records the gap
- Credentials ADR follow-up: Lightsail has no instance profile, so production runs on a
  bucket-scoped IAM user's keys; decide EC2 t4g / Roles Anywhere / accept (ADR 0012 gap)
- Two schema-change chores: errata re-check needs a last-checked column (walk oldest-first,
  per-pass limit); permanently-bad poll items need an attempt counter (retried every pass)
- ADR 0012 addendum recording the blob cache design (sync + prune) once wave 3 proves it
- Cameron's idea (2026-08-26): switch cadence from the alert email; a signed-link manage
  page per address (cadence is already per subscription; no login — ADR 0011). His decision

## Parked

- Benchmark step 2: 12GB VRAM ⇒ 14B dense / ~30B MoE; disable Qwen3 thinking per request
- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
