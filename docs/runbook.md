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

Not yet built. See [`stb-data-source.md`](stb-data-source.md) for endpoint mechanics. The failure
mode to guard against: passing search criteria as plain POST fields returns a **full unfiltered
result set with a 200**. Any ingest code must positively assert the filter applied, not merely
that the call succeeded.
