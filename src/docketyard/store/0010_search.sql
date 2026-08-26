-- Migration 0010: the search index (docs/search.md). Derived and disposable: search_doc is
-- rebuilt whole by ingest after every pass, from the registry, the party module and the
-- decisions' printed summaries; search_fts is an FTS5 index over it. It asserts nothing and
-- so carries no provenance — it points at rows that carry theirs. The web tier only reads.

BEGIN TRANSACTION;

CREATE TABLE search_doc (
    doc_id   INTEGER PRIMARY KEY,
    kind     TEXT NOT NULL CHECK (kind IN ('docket', 'party', 'decision')),
    ref      INTEGER NOT NULL,                    -- docket_id | party_id | decision_pk
    address  TEXT NOT NULL,                       -- the permanent path the hit resolves to
    title    TEXT NOT NULL,                       -- as printed (a number, a name, an id)
    body     TEXT NOT NULL,                       -- the words that find it
    fact     TEXT NOT NULL                        -- one measured line for the result row
);
CREATE UNIQUE INDEX search_doc_ref ON search_doc (kind, ref);

CREATE VIRTUAL TABLE search_fts USING fts5 (
    title, body,
    content = 'search_doc', content_rowid = 'doc_id',
    tokenize = "unicode61 remove_diacritics 2"
);

PRAGMA user_version = 10;

COMMIT;
