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
| host timer | `docketyard-dump.timer` | nightly 04:10 UTC: `docketyard dump` cuts the public snapshot into `data/public` (served at `/data/files/`) |
| maintenance | `data/flags/maintenance` | ADR 0020. `touch` it and the proxy answers every path except `/health` with a 503 and the maintenance page, per request and with no reload; `rm` it to come back. `ingest` and `litestream` never observe it, so the record keeps being kept — verified 2026-09-02 with `web` stopped outright |
| host timer | `docketyard-webwatch.timer` | every minute: restarts `web` if its healthcheck says `unhealthy`. Docker does not do this itself — `restart:` reacts to a process exiting, not to failing health — and on 2026-09-02 the container reported `unhealthy` for hours while nothing acted on it. `web` alone, never the stack: `ingest` and `litestream` keep the record either way |
| host timer | `docketyard-blobs.timer` | every 30 min: `aws s3 sync` of `data/blobs`, then `prune_blobs.py` deletes local blobs S3 holds (older than 30 days, or oldest-first below 20 GB free) — S3 is the store, the instance is a cache |

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
   sudo apt update && sudo apt install -y docker.io docker-compose-v2 rsync unzip
   # Noble has no awscli package; install AWS CLI v2 from the official archive
   cd /tmp && curl -sS https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip \
     && unzip -q awscliv2.zip && sudo ./aws/install && rm -rf aws awscliv2.zip
   sudo usermod -aG docker "$USER" && newgrp docker
   sudo mkdir -p /srv/docketyard/data && sudo chown -R "$USER" /srv/docketyard
   # copy compose.yaml, Caddyfile, litestream.yml, the two systemd units, and .env
   # (from docketyard.env.example) into /srv/docketyard
   sudo chown -R 1000:1000 /srv/docketyard/data     # the image's uid
   sudo cp /srv/docketyard/docketyard-blobs.* /etc/systemd/system/
   sudo systemctl enable --now docketyard-blobs.timer
   sudo cp /srv/docketyard/docketyard-dump.* /etc/systemd/system/
   sudo systemctl enable --now docketyard-dump.timer   # nightly public snapshot (M9)
   sudo cp /srv/docketyard/docketyard-webwatch.* /etc/systemd/system/
   sudo systemctl enable --now docketyard-webwatch.timer  # restart web when it is unhealthy
   ```

### Deploying a migrating release (ADR 0020)

A release that carries migrations rolls back by Litestream restore, not by a tag change, so
it is deployed behind the wall rather than under readers:

```sh
cd /srv/docketyard
touch data/flags/maintenance                 # readers get 503 + the page, immediately
curl -sD- -o /dev/null https://docketyard.org/ | head -1   # confirm: 503
# `ingest` and `litestream` keep running throughout — the record is still being kept
$EDITOR .env                                 # set DY_TAG to the new release
docker compose pull && docker compose up -d
docker compose logs migrate                  # the migrations ran, and what they said
curl -s https://docketyard.org/health        # answers throughout; check `schema`
rm data/flags/maintenance                    # back
```

Verify against the live store *before* clearing the flag: that is the whole point of the
window. If the migration is wrong, restore from Litestream while nothing else is writing.

4. **Seed the store** from rmi-ai-machine — a copy, not a migration (ADR 0012). Stop any
   writer on the source first so the WAL is checkpointed:

   ```sh
   # on rmi-ai-machine
   sqlite3 /data/docketyard/docketyard.sqlite "PRAGMA wal_checkpoint(TRUNCATE);"
   rsync -avz --progress /data/docketyard/ ubuntu@<static-ip>:/srv/docketyard/data/
   ```

   The one-shot `migrate` service brings the store to the release's schema before anything
   else starts; `serve` refuses a store that is behind, which is why nothing races it.

   **A release that rebuilds the search index should rebuild it in the deploy window.** Run
   `docker compose run --rm ingest search rebuild` straight after `migrate` (the image's
   entrypoint IS `docketyard`, so the subcommand alone is the whole argument), so the index
   is remade while you are watching rather than at the end of the first full pass. An index
   left stale or empty answers "Nothing on record" rather than an error — indistinguishable
   from a genuine miss. Migration 0012 was such a release.

   **This applies to any release that bumps `INDEX_FORMAT` in `store/search.py`, not only
   to one with a migration**, because the format is part of the index's signature: bumping
   it makes the next pass rebuild everything whether or not the schema moved. v2026.08.45
   (`INDEX_FORMAT` 3) is such a release.

   **It is not urgent, and an earlier version of this paragraph said it was.** Measured on
   the instance 2026-08-31 at 96,225 rows: 24.1 s in all, of which the write transaction —
   the only part holding the write lock — is **5.6 s**, well inside the 30 s `_connect_rw`
   waits. A `POST /subscribe` landing mid-rebuild waits about five seconds; it does not
   fail. The 32 s previously quoted here was whole-command wall time read as lock time.
   (Docket-number lookups are unaffected either way: they never touch the index.)

   **Rollback is not a tag change for a release that migrates.** `serve` refuses a store
   whose `user_version` differs from the image's in EITHER direction, so once `migrate` has
   run, the previous image will not start against the store. Recovery is a Litestream
   restore to a point before the migration, not `docker compose pull` on the old tag.
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

Since 2026-08-27 the **web tier holds its own key** (IAM user `docketyard-web`,
`DY_WEB_AWS_*` in `.env`): `s3:GetObject` on `blobs/*` and SES send from the alerts
address, nothing that writes, deletes or lists. The internet-facing process can therefore
read a pruned document and send a confirmation email, and nothing else; the read/write pair
(`docketyard-instance`) stays with `ingest` and Litestream. Compose refuses to start `web`
without the web key.

The bucket has versioning on and, since 2026-08-28, a lifecycle rule
(`expire-noncurrent-versions-30d`): noncurrent versions expire after 30 days, expired
delete markers are removed, and incomplete multipart uploads are aborted after 7 days. The
store is content-addressed and the blob sync compares by size, so a noncurrent version only
arises from a deliberate overwrite or delete; 30 days is the window to undo one.
