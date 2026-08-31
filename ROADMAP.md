# Roadmap

Forward-looking only, at milestone level. Detail lives in [`docs/`](docs/); what has shipped
lives in [`docs/milestones.md`](docs/milestones.md) — a milestone leaves this file the day it
lands. The menu it is chosen from is [`docs/capability-map.md`](docs/capability-map.md);
nothing moves from the menu to here without the operator's decision, recorded in the table
with its date. Hard line cap enforced by pre-commit: when it fires, prune.

**The wedge** (agency-wide docket sheets plus alerting, forward-only) **shipped 2026-08-26**
and is live at [docketyard.org](https://docketyard.org), unannounced. Since then, in
`docs/milestones.md`: backfill in dated waves, the party module, statistics, feeds and
webhooks, bulk data and JSON, the document viewer, the citation resolver and two registers,
docket-type explainers, and — v2026.08.40–41 — the week naming the proceeding that moved,
a series docket leading with its index, and captions for newly-opened proceedings. The Ripe
list is the menu for what follows.

## Chosen

| # | Milestone | Done means | Chosen | Status |
| --- | --- | --- | --- | --- |
| — | Environmental comments (F1's missing third) | The record captures the Board's environmental-comment table: a typed record with the commenter's own words, submitter, organisation, attachment and location, on the docket sheet beside filings and decisions, walked back over the record and watched forward | 2026-08-31 | **Merged to `main` 2026-08-31** (#11), through five reviews. **Not deployed**: production is v2026.08.41 at schema 10, and this release applies 0011–0012 — see the two deploy notes in `infra/deploy/README.md`. Then the archive wave |
| — | Party types on `/parties` (F3's first slice) | Every party carries a typed classification (railroad, company, government, association, individual, law firm, …) as a derived assertion with ADR 0007 provenance and an ADR 0016 review path; `/parties` gains a browse by type (large types collapsed) beside the search, which stays | 2026-08-30 | Design: vocabulary and method tiers from the measured corpus; schema-critic before the assertion table exists |
| — | OCR of the image-only record (M3's first slice, `docs/ocr-plan.md`) | Ground truth the operator checks (90 pages, three tiers); candidates measured by CER/WER and by docket-number and date errors, API candidate included; a review layer (agreement → confidence, registry checks, a reviewer queue with identity from the start, ~50 pages a week); text published only above the measured threshold, with provenance | 2026-08-28 | Ground truth checked 2026-08-29; five engines scored. Waiting on ADR 0017, which decides what ships |
| — | Extraction benchmark (background) | Local LLM on RMI-AI-MACHINE vs API on a hand-labelled sample, before any extraction commits to local output; unblocks the citator | 2026-08-26 | **Complete 2026-08-31**: nine local candidates and two role classifiers scored against the operator-checked sheet. Step 3 is ADR 0017, Proposed, awaiting acceptance |

## Ripe — awaiting a decision

Candidates the record can support now, in the order recommended 2026-08-27 (reviewed against
the capability map with the whole record held). None is chosen.

1. **The citation graph** — the first slice of the citator (C2): edges only (this decision
   cites that decision, docket or document) against the validated registry, shipped as "cited
   by" lists and search ranking; treatment classification lands later on the same edges.
   Wave 3 is done (19,829 decisions, 1996 →); gated on the labelled sample and the schema
   check in TODO § Next. The citation resolver (Chosen) is its front door.
2. **A machine-agent surface** (F7, proposed 2026-08-26) — read-only MCP over what exists
   plus the AI-crawler line in `robots.txt`; Low effort because F5, `/api` and `/llms.txt`
   shipped. On the menu, not chosen.
3. **Fielded search** (F4) — the one box shipped 2026-08-26 (captions, parties, summaries);
   fields, boolean and proximity wait for the extracted text.
4. **Rate-case index** (D5's first slice) — the 3,952 NOR dockets with parties and quoted
   spans; only 136 carry held filings, so thin until the ICC-era gap closes. The casebook
   proper (methodology, outcome) is human coding.

Measured not ripe 2026-08-27: trail-use (D1: no decision type names it; inside `Decision`
bodies, extraction), deadlines (C4), service metrics and reference data (D6/D3: other
sources), maps and geography (D2/C3: no geography rows yet), the public on-ramp (P1/P3–P5).

Later, each waiting for a decision rather than capacity: the geographic index (C3/D2), the
deadline engine (C4 — needs counsel's review before it ships; a hand-checked fixture of dated
obligations exists, see TODO § Next), reference data and rule status (D3/D4). The unfetched
documents (Chosen, running) improve the record gradually and defer none of these.
