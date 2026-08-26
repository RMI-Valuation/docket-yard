-- Migration 0007: subscribe by party (M6, docs/party-module.md § Subscriptions by party).
-- A subscription names exactly one predicate: a docket family, or a party. SQLite cannot
-- add a CHECK to a live table, so `subscription` is rebuilt and its rows copied — every
-- existing row carries forward (unlike 0005, which is recorded as the exception).

BEGIN TRANSACTION;

CREATE TABLE subscription_new (
    subscription_id   INTEGER PRIMARY KEY,
    email_hash        TEXT NOT NULL,
    email_enc         TEXT NOT NULL,
    docket_id         INTEGER REFERENCES docket (docket_id),
    party_id          INTEGER REFERENCES party (party_id),
    cadence           TEXT NOT NULL CHECK (cadence IN ('pass', 'daily')),
    status            TEXT NOT NULL CHECK (status IN ('pending', 'active')),
    high_water_event_id INTEGER,
    created_at        TEXT NOT NULL,
    confirmed_at      TEXT,
    expires_at        TEXT,
    CHECK (status <> 'active' OR high_water_event_id IS NOT NULL),
    CHECK (status <> 'pending' OR expires_at IS NOT NULL),
    CHECK ((docket_id IS NOT NULL) + (party_id IS NOT NULL) = 1)
);
INSERT INTO subscription_new (subscription_id, email_hash, email_enc, docket_id, cadence,
                              status, high_water_event_id, created_at, confirmed_at, expires_at)
    SELECT subscription_id, email_hash, email_enc, docket_id, cadence, status,
           high_water_event_id, created_at, confirmed_at, expires_at
      FROM subscription;

-- dependants (subscription_token, alert_event) reference subscription by id with ON DELETE
-- CASCADE. The runner turns foreign keys OFF for the script, so this DROP does not cascade
-- into them (it would, with enforcement on — measured); ids are unchanged, so their
-- references stay valid, and the runner's foreign_key_check proves it before commit
DROP TABLE subscription;
ALTER TABLE subscription_new RENAME TO subscription;

CREATE UNIQUE INDEX subscription_live ON subscription (email_hash, docket_id)
    WHERE docket_id IS NOT NULL;
CREATE UNIQUE INDEX subscription_live_party ON subscription (email_hash, party_id)
    WHERE party_id IS NOT NULL;
CREATE INDEX subscription_by_docket ON subscription (docket_id, status);
CREATE INDEX subscription_by_party ON subscription (party_id, status);

PRAGMA user_version = 7;

COMMIT;
