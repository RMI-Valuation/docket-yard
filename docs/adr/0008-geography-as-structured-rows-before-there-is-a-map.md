# ADR 0008 — Geography as structured rows before there is a map

- **Status:** Proposed
- **Date:** 2026-08-25

## Context

A geographic index — address to proceeding — is one of the four capabilities that would make
the site indispensable, and nothing in the federal government offers it. But if place mentions
live only inside summary prose, georeferencing later means re-reading the corpus.

## Decision

Every place mention is stored as a structured row — raw string, type, resolved coordinates,
confidence — **even when resolution is null**. Extraction records places long before anything
renders a map.

## Consequences

The map becomes a rendering problem rather than an extraction problem, and resolution quality
can improve independently. The cost is a table that carries no user-visible value for a long
time.

## Cost of reversing

Expensive. Re-reading every document to extract what could have been captured on the first
pass.

---

*Proposed, not accepted. Accept only after this decision has been checked against
[`../validation-queries.md`](../validation-queries.md).*
