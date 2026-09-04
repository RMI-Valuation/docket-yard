# Runbook

Failure modes and their fixes, written while the knowledge is fresh. Grows by one entry each time
something breaks. Does not need to be polished.

---

## DNS and redirects

**Live and verified 2026-08-25.** Sixteen redirect hostnames plus `www.docketyard.org` all return
301 to `https://docketyard.org`, path and query string preserved, valid certificates throughout,
no redirect chains. Verified from outside the operator's network.

Configuration is code: `infra/cf_redirects.py`, idempotent, safe to re-run. If a zone is ever
clobbered, re-running restores it.

- **Adding a domain:** append to `REDIRECT_DOMAINS`, create a token with the scopes in the script
  header, run `--dry-run`, then apply, then `--verify`. Revoke the token afterwards.
- **`Zone : Single Redirect : Edit`** is the token scope people miss. Cloudflare renamed it from
  "Dynamic Redirect"; the API phase is still `http_request_dynamic_redirect`.
- **The apex `AAAA` records point at `100::`** — the IPv6 discard prefix. Deliberate. Cloudflare
  needs a proxied record to answer on; the redirect fires at the edge before any origin fetch;
  a black-hole address means misconfiguration fails closed.
- **The canonical zone's rule matches only `www.docketyard.org`.** A blanket rule there would
  redirect the apex to itself forever.
- **A redirect that works on http but not https** means a certificate is missing on that
  hostname, not a rule problem. Newly added zones take a few minutes for issuance.

## Working with the repo from a Claude session

**Do not let a remote session run `git` against the mounted folder.** The desktop bridge cannot
unlink files, so git strands `.git/index.lock`, `.git/HEAD.lock` and temp objects, and a stranded
`index.lock` blocks every subsequent git command. The repository survives (`git fsck` stays
clean) but the locks have to be cleared from Windows.

Recovery:

```powershell
Remove-Item .git\HEAD.lock, .git\index.lock, .git\objects\maintenance.lock -Force
Get-ChildItem .git\objects -Recurse -Filter "tmp_obj_*" | Remove-Item -Force
git gc --prune=now
```

Same restriction means `unzip -o` cannot overwrite through the bridge. File updates go through
the commit path, not by unpacking an archive over existing files.

## Secrets

Nothing is stored. Tokens are created with a short TTL and IP restriction, used, and revoked.
In PowerShell use `Read-Host -AsSecureString` rather than assigning inline — PowerShell writes
every typed command to a plaintext history file.

## Production instance

Bootstrap, deploy, rollback, restore and health checks: [`../infra/deploy/README.md`](../infra/deploy/README.md).
The forward poller is `docketyard poll --every 1800` in the `ingest` service; one line per
pass in its log, `problems: []` when healthy. A pass whose slice reads `partial` on page 1
is the no-results trap (criteria, sort or nonce), not a quiet week — the window is seven
days precisely so that an empty result is implausible.

## The address key (`DY_EMAIL_KEY`)

Subscriber addresses are stored as an HMAC plus a Fernet ciphertext under this key
(`alerts/vault.py`, migration 0005). It lives in `/srv/docketyard/.env` on the instance and
in the operator's password manager — **nowhere else**: not the store, not S3, not a backup,
not the repo. `docketyard vault new-key` prints a fresh one.

- **Without the key** both services fail closed: the subscribe form answers 503 and the
  poller builds no alerts (`skipped: no sender or no DY_EMAIL_KEY` in the pass line).
- **Losing the key** loses every subscription (the ciphertext is unreadable). Recovery is
  to generate a new key and let people subscribe again; there is nothing else to restore.
- **Rotating** the key needs a re-encryption pass (decrypt under old, seal under new) — not
  written yet; do it in one sitting with both keys in the environment.
- **Restoring the store elsewhere** (a dev copy, a new box) restores ciphertext. That is the
  point: a `litestream restore` on a laptop holds no readable address.

## Mail (SES, us-east-2)

Set up 2026-08-26. Identity `docketyard.org` verified (DKIM: three `*._domainkey` CNAMEs;
custom MAIL FROM `mail.docketyard.org` with MX + SPF; DMARC `p=quarantine` reporting to
`dmarc@rmivaluation.com`), all DNS-only in Cloudflare. Sending is over SMTP
(`email-smtp.us-east-2.amazonaws.com:587`, STARTTLS) as the instance user
`docketyard-instance`, whose second inline policy `docketyard-ses-send` allows
`ses:SendRawEmail` only from `alerts@docketyard.org`. The SMTP password is derived from the
IAM secret in `docketyard.alerts.mail.smtp_password`; a real login proved it.

