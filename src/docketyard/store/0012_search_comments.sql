-- Migration 0012: the search index learns the third record row.
--
-- `search_doc.kind` was a closed CHECK of docket/party/decision (migration 0010), so an
-- environmental comment could be addressed at /comment/EI-34280 and shown on its docket
-- sheet while being unfindable by search. SQLite cannot alter a CHECK, so the table is
-- rebuilt — which costs nothing here because the whole index is derived and disposable:
-- `search rebuild` remakes every row from the record.
--
-- search_meta's SIGNATURE is cleared, not its row. The signature is what `rebuild()`
-- compares against; leaving it would mean an empty index that believes it is current, and
-- search would answer nothing until some unrelated event moved it. `signature()` can never
-- return an empty string (it joins nine integers), so a blank forces exactly one rebuild.
--
-- The `build` counter is deliberately NOT reset. It is part of the web tier's ETag
-- validator, so deleting the row would restart it at zero and invalidate every cached page
-- twice at deploy — once on the way down, once on the way back up — for no record change.

BEGIN TRANSACTION;

DROP TABLE IF EXISTS search_fts;   -- the FTS5 virtual table and its shadow tables
DROP TABLE IF EXISTS search_doc;

CREATE TABLE search_doc (
    doc_id   INTEGER PRIMARY KEY,
    kind     TEXT NOT NULL CHECK (kind IN ('docket', 'party', 'decision', 'comment')),
    ref      INTEGER NOT NULL,                    -- docket_id | party_id | decision_pk |
                                                  -- comment_pk
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

UPDATE search_meta SET signature = '' WHERE key = 'built';   -- see the note above

PRAGMA user_version = 12;

COMMIT;
