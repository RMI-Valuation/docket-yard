
# Capability map

Twenty-nine capabilities for a public STB records platform, ranked by how much pain they remove
and how defensible they are. Evidence base: [`research/comparable-platforms.md`](research/comparable-platforms.md).

**This is a menu, not a roadmap.** Version one is scoped to a wedge — agency-wide docket sheets
plus alerting, forward-only. Everything else waits for users to ask.

"Exists nowhere" means no public source was found that assembles the capability, not that none
exists. Effort ratings are relative judgements, not estimates.

## Tier 0 — The spine

Nothing else works without these.

| | Capability | Effort | Status |
| --- | --- | --- | --- |
| `F1` | **The unified docket sheet** | Low | Exists nowhere |
| `F2` | **Permanent, guessable URLs** | Low | Addresses shipped (ADR 0013); the citation resolver chosen 2026-08-27 |
| `F3` | **A carrier and party registry** | High | Exists nowhere |
| `F4` | **Fielded search that respects sub-dockets** | Medium | Partial |
| `F5` | **Free API, bulk dumps, coverage page** | Medium | Shipped (M9, `/api` 2026-08-27) |
| `F6` | **The cross-agency join** | Medium | Exists nowhere |
| `F7` | **A machine-agent surface** | Low | Exists nowhere — built 2026-08-31 |

**F1 — The unified docket sheet.** One chronological view per proceeding, merging filings, decisions and environmental comments, with the service list and a computed next deadline. *STB says its own system cannot combine filings and decisions into a single list.*

**F2 — Permanent, guessable URLs.** A stable address for every docket, decision, filing and party, plus a link service resolving a citation with no search step. *GovInfo proved the pattern. It is what makes a site citable in a brief.*

**F3 — A carrier and party registry.** One stable identifier per party with aliases, reporting marks, corporate parents and merger successors — seeded from published service lists. *STB exposes no public stable carrier identifier. Commercial platforms sell exactly this.*

**F4 — Fielded search that respects sub-dockets.** Prefix/sequence/sub/suffix as a composite key with reliable parent-child traversal, plus boolean, phrase and proximity. *FERC's own guide warns that searching a sub-docket is risky. That is the failure to avoid.*

**F5 — Free API, bulk dumps, coverage page.** Documented REST API, quarterly snapshots with schema and licence, and an honest page describing what is missing. *Every durable platform has all three. The coverage page matters most.*

**F6 — The cross-agency join.** A shared key linking STB proceedings to Federal Register notices and regulations.gov documents. *Verified: FR returns empty docket IDs on 6,400+ STB documents; regulations.gov holds zero STB comments.*

**F7 — A machine-agent surface.** A read-only MCP server over the endpoints that already exist (search, suggest, docket, decision, filing, party), `/.well-known/mcp.json`, and an explicit crawler and AI-training policy in `robots.txt` and on `/data` in place of today's silence. The audience already puts regulatory questions to assistants, which answer from training data and invent docket numbers and dates; being the grounded source they reach instead is a distribution channel. *Measured 2026-08-26: `/openapi.json` 200 (37 paths); `/llms.txt`, `/api` and `/.well-known/mcp.json` 404; `robots.txt` says nothing about AI crawlers either way. Re-measured 2026-08-27: `/api` and `/llms.txt` answer (v2026.08.32); `/.well-known/mcp.json` and the robots line remain.* Effort is Low **because** F5 shipped — a wrapper over existing endpoints, not new retrieval. "Exists nowhere" means no grounded STB source for assistants was found, not that MCP servers over legal corpora are novel. Two constraints travel with it: the surface is **read-only** — no capability may write, subscribe or spend on a reader's behalf — and anything an assistant is handed carries the same provenance and coverage caveats a human page carries; an assistant quoting this record without its caveats is worse than no source. Proposed 2026-08-26; **chosen 2026-08-31** and built — `docs/machine-surface.md` records the protocol choices and the AI policy.

## Tier 1 — The four that make it indispensable

Each surfaced independently from constituencies sharing no interests.