- **Production access was granted 2026-08-26** (requested the same day from the CLI). A
  new region or account starts in the sandbox — 200 messages a day, verified recipients
  only. Check: `aws sesv2 get-account --region us-east-2`.
- **535 on login** — the password derivation drifted or the key was rotated. Re-derive;
  the derivation is pinned by `tests/test_mail.py` in shape only, so a real login is the
  test.
- **554 Message rejected: Email address is not verified** — sandbox, see above.
- **Bounces and complaints feed back automatically** (from v2026.08.11): sends carry
  `X-SES-CONFIGURATION-SET: docketyard`; the configuration set's event destination
  publishes BOUNCE and COMPLAINT to the SNS topic `docketyard-ses-feedback`, which POSTs
  to `https://docketyard.org/ses/feedback`. The endpoint verifies the SNS signature and
  the topic ARN (`DY_SES_FEEDBACK_TOPIC`) before believing anything, then writes the
  address's HMAC to `email_suppression`. Check the subscription:
  `aws sns list-subscriptions-by-topic --region us-east-2 --topic-arn <arn>` — status must
  not be `PendingConfirmation`. `docketyard status` does not yet count suppressions; the
  ingest log line `ses feedback: bounce, 1 address(es) suppressed` is the trace.
- **SES's own account-level suppression list swallows sends silently** (measured
  2026-08-26): a hard bounce puts the address on it, and every later message to that
  address is accepted with a 250 and never delivered — our `alert` row says `sent`. Check
  `aws sesv2 list-suppressed-destinations --region us-east-2`; clear a legitimate address
  with `delete-suppressed-destination`. The first `hello@` test bounced before Cloudflare
  routing was live and suppressed the address for two later tests this way.

## Blobs: S3 is the store, the instance is a cache

From 2026-08-26 the host timer syncs `data/blobs` to S3 every 30 minutes and then runs
`prune_blobs.py`, which deletes a local blob only if a fresh S3 listing holds its key, and
then only when it is older than 30 days or free disk is under 20 GB (oldest first, back to
28 GB). The site never reads blobs (every entry links the Board's file), so nothing
user-facing changes; a document's bytes are fetched from S3 by hash when needed. A wave's
documents (wave 3: 150–250 GB) therefore pass through the 58 GB instance disk. If the
timer fails, the wave fills the disk: the heartbeat's `last_forward_capture` goes stale
when SQLite cannot write, which is the page. `systemctl status docketyard-prune` and the
sync unit's journal say why. RMI-AI-MACHINE pulls documents from S3 (read-only IAM user
`docketyard-reader`), not from the instance.

## Backfill waves

A wave adds history in dated slices (`docs/stb-data-source.md` § The 10,000 cap forces
it). It runs **on the instance**, against the same store the poller keeps, stamped
`backfill` so nothing it observes can alert; it is resumable from the store alone, so an
interrupted wave is simply run again.

```sh
cd /srv/docketyard
tmux new -s wave            # an SSH drop must not kill it
docker compose run --rm backfill --start 2024-08-01 --interval 4   # to the day the watch began
docker compose run --rm backfill --start 2024-08-01 --interval 4 --fetch-limit 500  # files in bites
```

Start on the 1st of a month: a slice of a few days at the start can be genuinely empty, and
an empty first page is treated as the trap, so it would stay `partial` forever. Use
`--interval 4` while the poller is up — two clients at 2 s each is twice the politeness
budget the endpoint was measured under. The poller fetches the watch's own files first;
the wave's backlog is the wave's.

One slice per calendar month per table (~2 s a page); documents follow at ~1 s each. A
two-year wave is ~100 table pages and a few thousand documents — an evening. The wave
prints `== YYYY-MM` per slice and a `wave {...}` summary; `partial` slices are re-run by
the next invocation, `capped` should never appear (a month is far below the cap). The
coverage page's "History before …" line is measured from the store and updates itself.

Interaction with the poller: both write the one WAL store; SQLite serialises them. A record
the wave re-observes inside the poller's window is unchanged and makes no event; if the
Board changed it in between, the wave's event carries a `backfill` capture and does not
alert — the poller's next observation matches the new state and stays quiet too. Rare and
accepted; the sheet is right either way.

## Ingest — STB endpoint

Endpoint mechanics and every measured trap: [`stb-data-source.md`](stb-data-source.md). The
pipeline asserts the filter positively on every capture and quarantines anything it cannot
prove; a quarantined capture is never ingested but its raw body is always kept.

