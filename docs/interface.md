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

## Deliberately not a government look

No USWDS, no .gov aesthetics. "Unaffiliated with the STB" is a legal posture, and a federal
look-and-feel undermines it. The identity reads as *serious independent reference* —
financial-data and law-review sensibilities, built on typography and restraint.

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

## Where the craft goes

**The docket sheet is the product.** Caption and parties, the chronological entry table, the
service list, subscribe, cite-this — one page designed to excellence, with a visual grammar
distinguishing filings from decisions from our own derived annotations. Every other page
inherits its system.

Process: mock the sheet visually (realistic content — FD 36873) and iterate to approval
**before** any template is written. Queued in `TODO.md` against M3.
