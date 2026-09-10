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
| host timer | `docketyard-adhoc.timer` | every 5 min: `adhoc_watch.sh` measures the longest-running BUSY process in the user slice and writes it as a gauge. It judges nothing (ADR 0019); the threshold is in Grafana. It exists because the 2026-09-06 outage was invisible to a no-data alert — the record was fresh and the poller fine, and the site simply could not serve |
| guard | `user-1000.slice.d/limits.conf` | caps ad-hoc ssh work at `CPUQuota=50%` — half of ONE core of two — with `MemoryHigh=1G`/`MemoryMax=2G`. Nothing operational lives in that slice; everything real is in `system.slice`. Measured 2026-09-06: a busy loop that would run at 100% runs at 50.1% |
| guard | `sshd_config.d/10-docketyard-clientalive.conf` | `ClientAliveInterval 60`, `ClientAliveCountMax 3`: a session whose client has stopped answering is reaped in about three minutes. sshd's default never probes |
| failure handler | `docketyard-failed@.service` | `OnFailure=` of the four periodic units: `unit_outcome.sh` writes `docketyard_unit_failed{unit=…} 1` into `data/metrics/`, which Alloy's textfile collector ships; the unit's own `ExecStartPost` writes the 0 back on its next success. The alert on the gauge is in Grafana Cloud, off the box. Before this a failed dump served last night's snapshot under an unchanged manifest with nothing saying so |

### The 2026-09-06 outage, and what now bounds it

An operator query — `python3 -` fed a heredoc over ssh — never received EOF on 2026-09-05, so
the session stayed open and the process ran **22 hours** pinning one of two vCPUs at 99%. The
site served through it. When `docketyard-blobs.timer` then took another 43-76%, `web` was left
with a fraction of a core: requests took 8-30 s, the healthcheck failed, `webwatch` restarted
the container, and the restarts compounded it. Load average reached 20.

**It was not a traffic flood**, though it looked like one: 183 requests in 3 minutes — about
one a second — of which Caddy logged 259 × 200 against 13 × status-0 over the window. The
record was fresh and the poller was fine throughout, which is why no existing alert fired.

Three guards followed, and what each is honestly worth:

- **the CPU cap bounds the class**, not the instance. Any ad-hoc command — a person's or an
  agent's at a person's direction — is now held to half a core, so the services keep 1.5
  whatever anyone runs. This alone would have prevented the outage.
- **`ClientAlive` closes an adjacent hole.** It would probably NOT have caught this one: when
  found, sshd was still alive and the connection had not dropped.
- **the gauge measures what nothing measured.** Not a decision: Grafana holds the threshold.