**The registry walk (running on rmi-ai-machine).** About 640 requests, ~25 minutes at the
polite 2-second interval; resumable — rerunning continues where it stopped.

```sh
# once: code + environment on the box (Ubuntu 24.04 ships Python 3.12 but not venv or tmux)
sudo apt install -y git python3-venv tmux
git clone https://github.com/RMI-Valuation/docket-yard.git ~/docket-yard
cd ~/docket-yard && python3 -m venv .venv && . .venv/bin/activate && pip install -e .
sudo mkdir -p /data/docketyard && sudo chown "$USER" /data/docketyard

# the walk, inside tmux so an SSH drop does not kill it — tmux opens a FRESH shell, so the
# venv and DY are set inside it (`tmux attach -t walk` to return later)
tmux new -s walk
cd ~/docket-yard && . .venv/bin/activate
export DY="--db /data/docketyard/docketyard.sqlite --data-dir /data/docketyard"
docketyard $DY walk dockets          # exit 0 = every prefix done, the census-empty six empty
docketyard $DY ingest dockets        # consumes every asserted capture into the ledger
docketyard $DY status                # expect ~30,200 dockets (a little more: parents
                                     # minted for sub-dockets whose parent never prints)
```

**Watching it.** The walk prints a line per page and a status line per prefix in its tmux
session (`tmux attach -t walk`; `Ctrl-B D` detaches without stopping it). From a second
shell, `watch -n 30 docketyard $DY status` follows the counts — SQLite is in WAL mode, so
reading while the walk writes is safe. `captures_quarantined` should sit at exactly 6 (the
census-empty prefixes); anything higher means a slice was refused and the log says why. The
`walk_slice` table is the durable per-prefix record a rerun resumes from. There is no
off-box heartbeat by design — that belongs to the cloud side (`architecture.md`).

What each prefix's status means:

- **done** — paged to the end AND the rows reconcile with the endpoint's reported total.
- **empty** — page 1 was the no-results envelope on one of the six prefixes the census
  found empty (ARB ASC DSO RER S5A SUS). Each leaves exactly one quarantined capture, once;
  reruns skip them.
- **partial** — rerun. The prefix is re-captured from page 1 (capture ids repeat; ingest
  is idempotent). A partial marked **TRAP** in the log is the no-results envelope on a
  prefix the census says is non-empty: the criteria format, the sort key, or the nonce
  broke. An expired nonce mid-slice is retried once with a fresh nonce automatically.
- **capped** — the display cap; needs sequence sub-slicing. Should never appear: no prefix
  reaches 10,000. Reruns skip it rather than re-burning 200 requests.

A walk that captured nothing exits 1 even if every slice says "empty": that is the trap,
not success.

Until the cloud store exists, the walk's output lives on the box under `/data/docketyard`.
Blobs are content-addressed and the store is rebuildable from captures, so moving it later is
a copy, not a migration.

- **403 on every request** — the WAF's User-Agent rules changed; see the UA note in
  `stb-data-source.md`.
- **`captures_unjudged` in status** — a capture saved but never verdicted (a crash between
  save and parse). Not a criteria failure; harmless, and the raw is in the blob store.
- **The dockets table order** is only stable under `sort_by=docketNum`; the walk pins it.
  Never page the table unsorted. Any manual `capture dockets` test before a walk should use
  `--mode backfill` so its events never reach a forward alert join.

## The citator's first load — planned 2026-09-04, NOT RUN

The whole chain was rehearsed on that date against a `VACUUM INTO` copy of production and
runs clean; production still holds `citation` 0 rows. What follows is what a real load would
be, with the blockers named first, because **two of them are not steps — one is missing code
and one is a decision about people.**

### What it would write, measured on the copy

    readings        20,062      findings   73,101   (41,954 captions, 31,147 citations)
    citation rows   73,101      judgements 219,303  (three per finding)
    resolution      71,185 resolved, 1,915 unresolved, 1 repaired
    PROJECTED       18,907 rows -> 15,164 distinct (citing work, target) edges,
                    over 5,294 citing works and 3,529 proceedings cited
    review owed     citation_exposed 1,946   citation_unresolved 489   citation_repaired 1
    failures        0 failed, 0 unreadable, 0 out of class

Wall clock on the instance: the finder ~45 s over 139,805 pages; the load a few minutes,
committing per document so the poller is never locked out for the run.

### ~~Blocker 1~~ — CLEARED 2026-09-04: `citator declare --scores`

