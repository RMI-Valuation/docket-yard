# Deploying the instance

ADR 0012 made physical: one Lightsail instance, Docker Compose, SQLite + Litestream, blobs
synced to S3. Everything here is copied to `/srv/docketyard` on the box. Deploys are
pull-based: change `DY_TAG` in `.env`, pull, up. Nothing pushes to production.

## What runs

| Service | Image | Does |
| --- | --- | --- |
| `web` | `ghcr.io/rmi-valuation/docket-yard:<tag>` | `docketyard serve`, read-only over the store |
| `ingest` | same image | `docketyard poll --every 1800`: capture, ingest, fetch, repeat |
| `litestream` | `litestream/litestream:0.3` | streams the store's WAL to S3 every 10 s |
| `caddy` | `caddy:2-alpine` | TLS (Let's Encrypt), reverse proxy, access log without IPs |
| host timer | `docketyard-blobs.timer` | hourly `aws s3 sync` of `data/blobs` |

One store, two processes: `ingest` writes, `web` reads through a `mode=ro` URI. SQLite WAL
makes that safe on one filesystem; it would not be safe over NFS, which is one reason this
is an instance and not the container service.

## One-time bootstrap

1. **AWS**: an S3 bucket (versioning on, public access blocked) and an IAM user whose only
   policy is object read/write/list on that bucket. Lightsail instances cannot assume an
   instance role — see the note at the end.
2. **Lightsail**: Ubuntu 24.04 LTS, the $12 plan (2 GB) is enough; attach a static IP; open
   ports 22, 80, 443 only. Point the `docketyard.org` apex A record at the static IP as
   **DNS only** (grey cloud) and leave it that way: Caddy issues and renews its own
   certificate over ACME, and a Cloudflare-proxied apex breaks renewal (TLS-ALPN cannot
   pass the proxy; the zone's always-use-HTTPS redirects the HTTP challenge). The
   redirect domains stay proxied — they never reach this box. If proxying the canonical
   host is ever wanted, that is a Cloudflare Origin CA certificate in Caddy, not a toggle.
3. **On the box** (as `ubuntu`):

   ```sh
   sudo apt update && sudo apt install -y docker.io docker-compose-v2 awscli
   sudo usermod -aG docker "$USER" && newgrp docker
   sudo mkdir -p /srv/docketyard/data && sudo chown -R "$USER" /srv/docketyard
   # copy compose.yaml, Caddyfile, litestream.yml, the two systemd units, and .env
   # (from docketyard.env.example) into /srv/docketyard
   sudo chown -R 1000:1000 /srv/docketyard/data     # the image's uid
   sudo cp /srv/docketyard/docketyard-blobs.* /etc/systemd/system/
   sudo systemctl enable --now docketyard-blobs.timer
   ```

4. **Seed the store** from rmi-ai-machine — a copy, not a migration (ADR 0012). Stop any
   writer on the source first so the WAL is checkpointed:

   ```sh
   # on rmi-ai-machine
   sqlite3 /data/docketyard/docketyard.sqlite "PRAGMA wal_checkpoint(TRUNCATE);"
   rsync -avz --progress /data/docketyard/ ubuntu@<static-ip>:/srv/docketyard/data/
   ```

   The one-shot `migrate` service brings the store to the release's schema before anything
   else starts; `serve` refuses a store that is behind, which is why nothing races it.
5. **Start**: `cd /srv/docketyard && docker compose pull && docker compose up -d`, then
   watch the first pass in `docker compose logs -f ingest`.
6. **Check**: `curl -sI https://docketyard.org/` is 200; `docker compose ps` shows `web`
   healthy and `ingest`, `litestream`, `caddy` running (`migrate` exited 0); the S3 bucket
   gains `litestream/` within a minute and `blobs/` after the first timer run
   (`systemctl list-timers`).

## Routine operations

- **Deploy a release**: edit `DY_TAG` in `.env`; `docker compose pull && docker compose up -d`.
  Roll back by setting the previous tag. Releases are the production ledger (ADR 0010).
- **Restore the store** on a fresh box: `litestream restore -o data/docketyard.sqlite
  s3://$DY_S3_BUCKET/litestream/docketyard.sqlite`, then `aws s3 sync s3://$DY_S3_BUCKET/blobs
  data/blobs`.
- **A dev copy of production**: the same `litestream restore` to a laptop. Blobs are fetched
  by hash on demand — most dev work needs none of them.
- **Ingest health**: `docker compose logs --since 1h ingest | grep -c "problems: \[\]"`
  should be about two (one clean pass per `DY_POLL_EVERY`). A `poll …: {… problems: […]}`
  line names what went wrong in that pass; a `pass ABORTED` line is a bug, not the
  endpoint. The off-box heartbeat (M4) is what pages someone.
- **Errata**: the poller fetches each document once. Nothing yet re-fetches known documents
  to catch a silent replacement (`fetch attachments --refresh` exists but is unscheduled);
  see `TODO.md`.

## Open: credentials without an instance role

ADR 0012 assumed the instance reaches S3 through an attached IAM role. Lightsail instances
do not support instance profiles, so the first deployment uses a bucket-scoped IAM user's
keys in `/srv/docketyard/.env` (mode 600). The honest alternatives are an EC2 `t4g.small`
(instance profile, similar price, more knobs) or IAM Roles Anywhere; either is a small
follow-up ADR, not a change to anything else here.
