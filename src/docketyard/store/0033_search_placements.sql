-- Migration 0033: search learns where a record belongs (docs/search-v2.md).
--
-- Search is being built out to group results by proceeding and filter them by docket type,
-- date and the Board's type. The index folded a record entered in several dockets to ONE row
-- under the docket nearest the parent, which could not answer either: 573 filings and 1,432
-- decisions sit in more than one family (measured on the 2026-09-17 restore), so a joint
-- FD/NOR filing folded to FD would be missed by a filter for NOR. An item is now FOUND once
-- (one `search_doc` row per record id) and PLACED in every proceeding it was entered in (one
-- `search_place` row per proceeding).
--
-- `search_doc` is rebuilt, as 0012 rebuilt it, because its kind CHECK must admit `filing`
-- and SQLite cannot alter a CHECK. Everything here is derived and disposable: `docketyard
-- search rebuild` remakes every row from the store, and nothing is a record.
--
-- search_meta's SIGNATURE is cleared and its row kept, for 0012's reasons: an empty index
-- that believed itself current would answer nothing, and the build counter is part of the
-- web tier's ETag.
--
-- Numbered 0033 on branch `search-v2`. The decided-dates addendum on `decided-date-grain`
-- also claims 0033; whichever lands second renumbers (`MIGRATIONS` must be contiguous).

BEGIN TRANSACTION;

DROP TABLE IF EXISTS search_fts;   -- the FTS5 virtual table and its shadow tables
DROP TABLE IF EXISTS search_doc;

CREATE TABLE search_doc (
    doc_id   INTEGER PRIMARY KEY,
    kind     TEXT NOT NULL
             CHECK (kind IN ('docket', 'party', 'decision', 'comment', 'filing')),
    ref      INTEGER NOT NULL,                    -- docket_id | party_id | decision_pk |
                                                  -- comment_pk | filing_pk: the headline copy
    path     TEXT NOT NULL,                       -- the permanent path the hit resolves to
    title    TEXT NOT NULL,                       -- as printed (a number, a name, an id)
    body     TEXT NOT NULL,                       -- the words that find it
    fact     TEXT NOT NULL,                       -- one measured line for the result row
    caption  TEXT NOT NULL DEFAULT ''             -- the row's own printed name (0013)
);
CREATE UNIQUE INDEX search_doc_ref ON search_doc (kind, ref);

CREATE VIRTUAL TABLE search_fts USING fts5 (
    title, body,
    content = 'search_doc', content_rowid = 'doc_id',
    tokenize = "unicode61 remove_diacritics 2",
    prefix = '2 3'
);

-- Where an index row belongs: one row per proceeding it was entered in, the proceeding by the
-- sheet rule (F4: a sub-docket with a caption of its own is itself, one repeating its
-- parent's caption is the family). An ID, never a path: an unparseable docket has no path
-- and must not become one shared empty group. The cells are that entry's own, mirroring the
-- latest observation as the record tables do — never history (validation queries 3 and 4
-- stay on the ledger). A party has no placement: it is not a proceeding.
CREATE TABLE search_place (
    doc_id          INTEGER NOT NULL,             -- search_doc.doc_id
    group_docket_id INTEGER NOT NULL,             -- docket.docket_id of the proceeding
    prefix          TEXT NOT NULL,
    date_kind       TEXT CHECK (date_kind IN ('filed', 'served', 'dated')),
    date            TEXT,                         -- the Board's printed date, ISO; NULL for a
                                                  -- docket, and never a computed date
    type_kind       TEXT CHECK (type_kind IN ('filing', 'decision')),
    type            TEXT,                         -- the Board's type as that entry prints it
    PRIMARY KEY (doc_id, group_docket_id),
    CHECK (date IS NULL OR date_kind IS NOT NULL),
    CHECK (type IS NULL OR type_kind IS NOT NULL)
) WITHOUT ROWID;
CREATE INDEX search_place_group ON search_place (group_docket_id);
CREATE INDEX search_place_prefix_date ON search_place (prefix, date);
CREATE INDEX search_place_type ON search_place (type_kind, type);

-- A document's owners in the index, so a page of text reaches its proceedings and filter
-- cells through its owner's placements. `page_fts` itself is not changed.
CREATE TABLE search_document (
    document_sha256 TEXT NOT NULL,
    doc_id          INTEGER NOT NULL,             -- search_doc.doc_id of a filing, decision
                                                  -- or comment carrying the document
    PRIMARY KEY (document_sha256, doc_id)
) WITHOUT ROWID;

UPDATE search_meta SET signature = '' WHERE key = 'built';

PRAGMA user_version = 33;

COMMIT;
