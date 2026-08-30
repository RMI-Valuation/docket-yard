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
| government | 28 | 40 | 70% |
| railroad | 28 | 40 | 70% |
| unmatched | 0 | 75 | — (that is what unmatched means) |

No matched type clears a publishable bar as drafted. The confusions are systematic, not
noise: the unmatched tail is mostly **elected officials (28)** plus individuals (13) and
companies (11); `railroad` loses 8 to span artefacts (joined pairs the leading-`And` rule
cannot see); `association` loses 7 to the new `labor-union` row; `government` loses 4
each to `association` and the new `port` row; `company` loses 6 to `railroad`
(rail-named LLCs the company rule caught first).

**The Wikidata tier**: 67 of 250 organisations linked; of the 31 whose `instance of`
mapped to the vocabulary, **22 right, 9 wrong** (71%) — and the wrong ones are
instructive: both law firms mapped `company` (the P31 map lacks a law-firm value), two
utilities mapped `company`/`government` (same gap), `State Of Georgia` mapped
`government` where the operator judged the party `railroad`, and one individual it
called `individual` the operator knows as an elected official. The link is evidence, not
a verdict.

**The judged distribution** (what 300 parties actually are): association 49, individual
48, company 44, railroad 39, government 36, elected-official 28, span-artefact 25,
law-firm 12, labor-union 7, port 4, utility 3, rail-holding 3, unknown 2.

**Span artefacts are 25 of 300** — 8% of the sample is not one party, and the operator's
SPLIT notes name the correct parties for the future re-split.

## What follows (recorded in TODO)

Rules v2 from the confusions (elected-official patterns, the joined-pair span rule,
labor-union/port/utility signals, rail-named-LLC ordering); then the model tier measured
against this sheet; nothing ships below the bar this sheet sets per type.
