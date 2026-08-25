-- Migration 0003: walk progress. A registry walk is hundreds of requests; this table makes
-- it resumable and auditable — each slice (one prefix) records how it ended.

BEGIN TRANSACTION;

CREATE TABLE walk_slice (
    slice_key    TEXT PRIMARY KEY,               -- e.g. 'stb_hook_table_dockets:FD'
    table_action TEXT NOT NULL,
    criteria     TEXT NOT NULL,                  -- JSON, as sent
    -- done: paged to the end and reconciled. empty: a census-expected empty prefix.
    -- capped: hit the display cap; needs sub-slicing. partial: anything else — rerun.
    status       TEXT NOT NULL CHECK (status IN ('done', 'empty', 'capped', 'partial')),
    rows         INTEGER NOT NULL,               -- rows from ASSERTED pages only
    captures     INTEGER NOT NULL,
    completed_at TEXT NOT NULL
);

PRAGMA user_version = 3;

COMMIT;
