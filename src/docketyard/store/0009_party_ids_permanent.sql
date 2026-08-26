-- Migration 0009: a party id is a permanent address (ADR 0015) and is never reused. The
-- party table's key is a plain rowid, which SQLite reuses after the highest row is deleted;
-- no code path deletes a party, and this trigger makes sure none ever does. Nothing else
-- changes: the address is the existing key, so there is no data to migrate.

BEGIN TRANSACTION;

CREATE TRIGGER party_never_deleted BEFORE DELETE ON party
BEGIN
    SELECT RAISE(ABORT, 'party ids are permanent addresses (ADR 0015): never delete a party');
END;

PRAGMA user_version = 9;

COMMIT;
