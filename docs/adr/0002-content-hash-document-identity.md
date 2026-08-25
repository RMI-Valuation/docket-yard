# ADR 0002 — Content-hash document identity

- **Status:** Proposed
- **Date:** 2026-08-25

## Context

STB serves documents from S3 URLs whose paths embed what appear to be timestamps, and the
agency has an "Errata/Correction" filing type — meaning documents get replaced. Keying on a
filing ID or a URL means a silently replaced document is invisible, and means no deduplication
across sources.

## Decision

Every document's primary identity is the **SHA-256 of its bytes**. STB filing IDs, decision
IDs, and source URLs are attributes of a document, never its key.

## Consequences

Silent replacement becomes detectable — a new hash under a known filing ID is an event worth
surfacing. Deduplication across sources is free. The cost is an indirection: humans think in
docket and filing numbers, so every lookup path needs a mapping.

## Cost of reversing

Expensive. Identity propagates into every derived table, every stored assertion, and every
permalink. Re-keying afterwards touches everything.

---

*Proposed, not accepted. Accept only after this decision has been checked against
[`../validation-queries.md`](../validation-queries.md).*
