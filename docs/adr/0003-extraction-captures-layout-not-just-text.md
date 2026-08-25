# ADR 0003 — Extraction captures layout, not just text

- **Status:** Proposed
- **Date:** 2026-08-25

## Context

Raising extraction fidelity later means re-running OCR across an archive on the order of
100,000 documents. Bounding boxes and font metrics cost essentially nothing at extraction time
and are impossible to add without a full re-run. Claim-level provenance — showing a reader the
exact region of the exact page a statement came from — depends on them.

## Decision

The document IR stores, per page: text, blocks with bounding boxes, font size and weight,
rotation, whether the page had a text layer or was OCR'd, and per-block confidence. Capture
more than the current feature set needs.

## Consequences

Deep-linking a derived claim to its source region becomes possible, which is the difference
between a site practitioners trust and one they spot-check. Storage grows, and the IR schema is
more complex than plain text. Headings and captions become detectable without a model.

## Cost of reversing

The most expensive on the list. Re-running OCR over the full archive, plus re-deriving
everything downstream.

---

*Proposed, not accepted. Accept only after this decision has been checked against
[`../validation-queries.md`](../validation-queries.md).*
