# Roadmap

Forward-looking only, at milestone level. Detail lives in [`docs/`](docs/); what has shipped
lives in [`docs/milestones.md`](docs/milestones.md) — a milestone leaves this file the day it
lands. The menu it is chosen from is [`docs/capability-map.md`](docs/capability-map.md);
nothing moves from the menu to here without the operator's decision, recorded in the table
with its date. Hard line cap enforced by pre-commit: when it fires, prune.

**The wedge** (agency-wide docket sheets plus alerting, forward-only) **shipped 2026-08-26**
and is live at [docketyard.org](https://docketyard.org), unannounced. Since then: backfill
in dated waves, the party module, the statistics page, feeds and webhooks, bulk data and JSON — see
the milestones record. The document viewer is chosen (2026-08-27); the Ripe list is the menu for what follows.

## Chosen

| # | Milestone | Done means | Chosen | Status |
| --- | --- | --- | --- | --- |
| — | Backfill waves 2–3 (2020 → 2024-07, then 1996 → 2019) | Every month `done` or declared `empty` on the coverage page; documents in S3; extraction re-run per wave | 2026-08-26 | Tables and documents landed 2026-08-27 (77,565 documents); 41 `partial` months to re-walk, then extraction on RMI-AI-MACHINE (TODO § Now) |
| — | Extraction benchmark (background) | Local LLM on RMI-AI-MACHINE vs API on a hand-labelled sample, before any extraction commits to local output; unblocks the citator | 2026-08-26 | Step 0 done; step 1 (60-decision labelled sample) awaits the operator's labels |

## Ripe — awaiting a decision

Candidates the record can support now, in the order recommended 2026-08-26. None is chosen.

1. **Docket-type explainers** (P2) — writing, not engineering; the operator's.
2. **The citation graph** — the first slice of the citator (C2): edges only (this decision
   cites that decision, docket or document) against the validated registry, shipped as "cited
   by" lists and search ranking; treatment classification lands later on the same edges. The
   precondition moved 2026-08-26 (decisions 2,815 → 19,829, the record reaching 1996); still
   gated on wave 3, the labelled sample, and the schema check in TODO § Next.
3. **A machine-agent surface** (F7, proposed 2026-08-26) — read-only MCP over what exists;
   Low effort because F5 shipped. On the menu, not chosen.
4. **Fielded search** (F4) — the one box shipped 2026-08-26 (captions, parties, summaries);
   fields, boolean and proximity wait for the extracted text.

Later, each waiting for a decision rather than capacity: the geographic index (C3/D2), the
deadline engine (C4 — needs counsel's review before it ships; a hand-checked fixture of dated
obligations exists, see TODO § Next), reference data and rule status (D3/D4). The unfetched
documents (Chosen, running) improve the record gradually and defer none of these.
