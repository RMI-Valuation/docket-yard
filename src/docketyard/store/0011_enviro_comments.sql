-- Migration 0011: environmental comments — the third record row F1 always named
-- (docs/schema-draft.md § 5, checked against the five queries and the schema-critic
-- 2026-08-31). Structurally a sibling of filing and decision_record: quoted cells, an
-- attachment set, and an event that establishes it. Two departures, both forced by
-- measurement rather than chosen:
--
-- 1. THE KEY IS THE COMMENT NUMBER, NOT THE ENDPOINT'S ROW ID. Filings and decisions key
--    on the middle part of data-stb-id, and the parser refuses any row whose printed id
--    cell disagrees with it. No cell of a comment row prints that part (measured over 150
--    rows, 2026-08-31), so keying on it would weld an uncorroborated number into an
--    append-only ledger through source_key, where re-keying is not an UPDATE but tens of
--    thousands of fresh events. The comment number IS printed, and is also the data-stb-id
--    of its own detail link: measured never blank, never colliding with a different row
--    ref, never repeated across dockets. stb_row_ref keeps the row id as a corroborating
--    attribute so a later re-key is a parse, never a re-ingest.
--
-- 2. THE RECORD IS PUBLISHED AS THE BOARD PUBLISHES IT, AND NO NAME IS MASKED (the
--    operator's decision, 2026-08-31, after a masking design was drafted and dropped).
--    A commenter filed on a public docket at a federal agency; that is the public record,
--    and republishing it is what this project is for. ADR 0011's posture is about the
--    site's READERS, whose attention we decline to collect, not about the people who
--    choose to file.
--
--    The design that was dropped, and why, so it is not re-proposed from scratch: a mask
--    over the submitter column, displaying initials while the store kept the name as the
--    Board prints it. It fails on its own terms. The same name is inside the comment's own
--    words in 5 of the 76 comments measured for 2026 (EI-34282 signs off "Erin Collins
--    President, Chesterton Town Council"), it is inside the attachment the Board serves,
--    and it will be inside the extracted text when the OCR milestone lands. Masking one
--    column while three other paths print the name is not a privacy measure, it is the
--    appearance of one — and the appearance is worse than nothing, because a reader takes
--    it for a promise.
--
--    So: no `masked_at` column, no CHECK, no trigger, and nothing in store/dump.py that
--    redacts a payload. Nothing published may imply that a name here can be held back.
--    Should that ever change, it is a new migration and a new decision, not a gap.

BEGIN TRANSACTION;

CREATE TABLE enviro_comment (
    comment_pk            INTEGER PRIMARY KEY,
    docket_id             INTEGER NOT NULL REFERENCES docket (docket_id),
    -- 'EI-34280' (a submitted comment) or 'EO-3243' (the Board's own environmental
    -- document); the prefix is inside the number and needs no column of its own —
    -- typing the row would be a derived claim, and this table derives none
    comment_number        TEXT NOT NULL,
    stb_row_ref           TEXT,                 -- the 203738 of FD_36873|203738|830758
    -- the Board heads this column "Date Received or Sent" and declines to say which;
    -- so does the schema. ISO normalisation of the cell; the printed form is in the
    -- event payload as date_printed, exactly as it is for filings and decisions
    date_received_or_sent TEXT,
    submitter_raw         TEXT,                 -- as printed (on an EO row, a document title)
    organisation_raw      TEXT,                 -- as printed
    -- 'Laramie, WY' AND 'Towson, Maryland' both occur: the state is not reliably a code,
    -- so this is kept whole and unparsed. It is the seed of the map layer (C3/D2) and
    -- that pass's whole input; ADR 0008's structured rows wait for that milestone
    location_raw          TEXT,
    -- the commenter's own words, as the table printed them and after markup.clean (tags
    -- stripped, whitespace collapsed — a multi-paragraph comment loses its paragraphing).
    -- Measured NOT truncated. Absent on about half the rows. There is NO position column
    -- here or anywhere: the words are quotation, and naming the position would be inference
    comment_text_printed  TEXT,
    observed_in_event     INTEGER NOT NULL REFERENCES event (event_id),
    UNIQUE (docket_id, comment_number)
);

CREATE INDEX enviro_comment_by_docket ON enviro_comment (docket_id, date_received_or_sent);
-- The number is looked up ALONE on two hot paths — serving /comment/<number>, and ingest's
-- check for the same number under another docket — and the UNIQUE index above cannot serve
-- either, because comment_number is its second column. Without this both are a full scan of
-- a 22,000-row table: once per page view, and once per comment minted by the archive wave.
CREATE INDEX enviro_comment_by_number ON enviro_comment (comment_number);
-- a withdrawal is rare and the snapshot checks every one of them: index the few, not the many
CREATE TABLE enviro_comment_attachment (
    comment_pk      INTEGER NOT NULL REFERENCES enviro_comment (comment_pk),
    source_url      TEXT NOT NULL,
    label           TEXT,
    document_sha256 TEXT REFERENCES document (document_sha256),   -- null until fetched
    UNIQUE (comment_pk, source_url)
);

-- A comment's attachment is a document like any other, so document_source must be able to
-- name a comment as its owner. Without this the fetcher writes NULL into both id columns
-- for every comment PDF, document_source_identity folds every comment association for a
-- URL into one anonymous row, and a document_replaced alert could only say "a record it
-- holds (not identified)".
--
-- NOT named stb_comment_id, and not the bare number. Its two siblings hold ids that are
-- unique across the whole source, and every consumer will assume the third is too — but
-- this migration's own key argument is that a comment number is identity only WITHIN a
-- docket. So the column holds the docket-qualified spelling the event ledger already uses
-- as its source_key, `FD_36873_0|EI-34280`, and is named for what it is.
ALTER TABLE document_source ADD COLUMN comment_source_key TEXT;

DROP INDEX document_source_identity;
CREATE UNIQUE INDEX document_source_identity
    ON document_source (document_sha256, source_url,
                        COALESCE(stb_filing_id, ''), COALESCE(stb_decision_id, ''),
                        COALESCE(comment_source_key, ''));

PRAGMA user_version = 11;

COMMIT;
