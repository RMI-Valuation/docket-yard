# ADR 0006 — Event grain over current state

- **Status:** Accepted
- **Date:** 2026-08-25
- **Accepted:** 2026-08-25

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

## Validation (2026-08-25)

Checked against [`../validation-queries.md`](../validation-queries.md) via
[`../schema-draft.md`](../schema-draft.md). The strongest part of the design — queries 3 and 4
are unanswerable without it and natural with it. Three refinements the review demanded, all
needed from row one:

- **Two timestamps per event**: the date the source states (quoted, never computed) and the
  ingest time. "What did the record say by date X" and "what did we know by date X" are
  different questions; storing one forecloses the other permanently.
- **Corrections must be joinable, not prose**: a typed supersedes pointer on the event, plus a
  typed target row when a correction amends a derived assertion.
- **Payloads carry a schema version**, or the first parser change poisons every replay
  forever.

The review also confirmed where current-state thinking sneaks back in: registry columns
(names, geometry) that silently update. Registries hold identity only.
