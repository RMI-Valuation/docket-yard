# Infrastructure

## `rmi-ai-machine.md`

Step-by-step conversion of the batch-enrichment box from Windows to headless Ubuntu Server,
written for a first Linux install. See [`rmi-ai-machine.md`](rmi-ai-machine.md).

## `cf_redirects.py`

Configures Cloudflare so every non-canonical domain 301s to `https://docketyard.org`, preserving
path and query string. Idempotent — safe to re-run.

```bash
export CF_API_TOKEN=...
python3 infra/cf_redirects.py --dry-run
python3 infra/cf_redirects.py
python3 infra/cf_redirects.py --verify
```

Token scopes are documented in the script header. `Zone : Single Redirect : Edit` is the one
people miss — Cloudflare renamed it from "Dynamic Redirect", though the API phase is still
`http_request_dynamic_redirect`.

### Domains

| Domain | Role |
| --- | --- |
| `docketyard.org` | **Canonical.** Everything else points here. |
| `docketyard.com`, `docketyard.net` | Defensive |
| `docketcommons.org`, `docketcommons.com` | Umbrella name, held |
| `stbdocket.org`, `stbdocket.com` | Descriptive doorway |
| `stbwatch.org`, `stbwatch.com` | Descriptive doorway |

The redirect zones carry a proxied `AAAA` on the apex pointing at `100::`, the IPv6 discard
prefix. That is deliberate: Cloudflare needs a proxied record to answer on, the redirect fires
at the edge before any origin fetch, and a black-hole address means a misconfiguration fails
closed rather than leaking traffic somewhere real.

The canonical zone is handled differently — its rule matches only `www.docketyard.org`, because
a blanket rule there would redirect the apex to itself forever.
