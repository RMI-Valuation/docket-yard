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
docket-type explainers, the week naming the proceeding that moved, a series docket leading
with its index, captions for newly-opened proceedings, and — v2026.08.42–43 —
environmental comments, the third record row F1 always named, walked back to the
record's start in September 2000. The Ripe list is the menu for what follows.

## Chosen

| # | Milestone | Done means | Chosen | Status |
| --- | --- | --- | --- | --- |
| — | Party types on `/parties` (F3's first slice) | Every party carries a typed classification (railroad, company, government, association, individual, law firm, …) as a derived assertion with ADR 0007 provenance and an ADR 0016 review path; `/parties` gains a browse by type (large types collapsed) beside the search, which stays | 2026-08-30 | Design: vocabulary and method tiers from the measured corpus; schema-critic before the assertion table exists |
| — | OCR of the image-only record (M3's first slice, `docs/ocr-plan.md`) | Ground truth the operator checks (90 pages, three tiers); candidates measured by CER/WER and by docket-number and date errors, API candidate included; a review layer (agreement → confidence, registry checks, a reviewer queue with identity from the start, ~50 pages a week); text published only above the measured threshold, with provenance | 2026-08-28 | Ground truth checked 2026-08-29; five engines scored. Waiting on ADR 0017, which decides what ships |

## Ripe — awaiting a decision

Candidates the record can support now, in the order recommended 2026-08-27 (reviewed against
the capability map with the whole record held). None is chosen.

1. **The citation graph** — the first slice of the citator (C2): edges only (this decision
   cites that decision, docket or document) against the validated registry, shipped as "cited
   by" lists and search ranking; treatment classification lands later on the same edges.
   Wave 3 is done (19,829 decisions, 1996 →); gated on the labelled sample and the schema
   check in TODO § Next. The citation resolver, shipped in v2026.08.36, is its front door.
2. **Fielded search** (F4) — the one box shipped 2026-08-26 (captions, parties, summaries);
   fields, boolean and proximity wait for the extracted text.
3. **Rate-case index** (D5's first slice) — the 3,952 NOR dockets with parties and quoted
   spans; only 136 carry held filings, so thin until the ICC-era gap closes. The casebook
   proper (methodology, outcome) is human coding.

Measured not ripe 2026-08-27: trail-use (D1: no decision type names it; inside `Decision`
bodies, extraction), deadlines (C4), service metrics and reference data (D6/D3: other
sources), maps and geography (D2/C3: no geography rows yet), the public on-ramp (P1/P3–P5).
**The geography verdict is stale and not yet re-taken**: it predates the comment wave, and
3,730 held captions name a county. What re-taking it must not do is count the 11,821 comment
locations as the proceeding's geography — a commenter's location is where the commenter is,
often nowhere near the line (the operator, 2026-09-01).

Later, each waiting for a decision rather than capacity: the geographic index (C3/D2), the
deadline engine (C4 — needs counsel's review before it ships; a hand-checked fixture of dated
obligations exists, see TODO § Next), reference data and rule status (D3/D4). The document
backlog drains on the poller's own schedule and defers none of these.
