-- Migration 0008: webhooks (M8, docs/alerts.md § Feeds and webhooks).
-- A subscription's recipient may be an HTTPS URL instead of an address. It is stored the
-- way an address is (ADR 0014: HMAC to match, ciphertext to deliver — the columns keep
-- their names), confirmed the way an address is (a ping the endpoint's owner must act
-- on), and deleted the way an address is. A webhook carries a signing secret, sealed
-- under the same key; the alert row records which channel it goes out on so delivery
-- can split without reading the subscription again.

BEGIN TRANSACTION;

ALTER TABLE subscription ADD COLUMN channel TEXT NOT NULL DEFAULT 'email'
    CHECK (channel IN ('email', 'webhook'));
ALTER TABLE subscription ADD COLUMN secret_enc TEXT;  -- webhook only; enforced in code

ALTER TABLE alert ADD COLUMN channel TEXT NOT NULL DEFAULT 'email'
    CHECK (channel IN ('email', 'webhook'));

PRAGMA user_version = 8;

COMMIT;
