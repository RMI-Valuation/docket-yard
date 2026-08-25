# ADR 0002 — Content-hash document identity

- **Status:** Accepted
- **Date:** 2026-08-25
- **Accepted:** 2026-08-25

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

## Validation (2026-08-25)

Checked against [`../validation-queries.md`](../validation-queries.md) via the paper schema in
[`../schema-draft.md`](../schema-draft.md). The decision survived, and query 2 sharpened its
boundary: **the hash identifies bytes, and only bytes.** Filings and decisions are different
things and need their own identity — a filing can have zero attachments (measured), and
byte-identical boilerplate recurs across proceedings, so hanging party or docket facts on the
hash loses or cross-contaminates them. Work-level identity for a decision across errata comes
from a decision record plus a typed supersedes chain on document sources; a citator keyed on
single hashes returns half its edges the day an erratum lands.
