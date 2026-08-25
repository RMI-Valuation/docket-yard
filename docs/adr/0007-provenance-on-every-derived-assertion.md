# ADR 0007 — Provenance on every derived assertion

- **Status:** Proposed
- **Date:** 2026-08-25

## Context

A public site publishing derived claims about what parties told a federal agency must be able
to correct at scale, and a correction has to reach every page displaying the affected data.
Selective re-extraction with a better model must not silently overwrite human corrections.

## Decision

Every extracted fact and every graph edge carries: source document, location within it,
extraction method, method version, timestamp, and confidence.

## Consequences

Corrections propagate. Partial re-runs become a query — `WHERE extractor_version < N` — rather
than a migration. Claim-level citation becomes possible. The cost is that provenance is roughly
as large as the assertions themselves.

## Cost of reversing

Expensive. Everything derived without provenance has to be discarded and regenerated.

---

*Proposed, not accepted. Accept only after this decision has been checked against
[`../validation-queries.md`](../validation-queries.md).*
