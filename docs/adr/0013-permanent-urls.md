# ADR 0013 — Permanent URLs

- **Status:** Proposed
- **Date:** 2026-08-25

## Context

A stable address for every docket, decision and filing is capability F2 and the reason a
site becomes citable in a brief (GovInfo proved the pattern). Once published, an address is
a promise for the life of the site: it can never be reused, repointed, or allowed to rot.
That makes the scheme a public promise and a one-way door. The identifiers the Board itself
prints — prefix, sequence, sub-number, suffix (ADR 0005), filing id, decision id — are the
only material the scheme may be built from, because anything else could change.

## Decision

- **Dockets:** `/d/{PREFIX}-{SEQUENCE}` for a parent, e.g. `/d/FD-36873`;
  `/d/{PREFIX}-{SEQUENCE}/sub/{SUB}` for a sub-docket, e.g. `/d/FD-36873/sub/1`. A suffix
  attaches to the level it belongs to: `/d/S5M-1-A` (suffix on a parent),
  `/d/AB-55/sub/785X` (suffix on a sub). Prefix and suffix are upper-case in the canonical
  address; any case resolves and redirects to canonical.
- **Records:** `/decision/{STB-DECISION-ID}` and `/filing/{STB-FILING-ID}`, e.g.
  `/decision/53210`, `/filing/311981` — the Board's own record ids, which its search form
  and links already expose.
- **Both parent spellings the source uses** (`FD_36873`, `FD_36873_0`) resolve to the one
  canonical address; the site never mints an address from a synthesised spelling.
- **Permanence rules:** an address, once served, is never reused for a different identity
  and never removed; a superseded record (an erratum, ADR 0002) keeps its address and
  points at its replacement; a corrected identity redirects with a 301 and keeps redirecting.
- **Cite-this** on every page emits exactly the canonical address, and the printed short
  form ("STB Finance Docket No. 36873") beside it.

## Consequences

Addresses are short, guessable and derivable by anyone who knows STB's numbering, so a
practitioner can type one without a search step. Routing needs the same parser the ingest
uses (`parse_docket_id`) — one definition of identity. The cost is the discipline: the URL
table is append-only forever, and a redesign that removes a path is forbidden by this record.

## Cost of reversing

Effectively impossible after launch. Every citation in a brief, every bookmark and every
inbound link is a promise this record made; changing the scheme means keeping the old one
alive forever anyway.

---

*Proposed, not accepted. Accept only after this decision has been checked against
[`../validation-queries.md`](../validation-queries.md).*
