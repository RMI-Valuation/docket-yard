-- Migration 0008: webhooks (M8, docs/alerts.md § Feeds and webhooks).
-- A subscription's recipient may be an HTTPS URL instead of an address. It is stored the
-- way an address is (ADR 0014: HMAC to match, ciphertext to deliver — the columns keep
-- their names), confirmed the way an address is (a ping the endpoint's owner must act
-- on), and deleted the way an address is. A webhook carries a signing secret, sealed
-- under the same key; the alert row records which channel it goes out on so delivery
-- can split without reading the subscription again.
--
-- Reviewed by the schema-critic 2026-08-26. Conventions it asked to have written down:
-- a URL's hash is domain-separated from an address's (vault.hash_recipient); the secret
-- is one per endpoint, copied as the same ciphertext into each of the endpoint's rows
-- (an endpoint table would make that structural — a known refactor); `secret_enc` is
-- a fourth sealed column the key-rotation pass must cover; for a webhook alert,
-- `message_id` holds `http-<status>` and the delivery id is `alert_id` itself.

BEGIN TRANSACTION;

ALTER TABLE subscription ADD COLUMN channel TEXT NOT NULL DEFAULT 'email'
    CHECK (channel IN ('email', 'webhook'));
ALTER TABLE subscription ADD COLUMN secret_enc TEXT
    CHECK ((channel = 'webhook') = (secret_enc IS NOT NULL));  -- webhook ⇔ secret

ALTER TABLE alert ADD COLUMN channel TEXT NOT NULL DEFAULT 'email'
    CHECK (channel IN ('email', 'webhook'));

PRAGMA user_version = 8;

COMMIT;
