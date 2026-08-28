# Roadmap

Forward-looking only, at milestone level. Detail lives in [`docs/`](docs/); what has shipped
lives in [`docs/milestones.md`](docs/milestones.md) — a milestone leaves this file the day it
lands. The menu it is chosen from is [`docs/capability-map.md`](docs/capability-map.md);
nothing moves from the menu to here without the operator's decision, recorded in the table
with its date. Hard line cap enforced by pre-commit: when it fires, prune.

**The wedge** (agency-wide docket sheets plus alerting, forward-only) **shipped 2026-08-26**
and is live at [docketyard.org](https://docketyard.org), unannounced. Since then: backfill
in dated waves, the party module, the statistics page, feeds and webhooks, bulk data and JSON — see
the milestones record, and the document viewer (2026-08-27). The Ripe list is the menu for what follows.

## Chosen

| # | Milestone | Done means | Chosen | Status |
| --- | --- | --- | --- | --- |
| — | Extraction benchmark (background) | Local LLM on RMI-AI-MACHINE vs API on a hand-labelled sample, before any extraction commits to local output; unblocks the citator | 2026-08-26 | Step 0 done; step 1 (60-decision labelled sample) awaits the operator's labels |
| — | Three held-metadata slices, chosen by delegation ("proceed with whatever you see fit", 2026-08-27) | The citation resolver (F2's second half: a docket or decision citation in any of the Board's printed forms resolves to its address with no search step); a court-action index (D4's first slice: the 491 `Notice Of Court Action` decisions by rulemaking, quoted); a protective-order register (D7's first slice: the 695 `Motion For Protective Order` filings on one page and marked on the sheet). No inference, no extraction — projections of held rows | 2026-08-27 | Landed v2026.08.36 (milestones) |

## Ripe — awaiting a decision

Candidates the record can support now, in the order recommended 2026-08-27 (reviewed against
the capability map with the whole record held). None is chosen.

1. ~~Docket-type explainers (P2)~~ — reviewed and published 2026-08-28 (milestones).
2. **The citation graph** — the first slice of the citator (C2): edges only (this decision
   cites that decision, docket or document) against the validated registry, shipped as "cited
   by" lists and search ranking; treatment classification lands later on the same edges.
   Wave 3 is done (19,829 decisions, 1996 →); gated on the labelled sample and the schema
   check in TODO § Next. The citation resolver (Chosen) is its front door.
3. **A machine-agent surface** (F7, proposed 2026-08-26) — read-only MCP over what exists
   plus the AI-crawler line in `robots.txt`; Low effort because F5, `/api` and `/llms.txt`
   shipped. On the menu, not chosen.
4. **Fielded search** (F4) — the one box shipped 2026-08-26 (captions, parties, summaries);
   fields, boolean and proximity wait for the extracted text.
5. **Rate-case index** (D5's first slice) — the 3,952 NOR dockets with parties and quoted
   spans; only 136 carry held filings, so thin until the ICC-era gap closes. The casebook
   proper (methodology, outcome) is human coding.

Measured not ripe 2026-08-27: trail-use (D1: no decision type names it; inside `Decision`
bodies, extraction), deadlines (C4), service metrics and reference data (D6/D3: other
sources), maps and geography (D2/C3: no geography rows yet), the public on-ramp (P1/P3–P5).

Later, each waiting for a decision rather than capacity: the geographic index (C3/D2), the
deadline engine (C4 — needs counsel's review before it ships; a hand-checked fixture of dated
obligations exists, see TODO § Next), reference data and rule status (D3/D4). The unfetched
documents (Chosen, running) improve the record gradually and defer none of these.
