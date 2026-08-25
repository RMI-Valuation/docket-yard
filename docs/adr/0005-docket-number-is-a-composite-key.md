# ADR 0005 — Docket number is a composite key

- **Status:** Proposed
- **Date:** 2026-08-25

## Context

STB docket numbers decompose into prefix, sequence, sub-sequence, and suffix — the agency's own
search form exposes those four parts. FERC, the closest sibling agency, stores them opaquely,
and its own practitioner guidance warns that searching a sub-docket is "risky because you might
exclude the documents you're looking for."

## Decision

Store prefix, sequence, sub-sequence, and suffix as separate columns forming a composite key,
with explicit parent/child links between a docket and its sub-dockets. Never store
`"FD_36873_1"` as an opaque string.

## Consequences

Sub-docket traversal becomes reliable, which is table stakes for a docket sheet. Sorting and
filtering behave correctly. The cost is a parser that must handle every prefix and suffix STB
uses, including historical forms.

## Cost of reversing

Expensive. Reparsing and re-linking the entire corpus, and any permalink built on the opaque
form breaks.

---

*Proposed, not accepted. Accept only after this decision has been checked against
[`../validation-queries.md`](../validation-queries.md).*
