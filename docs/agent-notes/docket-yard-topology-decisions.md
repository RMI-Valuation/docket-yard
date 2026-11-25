---
name: docket-yard-topology-decisions
description: "Hosting, URL scheme and web-dependency decisions made 2026-08-25 (ADR 0012/0013, FastAPI+Jinja2+uvicorn)"
metadata:
  type: project
---

Decided by Cameron on 2026-08-25 (multiple-choice, all three recommendations accepted):

- **Hosting:** one Lightsail *instance* (not the container service), Docker Compose with
  web/ingest/caddy, SQLite WAL + Litestream to S3, blobs in S3, pull-based deploys per ADR
  0010, IAM role on the instance, heartbeats off-box. ADR 0012.
- **Permanent URLs:** `/d/FD-36873`, `/d/FD-36873/sub/1`, suffix at its level
  (`/d/S5M-1-A`, `/d/AB-55/sub/785X`), `/decision/{id}`, `/filing/{id}`; both source
  parent spellings resolve to canonical; addresses never reused or removed. ADR 0013.
- **Web dependencies:** FastAPI + Jinja2 + uvicorn only; no frontend framework.

**How to apply:** build M3 against these; do not re-ask. ADRs 0012/0013 were Proposed in
the drafting session and await Cameron's accept (ADR discipline: never accepted the same
session they were drafted).

Related: [[docket-yard-github-home]], [[rmi-ai-machine-specs]]