| | Capability | Effort | Status |
| --- | --- | --- | --- |
| `C1` | **Alerting — docket, search and citation** | Medium | Exists nowhere |
| `C2` | **An STB and ICC citator** | High | Exists nowhere |
| `C3` | **Address-to-docket lookup** | Medium | Exists nowhere |
| `C4` | **The deadline engine** | Medium | Exists nowhere |

**C1 — Alerting — docket, search and citation.** Three subscriptions: everything new in this proceeding, anything matching this query, anything newly citing this decision. Email, RSS, webhook. *FERC's equivalent is the one feature its bar uses daily. STB has none of it.*

**C2 — An STB and ICC citator.** Extract every citation, validate against the docket registry, publish forward citations with counts, flag negative treatment. *No citator exists. The official reporter stopped at Volume 7 in 2004. The deepest moat available.* A 988-document hand-checked fixture exists (`upns-tracker-inheritance.md`).

**C3 — Address-to-docket lookup.** Enter an address, county or map point; get every proceeding touching that corridor, past and present. *Nothing in the federal government does place → proceeding. Rail geometry is free and unrestricted.*

**C4 — The deadline engine.** Enter a filing or publication date; get every downstream deadline under the correct procedural track, with traps surfaced. *Windows are unforgiving and track-dependent. Miss one and the right is gone.* The output shape and a quoted fixture are in `upns-tracker-inheritance.md`; dates are quoted, never computed.

## Tier 2 — Datasets nobody has assembled

Public, mandated or routinely published, never collected in one place.

| | Capability | Effort | Status |
| --- | --- | --- | --- |
| `D1` | **Trail-use and railbanking register** | Medium | Exists nowhere |
| `D2` | **System diagram maps, aggregated** | Medium | Exists nowhere |
| `D3` | **Reference-data time series** | Medium | Exists nowhere |
| `D4` | **Rule-status tracker** | Low | Exists nowhere — first slice (court-action index from 491 held notices) chosen 2026-08-27 |
| `D5` | **Rate-case casebook** | Low | Exists nowhere |
| `D6` | **Service-metrics warehouse** | Low | Partial |
| `D7` | **Confidentiality and designation tracking** | Low | Exists nowhere — first slice (695 held protective-order motions) chosen 2026-08-27 |

**D1 — Trail-use and railbanking register.** Every interim trail use certificate and notice: docket, railroad, mileposts, counties, issue date, extensions, expiration, outcome. *Notice issuance is the date of taking in Court of Federal Claims litigation. Dispositive, and only in scattered PDFs.*

**D2 — System diagram maps, aggregated.** Every carrier's mandated system map, geocoded nationally. Category 1 lines are those the railroad anticipates abandoning within three years. *A legally required, continuously updated, already-public national early-warning system for abandonment that nobody has assembled.*

**D3 — Reference-data time series.** Cost adjustment factors by quarter, cost of capital by year, revenue adequacy by carrier, annual report schedules, costing-system unit costs — dated, sourced, downloadable. *Every number a rate practitioner needs exists only as scattered PDFs and a legacy desktop binary.*

**D4 — Rule-status tracker.** One page per rulemaking: status, effective date, whether challenged, the court's outcome, whether vacated or withdrawn. *Much of what is written about current STB law is out of date.*

**D5 — Rate-case casebook.** Every rate case since 1996: docket, parties, commodity, methodology, outcome, duration, key evidentiary rulings. *Turns folklore into citable evidence.*

**D6 — Service-metrics warehouse.** Weekly carrier performance normalised into one time series, with anomaly alerting. *Published as one spreadsheet per carrier per week. The agency's portal carries no history or comparison.*

**D7 — Confidentiality and designation tracking.** Every document filed under seal, every protective order, every successful challenge to a designation — on the face of the docket. *Unions had to litigate to see employee-impact data. That precedent is only useful if someone indexes it.*

## Tier 3 — The public on-ramp

Mostly writing, not engineering. Highest ratio of value to cost.

