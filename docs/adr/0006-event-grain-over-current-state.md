# ADR 0006 — Event grain over current state

- **Status:** Proposed
- **Date:** 2026-08-25

## Context

Two of the five validation queries are unanswerable against a store that holds only current
state: point-in-time docket reconstruction, and trail-use notice lifecycles where extensions and
expirations are the product rather than metadata. History cannot be reconstructed after the
fact from a store that overwrote it.

## Decision

The store holds the **sequence of events** in a proceeding. Current-state views are derived
from that sequence, never the source of truth.

## Consequences

Point-in-time queries, diffs between versions, and lifecycle histories all become natural.
Corrections become events rather than overwrites. The cost is that every read path needs a
projection, and naive queries are slower.

## Cost of reversing

Impossible in practice. You cannot recover history that was never recorded.

---

*Proposed, not accepted. Accept only after this decision has been checked against
[`../validation-queries.md`](../validation-queries.md).*
