-- Migration 0004: subscriptions and the alert ledger — the M4 slice of schema-draft.md § 6,
-- shaped by ADR 0011 (an account is an email address; confirmed opt-in; hashed tokens; no
-- tracking) and the delivery promise in docs/alerts.md (two cadences, no backfill, fire off
-- the event ledger only). Reviewed by the schema-critic 2026-08-26; its findings shaped
-- what follows and are noted where they bit.

BEGIN TRANSACTION;

-- One row per (address, docket family) while it is wanted. The docket is the family's
-- parent: a sheet folds its sub-dockets, and so does its subscription. Nothing else about
-- the subscriber is stored (ADR 0011).
--
-- There is no 'cancelled' state: a withdrawn subscription is DELETED, cascading its tokens
-- and its alert history. A retained cancelled row would be exactly the attention data the
-- ADR forbids ("this address watched this docket from X to Y"). One-click unsubscribe still
-- works from any alert ever sent because an unknown token is answered as "already
-- unsubscribed" — RFC 8058 asks for idempotence, not a persistent row.
CREATE TABLE subscription (
    subscription_id   INTEGER PRIMARY KEY,
    email             TEXT NOT NULL CHECK (email = lower(trim(email))),
    -- nullable so query 5's party / service-list predicates can be ADDED as columns later
    -- (SQLite cannot relax NOT NULL without a rebuild); the wedge always sets it
    docket_id         INTEGER REFERENCES docket (docket_id),
    cadence           TEXT NOT NULL CHECK (cadence IN ('pass', 'daily')),
    status            TEXT NOT NULL CHECK (status IN ('pending', 'active')),
    -- alerts carry only events with event_id > high_water: set at confirmation to the
    -- ledger's head, in the same transaction, so nothing observed before the subscriber
    -- said yes is ever sent (docs/alerts.md: no backfill). No default: an active row
    -- without a mark is refused rather than allowed to alert the whole ledger. A floor,
    -- not a reference: 0 on an empty ledger is valid, so no FK to event
    high_water_event_id INTEGER,
    created_at        TEXT NOT NULL,
    confirmed_at      TEXT,
    -- a pending row is a stranger's address pointed at a docket until the owner says yes:
    -- it expires with its confirmation link and is deleted by the sweep (ADR 0011)
    expires_at        TEXT,
    CHECK (status <> 'active' OR high_water_event_id IS NOT NULL),
    CHECK (status <> 'pending' OR expires_at IS NOT NULL)
);

CREATE UNIQUE INDEX subscription_live ON subscription (email, docket_id)
    WHERE docket_id IS NOT NULL;
CREATE INDEX subscription_by_docket ON subscription (docket_id, status);

-- Single-use links (confirm, unsubscribe): the token itself is never stored, only its
-- SHA-256 of >= 128 random bits, so a copy of the store cannot mint a working link. The
-- unsubscribe token never expires and is never marked used — the row it points at is
-- simply gone once it has done its job.
CREATE TABLE subscription_token (
    token_sha256    TEXT PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES subscription (subscription_id)
                    ON DELETE CASCADE,
    purpose         TEXT NOT NULL CHECK (purpose IN ('confirm', 'unsubscribe')),
    created_at      TEXT NOT NULL,
    expires_at      TEXT,                        -- NULL = never (unsubscribe only)
    CHECK (purpose <> 'confirm' OR expires_at IS NOT NULL)
);

CREATE INDEX subscription_token_by_subscription ON subscription_token (subscription_id);

-- Gaps in the record, as intervals the operator annotates. The heartbeat runs off-box and
-- cannot write here; lateness is DERIVED at alert-build time from the capture ledger (an
-- event is late when the forward table captures around it are further apart than the
-- heartbeat threshold) and an alert_event points at the gap that explains it when one has
-- been recorded. The coverage page lists these rows.
CREATE TABLE coverage_gap (
    gap_id      INTEGER PRIMARY KEY,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,                            -- NULL while open
    failure     TEXT NOT NULL
                CHECK (failure IN ('captures', 'events', 'documents', 'delivery')),
    note        TEXT
);

-- One alert = one email to one address. Under the 'pass' cadence it carries one docket's
-- new events; under 'daily' it is the subscriber's digest across every daily docket — one
-- row either way, so a retry is an attempt on the message that actually went out.
-- Unsubscribing deletes the address's alert rows too (code, since nothing here references
-- the subscription): an alert row is "this address was being mailed on this date".
CREATE TABLE alert (
    alert_id    INTEGER PRIMARY KEY,
    email       TEXT NOT NULL CHECK (email = lower(trim(email))),
    cadence     TEXT NOT NULL CHECK (cadence IN ('pass', 'daily')),
    status      TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed')),
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    sent_at     TEXT,
    message_id  TEXT,                            -- the provider's id, from its 250 reply
    CHECK (status <> 'sent' OR (sent_at IS NOT NULL AND message_id IS NOT NULL))
);

-- What each alert carried, per subscription. An event reaches a subscription at most once:
-- that is the UNIQUE below, not a convention. The high-water mark advances with it. The
-- key includes the subscription because one address may hold a parent and a sub-docket
-- subscription and a daily digest folds both into one alert; events are never deleted,
-- so the FK to event is deliberately restrictive.
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

-- Addresses the provider reported as bouncing or complaining: never mailed again, and the
-- row is the only record of why. Populated by the bounce/complaint path when it exists;
-- consulted by every send from day one. (A bounce on a confirmation records an address
-- that never opted in — the privacy page must say so.)
CREATE TABLE email_suppression (
    email       TEXT PRIMARY KEY CHECK (email = lower(trim(email))),
    reason      TEXT NOT NULL CHECK (reason IN ('bounce', 'complaint', 'manual')),
    created_at  TEXT NOT NULL
);

PRAGMA user_version = 4;

COMMIT;
