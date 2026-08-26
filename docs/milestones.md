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

## Background work completed

| Work | Landed |
| --- | --- |
| Backfill wave 1 (2024-08 → watch start): 25 months, 4,864 documents; October 2025 declared empty (federal shutdown) | 2026-08-26 |
| Blob storage: S3 is the store, the instance a cache (prune after each 30-minute sync) — what lets wave 3's 150–250 GB pass through a 58 GB disk | 2026-08-26, v2026.08.16 |
| Extraction benchmark step 0: text layer for wave 1's files on RMI-AI-MACHINE — 4,273 PDFs, 2 image-only, 0 failed | 2026-08-26 |
