-- Migration 0002: filings, decisions, documents, attachments — the M2 slice.
-- Filing/decision columns mirror the LATEST observation for cheap reads; history lives in
-- the event ledger and every row points at the event that last shaped it.

BEGIN TRANSACTION;

-- which table (or fetch kind) a capture came from, so ingest picks the right parser.
-- Every capture that exists before this migration came from the dockets table (the only
-- capture path in migration 0001), so they are labelled rather than orphaned.
ALTER TABLE capture ADD COLUMN table_action TEXT NOT NULL DEFAULT '';
UPDATE capture SET table_action = 'stb_hook_table_dockets' WHERE table_action = '';

CREATE TABLE document (
    document_sha256 TEXT PRIMARY KEY,           -- SHA-256 of the bytes; THE identity (ADR 0002)
    size_bytes      INTEGER NOT NULL,
    media_type      TEXT,                       -- pdf, xlsx, zip, jpg, docx all observed
    first_seen_at   TEXT NOT NULL
);

CREATE TABLE document_source (
    document_sha256   TEXT NOT NULL REFERENCES document (document_sha256),
    source_url        TEXT NOT NULL,
    stb_filing_id     TEXT,
    stb_decision_id   TEXT,
    supersedes_sha256 TEXT REFERENCES document (document_sha256),  -- errata chain (ADR 0002)
    capture_id        INTEGER NOT NULL REFERENCES capture (capture_id),
    observed_at       TEXT NOT NULL
);

-- one association per (bytes, url, owning record); expression index because the record
-- reference columns are nullable and SQLite UNIQUE would treat NULLs as distinct
CREATE UNIQUE INDEX document_source_identity
    ON document_source (document_sha256, source_url,
                        COALESCE(stb_filing_id, ''), COALESCE(stb_decision_id, ''));

-- change-detection for filings/decisions keys on source_key; without this every record
-- ingested would scan the ledger
CREATE INDEX event_by_key ON event (source_key, event_type, event_id);

CREATE TABLE filing (
    filing_pk         INTEGER PRIMARY KEY,
    docket_id         INTEGER NOT NULL REFERENCES docket (docket_id),
    stb_filing_id     TEXT NOT NULL,
    filing_type       TEXT,
    filed_date        TEXT,                     -- quoted from the Official Filing Date cell
    filed_for_raw     TEXT,                     -- raw cell, uncut; splitting into party rows
                                                -- is the party module's pass (ADR 0004) and
                                                -- loses nothing while this raw is kept
    observed_in_event INTEGER NOT NULL REFERENCES event (event_id),
    UNIQUE (docket_id, stb_filing_id)
);

CREATE TABLE filing_attachment (
    filing_pk       INTEGER NOT NULL REFERENCES filing (filing_pk),
    source_url      TEXT NOT NULL,
    label           TEXT,
    document_sha256 TEXT REFERENCES document (document_sha256),   -- null until fetched
    UNIQUE (filing_pk, source_url)
);

CREATE TABLE decision_record (
    decision_pk       INTEGER PRIMARY KEY,
    docket_id         INTEGER NOT NULL REFERENCES docket (docket_id),
    stb_decision_id   TEXT NOT NULL,             -- the table's own id: the natural key
    decision_number   TEXT,                      -- 'Decision No. 30' — printed inside the
                                                -- document, filled by extraction later
    decision_type     TEXT,
    deciding_body     TEXT,
    service_date      TEXT,                     -- quoted from the Service Date cell
    observed_in_event INTEGER NOT NULL REFERENCES event (event_id),
    UNIQUE (docket_id, stb_decision_id)
);

CREATE TABLE decision_attachment (
    decision_pk     INTEGER NOT NULL REFERENCES decision_record (decision_pk),
    source_url      TEXT NOT NULL,
    label           TEXT,
    document_sha256 TEXT REFERENCES document (document_sha256),
    UNIQUE (decision_pk, source_url)
);

PRAGMA user_version = 2;

COMMIT;
