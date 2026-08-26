-- Migration 0006: the party module (ADR 0004; docs/party-module.md, reviewed by the
-- schema-critic 2026-08-26). Parties are entities; a "Filed For" cell becomes spans, a span
-- may acquire a link to a party, and every judgement carries ADR 0007's provenance block
-- and a supersession pointer. Nothing here is ever UPDATEd into a different meaning: a
-- better judgement is a new row that supersedes the old. Parties are a facet of the record,
-- not an address (ADR 0013 addendum): ids are internal.

BEGIN TRANSACTION;

CREATE TABLE party (
    party_id     INTEGER PRIMARY KEY,
    founding_key TEXT NOT NULL UNIQUE,          -- the normalised span it was minted from
    created_at   TEXT NOT NULL
);

-- ADR 0007's block, repeated on every assertion table below:
--   asserted_from_capture  the capture whose observation the assertion was made from
--   source_location        where in that source (JSON: cell, span offsets, seed row)
--   method / method_version / asserted_at / confidence
--   superseded_by          the row that replaced this judgement, never a DELETE

CREATE TABLE party_name (
    name_id               INTEGER PRIMARY KEY,
    party_id              INTEGER NOT NULL REFERENCES party (party_id),
    raw_name              TEXT NOT NULL,
    norm_name             TEXT NOT NULL,        -- the matcher's form; part of its version
    name_kind             TEXT NOT NULL
                          CHECK (name_kind IN ('as_filed', 'legal', 'mark', 'trade', 'colloquial', 'display')),
    asserted_from_capture INTEGER REFERENCES capture (capture_id),
    source_location       TEXT,
    method                TEXT NOT NULL,
    method_version        TEXT NOT NULL,
    asserted_at           TEXT NOT NULL,
    confidence            REAL NOT NULL CHECK (confidence > 0 AND confidence <= 1),
    superseded_by         INTEGER REFERENCES party_name (name_id)
);
CREATE UNIQUE INDEX party_name_live ON party_name (party_id, norm_name, name_kind)
    WHERE superseded_by IS NULL;
CREATE INDEX party_name_by_norm ON party_name (norm_name) WHERE superseded_by IS NULL;

CREATE TABLE relationship_vocab (
    rel_type  TEXT PRIMARY KEY,
    reading   TEXT NOT NULL,                    -- the direction convention, as data
    symmetric INTEGER NOT NULL CHECK (symmetric IN (0, 1))
);
INSERT INTO relationship_vocab VALUES
    ('succeeded_by', 'from = earlier entity, to = later entity', 0),
    ('merged_into',  'from = entity that ceased, to = entity it merged into', 0),
    ('renamed_to',   'from = earlier name-holder, to = later', 0),
    ('parent_of',    'from = parent, to = subsidiary', 0),
    ('same_as',      'the two ids are one entity; traverse both ways', 1);

CREATE TABLE party_relationship (
    edge_id               INTEGER PRIMARY KEY,
    from_party            INTEGER NOT NULL REFERENCES party (party_id),
    to_party              INTEGER NOT NULL REFERENCES party (party_id),
    rel_type              TEXT NOT NULL REFERENCES relationship_vocab (rel_type),
    effective_date        TEXT,                 -- quoted from a cited source, never computed
    asserted_from_capture INTEGER REFERENCES capture (capture_id),
    source_location       TEXT,
    method                TEXT NOT NULL,
    method_version        TEXT NOT NULL,
    asserted_at           TEXT NOT NULL,
    confidence            REAL NOT NULL CHECK (confidence > 0 AND confidence <= 1),
    superseded_by         INTEGER REFERENCES party_relationship (edge_id)
);
CREATE UNIQUE INDEX party_relationship_live
    ON party_relationship (from_party, to_party, rel_type, COALESCE(effective_date, ''))
    WHERE superseded_by IS NULL;
CREATE INDEX party_relationship_by_to ON party_relationship (to_party) WHERE superseded_by IS NULL;

-- the split: one row per piece the rules cut from a cell; raw_text is the WHOLE cell
CREATE TABLE filing_party_span (
    span_id               INTEGER PRIMARY KEY,
    filing_pk             INTEGER NOT NULL REFERENCES filing (filing_pk),
    raw_text              TEXT NOT NULL,
    ordinal               INTEGER NOT NULL,
    span_start            INTEGER NOT NULL,
    span_end              INTEGER NOT NULL,
    span_text             TEXT NOT NULL,
    role                  TEXT NOT NULL CHECK (role IN ('filed_for', 'on_behalf_of')),
    asserted_from_capture INTEGER REFERENCES capture (capture_id),
    source_location       TEXT,
    method                TEXT NOT NULL,
    method_version        TEXT NOT NULL,
    asserted_at           TEXT NOT NULL,
    confidence            REAL NOT NULL CHECK (confidence > 0 AND confidence <= 1),
    superseded_by         INTEGER REFERENCES filing_party_span (span_id)
);
CREATE UNIQUE INDEX filing_party_span_live ON filing_party_span (filing_pk, raw_text, ordinal)
    WHERE superseded_by IS NULL;
CREATE INDEX filing_party_span_by_filing ON filing_party_span (filing_pk)
    WHERE superseded_by IS NULL;

-- the resolution: a span held to name a party. No live link = unresolved, never a NULL
CREATE TABLE filing_party_link (
    link_id               INTEGER PRIMARY KEY,
    span_id               INTEGER NOT NULL REFERENCES filing_party_span (span_id),
    party_id              INTEGER NOT NULL REFERENCES party (party_id),
    asserted_from_capture INTEGER REFERENCES capture (capture_id),
    source_location       TEXT,
    method                TEXT NOT NULL,
    method_version        TEXT NOT NULL,
    asserted_at           TEXT NOT NULL,
    confidence            REAL NOT NULL CHECK (confidence > 0 AND confidence <= 1),
    superseded_by         INTEGER REFERENCES filing_party_link (link_id)
);
CREATE UNIQUE INDEX filing_party_link_live ON filing_party_link (span_id)
    WHERE superseded_by IS NULL;
CREATE INDEX filing_party_link_by_party ON filing_party_link (party_id)
    WHERE superseded_by IS NULL;

-- a human's amendment of any assertion row: the path ADR 0007 requires for human rows,
-- which a model pass may never supersede
CREATE TABLE correction (
    correction_id INTEGER PRIMARY KEY,
    target_table  TEXT NOT NULL,
    target_id     INTEGER NOT NULL,
    note          TEXT NOT NULL,
    method        TEXT NOT NULL DEFAULT 'human',
    asserted_at   TEXT NOT NULL
);

PRAGMA user_version = 6;

COMMIT;
