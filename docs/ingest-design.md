# Ingest design — M1: the docket registry

Module layout and rules for the pipeline's first slice, designed before the code exists.
The mistakes this document prevents: copying the sibling project's docket-scoped client
instead of building against this schema, parsing before persisting the raw, and shipping a
request path without the positive filter assertion.

## The M1 slice

Ingest **the dockets table only** — metadata, no PDFs (capability sequence step 1). This
yields the validated docket registry that makes later citation extraction trustworthy, and
exercises the whole spine (capture → event → registry → projection) on the smallest table.
Forward-only; backfill waves come later and are already forced into date-slices by the
10,000 display cap.

## Module layout

```text
src/docketyard/
  capture/
    stb.py          # nonce scrape, request builder (criteria array form), rate limiting
    records.py      # capture rows: params, response hash, filter_asserted, ingest_mode
  store/
    schema.sql      # DDL, hardened from docs/schema-draft.md as code meets it
    db.py           # SQLite connection, WAL, migration runner (monotonic, ADR 0010)
    events.py       # append-only ledger writes; every event references its capture
    projections.py  # current-state views derived from events, rebuildable
  ingest/
    dockets.py      # dockets-table rows -> docket registry + docket_observed events
  cli.py            # entry points: capture | ingest | status
```

Standard library throughout — `urllib` for HTTP, `sqlite3` for the store. A dependency
enters only when it earns its place, and M1 needs none.

## Rules the code is built around

1. **Capture-first.** Persist the raw response (a `capture` row + body blob) *before*
   parsing. A parse failure must never lose the raw. Events reference their capture.
2. **Positive filter assertion.** The endpoint's failure mode is a 200 with a full
   unfiltered result set. After every filtered request, assert from the response content
   that the filter applied; record the verdict in `capture.filter_asserted`. An unasserted
   capture is quarantined, not ingested.
3. **Zero rows is a signal.** The wrong date-field pair returns zero rows with no error. A
   zero-row response for a slice expected to have activity fails loudly.
4. **Idempotent by construction.** Docket identity is the composite key with
   `NULLS NOT DISTINCT`; re-running a capture or ingest step must change nothing the second
   time. Retries are safe because writes are keyed, never appended blindly — except the
   event ledger, where dedup is by (capture, source row).
5. **Politeness.** Rate-limited, identifying User-Agent with contact address, backoff on
   errors. Never a headless browser.
6. **The sibling is reference, not source.** `../up-ns-merger-tracker/tracker/stb_client.py`
   may be read for endpoint behaviour; no code is copied — it is docket-scoped and has no
   entity model.
7. **Multi-page walks need a measured sort.** Pages are currently fetched with the default
   ordering, which is unverified for stability; an unstably-ordered result set can silently
   *omit* rows across page boundaries (dedup absorbs duplicates, not omissions). Before the
   registry walk campaign, measure which `sort_by` the dockets table honours and pin it.

## Testing

Recorded captures are the fixtures — the capture layer gives cassettes for free. The
regression suite must include, from day one: an unfiltered-response detection test (criteria
sent as plain fields), a wrong-date-pair test (zero rows flagged), a cap-hit slice test, and
a duplicate-run idempotence test. `stb-ingest-specialist` reviews every ingest change
against the ten traps before commit (see `CLAUDE.md` § Review before commit).
