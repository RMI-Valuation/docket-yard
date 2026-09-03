"""The record's own text — ADR 0021 (the grain) and ADR 0022 (where the bytes live).

Migration 0018 shipped the shape; the passes that fill it live here. `paginate` is the first:
one row per document in `document_pagination`, the denominator of the coverage arithmetic.
The page-grained loader for `document_text`, the search wiring and the page-text render are
the next pieces (`docs/ocr-migration.md` items 11, 13 and § Search).
"""
