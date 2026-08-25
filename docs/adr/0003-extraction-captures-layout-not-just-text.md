# ADR 0003 — Extraction captures layout, not just text

- **Status:** Accepted
- **Date:** 2026-08-25
- **Accepted:** 2026-08-25

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

## Validation (2026-08-25)

Checked against [`../validation-queries.md`](../validation-queries.md) via
[`../schema-draft.md`](../schema-draft.md). No query's join path stresses the IR directly, but
two of them depend on it existing: query 2's per-edge provenance and ADR 0007's
`source_location` both resolve to page/block/bbox, which only exist if captured at extraction
time. The queries also confirmed nothing forces the IR's cost early — it adds tables, not
constraints, and the wedge can ship reading only the text field.
