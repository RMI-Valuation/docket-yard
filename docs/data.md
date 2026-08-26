# Bulk data and JSON (M9, capability F5)

**Status:** published 2026-08-26 at `/data`. Licence **CC0 1.0** for the data (the operator's
decision, 2026-08-26); the code stays AGPL. This document is the spec the page is generated
from; `src/docketyard/store/dump.py` is what it describes.

## The snapshot

`docketyard dump` cuts `data/public/docketyard-latest.sqlite.gz` nightly (host timer
`docketyard-dump.timer`, 04:10 UTC): `VACUUM INTO` a consistent copy of the live store, drop
the five private tables — `subscription`, `subscription_token`, `alert`, `alert_event`,
`email_suppression` — **including their ciphertext** (nothing about a reader is published,
readable or not: ADR 0011, 0014), `VACUUM` again so no freed page carries a trace, gzip.
The scrub asserts no private table survived before the file is offered.

Alongside it: `schema.sql` (the live store's DDL), `LICENSE.txt` (CC0 text from
`docketyard/LICENSE-DATA.txt`), and `index.json` — the manifest, **measured from the files**
(sizes, SHA-256, counts read from the snapshot itself). The `/data` page renders the
manifest; it cannot list a file that is not there, and says so when none has been cut.

Retention: `latest` every night; the first snapshot of each month is kept as a dated
archive; other dated files are deleted. Files are served by the web app from `data/public`
at `/data/files/<name>`.

What the snapshot does not contain: the Board's PDFs (in S3 by content hash; each record
lists the Board's own URL), and anything about readers.

## JSON

The same permanent addresses (ADR 0013) with `.json` appended: `/d/FD-36873.json` (the
family sheet — `sheet.DocketSheet` serialised, plus `printed`, `url`, and a `url` per
entry), `/filing/<id>.json`, `/decision/<id>.json` (the entry plus its docket). Every
response carries `source`, `licence`, `licence_url`, `generated_at`, and
`Cache-Control: public, max-age=1800`. No keys, no accounts, no rate limits; the page asks
for a reasonable pace and a `User-Agent`.

Shapes are the dataclasses in `store/sheet.py`; a blank in the Board's record is `null`.
Changes are announced on `/data` and reflected in `schema.sql`'s `user_version`.

## Not built, deliberately

A query API (search, filters) — the snapshot answers every whole-record question and the
sheet JSON every per-docket one; anything more waits for a request. Documents in bulk —
150–250 GB once wave 3 lands; a public S3 prefix is the natural route when someone needs it.
