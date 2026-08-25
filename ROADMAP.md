# Roadmap

The plan for **version one — the wedge**: agency-wide docket sheets plus alerting,
forward-only. Milestone level only; detail lives in [`docs/`](docs/). Anything beyond the
wedge lives in [`docs/capability-map.md`](docs/capability-map.md), which is a menu, not a
roadmap. This file has a hard line cap enforced by pre-commit: when it fires, prune.

| # | Milestone | Done means | Status |
| --- | --- | --- | --- |
| M0 | Foundations | Repo public, tooling live, schema validated on paper, ADRs 0001–0009 accepted | **Done 2026-08-25** |
| M1 | Docket registry | Dockets table ingested forward (metadata only, no PDFs); filter application positively asserted; registry validates extracted citations | Not started |
| M2 | Filings + decisions ingest | Forward capture of filings/decisions tables into the event ledger; documents hashed and stored; errata detection live | Not started |
| M3 | Docket sheets + permanent URLs | One chronological page per proceeding at a stable, guessable URL | Not started |
| M4 | Alerting | Docket subscriptions, email delivery, silent-failure detection per `docs/alerts.md` | Not started |
| M5 | Launch | Coverage, corrections, about pages published; **the wedge is live** | Not started |

Sequencing rationale: [`docs/capability-map.md`](docs/capability-map.md) § Sequence.
M1 before anything touching documents — the validated registry is what makes every later
citation trustworthy.

## Not in version one

Historical backfill, the citator, the geographic index, the deadline engine, bulk API,
cross-agency joins. Real, later, and chosen deliberately — see the capability map for the
full menu and `docs/README.md` for what stays unwritten until it is needed.