`citator load` refuses a batch it cannot stamp (`methods.Unscored`), because ADR 0017 D3 says
a class nobody has scored is unmeasured and projects nothing — and until this date no shipped
verb could satisfy it. The operator chose the shape on 2026-09-04, out of three that were
weighed (the reasoning is kept in `citator/scorecard.py`): **the figures come from the tool
that measured them and are re-typed by nobody.**

    # on the enrichment box, against the sixty-decision sheet
    python tools/rmi-ai-machine/citation_dryrun.py --scores-out data/citator-scores.json
    # it writes the card ONLY if the run agreed with itself; a failing run leaves none

    # on the instance
    docker compose run --rm --no-deps ingest citator declare         --scores /data/citator-scores.json </dev/null

The card carries COUNTS and never a precision, so it cannot claim one its own numbers do not
support; `declare` computes each stage's precision from them, over that stage's own
denominator. It refuses a card that does not say what it measured, one whose extractor is not
this build's, and one with a zero denominator — `0/0` is not a small precision, it is no
measurement. Declaring the same card twice is a refusal, not a traceback.

**The card's `extractor_version` must be the findings' `method_version`** (both are
`find.FINDER_VERSION` in production). ADR 0018 D1 allows one owner per class per
rank_version, so a card measuring another pass is refused by the registry rather than quietly
stamping these rows from that pass's figures.

### Blocker 2 — the reviewer, granted 2026-09-04; the capacity is still the question

**Reviewer 1 is the operator, credited "Cameron Rex"** — ADR 0016's reviewer zero, granted by
hand as that record requires, with the address sealed under the vault key and only the credit
name public. Verified after the grant: `email_enc` 120 bytes of ciphertext, `email_hash` 64
hex, no plaintext anywhere in `reviewer`, and `/review` answering with its sign-in form.
`/review` is disallowed for every agent in `robots.txt` and is in no sitemap.

    docker compose run --rm --no-deps ingest citator grant <email>         --credit-name '<how they are shown>' --note '<the operator's reason>' </dev/null

The grant needs the vault key, which `ingest` carries; `decide` does not, which is what lets
a review happen on a box that cannot read an address. Signing in is the reviewer's own act:
`/review`, enter the address, follow the emailed link.

**The capacity question stands.** A load creates **1,946 exposed keys** that the projection
holds back until a human answers them, against five on the sixty-decision sheet — thirty
seconds of reading each is about sixteen hours. One reviewer exists; whether one is enough
for that backlog is the decision, and loading first is allowed because the edges are simply
held, which is what the gate is for.

### Blocker 3 — the figures are the benchmark's, and the load does not change that

Every one of the 15,164 edges would be stamped with a precision measured on sixty decisions.
A corpus run cannot check it: recall and precision need hand-made ground truth and there is
none for 19,229 decisions. The load is therefore a decision to publish edges at a stated
confidence, not a measurement of that confidence — and `/methodology` says what the figure
is measured on.

### The steps, once those are settled

    # 1. behind the wall? NO — the load commits per document and holds no long lock, and
    #    `web` serves the same store throughout. But nothing may write the page index or
    #    load text beside it (see `search rebuild-pages`).
    docker compose run --rm --no-deps ingest citator find /data/citation-findings </dev/null
    # one subdirectory per reading channel; today that is `text-layer` alone, and after the
    # OCR wave lands there will be an `ocr` one, which is its OWN batch and its own
    # measurement — a channel nobody has scored is refused, by design (ADR 0018 D8).

    # 2. declare the methods and the measurements, from the scorer's own card
    docker compose run --rm --no-deps ingest citator declare         --scores /data/citator-scores.json </dev/null
    # it prints the recall and precision it just recorded per stage. An EDGE carries the
    # RESOLUTION class's precision (ADR 0017 D3), not the projection's.

    docker compose run --rm --no-deps ingest citator load \
        /data/citation-findings/text-layer </dev/null
    # it prints the totals and what the queues now hold. `failed` must be 0.

### Verifying, and going back

    docker compose run --rm --no-deps ingest citator cited-by --docket <id> </dev/null
    docker compose run --rm --no-deps ingest citator review citation_exposed </dev/null

Rollback is Litestream restore, as for any migrating change — but note the load writes no
schema and supersedes nothing, so an unwanted load is *additive*: the rows can also be left
in place and the projection starved by withdrawing the measurement, which is ADR 0017 D3's
own mechanism ("unmeasured projects nothing"). That is the cheaper reversal and the one to
reach for first.
