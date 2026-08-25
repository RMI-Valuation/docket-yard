# ADR 0004 — Party is an entity, not a string

- **Status:** Proposed
- **Date:** 2026-08-25

## Context

Measured on the UP–NS docket: naive normalisation of 605 "Filed For" values collapsed them to
only 597 — name variants are not the problem within a proceeding. The real problem is that **91
of 605 cells are lists of parties**, not one party. Across thirty years the variant problem is
real too, because rail's merger history means the same railroad has many identities. STB exposes
no stable public carrier identifier.

## Decision

Parties are first-class entities with stable identifiers, aliases, reporting marks, corporate
parents, and successor edges. Documents relate to parties through join rows. **Multi-party
cells are split at ingest**, never stored as a single string.

## Consequences

Party pages, portfolio alerts, corporate succession, and entity resolution all become
possible, and resolution can improve forever without schema change. The cost is that ingest
must make a splitting judgement, and resolution is never finished.

## Cost of reversing

Expensive. Retrofitting means reprocessing every filing and rebuilding every relationship
derived from a party string.

---

*Proposed, not accepted. Accept only after this decision has been checked against
[`../validation-queries.md`](../validation-queries.md).*
