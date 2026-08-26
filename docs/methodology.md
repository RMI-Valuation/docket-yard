# Extraction and interpretation

> **Status: drafted 2026-08-26, awaiting operator sign-off.** The published page is `src/docketyard/web/templates/methodology.html`, served at `/methodology` and not yet linked from the footer. This file is the brief the page was written to; the page is the source.

## Purpose

The rules every derived fact is produced under — and the page a sceptical practitioner reads to decide whether to rely on the site.

## What this locks in

The accuracy contract, and the boundary between what is extracted and what is inferred.

## Skeleton

- **Tiering:** which document types are read in full, which get a short treatment, which are
  logged but never read.
- **Output schema** for every derived field, with worked examples.
- **What is never inferred.** A party's position comes from the document's own words. A
  procedural filing takes no position regardless of who filed it. Dates are quoted, never
  computed from context.
- **Model and prompt versioning**, so a stored assertion always names what produced it.
- **Known failure modes**, written honestly. This is the section that earns trust.
