# ADR 0008 — Geography as structured rows before there is a map

- **Status:** Accepted
- **Date:** 2026-08-25
- **Accepted:** 2026-08-25

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

## Validation (2026-08-25)

Checked against [`../validation-queries.md`](../validation-queries.md) via
[`../schema-draft.md`](../schema-draft.md). Query 1 is expressible from day one on this
decision's rows — geometry intersection or milepost-range overlap, with answer quality scaling
as extraction coverage grows rather than requiring a re-read of the corpus. One correction
from the review: **resolved geometry is itself a derived assertion** and carries the full
provenance block in its own table, rather than sitting in the place registry as a
silently-updated column. Milepost ranges need structured fields (line reference, from, to)
beside the raw string, since range overlap cannot be computed from prose.