**Habit, which is what actually failed:** `</dev/null` and a remote `timeout` on every ad-hoc
command sent over ssh. A command that never closes its stdin does not end, it persists. The
structural answer, not taken yet, is to stop querying the serving store at all — restore a
Litestream replica and analyse that.

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
   # the text stage's two bind mounts, made HERE so the chown below reaches them: Docker
   # creates a missing bind source as root, and both the parser and the loader run as 1000,
   # so a first `up` would otherwise leave the stage unable to write with a permission
   # error rather than a reason (ADR 0024; security review 2026-09-10)
   mkdir -p /srv/docketyard/data/extract/spool /srv/docketyard/data/extract/requests
   # copy compose.yaml, Caddyfile, litestream.yml, the two systemd units, and .env
   # (from docketyard.env.example) into /srv/docketyard, AND the `infra/extract/`
   # directory as /srv/docketyard/extract — it is the parser's build context (ADR 0024),
   # the one service built on the box rather than pulled
   sudo chown -R 1000:1000 /srv/docketyard/data     # the image's uid, and the parser's
   sudo cp /srv/docketyard/docketyard-blobs.* /etc/systemd/system/
   sudo systemctl enable --now docketyard-blobs.timer
   sudo cp /srv/docketyard/docketyard-dump.* /etc/systemd/system/
   sudo systemctl enable --now docketyard-dump.timer   # nightly public snapshot (M9)
   sudo cp /srv/docketyard/docketyard-webwatch.* /etc/systemd/system/
   sudo systemctl enable --now docketyard-webwatch.timer  # restart web when it is unhealthy
   sudo cp /srv/docketyard/docketyard-failed@.service /etc/systemd/system/ && chmod +x /srv/docketyard/unit_outcome.sh
   sudo systemctl daemon-reload                             # the units' OnFailure= handler
   # the three guards from the 2026-09-06 outage (§ above): the ad-hoc gauge, the user-slice
   # cap, and the ssh keepalive. A rebuild without them has the outage's shape again.
   sudo cp /srv/docketyard/docketyard-adhoc.* /etc/systemd/system/ && chmod +x /srv/docketyard/adhoc_watch.sh
   sudo systemctl enable --now docketyard-adhoc.timer
   sudo mkdir -p /etc/systemd/system/user-1000.slice.d
   sudo cp /srv/docketyard/user-slice-limits.conf /etc/systemd/system/user-1000.slice.d/limits.conf
   sudo systemctl daemon-reload && sudo systemctl restart user-1000.slice
   sudo cp /srv/docketyard/sshd-clientalive.conf /etc/ssh/sshd_config.d/10-docketyard-clientalive.conf
   sudo sshd -t && sudo systemctl reload ssh
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
docker compose pull --ignore-buildable && docker compose up -d --build
docker compose logs migrate                  # the migrations ran, and what they said
curl -s https://docketyard.org/health        # answers throughout; check `schema`
# a release that changes the display view (search.PAGE_INDEX_FORMAT) rebuilds the page
# index HERE, still behind the wall: until it runs the index holds the old view's bytes,
# which every later 'delete' then fails to clear. It is BATCHED since v2026.09.7, so it no
# longer holds the write lock for its whole run (it did: 27 m 26 s at 1.1 M rows) — the
# poller and Litestream get in between batches — but it still EMPTIES the index first and
# fills it back, marking `search_meta.page_built` 'rebuilding' meanwhile. `web` refuses to
# start against that mark, a page search that reaches a running `web` says the text index
# is being rebuilt rather than answering short, and `text load` refuses to run beside it.
# So: stop web first and start it after, and do not load text in another shell until it is
# done. A rebuild that dies leaves the mark; re-run it, no --force needed. Watch the
# `page index: N rows` lines — it prints its progress
docker compose stop web
docker compose run --rm --no-deps ingest search rebuild-pages </dev/null
docker compose start web
rm data/flags/maintenance                    # back
```

Verify against the live store *before* clearing the flag: that is the whole point of the
window. If the migration is wrong, restore from Litestream while nothing else is writing.

**Both halves of that were rehearsed on 2026-09-02 against the real store**, because neither
had ever been tested and the whole hesitation about a migrating deploy rested on them:

- **The rollback works.** `litestream restore` reconstructed the store from S3 into a scratch
  path, and the result matched the live database on every fact checked — schema, and the row
  counts of `capture` (110,118), `event` (145,522), `docket` (32,627), `filing` (54,642),
  `decision_record` (23,716), `enviro_comment` (34,381), `enviro_comment_attachment` (26,949)
  and `document` (104,091) — with `integrity_check` ok and zero foreign-key violations. No
  differences. The restore is the reason a migrating deploy is survivable, and it is now a
  measurement rather than an assumption.
- **Migrations 0014-0017 apply to that data in 2.2 s**, landing at schema 17 with
  `integrity_check` ok and zero foreign-key violations, and the whole site then serves from
  the migrated store: home, `/coverage`, `/methodology`, `/parties`, `/dockets`, `/stats`,
  `/api`, `/llms.txt`, the docket sheets and the record pages, all 200.

Rehearse it again if the release carries a migration this one did not.

**Rehearsed again 2026-09-10 for migrations 0022–0024 against a live copy (4.28 GB, schema
21).** Each applied cleanly with `integrity_check` ok and zero foreign-key violations — and
each took **about 280 s**, including 0023, which only creates a table. That time is the
runner's `PRAGMA foreign_key_check` after every script, which walks every child row in the
store; at 976,058 text pages it is minutes, where the 2026-09-02 rehearsal's 2.2 s was a
store without them. **On the live store the same three ran in 50 s in all** (deployed
2026-09-10 10:51 UTC): the copy was cold and the live store's pages were cached. Budget the
five minutes per migration anyway, and expect the `migrate` service to look idle while it
checks. A per-table check in `db.migrate` would cut it and is recorded in `docs/deferred.md`.

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
5. **Start**: `cd /srv/docketyard && docker compose pull --ignore-buildable && docker compose up -d --build`, then
   watch the first pass in `docker compose logs -f ingest`.
6. **Check**: `curl -sI https://docketyard.org/` is 200; `docker compose ps` shows `web`
   healthy and `ingest`, `litestream`, `caddy` running (`migrate` exited 0); the S3 bucket
   gains `litestream/` within a minute and `blobs/` after the first timer run
   (`systemctl list-timers`).

## Routine operations

