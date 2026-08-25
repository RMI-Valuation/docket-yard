# What comparable platforms already solved

Research conducted 2026-08-25 against CourtListener/RECAP, the Federal Register, regulations.gov,
FERC eLibrary, SEC EDGAR, FCC ECFS, the paid litigation-analytics products, and the public-interest
data projects that survived or died. This is the evidence base under
[`../capability-map.md`](../capability-map.md).

Everything here is secondary research and should be re-verified before it drives a decision.

---

## Table stakes — present on every platform that worked

1. A stable, guessable, permanent URL per entity, and a page per entity that is server-rendered
   and indexable. SEO is the distribution channel for public-interest data.
2. Full-text search with real operators — phrase, boolean, proximity, date ranges — and fielded
   search. The platforms people hate have a search box that returns noise.
3. Faceted filters that mirror the actual data model.
4. **Saved search → email alert.** Universal.
5. **Subscribe-to-a-docket.** The atomic unit of value.
6. A free, documented, versioned REST API.
7. Bulk downloads on a published cadence, with a schema and an explicit licence.
8. **Published coverage and limitations documentation.** The most underrated trust mechanism.
9. Direct document access with no interstitial and no login.

## Rare, and disproportionately loved

- **Three distinct alert primitives, not one** (CourtListener): search alerts on any saved query,
  docket alerts on one case, and *citation alerts* — "tell me when this decision gets cited by
  anything new." Delivered by email **or webhook**; the webhook is what makes it infrastructure
  rather than a website.
- **A citation lookup tool.** Paste text, get every citation extracted, normalised, validated,
  and linked, with character offsets. Small tool, became infrastructure — including as a
  hallucination guardrail.
- **"Cited by" with counts over time**, plus a table of authorities on every decision.
- **Harvest summaries rather than generate them.** When one decision cites another it often
  explains it in a parenthetical. CourtListener extracts, clusters and ranks these — a million
  summaries written by the most credible possible authors. *STB decisions describe prior
  decisions the same way.*
- **Point-in-time views with diffs** (eCFR): any section as of any date, with removals and
  additions rendered inline. Rare and universally praised.
