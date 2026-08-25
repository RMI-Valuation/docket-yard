# Interface

Design direction for the web face, settled in discussion 2026-08-25, ahead of any frontend
code. The mistakes this document prevents: borrowing a federal look that undermines the
unaffiliated posture, drifting into an SPA, dropping the trust signals that are the actual
product, and framework churn on a site meant to last decades.

## The design problem

A **trust-and-density** product. The users — rail attorneys, valuation practitioners, city
attorneys, reporters — want density done well: scannable tables, precise dates, everything
one click from the primary source. Consumer-web instincts (whitespace, heroes, minimal
tables) are wrong here. The bar: CourtListener's functional credibility with the design
attention neither government nor nonprofit sites invest in.

## Deliberately not a government look — or a government voice

No USWDS, no .gov aesthetics. "Unaffiliated with the STB" is a legal posture, and a federal
look-and-feel undermines it. The identity reads as *serious independent reference* —
financial-data and law-review sensibilities, built on typography and restraint.

The same rule governs copy. Never "the public record of the Board" — that reads as the
Board's own site. Always *a* record of proceedings *before* the Board, and the lead of every
top-level page says in its own words that Docket Yard is independent and not affiliated,
not only the footer. (Caught on the home-page mockup, 2026-08-25.)

## Trust signals are the features

- **Claim-level deep links**: every derived assertion links to the exact region of the exact
  page it came from (ADR 0003's bounding boxes). No competitor has this.
- **Cite-this** on every permanent URL (ADR 0009 / capability F2).
- **Dates quoted, never computed**, and shown with their source.
- **A visible corrections trail** (ADR 0006: corrections are events, so they can render).
- **A print stylesheet good enough to attach to a brief.** Lawyers print; a sheet that
  prints beautifully gets cited.
- No marketing chrome, no third-party trackers, self-hosted fonts — a legal-research site
  must not leak its visitors' reading habits.

## Technical direction

- **HTML-first, server-rendered, progressively enhanced. No SPA.** Citable pages need real
  URLs and instant loads; SEO is the growth channel; accessibility (WCAG AA target) comes
  nearly free with semantic HTML and is expensive to retrofit; boring HTML still works in
  fifteen years.
- Interactivity (filtering a sheet's entries, subscribe flows) via small enhancements —
  htmx-class, never a frontend framework.
- **Hand-rolled modern CSS on design tokens**, no framework build chain — the
  stdlib-preferred ethos applied to the frontend. Tabular numerals so date and docket
  columns align. Dark mode via tokens. Mobile is real: reporters read on phones.

## One design, with preferences — not skins

Decided 2026-08-25 after the docket-sheet mockup. Alternate visual systems (a dense
"ledger", an editorial "broadsheet") were explored and retired: every trust feature would
have to be built and kept right per skin, and a reference site should be recognisable as
itself in a brief or a news story. What people wanted from those alternates ships as
**per-viewer preferences on the one design**: density (comfortable/compact — row padding and
how much of a decision summary shows), record IDs on/off (practitioners cite by filing ID),
and light/dark. Preferences live in the browser, never in an account (ADR 0011).

## Where the craft goes

**The docket sheet is the product.** Caption and parties, the chronological entry table, the
service list, subscribe, cite-this — one page designed to excellence, with a visual grammar
distinguishing filings from decisions from our own derived annotations. Every other page
inherits its system.

Process: mock the sheet visually (realistic content — FD 36873) and iterate to approval
**before** any template is written. Done 2026-08-25; working files in `design/docket-sheet/`.

## Surfaces beyond the sheet

Brief for what comes after M3, drawn from the project's ancestor — the single-docket UP–NS
merger tracker (`../up-ns-merger-tracker/dashboard.html`, read-only). The tracker is what
one docket looks like when a person builds a dashboard for it; Docket Yard makes that
available for every docket without a person per docket. Its surfaces generalise as follows,
each gated on the extraction it needs:

| Surface | What it is | Gated on | Rule to honour |
| --- | --- | --- | --- |
| **Docket calendar** (rail on the sheet, plus a "next deadline" callout at the top) | Dated deadlines *as set by Board and ALJ decisions*, each with the decision that set it | Decision-text extraction | Dates quoted from the decision, never computed; per-item source link. This is the honest, narrow form of the deadline engine (C4). Reserve the slot; leave it empty until the extraction ships — no filler |
| **Entry briefs** (expand a row) | Key points of a filing, and any deadlines it sets, as derived assertions | Extraction with ADR 0007 provenance | Labelled derived, with method, version, confidence, and a deep link to the passage (ADR 0003). Stronger than the tracker's because each claim can point at its page region |
| **Home — "what is moving"** | The tracker's record-to-date tiles, monthly sparkline and stage badge, generalised agency-wide: most active proceedings this week, decisions served, activity per docket | M1–M2 data (exists) | The homepage is a dashboard; the sheet is not. Keep tiles off the sheet |
| **Parties view** on the sheet | Who is on the record (entities, not strings) and, later, where they stand — the tracker's stance bar and party-type breakdown | Party module (ADR 0004); position extraction with provenance; a published methodology | Positions come from the document's own words; procedural filings take none (the tracker marks them n/a — keep that). An aggregate stance bar is a claim about what parties told a federal agency and ships only with its methodology page |
| **Significance tiers** (filter) | high / medium / routine | Extraction | Editorial judgement: publish the method, present as a filter, never as the record's own weighting |
| **Press releases + Federal Register** | The tracker joined these by hand for one docket | Capability F6 — the cross-agency join (the FR carries no docket key on 6,400+ STB documents) | Its own milestone, not a sheet feature |

Two tracker habits to copy everywhere: an "Updated `<timestamp>`" stamp on every surface, and
a per-item source link on every derived card. One tracker choice not copied: the single-file
data-embedded build — server-rendered pages get the same cacheability from the agency moving
only ~250 times a month.