- **Deploy a release**: edit `DY_TAG` in `.env`;
  `docker compose pull --ignore-buildable && docker compose up -d --build`. The flags are for
  ONE service: `extract` (ADR 0024's parser) is built on the box from `infra/extract` rather
  than pulled, because it is deliberately not the application image — a plain `pull` tries to
  fetch its local-only tag and fails the whole deploy.
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

## Resizing the instance (a rebuild)

A Lightsail bundle change is a new instance from a snapshot, not a slider, and while the
writers are stopped the record is not being kept: it is a coverage gap and is recorded as
one (ADR 0022 D5). Done 2026-09-03/04, small_3_0 to large_3_0: 55 minutes of gap
(23:40–00:35 UTC), no records missed — the first poll on the new box re-walked the window
and found nothing it did not hold. In the order that loses nothing:

1. `touch data/flags/maintenance`; confirm the 503.
2. `docker compose run --rm --no-deps web gap open captures --note "planned instance resize
   (ADR 0022 D5)"` — before the writers stop, so the snapshot carries the open gap and the
   new box closes it.
3. `sudo systemctl disable --now docketyard-dump.timer docketyard-blobs.timer` and
   `sudo systemctl stop docketyard-webwatch.timer`. Both timers are `Persistent=true`: left
   enabled, the new box fires every missed run on first boot. `mask` fails here — the units
   are real files in `/etc/systemd/system` and masking needs the path free — and `disable`
   gives the same guarantee, since a disabled timer never starts. Webwatch would restart
   `web` under you.
4. `docker compose stop ingest web litestream` — all three: Litestream holds a read
   transaction that blocks the truncate. Leave `caddy` up; it keeps serving the page.
5. Checkpoint with the host's `python3` (no `sqlite3` CLI on the box): `PRAGMA
   wal_checkpoint(TRUNCATE)` on `docketyard.sqlite` and `traffic.sqlite`, expect `(0, 0, 0)`
   and no `-wal` file; `PRAGMA quick_check`; `sync`.
6. `aws lightsail create-instance-snapshot` — nine minutes for 60 GB. The TLS certificate is
   in the `caddy-data` volume, inside the snapshot: that is why a snapshot and not a fresh
   instance plus rsync.
7. `sudo systemctl disable docker.service docker.socket containerd.service` on the old box;
   stop them just before the IP moves, so caddy serves the page until then. Two Litestreams
   replicating divergent stores to one path is the failure this prevents.
8. `aws lightsail create-instances-from-snapshot ... --bundle-id large_3_0 --key-pair-name
   docketyard`, then `put-instance-public-ports` for 22, 80 and 443 with their IPv6 ranges —
   the firewall is not in the snapshot, and a new instance opens 22 and 80 only. The root
   filesystem grows to the new disk on first boot by itself.
9. On the new box's temporary IP: the containers are as the snapshot left them, so `docker
   compose --profile metrics up -d`; then `/health` with `--resolve
   docketyard.org:443:127.0.0.1` (the bare IP fails the TLS handshake, no SNI). Check the
   store's counts against the old box and that Litestream opened a new generation.
10. Stop Docker on the old box; `detach-static-ip`, then `attach-static-ip` to the new
    instance; DNS is untouched. Cloud-init regenerates the SSH host keys on a snapshot-born
    instance: `ssh-keygen -R` the static IP before reconnecting.
11. `enable --now` the two timers, `gap close <id>`, `rm data/flags/maintenance`. Stop the
    old instance; delete it once the new one has run a while. Its snapshot is the
    out-of-band copy ADR 0022 D6 asks for — keep it.

Gotcha: a script piped over `ssh 'bash -s'` dies at the first `docker compose run`, which
reads the rest of the script from stdin. Copy the script over and run it by path.

## Open: credentials without an instance role

ADR 0012 assumed the instance reaches S3 through an attached IAM role. Lightsail instances
do not support instance profiles, so the first deployment uses a bucket-scoped IAM user's
keys in `/srv/docketyard/.env` (mode 600). The honest alternatives are an EC2 `t4g.small`
(instance profile, similar price, more knobs) or IAM Roles Anywhere; either is a small
follow-up ADR, not a change to anything else here.

Since 2026-08-27 the **web tier holds its own AWS key** (IAM user `docketyard-web`,
`DY_WEB_AWS_*` in `.env`): `s3:GetObject` on `blobs/*` and SES send from the alerts address,
nothing that writes, deletes or lists. So the internet-facing process can read a pruned
document and send a confirmation email, and nothing else **in S3** — but it is not the whole
of what it holds: `web` takes the `x-mail` anchor, so it also has `DY_EMAIL_KEY`, the key
under which subscriber addresses are ciphertext at rest (ADR 0014). It needs an address to
send a confirmation to; whether that is the right trade is undecided and is in
`docs/deferred.md` (2026-09-04). An earlier version of this paragraph said "and nothing
else", which was wrong about exactly that key.

The read/write pair (`docketyard-instance`) is **not** confined to containers either: it is
in `.env`, which `ingest` and Litestream read and which `docketyard-blobs.service` and
`docketyard-prune.service` also load as root systemd units — the sync and the prune are host
processes and authenticate with it. A third user, `docketyard-reader` (read-only), is used
by RMI-AI-MACHINE to pull blobs (`docs/runbook.md`). Three principals, three scopes.

Compose's `${DY_WEB_AWS_*:?}` guard fails interpolation for the whole file, not just `web`,
so a missing or rotating reader key stops `ingest` too — which is the coupling the file
itself forbids nine lines lower down. In `docs/deferred.md`, 2026-09-04.

The bucket has versioning on and, since 2026-08-28, a lifecycle rule
(`expire-noncurrent-versions-30d`): noncurrent versions expire after 30 days, expired
delete markers are removed, and incomplete multipart uploads are aborted after 7 days. The
store is content-addressed and the blob sync compares by size, so a noncurrent version only
arises from a deliberate overwrite or delete; 30 days is the window to undo one.
