# Deferred findings

Review findings and known gaps recorded for later — accepted as not-now, never silently
dropped (`CLAUDE.md` § Review before commit). Each carries the date and the release it was
found against. `TODO.md` holds only near-term work and points here; an item leaves this file
when it is fixed (the commit is the record) or graduates back to `TODO.md` when chosen.

## Web tier

- **Search rebuild is whole, not a diff** (2026-08-26, v2026.08.28): any moved id rebuilds all
  ~62k rows (40 s on the instance while a wave runs); a diff by `(kind, ref)` would write only
  what changed. Related: `_connect_rw` waits up to 30 s on the rebuild's write lock, so a
  `/subscribe` during one is slow rather than failed.
- **Two curated "what changed" lists** (2026-08-26): the ETag stamp and the search signature
  each enumerate max ids; one store-level record version (a counter bumped by every writer)
  would make both correct by construction.
- **Snapshot's FTS shadow-table list is by hand** (2026-08-26, `dump.SEARCH_SHADOWS`); derive
  it from `sqlite_master` or drop the FTS table in the snapshot instead.
- **`/parties` and `/search` cost at scale** (2026-08-26): `Components.members()` walks the
  whole graph per call; `search()` loads a caption per row. Fine at 10k parties; re-measure
  after wave 3's documents land.
- **FD 36873 sheet** is 1.1 MB / 908 entries unpaginated; measure DOM cost on a low-end phone
  before changing anything (external review, 2026-08-26).

## Party module (M10, 2026-08-26)

- An address following two ids that are later joined receives each filing twice per pass
  (dedup is per subscription, not per component).
- The follow form on a 301'd page follows the representative, so a later unjoin narrows the
  subscription silently.
- `--cite` on `parties join` is free text, not a typed filing/decision reference.

## Alerts (M8, 2026-08-26)

- Dead webhook endpoints should self-suppress after N failures; a per-pass delivery budget;
  one delivery loop over a channel object; TTL-cache feeds on the ledger head.

## Store and operations

- **Prove an empty month automatically** (2026-08-27): a month slice that answers the
  envelope on its first page could be settled by two requests — a window over it and an
  adjacent `done` month, reconciled to the done month's total — instead of a hand-measured
  entry in `EXPECTED_EMPTY_MONTHS`. Worth it before the next thin era is walked (ICC years,
  if ever).
- **A 403 on one document reads as a WAF rule change** (2026-08-27, v2026.08.29): `StbClient`
  diagnoses every 403 as "the WAF likely changed its User-Agent rules". A single legacy
  `dcms-external.s3.amazonaws.com/MPD/…` attachment (double-encoded old-DCMS path) returned
  403 mid-wave while every other fetch succeeded; the message should say which host answered
  and reserve the WAF diagnosis for the STB search endpoint. The item is retried every batch
  (the attempt-counter chore below).
- **Key rotation** for `DY_EMAIL_KEY` (decrypt under old, seal under new; four sealed columns
  across three tables since 0008) — unwritten; ADR 0014 records the gap.
- **Credentials**: Lightsail has no instance profile, so production runs on a bucket-scoped
  IAM user's keys; decide EC2 t4g / Roles Anywhere / accept (ADR 0012 gap).
- **Schema chores**: the errata re-check needs a last-checked column (walk oldest-first under
  a per-pass limit); permanently-bad poll items need an attempt counter (retried every pass).
- **ADR 0012 addendum** recording the blob cache design (S3 the store, the instance a cache;
  sync + prune) once wave 3 proves it.
- **`docketyard gap open/close`** so a recorded outage has a `coverage_gap` row for the
  coverage page and the late-delivery marking to cite (today nothing writes that table).
- **Streamed downloads** (2026-08-26, v2026.08.25): no Range-resume on a mid-body failure;
  the file is written, hashed and sniffed in three passes rather than one; one commit per
  document is the dominant DB cost of a wave.
- **Enriched layer into the snapshot and JSON** after the attorney review (`licensing.md`
  § Open): remove `dump.HELD_TABLES`, restore the Parties block, bump `JSON_SHAPE`, announce
  on `/data`. Money on `/contribute` is omitted by decision until the same review and the
  entity question.
