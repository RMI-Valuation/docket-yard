-- Migration 0005: addresses at rest become an HMAC (for matching) and a ciphertext (for
-- sending) under a key held only on the serving machine (alerts/vault.py; ADR 0011,
-- decided 2026-08-26). The subscription tables are rebuilt rather than altered — SQLite
-- cannot rewrite a CHECK — and their rows are DROPPED: a plaintext address cannot be
-- sealed inside SQL, and at this migration the tables held two test subscriptions, both
-- the operator's, re-made by hand afterwards. This is recorded here because it is the
-- one migration in the set that does not carry every row forward.

BEGIN TRANSACTION;

DROP TABLE alert_event;
DROP TABLE alert;
DROP TABLE subscription_token;
DROP TABLE subscription;
DROP TABLE email_suppression;

CREATE TABLE subscription (
    subscription_id   INTEGER PRIMARY KEY,
    email_hash        TEXT NOT NULL,              -- HMAC-SHA256 of the normalised address
    email_enc         TEXT NOT NULL,              -- Fernet ciphertext of the same
    docket_id         INTEGER REFERENCES docket (docket_id),
    cadence           TEXT NOT NULL CHECK (cadence IN ('pass', 'daily')),
    status            TEXT NOT NULL CHECK (status IN ('pending', 'active')),
    high_water_event_id INTEGER,
    created_at        TEXT NOT NULL,
    confirmed_at      TEXT,
    expires_at        TEXT,
    CHECK (status <> 'active' OR high_water_event_id IS NOT NULL),
    CHECK (status <> 'pending' OR expires_at IS NOT NULL)
);

CREATE UNIQUE INDEX subscription_live ON subscription (email_hash, docket_id)
    WHERE docket_id IS NOT NULL;
CREATE INDEX subscription_by_docket ON subscription (docket_id, status);

CREATE TABLE subscription_token (
    token_sha256    TEXT PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES subscription (subscription_id)
                    ON DELETE CASCADE,
    purpose         TEXT NOT NULL CHECK (purpose IN ('confirm', 'unsubscribe')),
    created_at      TEXT NOT NULL,
    expires_at      TEXT,
    CHECK (purpose <> 'confirm' OR expires_at IS NOT NULL)
);

CREATE INDEX subscription_token_by_subscription ON subscription_token (subscription_id);

CREATE TABLE alert (
    alert_id    INTEGER PRIMARY KEY,
    email_hash  TEXT NOT NULL,
    email_enc   TEXT NOT NULL,
    cadence     TEXT NOT NULL CHECK (cadence IN ('pass', 'daily')),
    status      TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed')),
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    sent_at     TEXT,
    message_id  TEXT,
    CHECK (status <> 'sent' OR (sent_at IS NOT NULL AND message_id IS NOT NULL))
);

CREATE TABLE alert_event (
    alert_id        INTEGER NOT NULL REFERENCES alert (alert_id) ON DELETE CASCADE,
    subscription_id INTEGER NOT NULL REFERENCES subscription (subscription_id)
                    ON DELETE CASCADE,
    event_id        INTEGER NOT NULL REFERENCES event (event_id),
    late_gap_id     INTEGER REFERENCES coverage_gap (gap_id) ON DELETE SET NULL,
    late            INTEGER NOT NULL DEFAULT 0 CHECK (late IN (0, 1)),
    PRIMARY KEY (alert_id, subscription_id, event_id),
    UNIQUE (subscription_id, event_id)
);

CREATE INDEX alert_pending ON alert (status) WHERE status = 'pending';

-- matched by the HMAC; the ciphertext is kept only so a key rotation can re-derive the
-- hash — without it every bounced address would be silently forgotten at rotation
CREATE TABLE email_suppression (
    email_hash  TEXT PRIMARY KEY,
    email_enc   TEXT NOT NULL,
    reason      TEXT NOT NULL CHECK (reason IN ('bounce', 'complaint', 'manual')),
    created_at  TEXT NOT NULL
);

PRAGMA user_version = 5;

COMMIT;
