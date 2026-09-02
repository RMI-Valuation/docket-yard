# ADR 0012 — Deployment topology

- **Status:** Accepted
- **Date:** 2026-08-25
- **Accepted:** 2026-08-25

## Context

The pipeline exists (M1–M2), the docket sheet and home page are designed, and rendering
them at a public address is the next milestone — which makes hosting the decision that can
no longer be deferred. `architecture.md` set the shape: promise-bearing work (capture,
alerts, serving) in cloud; batch enrichment on RMI-AI-MACHINE over a Tailscale seam; S3 as
the one thing that must never be lost. Two traps were parked against the day this was
decided: Lightsail's container service has neither persistent volumes nor cron, and a
production corpus is not practically re-fetchable from a small agency's endpoint.

The store is rebuildable by replay from captures and blobs (ADR 0006/0007), so the database
choice is a two-way door. Hosting is decided on cost and operational surface, not on fear
of the migration.

## Decision

- **One Lightsail instance** (Ubuntu LTS), not the container service. Docker Compose runs
  three services: `web` (FastAPI under uvicorn), `ingest` (the forward poller and alert
  sender on a timer), `caddy` (TLS, reverse proxy, static assets).
- **SQLite in WAL mode is the store**, on the instance's disk. **Litestream** streams it
  continuously to S3: the backup, and the prod-snapshot-to-dev path, in one tool.
- **Blobs live in S3**, content-addressed by SHA-256 (ADR 0002 made physical); the instance
  keeps a local cache only.
- **Deploys are pull-based** per ADR 0010: a GitHub Release builds the image tagged with the
  release version; the instance pulls that tag. Nothing pushes to production.
- **Credentials**: the instance reaches S3 through an attached IAM role — no long-lived keys
  on disk; CI reaches AWS through GitHub OIDC role assumption, never stored secrets.
- **Heartbeats live off the box.** The silent-failure decomposition in `alerts.md` (no
  captures / captures but no events / events but no deliveries) is checked from outside the
  instance, because a dead box cannot report its own death.

  > **Note (2026-09-02):** the principle stands and the mechanism is in question.
  > [ADR 0019](0019-telemetry-and-what-watches-the-box.md) proposes replacing the GitHub
  > Actions schedule with an alert on absent metrics evaluated in Grafana Cloud, after an
  > outage this one took 6 h 13 m to notice — the hourly cron runs every three to five hours.
  > [ADR 0020](0020-maintenance-is-a-state-the-record-does-not-share.md) proposes making the
  > four-container split operable, so the reading surface can be taken down without stopping
  > the record. This record is not edited; the note is appended (ADR 0001).
- **The enrichment box is not production.** It pulls work batches and pushes assertions
  through an internal API reachable only over Tailscale; it can be off for a week without
  anything user-facing noticing.

## Consequences

Production is one small instance plus S3 plus SES: deliberately boring, roughly $12–24 a
month before storage. Operations are a compose file and a systemd timer. The registry
walked on RMI-AI-MACHINE moves to the instance as a copy of a SQLite file and a blob
directory — not a migration. The cost: one machine is one machine; there is no horizontal
story, and none is needed at ~250 events a month. PostGIS, when the geographic index gets
real, is a replay of the ledger into Postgres.

## Cost of reversing

Low to moderate, by design. The store replays; blobs are already in S3; the compose file
runs anywhere Docker does. What would hurt is losing the S3 bucket, which is why nothing
else in this record is allowed to be the only copy of anything.

## Validation (2026-08-25)

Checked against [`../validation-queries.md`](../validation-queries.md): the five queries do
not depend on where the store runs, and none needs anything SQLite lacks at the wedge's
scale. The one query that will outgrow it — query 1's geometry intersection — is answered by
the replay path this record relies on (ledger → Postgres/PostGIS) rather than by choosing
Postgres now. The web tier built the same day runs read-only against the SQLite store
exactly as this record assumes.
