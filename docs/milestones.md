# Milestones completed

The record of what has shipped, milestone by milestone. `ROADMAP.md` is forward-looking only;
when a milestone there is done, its row moves here with the date and release it landed in.
Append-only, newest last.

| # | Milestone | Done meant | Landed |
| --- | --- | --- | --- |
| M0 | Foundations | Repo public, tooling live, schema validated on paper against the five queries, ADRs 0001–0009 accepted | 2026-08-25 |
| M1 | Docket registry | Dockets table ingested (metadata only, no PDFs); filter application positively asserted; the registry validates extracted citations | 2026-08-25 — full registry walked on RMI-AI-MACHINE (32,604 dockets), now the production store |
| M2 | Filings + decisions ingest | Forward capture of the filings and decisions tables into the event ledger; documents hashed and stored; errata detection | 2026-08-26 in production (errata *re-check* built, unscheduled — TODO) |
| M3 | Docket sheets + permanent URLs | One chronological page per proceeding at a stable, guessable URL (ADR 0013) | 2026-08-26, v2026.08.2 — live at [docketyard.org](https://docketyard.org) on one Lightsail instance (ADR 0012), polling forward every 30 min, Litestream + blob sync to S3 |
| M4 | Alerting | Docket subscriptions, email delivery, silent-failure detection per `docs/alerts.md` | 2026-08-26, v2026.08.4–11 — confirmed-opt-in subscriptions (ADR 0011) with addresses ciphertext at rest (ADR 0014); per-pass and daily alerts over SES with bounce/complaint feedback; hourly off-box heartbeat on captures, events, documents and delivery. First real alert delivered 2026-08-26 |
| M5 | Launch | About, coverage, methodology, corrections and privacy pages published; **the wedge is live** | 2026-08-26, v2026.08.9–11 — coverage measured from the store; corrections are of this record against the Board's, seven days usual and not guaranteed; `hello@docketyard.org` routed. Unannounced |
| M6 | Party module (ADR 0004) | "Filed for" strings resolved to entities with aliases and successions, provenance on every link; a Parties view on every sheet; subscribe by party | 2026-08-26, v2026.08.14–15 — 1,097 parties and 3,989 links resolved in production; `/parties` is a facet, not an address (ADR 0013 addendum); service-list predicate deferred to extraction |
| M7 | Statistics page | What the record holds and what moves, every number measured (`docs/stats.md`); nothing about readers | 2026-08-26, v2026.08.17–19 — `/stats`, column charts drawn server-side from the same rows |
| M9 | Bulk data and JSON (rest of F5) | A nightly scrubbed snapshot with measured manifest, schema and licence at `/data`; JSON twins of every docket, sub-docket, filing and decision address | 2026-08-26, v2026.08.21–22 (PR #2) — CC0 for the raw index; the enriched party layer withheld pending the licence review in `docs/licensing.md`; the scrub is an allowlist that fails rather than publishes, and caught Litestream's bookkeeping tables on its first live run |
| M8 | Feeds and webhooks (rest of C1) | Atom feeds per docket, per party and agency-wide from the same events as the email alerts; signed webhooks carrying the same payload, confirmed like an address (migration 0008) | 2026-08-26, v2026.08.20 (PR #1) — reviewed by code, security and schema passes before merge; first ping delivered, signature verified, and confirmed against a throwaway endpoint the same day |
| M10 | Party pages (ADR 0015) | A permanent address per party at `/p/<id>` — names with provenance, joins, successions, dockets with captions; 301 from every folded id, slug and the old feed path; `docketyard parties join`/`unjoin` | 2026-08-26, v2026.08.24 (PR #3) — reviewed by code, security and schema passes; migration 0009 forbids deleting or renumbering a party; verified from outside on 10,110 parties (UP: 3,441 filings in 318 dockets, 54 ms). Shipped through a GitHub Actions outage: the PR's CI run was orphaned, CI on `main` confirmed the merge |

## Background work completed

| Work | Landed |
| --- | --- |
| Backfill wave 1 (2024-08 → watch start): 25 months, 4,864 documents; October 2025 declared empty (federal shutdown) | 2026-08-26 |
| Blob storage: S3 is the store, the instance a cache (prune after each 30-minute sync) — what lets wave 3's 150–250 GB pass through a 58 GB disk | 2026-08-26, v2026.08.16 |
| Extraction benchmark step 0: text layer for wave 1's files on RMI-AI-MACHINE — 4,273 PDFs, 2 image-only, 0 failed | 2026-08-26 |
| Streamed document downloads (v2026.08.25, PR #4): the record holds a 1.07 GB filing (FD 36500's merger application) that had the wave's documents step OOM-killed on the 2 GB instance; documents now stream to disk in 1 MB chunks and are hashed by chunks; the host's blob sync and prune leave the staging area alone | 2026-08-26 |
| `/contribute` (v2026.08.26, PR #5): ideas through an issue template, code through the repository under the CLA (pull requests held until its legal review), what helping does not get anyone; silent on money by the operator's decision | 2026-08-26 |
