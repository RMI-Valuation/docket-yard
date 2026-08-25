# ADR 0007 — Provenance on every derived assertion

- **Status:** Accepted
- **Date:** 2026-08-25
- **Accepted:** 2026-08-25

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

## Validation (2026-08-25)

Checked against [`../validation-queries.md`](../validation-queries.md) via
[`../schema-draft.md`](../schema-draft.md). Survived, and the queries extended it three ways:

- **Provenance has two source kinds.** An assertion extracted from an API table row has no
  source document — it has a capture. Source is document XOR capture; with only a document
  column, every table-derived assertion would have needed a migration.
- **Provenance without supersession is not enough.** Every assertion table needs a declared
  natural key and a superseded-by pointer, or the first higher-method-version re-extraction
  pass silently doubles every citation and every lifecycle date in the corpus. Selective
  re-runs remain a query; retirement becomes one too.
- **The rule reaches registries.** A geometry or a canonical-name choice is a derived
  assertion; parking it as a mutable registry column destroys the history this decision exists
  to keep. Human assertions are never overwritten by model re-runs — amending one takes a
  correction event with a typed target.
