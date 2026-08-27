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

## Document viewer (PR #10, 2026-08-27)

- **The web tier holds write-capable S3 keys.** The container already carried the bucket
  user's keys for SES; the viewer's store fetch now uses them for `GetObject`. A second key
  pair scoped to `s3:GetObject` on `blobs/*` for `web` (keep the read/write pair on `ingest`
  and `litestream`) keeps a write key out of the one internet-facing process. Cameron's
  (keys live in his password manager; nothing recreates them silently).
- **Sandbox the document response.** `Content-Security-Policy: sandbox; frame-ancestors
  'self'` on `/document/*` would put the PDF in an opaque origin (the pdf.js CVE-2024-4367
  class could not reach the site's origin). Not shipped because a `sandbox`ed PDF's
  rendering in Chrome's viewer must be checked in a browser first; the site sets no cookie
  and holds no per-user state, so the exposure today is small.
- **The sitemap advertises pruned documents.** A crawler walking every document address
  pulls every pruned file back from S3 (egress at ~$0.09/GB; the prune re-bounds the disk).
  Watch the `document` class on `docketyard traffic`; drop the section or add `crawl-delay`
  if it costs.
- **The S3 key layout** `blobs/aa/<sha>` is spelled in `web/documents.py`, `prune_blobs.py`
  and the sync unit; one `records.blob_key(sha)` when any of them next changes.

## Store and operations

- **Key rotation** for `DY_EMAIL_KEY` (decrypt under old, seal under new; four sealed columns
  across three tables since 0008) — unwritten; ADR 0014 records the gap.
- **Credentials**: Lightsail has no instance profile, so production runs on a bucket-scoped
  IAM user's keys; decide EC2 t4g / Roles Anywhere / accept (ADR 0012 gap).
- **Schema chore**: a poll item that is permanently bad for a reason other than a refused
  document (which rests a week from its capture, PR #10) still has no attempt counter.
- **Re-check bytes** (2026-08-27, v2026.08.35): the errata re-check downloads each held file
  whole (≤64 MB; ~1,900 a day, tens of GB per six-week cycle from the Board's bucket). S3
  honours `If-None-Match`; recording the response `ETag` on the fetch capture and sending
  it on re-check would make an unchanged file a 304. Larger files are the operator's
  `fetch attachments --refresh`, which has no age floor and no default limit.
- **ADR 0012 addendum** recording the blob cache design (S3 the store, the instance a cache;
  sync + prune) once wave 3 proves it.
- **Streamed downloads** (2026-08-26, v2026.08.25): no Range-resume on a mid-body failure;
  the file is written, hashed and sniffed in three passes rather than one; one commit per
  document is the dominant DB cost of a wave.
- **Enriched layer into the snapshot and JSON** after the attorney review (`licensing.md`
  § Open): remove `dump.HELD_TABLES`, restore the Parties block, bump `JSON_SHAPE`, announce
  on `/data`. Money on `/contribute` is omitted by decision until the same review and the
  entity question.
