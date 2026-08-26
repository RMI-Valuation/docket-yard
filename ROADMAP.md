# Roadmap

Forward-looking only, at milestone level. Detail lives in [`docs/`](docs/); what has shipped
lives in [`docs/milestones.md`](docs/milestones.md) — a milestone leaves this file the day it
lands. The menu it is chosen from is [`docs/capability-map.md`](docs/capability-map.md);
nothing moves from the menu to here without the operator's decision, recorded in the table
with its date. Hard line cap enforced by pre-commit: when it fires, prune.

**The wedge** (agency-wide docket sheets plus alerting, forward-only) **shipped 2026-08-26**
and is live at [docketyard.org](https://docketyard.org), unannounced. Since then: backfill
in dated waves, the party module, the statistics page — see the milestones record.

## Chosen

| # | Milestone | Done means | Chosen | Status |
| --- | --- | --- | --- | --- |
| — | Backfill waves 2–3 (2020 → 2024-07, then 1996 → 2019) | Every month `done` or declared `empty` on the coverage page; documents in S3; extraction re-run per wave | 2026-08-26 | Running unattended on the instance (TODO § Now) |
| — | Extraction benchmark (background) | Local LLM on RMI-AI-MACHINE vs API on a hand-labelled sample, before any extraction commits to local output; unblocks the citator | 2026-08-26 | Step 0 done; step 1 (60-decision labelled sample) awaits the operator's labels |

## Ripe — awaiting a decision

Candidates the record can support now, in the order recommended 2026-08-26. None is chosen.

1. **RSS and webhooks** (rest of C1) — per-docket and per-party feeds from the alert builder; a
   signed webhook of the same payload. The map's own sequence: "email first, RSS and webhooks
   immediately after."
2. **Bulk dumps and a minimal API** (rest of F5) — a nightly snapshot published with schema and
   licence; `/d/<docket>.json`. "Bulk access is a promise, not a feature."
3. **Docket-type explainers** (P2) — writing, not engineering; the operator's.
4. **The citator** (C2) — milestone-scale, on a branch; waits for wave 3 and the labelled sample.
5. **Fielded search** (F4) — meaningful once thirty years are in the store.

Later, each waiting for a decision rather than capacity: the geographic index (C3/D2), the
deadline engine (C4 — needs counsel's review before it ships), reference data and rule status
(D3/D4).
