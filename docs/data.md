# Bulk data and JSON (M9, capability F5)

**Status:** published 2026-08-26 at `/data`. Licence **CC0 1.0** for the **raw index** (the
operator's decision, 2026-08-26); the **enriched layer** — the party module today, the
citator later — is **withheld** from the snapshot and the JSON (`dump.HELD_TABLES`, the
Parties block stripped from the JSON, the envelope's `held` field saying so) until the
attorney review in `licensing.md` is done, because a dedication cannot be withdrawn. The
code stays AGPL. This document is the spec the page is generated
from; `src/docketyard/store/dump.py` is what it describes.

## The snapshot

`docketyard dump` cuts `<store dir>/public/docketyard-latest.sqlite.gz` nightly (host timer
`docketyard-dump.timer`, 04:10 UTC, no mail key or bucket credentials in its environment):
`VACUUM INTO` a consistent copy of the live store, drop the private tables
(`dump.PRIVATE_TABLES`) — **including their ciphertext** (nothing about a reader is
published, readable or not: ADR 0011, 0014), `VACUUM` again so no freed page carries a
trace, gzip. Two safeguards, reviewed 2026-08-26: the copy is built in `.dump-work`
beside the public directory, never inside it, so the unscrubbed file never has a URL;
and the scrub is an **allowlist** — every surviving table must be in `dump.PUBLIC_TABLES`
and no surviving column may look like a recipient, token or ciphertext, else the dump
fails rather than publishes. Operator rule that follows: free-text columns that do
survive (`correction.note`, `coverage_gap.note`) must never carry a person's address.

Alongside it: `schema.sql` (the snapshot's own DDL, with its `user_version`), `LICENSE.txt` (CC0 text from
`docketyard/LICENSE-DATA.txt`), and `index.json` — the manifest, **measured from the files**
(sizes, SHA-256, counts read from the snapshot itself). The `/data` page renders the
manifest; it cannot list a file that is not there, and says so when none has been cut.

Retention: `latest` every night; the first cut of each month is kept as a dated archive
(whichever day it runs — a missed first does not lose the month). Served files are
written atomically. Files are served by the web app from `<store dir>/public` at
`/data/files/<name>`.

What the snapshot does not contain: the Board's PDFs (in S3 by content hash; each record
lists the Board's own URL), and anything about readers.

## JSON

The same permanent addresses (ADR 0013) with `.json` appended, case-normalised by 301 as
the pages are: `/d/FD-36873.json` and `/d/FD-36873/sub/1.json` (the family sheet —
`sheet.DocketSheet` serialised, plus `printed`, `url`, a `url` per entry, and `requested`
when a sub-docket was asked for), `/filing/<id>.json`, `/decision/<id>.json` (the entry
plus its docket). Every response carries `source`, `licence`, `licence_url`,
`shape_version`, `generated_at`, and `Cache-Control: public, max-age=1800`. No keys, no
accounts, no rate limits; the page asks for a reasonable pace and a `User-Agent`.

Shapes are the dataclasses in `store/sheet.py`; a blank in the Board's record is `null`.
`web.app.JSON_SHAPE` is raised, and the change announced on `/data`, when a field changes
name or meaning; `tests/test_data.py` pins the key set so a rename cannot pass unnoticed.

## Not built, deliberately

The search index (`search_doc`, `search_fts`; migration 0010) — derived, rebuilt from the
record after every pass, and it carries party names, so it is dropped with the held layer;
`docketyard search rebuild` remakes it from a restored copy.

A query API (search, filters) — the snapshot answers every whole-record question and the
sheet JSON every per-docket one; anything more waits for a request. Documents in bulk —
150–250 GB once wave 3 lands; a public S3 prefix is the natural route when someone needs it.
