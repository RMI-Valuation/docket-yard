# Roadmap

Forward-looking only, at milestone level. Detail lives in [`docs/`](docs/); what has shipped
lives in [`docs/milestones.md`](docs/milestones.md) — a milestone leaves this file the day it
lands. The menu it is chosen from is [`docs/capability-map.md`](docs/capability-map.md);
nothing moves from the menu to here without the operator's decision, recorded in the table
with its date. Hard line cap enforced by pre-commit: when it fires, prune.

**The wedge** (agency-wide docket sheets plus alerting, forward-only) **shipped 2026-08-26**
and is live at [docketyard.org](https://docketyard.org). It stayed unannounced by decision
(2026-09-10) until the operator presented it at the ARDA Technology Section's AI Spotlight
(2026-09-17); since then it travels by word of mouth, including inside a Class I railroad.
A broader announcement is still not an item anywhere. Since then, in
`docs/milestones.md`: backfill in dated waves, the party module, statistics, feeds and
webhooks, bulk data and JSON, the document viewer, the citation resolver and two registers,
docket-type explainers, the week naming the proceeding that moved, a series docket leading
with its index, captions for newly-opened proceedings, environmental comments (v2026.08.42–43,
the third record row, walked back to September 2000), the record's own text (Migration A,
v2026.09.2: 976,058 pages, one row per reading), the citator's finder and work-level step
(v2026.09.9–11), the derivation fleet on the operator's LAN (ADR 0025, 2026-09-09), and text for
new material read on the instance (ADR 0024, v2026.09.12–13), the finder's line wrap and the
Board's long docket forms (v2026.09.15, v2026.09.19: 22,547 citation edges in the store, none
shown), search built out (v2026.09.27), the machine surface for assistants (MCP, through
v2026.10.1), and decided dates quoted (v2026.10.3, held). The Ripe list is the menu for what
follows.

## Chosen

| # | Milestone | Done means | Chosen | Status |
| --- | --- | --- | --- | --- |
| — | Party types on `/parties` (F3's first slice) | Every party carries a typed classification (railroad, company, government, association, individual, law firm, …) as a derived assertion with ADR 0007 provenance and an ADR 0016 review path; `/parties` gains a browse by type (large types collapsed) beside the search, which stays | 2026-08-30 | Design done (`docs/party-types.md`); rules v2 at 83.3% on its own sheet. The unseen held-out sheet has been with the operator since 2026-09-10 (`docs/research/party-types/held-out/`); 95% per type on it gates the assertion migration (schema-critic first) |
| — | OCR of the image-only record (M3's first slice, `docs/ocr-plan.md`) | Ground truth the operator checks (90 pages, three tiers); candidates measured by CER/WER and by docket-number and date errors, API candidate included; a review layer (agreement → confidence, registry checks, a reviewer queue with identity from the start, ~50 pages a week); text published only above the measured threshold, with provenance | 2026-08-28 | Ground truth checked 2026-08-29; five engines scored; ADRs 0017–0023 accepted; Migration A shipped 2026-09-03 (v2026.09.2, 161,801 text-layer pages loaded 2026-09-04); the `dots` OCR wave read on the fleet (ADR 0025) and, with Paddle's `second` and `graphic` passes, loaded 2026-09-11 — 41,622 `dots` pages each with a band, 13,943 routed graphic. Since: the tabular pass reads through the fleet's broker, and the text-layer re-read is built; both wait on publishing rules that are the operator's (`TODO.md`). The review layer (Migration B) is owed |

## Ripe — awaiting a decision

Candidates the record can support now, in the order recommended 2026-08-27 (reviewed against
the capability map with the whole record held). None is chosen.

1. **The citation graph** — the first slice of the citator (C2): edges only (this decision
   cites that decision, docket or document) against the validated registry, shipped as "cited
   by" lists and search ranking; treatment classification lands later on the same edges.
   The schema (migration 0014), the finder, the resolver and the work-level step are
   shipped (v2026.08.51–v2026.09.19): 22,547 edges in the store, 428 exposed keys held for
   review. What is not built is the display — the "cited by" lists and ranking this slice
   would ship — and its review page waits on the citations brief (`TODO.md`). The citation resolver, shipped in
   v2026.08.36, is its front door.
2. **Fielded search** (F4) — search built out in v2026.09.27 (grouped by proceeding,
   filters by docket type, dates, kinds and the Board's types, paged); fields, boolean and
   proximity remain.
3. **Rate-case index** (D5's first slice) — the 3,952 NOR dockets with parties and quoted
   spans; only 136 carry held filings, so thin until the ICC-era gap closes. The casebook
   proper (methodology, outcome) is human coding.
5. **Places quoted from captions** (C3/D2's first slice, ADR 0008) — re-taken ripe 2026-09-10:
   3,730 of 30,184 held captions name a county, parish or borough, 52.1% of AB captions
   (3,158 of 6,056); a `place` row per mention with the caption as provenance, AB first, a
   checked sheet, an index from state to county to docket. Comment locations are never the
   proceeding's place. Also a line a docket summary (`docs/summaries.md`) could carry.

Measured not ripe 2026-08-27: trail-use (D1: no decision type names it; inside `Decision`
bodies, extraction — since specified as the typed acts of `docs/summaries.md`, 2026-09-10,
with 941 consummation notices and 714 trail-use filings available by rule), deadlines (C4), service metrics and reference data (D6/D3: other
sources), maps (D2: no geography rows yet; the caption slice is Ripe since 2026-09-10),
the public on-ramp (P1/P3–P5).

Later, each waiting for a decision rather than capacity: the map (D2), the
deadline engine (C4 — needs counsel's review before it ships; a hand-checked fixture of dated
obligations exists, see TODO § Next), reference data and rule status (D3/D4). The document
backlog drains on the poller's own schedule and defers none of these.
