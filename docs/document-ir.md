# Document IR specification

> **Status: stub.** Write before any extraction code runs. Raising fidelity later means re-running OCR across the whole archive.

## Purpose

Exactly what the PDF-to-JSON layer captures, and the version stamps that make partial re-runs possible.

## What this locks in

Extraction fidelity — the most expensive thing on the project to change after the fact.

## Skeleton

- **Per page:** text, blocks with bounding boxes, font size and weight, rotation, whether the
  page carried a text layer or was OCR'd, per-block confidence.
- **Per document:** content hash, page count, source URL, retrieved-at, extractor name and
  version, OCR engine and version.
- **Storage layout:** content-addressed tree, gzipped JSON per document. The search index is
  derived and disposable — say so explicitly.
- **Versioning contract:** outputs are write-once keyed by `(content_hash, extractor_version)`.
  A partial re-run is a query, not a migration.
- **Known degradations:** scanned eras, low-confidence thresholds, page caps.
