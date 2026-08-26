-- Migration 0010: the search index (docs/search.md). Derived and disposable: search_doc is
-- rebuilt whole by ingest when the record has changed, from the registry, the party module
-- and the decisions' printed summaries; search_fts is an FTS5 index over it. It asserts
-- nothing and so carries no provenance — it points at rows that carry theirs. The web tier
-- only reads. The snapshot (dump.py) keeps the tables and empties them: the index carries
-- party names, the held layer, and a restored copy rebuilds it with `docketyard search
-- rebuild`.

BEGIN TRANSACTION;

CREATE TABLE search_doc (
    doc_id   INTEGER PRIMARY KEY,
    kind     TEXT NOT NULL CHECK (kind IN ('docket', 'party', 'decision')),
    ref      INTEGER NOT NULL,                    -- docket_id | party_id | decision_pk
    path     TEXT NOT NULL,                       -- the permanent path the hit resolves to
    title    TEXT NOT NULL,                       -- as printed (a number, a name, an id)
    body     TEXT NOT NULL,                       -- the words that find it
    fact     TEXT NOT NULL                        -- one measured line for the result row
);
CREATE UNIQUE INDEX search_doc_ref ON search_doc (kind, ref);

CREATE VIRTUAL TABLE search_fts USING fts5 (
    title, body,
    content = 'search_doc', content_rowid = 'doc_id',
    tokenize = "unicode61 remove_diacritics 2",
    prefix = '2 3'
);

-- what the index was built from, so an unchanged record is not rebuilt and a rebuild is
-- part of the web tier's version stamp
CREATE TABLE search_meta (
    key       TEXT PRIMARY KEY,
    signature TEXT NOT NULL,
    build     INTEGER NOT NULL,
    built_at  TEXT NOT NULL
);

PRAGMA user_version = 10;

COMMIT;
