-- Migration 0009: a party id is a permanent address (ADR 0015) and is never reused or
-- renumbered. The party table's key is a plain rowid, which SQLite reuses after the
-- highest row is deleted; no code path deletes or renumbers a party, and these triggers
-- make sure none ever does. (VACUUM never renumbers an INTEGER PRIMARY KEY.) Any later
-- rebuild of the party table must re-create them; tests/test_party_pages.py checks.
--
-- Also declared here: a party_relationship row whose superseded_by points at itself is
-- RETIRED WITHOUT SUCCESSOR — the operator withdrew the judgement (`docketyard parties
-- unjoin`) and nothing replaced it. Readers filter on superseded_by IS NULL as before;
-- anything that walks a supersession chain must treat the self-pointer as its end.
--
-- The correction table (0006) gains the two ADR 0007 fields it lacked, so a withdrawal
-- carries its method version and its source alongside the judgement it withdraws. The
-- table is empty in every store at this version; the defaults are for the schema's sake.

BEGIN TRANSACTION;

CREATE TRIGGER party_never_deleted BEFORE DELETE ON party
BEGIN
    SELECT RAISE(ABORT, 'party ids are permanent addresses (ADR 0015): never delete a party');
END;

CREATE TRIGGER party_never_renumbered BEFORE UPDATE OF party_id ON party
BEGIN
    SELECT RAISE(ABORT, 'party ids are permanent addresses (ADR 0015): never renumber a party');
END;

ALTER TABLE correction ADD COLUMN method_version TEXT NOT NULL DEFAULT 'unversioned';
ALTER TABLE correction ADD COLUMN source_location TEXT;

PRAGMA user_version = 9;

COMMIT;
