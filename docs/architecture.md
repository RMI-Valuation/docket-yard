# Architecture

The full-stack topology, settled in discussion 2026-08-25. The mistakes this document
prevents: re-deriving the topology every session, letting promise-bearing duties creep onto
the batch machine, and treating the SQL store as the source of truth.

**What is settled** (by ADRs 0002, 0006, 0007, 0010): the layering, the identity of every
artifact, and the property below. **What is recommendation until a deployment-topology ADR**:
SQLite vs Postgres, Lightsail instance vs container service, server-rendered vs static
generation. None is urgent; none is expensive to reverse, because of the property below.

## The load-bearing property: the store is rebuildable

**Captures (raw response bodies) + document blobs + the event ledger are the source of
truth. Everything else — the SQL store, projections, assertions — can be rebuilt by
replay.** The one-way doors were the schema's grain and identity (closed, ADRs 0002–0008);
the database and hosting choices are two-way doors and are treated as such.

## What runs where

| Machine | Role | Runs |
| --- | --- | --- |
| Dev workstations | Write code, docs, tests | venv, pytest, disposable local SQLite in `data/`, recorded captures as fixtures. Never touches production. No secrets. |
| Cloud (Lightsail instance) | Promise-bearing, always-on | Forward capture (polling), event ledger + store, web app, alert delivery (SES), heartbeat monitoring |
| RMI-AI-MACHINE | Batch, restartable, GPU | LLM extraction passes, OCR of the pre-2000 archive, backfill enrichment |

The rule that assigns a workload: **anything carrying the alert or uptime promise runs in
cloud; anything that can die mid-run and simply resume runs on the batch box.** ADR 0007's
method versioning makes extraction location-independent, which is what licenses the split.

The seam between them is a small internal API on the cloud box, reachable only over
Tailscale: the enrichment box asks for a work batch, fetches blobs from S3, and POSTs
assertion rows back with provenance. The AI machine can be off for a week without anything
user-facing noticing. A dead enrichment box delays the citator; it never touches a docket
sheet or an alert. Heartbeat checks live off-box — a dead machine cannot report its own death.

## Storage

1. **Blobs → S3, keyed by content hash.** ADR 0002 made physical: the object key is the
   identity, writes are idempotent, dedup is free. PDFs plus raw capture bodies for the full
   record ≈ 100–200 GB. This layer is also disaster recovery: the production corpus is
   *practically* irreplaceable — re-pulling 100k documents from a small agency's endpoint is
   rude and slow, so "data/ is reproducible" is a local-dev truth only.
2. **Structured store → SQLite for the wedge** (recommendation). ~250 docs/month forward and
   tens of millions of rows only once the layout IR fills in — inside SQLite's envelope, zero
   ops, WAL mode covers ingest-writes-while-web-reads at this volume. **Litestream** streams
   the DB to S3 continuously: backup and prod-snapshot-to-dev in one tool.
3. **The escape hatch:** when the geographic index gets real (post-wedge), query 1's geometry
   intersection wants PostGIS. That migration is a replay of the ledger into Postgres, not
   data surgery — which is why SQLite-now costs nothing later.

## The web side

One Python app — FastAPI + server-rendered templates — behind Caddy (auto-TLS), on a
Lightsail **instance**, not the container service (no persistent volumes, no cron there).
Docket sheets are extremely cacheable: the agency moves ~250 times a month, so pages
regenerate on events and are static the rest of the time. Version-one search is a docket
lookup; SQLite FTS5 carries fielded search a long way when F4's turn comes. Alert email goes
through SES — never from a box's own IP.

Deploy is the ADR 0010 loop: GitHub release → container image (tag = release = image) → the
instance pulls the release tag. Pull-based; nothing pushes to production.

Production, in full: **one small instance + S3 + SES**, compose running `web`, `ingest`,
`caddy`. Deliberately boring.

## The mental model

The cloud box is a small, boring clerk that never sleeps. The AI machine is a strong worker
that naps between shifts. Dev machines only ever handle copies. S3 holds the one thing that
must never be lost.
