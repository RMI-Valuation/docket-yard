# ADR 0013 — Permanent URLs

- **Status:** Accepted
- **Date:** 2026-08-25
- **Accepted:** 2026-08-25

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

## Validation (2026-08-25)

Checked against [`../validation-queries.md`](../validation-queries.md): addresses are built
only from the identity ADR 0005 keys on (prefix, sequence, sub, suffix) and the record ids
the source prints, so every query's join path is unchanged. Query 3's "the day before
Decision No. 30" resolves through `/decision/{id}` once the printed decision number is
extracted — an addition, not a re-keying. Implemented the same day in `web/urls.py`, which
delegates to the ingest parser so there is one definition of identity; the review of that
code caught a second grammar creeping in and it was removed.

## Addendum (2026-08-26): weeks

A fourth address class, decided by the operator: **`/week/{Monday}`** — a fixed Monday to
Sunday calendar week (ISO), addressed by the ISO date of its Monday, e.g. `/week/2026-08-17`.
Any day of the week resolves to its Monday with a 301; `/week` redirects to the most
recent complete week. The home page's "this week" stays a rolling seven days ending at the
latest activity and is not an address. A week the record does not yet cover exists at its
address and says so, filling in when a backfill wave reaches it. The permanence rules
above apply unchanged: a week address, once served, is never removed or repointed.

## Addendum (2026-08-26): the boundary of the promise

Decided by the operator: the promise covers addresses built from what the Board itself
identifies — dockets, filings, decisions — and calendar weeks, which are dates. It does
**not** extend to anything the pipeline derives: parties, places, labels, folds. Those are
reading aids reached by query, may be re-minted or re-resolved as methods improve, and are
never offered in a "cite this" box. A derived thing earns a permanent address only by a
further record here, never by being served once.

> **Note (2026-08-26):** the paragraph above is superseded for **parties** by
> [ADR 0015](0015-a-party-has-an-address.md), accepted the same day: a party's id is its
> permanent address (`/p/<id>`), never reused or renumbered, with 301 from any id folded
> into a same_as component to its representative. The boundary stands unchanged for
> places, labels and folds. This record is not edited; the note is appended (ADR 0001).
