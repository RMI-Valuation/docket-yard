# Roadmap

The plan for **version one — the wedge**: agency-wide docket sheets plus alerting,
forward-only. Milestone level only; detail lives in [`docs/`](docs/). Anything beyond the
wedge lives in [`docs/capability-map.md`](docs/capability-map.md), which is a menu, not a
roadmap. This file has a hard line cap enforced by pre-commit: when it fires, prune.

**The wedge shipped 2026-08-26** (v2026.08.11) and is live, unannounced. What comes next was
chosen from the capability map by the operator on 2026-08-26: see *After the wedge*.

| # | Milestone | Done means | Status |
| --- | --- | --- | --- |
| M0 | Foundations | Repo public, tooling live, schema validated on paper, ADRs 0001–0009 accepted | **Done 2026-08-25** |
| M1 | Docket registry | Dockets table ingested forward (metadata only, no PDFs); filter application positively asserted; registry validates extracted citations | **Done 2026-08-25** — full registry walked on rmi-ai-machine (32,604 dockets), now the production store |
| M2 | Filings + decisions ingest | Forward capture of filings/decisions tables into the event ledger; documents hashed and stored; errata detection live | **Done 2026-08-26** in production; errata *re-check* is built but unscheduled (TODO) |
| M3 | Docket sheets + permanent URLs | One chronological page per proceeding at a stable, guessable URL | **Done 2026-08-26** — live at [docketyard.org](https://docketyard.org), polling forward every 30 min, Litestream + blob sync to S3 |
| M4 | Alerting | Docket subscriptions, email delivery, silent-failure detection per `docs/alerts.md` | **Done 2026-08-26** — confirmed-opt-in subscriptions with addresses ciphertext at rest (ADR 0014), per-pass + daily alerts over SES with bounce/complaint feedback, hourly off-box heartbeat on captures / events / documents / delivery; first real subscription live, first alert awaited |
| M5 | Launch | Coverage, corrections, about pages published; **the wedge is live** | **Done 2026-08-26** — about, coverage (measured), methodology, corrections and privacy pages signed off and linked; `hello@docketyard.org` routed |

## After the wedge

| # | Milestone | Done means | Status |
| --- | --- | --- | --- |
| M6 | Party module (ADR 0004) | "Filed for" strings resolved to entities with aliases and successors, provenance on every link; a Parties view on the sheet; subscribe by party and by service-list membership (validation query 5) | **Done 2026-08-26** (v2026.08.14–15): parties, aliases and successions with provenance; Parties block + filter on every sheet; `/parties` browse view (a facet, not an address — ADR 0013 addendum); subscribe by party. Service-list predicate deferred to extraction |
| M7 | Statistics page | What the record holds and what moves, every number measured (`docs/stats.md`); nothing about readers | **Done 2026-08-26** — `/stats`, chosen by the operator |
| — | Extraction benchmark (background) | Local LLM on RMI-AI-MACHINE vs API on a hand-labelled sample, before any extraction commits to local output; unblocks the citator and the calendar | Not started |

Deliberately not yet: RSS/webhooks, the citator, the
geographic index. Each waits for a decision, not for capacity.

Sequencing rationale: [`docs/capability-map.md`](docs/capability-map.md) § Sequence.
M1 before anything touching documents — the validated registry is what makes every later
citation trustworthy.

## Not in version one

Historical backfill, the citator, the geographic index, the deadline engine, bulk API,
cross-agency joins. Real, later, and chosen deliberately — see the capability map for the
full menu and `docs/README.md` for what stays unwritten until it is needed.
