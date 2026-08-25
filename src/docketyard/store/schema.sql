-- Migration 0001: the M1 slice of docs/schema-draft.md — captures, the docket registry,
-- and the event ledger. Hardened here as code meets it; the draft remains the paper model.
-- The whole migration, INCLUDING its user_version stamp, runs in one transaction so an
-- interruption leaves a cleanly un-migrated database, never a half-migrated one.

BEGIN TRANSACTION;

CREATE TABLE capture (
    capture_id      INTEGER PRIMARY KEY,
    source_system   TEXT NOT NULL,
    endpoint        TEXT NOT NULL,
    request_params  TEXT NOT NULL,              -- JSON, criteria pairs exactly as sent
    response_sha256 TEXT NOT NULL,              -- body itself lives in blob storage
    http_status     INTEGER NOT NULL,
    row_count       INTEGER,                    -- rows actually parsed
    reported_total  INTEGER,                    -- the endpoint's total; >= 10000 = cap hit,
                                                -- the slice is INCOMPLETE, not invalid
    filter_asserted INTEGER NOT NULL CHECK (filter_asserted IN (0, 1)),
    ingest_mode     TEXT NOT NULL CHECK (ingest_mode IN ('forward', 'backfill')),
    captured_at     TEXT NOT NULL,              -- ISO-8601 UTC
    processed_at    TEXT                        -- set when ingest has consumed this capture
);

CREATE TABLE docket (
    docket_id        INTEGER PRIMARY KEY,
    raw_docket       TEXT NOT NULL,             -- as the source printed it; a parent minted
                                                -- from a sub-docket before being seen keeps a
                                                -- synthesised spelling ONLY until directly
                                                -- observed (see ingest/dockets.py)
    prefix           TEXT NOT NULL,
    sequence         INTEGER NOT NULL,
    sub_sequence     INTEGER,                   -- NULL = the parent docket
    suffix           TEXT,                      -- normalised upper; raw keeps original case
    parent_docket_id INTEGER REFERENCES docket (docket_id)
);

-- SQLite has no UNIQUE NULLS NOT DISTINCT; this expression index enforces the same identity
-- (docs/adr/0005 validation note: without it, retried ingest mints duplicate dockets).
CREATE UNIQUE INDEX docket_identity
    ON docket (prefix, sequence, COALESCE(sub_sequence, -1), COALESCE(suffix, ''));

CREATE TABLE event (
    event_id            INTEGER PRIMARY KEY,
    event_type          TEXT NOT NULL,          -- docket_observed | docket_inferred | ...
    docket_id           INTEGER REFERENCES docket (docket_id),
    document_sha256     TEXT,                   -- no document table yet; M2 hardens this
    occurred_at         TEXT,                   -- date quoted from the source, never computed
    recorded_at         TEXT NOT NULL,          -- when ingest observed it
    -- null ONLY for human-entered correction events (docs/schema-draft.md § events)
    capture_id          INTEGER REFERENCES capture (capture_id)
                        CHECK (capture_id IS NOT NULL OR event_type = 'correction'),
    supersedes_event_id INTEGER REFERENCES event (event_id),
    -- NOT NULL because SQLite UNIQUE treats NULLs as distinct: a null source_key would
    -- silently void the dedup index below
    source_key          TEXT NOT NULL,
    payload             TEXT NOT NULL,          -- JSON
    payload_version     INTEGER NOT NULL
);

CREATE INDEX event_by_docket ON event (docket_id, event_type, event_id);
CREATE UNIQUE INDEX event_dedup ON event (capture_id, event_type, source_key);

-- Projection: current docket sheet attributes = the latest observation. Derived, rebuildable.
-- tests/test_store_and_ingest.py pins this view's answer to events.latest_payload so the two
-- definitions of "latest" cannot drift apart.
CREATE VIEW docket_current AS
SELECT d.docket_id, d.raw_docket, d.prefix, d.sequence, d.sub_sequence, d.suffix,
       d.parent_docket_id,
       (SELECT e.payload
          FROM event e
         WHERE e.docket_id = d.docket_id AND e.event_type = 'docket_observed'
         ORDER BY e.event_id DESC
         LIMIT 1) AS latest_payload
  FROM docket d;

PRAGMA user_version = 1;

COMMIT;
