-- Migration 0017: a reviewer token knows what it is for.
--
-- Migration 0015 gave `reviewer_token` a hash, an expiry and a `used_at`, which is enough
-- for a magic link and not enough for the session that link mints. Two rows in one table
-- with no way to tell them apart means the SESSION COOKIE'S VALUE IS ALSO A VALID SIGN-IN
-- LINK — and a sign-in link travels in a URL, where it lands in browser history, in a
-- `Referer`, and in whatever logs a mail gateway keeps. A session value must never be
-- pasteable into an address bar and still work.
--
-- So: `purpose`, the same column `subscription_token` has carried since migration 0005 for
-- the same reason. The table is empty (no reviewer has signed in; there is no sign-in), so
-- this is a column and not a rebuild.
--
-- THE TWO LIVES ARE DIFFERENT AND THAT IS THE POINT. A 'sign-in' token is minted from an
-- address, mailed, single-use, and short — it proves someone reads that mailbox. A
-- 'session' token is minted from a consumed sign-in, never mailed, never single-use, and
-- longer — it proves the same thing without asking again. Neither is a password, which is
-- what ADR 0011 rules out and ADR 0016 inherits.

BEGIN TRANSACTION;

-- DEFAULT 'sign-in' is for the ALTER and nothing else: every writer names its purpose, and
-- the CHECK below is what stops a third value arriving by accident. (SQLite cannot add a
-- CHECK to an existing table, so it is declared here as part of the column.)
ALTER TABLE reviewer_token ADD COLUMN purpose TEXT NOT NULL DEFAULT 'sign-in'
    CHECK (purpose IN ('sign-in', 'session'));

-- The read on every signed-in request is (hash, purpose, expiry), and the hash is already
-- the primary key; this index is for the OTHER read — retiring a reviewer's live sessions
-- when a grant is withdrawn, which is ADR 0016's "a role that can be withdrawn needs a way
-- to be withdrawn" and cannot wait for an expiry.
DROP INDEX reviewer_token_by_reviewer;
CREATE INDEX reviewer_token_by_reviewer ON reviewer_token (reviewer_id, purpose, expires_at);

PRAGMA user_version = 17;

COMMIT;