| | Capability | Effort | Status |
| --- | --- | --- | --- |
| `P1` | **The jurisdiction router** | Low | Exists nowhere |
| `P2` | **Plain-language docket-type explainers** | Low | Exists nowhere |
| `P3` | **A participation toolkit** | Medium | Exists nowhere |
| `P4` | **A conditions-and-precedent library** | Medium | Exists nowhere |
| `P5` | **The newsroom kit** | Low | Exists nowhere |

**P1 — The jurisdiction router.** An honest page answering 'who actually handles this?' — blocked crossings, horn noise, crossing safety, derailments, hazmat. *A large share of people who reach the STB are at the wrong agency, and nothing tells them.*

**P2 — Plain-language docket-type explainers.** What each prefix and suffix means, what is being asked for, what the Board can and cannot do, what happens next. *The search form offers 33 prefixes and 20 suffixes and defines none of them.*

**P3 — A participation toolkit.** Model comments, protests and requests for conditions; machine-readable service lists; deadline math done for you. *Serving every party of record plus prescribed formatting is the practical bar that stops ordinary parties filing.*

**P4 — A conditions-and-precedent library.** Every condition the Board has imposed in past mergers and abandonments, tagged by problem. *The recurring question from a city attorney is 'what can we realistically ask for?'*

**P5 — The newsroom kit.** Per-docket press pages: what changed, affected counties, embeddable maps, links to primary documents. *A local reporter cannot currently answer 'does this merger touch my city?'*

## Tier 4 — Long moats

Years of work, and why a competitor never catches up.

| | Capability | Effort | Status |
| --- | --- | --- | --- |
| `M1` | **ICC-era finding aid, 1887–1995** | High | Exists nowhere |
| `M2` | **The valuation-map index** | High | Exists nowhere |
| `M3` | **OCR the pre-2000 record** | High | Exists nowhere |
| `M4` | **Recordation reconciliation** | High | Partial |
| `M5` | **Outcome coding** | High | Exists nowhere |

**M1 — ICC-era finding aid, 1887–1995.** Index the printed reports by docket, railroad and geography; deep-link existing scans; cross-walk predecessors to modern dockets. *The volumes are already digitised and free — reachable only if you know the citation. A metadata project, not a scanning project.*

**M2 — The valuation-map index.** Index and georeference the 1915–1920 federal valuation maps and land records, cross-walked to modern dockets and mileposts. *Includes parcel-level acquisition records with landowner names. A title, takings and genealogical resource at once.*

**M3 — OCR the pre-2000 record.** Make searchable the older decisions and filings the agency itself flags as not searchable, with per-document quality scoring. *Everything above degrades at the same boundary.*

**M4 — Recordation reconciliation.** A searchable equipment-lien index by mark, road number, grantor and secured party, with reporting-mark history and explicit warnings. *Federal law preempts state filing for rolling stock, so lenders must use a registry that is not a title registry.*

**M5 — Outcome coding.** For every contested proceeding: who prevailed, on which issues, with what remedy, and how long it took. *The most valuable thing commercial legal analytics sells, and the only item that cannot be automated cleanly.*

## What not to build

- **A citation-network visualisation.** CourtListener deprecated theirs in 2025 for lack of
  traction. Build the graph; ship it as "cited by" lists, search ranking and negative-treatment
  flags — never as a force-directed diagram.
- **A comment-submission system.** STB accepts filings only through its own e-filing. Help people
  produce a correct filing; do not try to become the filing channel.
- **Anything duplicating STB's Open Data Portal.** Consume its API as an input.
- **Anything that makes you a shim.** Build what a small agency structurally cannot: the citation
  graph, entity resolution across carriers and successors, cross-agency joins, historical
  backfill, analytics.
- **A redesign that removes a bulk path.** Bulk access is a promise, not a feature.

## Sequence

1. Ingest the dockets table alone — metadata only, no PDFs. Yields the validated docket registry
   that makes citation extraction trustworthy, plus the graph skeleton, before a single document
   is downloaded.
2. Docket sheets and permanent URLs.
3. Alerting — the reason people return daily. Email first, RSS and webhooks immediately after.
4. The geographic index.
5. The citator, starting at 1996 where the record is structured.
6. Reference data and rule status — a calendar reason to come back between proceedings.
