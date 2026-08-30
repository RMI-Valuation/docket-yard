# The party-type sample — provenance and what the check measured

`labels.csv` is **checked ground truth**: 300 parties drawn 2026-08-30 (seed 20260826's
sibling, `sample.json`), drafted by `rule:party-type/2026-08-30`, and **judged by the
operator the same day — all 300, through the check queue** (the artifact the session
published; judgements applied from the operator's Copy-findings block). The `type` column
is the operator's; `draft_type` is what the rule said; the conventions the judging set —
a role is never a type, joined-pair names are span artefacts, carrier status and class
are quoted attributes — are recorded in `docs/party-types.md`.

## What the check measured

**The rule tier** (`rule:party-type/2026-08-30`), judged against the operator:

| draft | right | of | precision |
|---|---|---|---|
| span-artefact | 10 | 10 | 100% |
| individual | 35 | 40 | 87.5% |
| law-firm | 12 | 15 | 80% |
| association | 31 | 40 | 77.5% |
| company | 28 | 40 | 70% |
| government | 29 | 40 | 72.5% |
| railroad | 28 | 40 | 70% |
| unmatched | 0 | 75 | — (that is what unmatched means) |

No matched type clears a publishable bar as drafted. The confusions are systematic, not
noise: the unmatched tail is mostly **elected officials (28)** plus individuals (13) and
companies (11); `railroad` loses 8 to span artefacts (joined pairs the leading-`And` rule
cannot see); `association` loses 7 to the new `labor-union` row; `government` loses 4
each to `association` and the new `port` row; `company` loses 6 to `railroad`
(rail-named LLCs the company rule caught first).

**The Wikidata tier**: 67 of 250 organisations linked; of the 31 whose `instance of`
mapped to the vocabulary, **23 right, 8 wrong** (74%) — and the wrong ones are
instructive: both law firms mapped `company` (the P31 map lacks a law-firm value), two
utilities mapped `company`/`government` (same gap), and one individual it called
`individual` the operator knows as an elected official. (`State Of Georgia`, first
judged `railroad`, was the operator's slip — corrected to `government` the same day;
Wikidata had it right, one small point for the tier.) The link is evidence, not a
verdict.

**The judged distribution** (what 300 parties actually are): association 49, individual
48, company 44, railroad 38, government 37, elected-official 28, span-artefact 25,
law-firm 12, labor-union 7, port 4, utility 3, rail-holding 3, unknown 2.

**Span artefacts are 25 of 300** — 8% of the sample is not one party, and the operator's
SPLIT notes name the correct parties for the future re-split.

## Rules v2, measured the same day

`tools/party_types_rules.py` (`rule:party-type/2026-08-30b`) rewrites the tier from the
confusion table above: the `Honorable` prefix case-fixed, `Nth District` moved to
`elected-official`, a **two-sided join test** for the pair names (both halves must carry
an entity suffix, or `Delaware And Hudson Railway Company` — one railroad — would be torn
in half), `labor-union`/`port`/`utility` signals, `association` outranking `railroad` so a
*coalition on high speed rail* is not a carrier, and an organisation-word guard on the
person shape so `Farm Action` is not a person.

Agreement with the operator's sheet rises **57.7% → 82.3%**, and the per-type figures are
what a confidence stamp would be keyed on:

| judged type | recall | precision | reading |
|---|---|---|---|
| labor-union | 7/7 | 100% | publishable |
| port | 4/4 | 100% | publishable |
| government | 35/37 94.6% | 97.2% | publishable |
| elected-official | 24/28 85.7% | 100% | publishable |
| railroad | 31/38 81.6% | 83.8% | review or model |
| law-firm | 12/12 100% | 80% | review or model |
| association | 37/49 75.5% | ~90% | review or model |
| company | 30/44 68.2% | 81.1% | model tier |
| span-artefact | 16/25 64% | 100% | high precision, half the recall — the rest need the model |
| individual | 38/48 79.2% | 84.4% | model tier |
| utility | 2/3 | 33% of 6 | too few to read |
| rail-holding | 0/3 | — | unreachable by name, as designed |

**These figures are an upper bound, not a measurement.** The rules were written from this
sheet's confusion table and scored against the same 300 rows: that is tuning, and honest
tuning still overfits. What the numbers license is the *ordering* of the tiers and the
knowledge of which types need a model; before any type ships on rule confidence alone, a
**second sample the rules have never seen** must confirm it — the same discipline the
extraction benchmark applies to a prompt.

## What follows (recorded in TODO)

A second sample the rules have never seen, to turn the figures above into a measurement;
then the model tier for the types the rules cannot reach — `company`, `individual`,
`rail-holding`, and the half of the span artefacts a name cannot betray. Nothing ships
below the bar a *held-out* sheet sets per type.
