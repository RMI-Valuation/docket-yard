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