- **A "filed but not yet published" feed** (Federal Register's Public Inspection). The most
  time-sensitive queue in federal regulation.
- **Auto-detected portfolio monitoring** (Bloomberg): "we detect when your firm is counsel of
  record and surface those cases automatically." *The STB analogue is service lists, which the
  agency publishes and nobody uses.*
- **A citation-to-URL link service** (GovInfo): construct a permanent URL from a citation with no
  search step.
- **Crowdsourced acquisition with zero marginal effort** (RECAP's `@recap.email`): users add a
  personal address to their court notification settings and every notice they receive is silently
  archived. The best acquisition mechanism in public records.

## What failed, and why

| Thing | Fate | Lesson |
| --- | --- | --- |
| **Citation-network visualisation** (CourtListener, 2016–2025) | Deprecated — "has not gotten much traction among users" | **Build the graph, not the picture.** The graph is enormously valuable as search ranking, "cited by" lists, and negative-treatment flags. The force-directed diagram is a demo. |
| **Docket Wrench** (Sunlight) | Dead 2016 | Genuinely brilliant — clustered comments by textual similarity to expose form-letter campaigns. Died because its parent organisation died and nobody would keep 3TB fresh. |
| **Scout** (Sunlight) | Retired 2016 | Cross-corpus keyword alerts. **Alerts are cheap to launch and expensive to keep correct forever** — every upstream change breaks them silently. |
| **ProPublica Congress API, GovTrack bulk data** | Retired | Both dissolved when government shipped its own. **Don't be a shim.** |
| **regulations.gov bulk downloads** | Removed in the 2021 rebuild | A redesign optimised for casual users that broke every power user. **Never remove a bulk path.** |
| **Caselaw Access Project** | Interface shut down 2024 | Survived only because Harvard planned the handoff and gave 9M decisions to CourtListener. **Model succession.** |
| **Sunlight Foundation** | Closed 2020 | Single-source philanthropic funding, no earned revenue. |

**The pattern: nothing died because the data was wrong.** They died because the organisation ran
out of money, or because government finally shipped the thing itself.

## What people actually pay for

Ranked by observed willingness to pay:

1. **Outcome coding** — someone read the decision and recorded who prevailed, on what, with what
   remedy. Irreducibly expensive; the entire moat of legal analytics.
2. **Entity resolution and corporate hierarchy** — one canonical ID per party with every alias,
   subsidiary and successor. Sold as a standalone product.
3. **Typed classification of every docket entry** — the difference between "search these words"
   and "show me every petition to revoke."
4. **Latency** — real-time versus next-morning.
5. **Timing analytics** — median days to decision by proceeding type and decision-maker.
6. **Portfolio monitoring at scale.**

Items 3, 4 and 5 are computable from clean metadata and should be **free** here — they are cheap
and they are what makes a public resource beloved. Items 1 and 2 are the expensive parts, and
where a revenue line would live if one is ever needed.

## What sustains these projects

- **Sell latency and limits, never data.** CourtListener's membership buys real-time instead of
  daily, more alerts, and higher API rate limits. Every document stays free. The most
  transferable idea on this list.
- **Sell the labour, not the access.** ProPublica gives government data away and charges for
  cleaned, assembled datasets.
- **Commercial adoption of the open layer.** Open States was volunteer-run, then adopted by a
  company whose paid product sits on top of it; the API and bulk data stayed free.
- **AI-era data licensing.** Verified, authoritative corpora have become a scarce input.
- **Open-source the brittle layer** so outsiders maintain it. CourtListener open-sourced its
  scraper library, citation extractor, and reference databases.
- **Radical transparency** — published finances, published coverage gaps. Costs nothing, buys
  the credibility that funds the work.

## The specific opening for an STB platform

Verified during this research:

- **The Federal Register returns an empty `docket_ids` array on all 6,400+ STB documents.**
- **regulations.gov holds zero STB dockets and zero STB comments.** STB takes comments only
  through its own e-filing.
- **STB states its own system "is not yet configured to generate a single list that combines
  both filings and decisions for individual dockets."**
- There is no citator for STB-on-STB citations; the official reporter stopped at Volume 7 in 2004.
- No RSS, no docket subscription, no webhook, no bulk export.

Three federal systems hold one record with no shared key, and the agency has publicly said it
cannot produce a docket sheet. That is not a crowded field.

## Sources

CourtListener / Free Law Project: [help](https://www.courtlistener.com/help/) ·
[alerts](https://wiki.free.law/c/courtlistener/help/alerts) ·
[search operators](https://www.courtlistener.com/help/search-operators/) ·
[bulk data](https://wiki.free.law/c/courtlistener/help/api/bulk-data/bulk-legal-data) ·
[citation lookup](https://www.courtlistener.com/help/api/rest/citation-lookup/) ·
[visualisation deprecation](https://wiki.free.law/c/courtlistener/help/api/rest/v4/visualizations) ·
[parentheticals](https://free.law/2022/03/17/summarizing-important-cases/) ·
[@recap.email](https://free.law/2022/08/26/personal-recap-dot-email-addresses/) ·
[membership](https://free.law/membership/) · [open-source tools](https://free.law/open-source-tools/)

Federal agencies: [FR API](https://www.federalregister.gov/developers/documentation/api/v1) ·
[FR subscriptions](https://www.federalregister.gov/reader-aids/using-federalregister-gov/subscription-options-and-managing-your-subscriptions) ·
[eCFR point-in-time](https://www.ecfr.gov/reader-aids/using-ecfr/ecfr-changes-through-time) ·
[regulations.gov API](https://open.gsa.gov/api/regulationsgov/) ·
[FERC eLibrary FAQ](https://www.ferc.gov/elibrary-frequently-asked-questions-faqs) ·
[FERC eSubscription](https://www.ferc.gov/esubscription) ·
[EBA practitioner guide to eLibrary](https://www.eba-net.org/eba-ylc-blog-getting-the-most-out-of-fercs-elibrary/) ·
[EDGAR full-text search FAQ](https://www.sec.gov/edgar/search/efts-faq.html) ·
[FCC ECFS API](https://www.fcc.gov/ecfs/help/public_api) ·
[GovInfo Link Service](https://github.com/usgpo/link-service/)

Commercial and post-mortem: [Docket Alarm pricing](https://www.docketalarm.com/pricing) ·
[Bloomberg Law Dockets](https://pro.bloomberglaw.com/insights/company-news/new-bloomberg-law-dockets-features-deliver-faster-insights-and-broader-coverage/) ·
[UniCourt party data](https://datarade.ai/data-products/party-data-api-unicourt) ·
[Docket Wrench launch](https://sunlightfoundation.com/2013/01/31/docket-wrench-exposing-trends-regulatory-comments/) ·
[Sunlight closure](https://thefulcrum.us/governance-legislation/sunlight-foundation) ·
[CAP transition](https://lil.law.harvard.edu/blog/2024/03/26/transitions-for-the-caselaw-access-project/) ·
[ProPublica news-apps guide](https://github.com/propublica/guides/blob/master/news-apps.md) ·
[Open States](https://open.pluralpolicy.com/about/)
