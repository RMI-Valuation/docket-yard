#!/usr/bin/env python3
"""Configure Cloudflare 301 redirects for the Docket Yard domain set.

Points every non-canonical domain (apex and www) at https://docketyard.org,
preserving path and query string. Idempotent — safe to re-run.

For each zone it:
  1. creates or updates a proxied AAAA record on the apex pointing at 100::
     (the IPv6 discard prefix, a deliberate black hole — nothing reaches an origin)
  2. creates or updates a proxied CNAME for www -> apex
  3. installs a single dynamic-redirect rule in the zone's redirect ruleset
  4. turns on Always Use HTTPS

Usage:
    export CF_API_TOKEN=...            # see TOKEN SCOPES below
    python3 cf_redirects.py --dry-run  # show what would change
    python3 cf_redirects.py            # apply
    python3 cf_redirects.py --verify   # check the live redirects afterwards

TOKEN SCOPES — create a CUSTOM token (not a preset) at
dash.cloudflare.com/profile/api-tokens:

    Zone : Zone            : Read
    Zone : DNS             : Edit
    Zone : Zone Settings   : Edit
    Zone : Single Redirect : Edit

Note: "Single Redirect" is what Cloudflare now calls what its API still refers
to as the http_request_dynamic_redirect phase. Older docs and forum posts call
it "Dynamic Redirect"; it is the same thing. If the picker doesn't show it,
"Zone : Transform Rules : Edit" also grants access to the phase.

Set Zone Resources to include all nine zones. A 403 on the rule step means the
Single Redirect scope is missing; a 403 on the settings step means Zone
Settings is missing.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

CANONICAL = "docketyard.org"

# Every domain that should 301 to CANONICAL. CANONICAL itself is handled
# separately below (www -> apex only).
REDIRECT_DOMAINS = [
    "docketyard.com",
    "docketyard.net",
    "docketcommons.org",
    "docketcommons.com",
    "stbdocket.org",
    "stbdocket.com",
    "stbwatch.org",
    "stbwatch.com",
]

API = "https://api.cloudflare.com/client/v4"
BLACKHOLE_V6 = "100::"          # RFC 6666 discard prefix
DRY = "--dry-run" in sys.argv


def token():
    t = os.environ.get("CF_API_TOKEN")
    if not t:
        sys.exit("CF_API_TOKEN is not set. See the docstring for required scopes.")
    return t


def call(method, path, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token(),
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        raise SystemExit(f"\n  API {method} {path} failed ({e.code}):\n  {detail}\n")


def zone_id(name):
    d = call("GET", "/zones?name=" + urllib.parse.quote(name))
    res = d.get("result") or []
    if not res:
        raise SystemExit(f"  Zone not found in this account: {name}")
    return res[0]["id"]


def upsert_record(zid, zone, rtype, name, content):
    """Create or update one proxied DNS record."""
    q = urllib.parse.urlencode({"type": rtype, "name": name})
    existing = (call("GET", f"/zones/{zid}/dns_records?{q}").get("result") or [])
    body = {"type": rtype, "name": name, "content": content,
            "proxied": True, "ttl": 1,
            "comment": "Docket Yard redirect target (no origin)"}
    if existing:
        cur = existing[0]
        if cur.get("content") == content and cur.get("proxied") is True:
            print(f"    {rtype:5} {name:28} ok")
            return
        print(f"    {rtype:5} {name:28} UPDATE -> {content}")
        if not DRY:
            call("PATCH", f"/zones/{zid}/dns_records/{cur['id']}", body)
    else:
        print(f"    {rtype:5} {name:28} CREATE -> {content}")
        if not DRY:
            call("POST", f"/zones/{zid}/dns_records", body)


def set_redirect(zid, zone, target_host, match="true"):
    """Install a single dynamic-redirect rule.

    match="true" redirects every hostname in the zone (apex and www).
    On the canonical zone we pass a narrower match so the apex does NOT
    redirect to itself — that would be an infinite loop.
    """
    expr = f'concat("https://{target_host}", http.request.uri.path)'
    rules = [{
        "action": "redirect",
        "action_parameters": {
            "from_value": {
                "target_url": {"expression": expr},
                "status_code": 301,
                "preserve_query_string": True,
            }
        },
        "expression": match,
        "description": f"301 {zone} -> {target_host} (path preserved)",
        "enabled": True,
    }]
    print(f"    rule  301 -> https://{target_host}/<path>")
    if not DRY:
        call("PUT",
             f"/zones/{zid}/rulesets/phases/http_request_dynamic_redirect/entrypoint",
             {"rules": rules})


def always_https(zid):
    print("    setting always_use_https = on")
    if not DRY:
        call("PATCH", f"/zones/{zid}/settings/always_use_https", {"value": "on"})


def configure(zone, target_host, include_apex=True):
    print(f"\n  {zone}")
    zid = zone_id(zone)
    if include_apex:
        upsert_record(zid, zone, "AAAA", zone, BLACKHOLE_V6)
    upsert_record(zid, zone, "CNAME", "www." + zone, zone)
    set_redirect(zid, zone, target_host)
    always_https(zid)


def verify():
    import ssl
    ctx = ssl.create_default_context()
    hosts = []
    for d in REDIRECT_DOMAINS:
        hosts += [d, "www." + d]
    hosts.append("www." + CANONICAL)
    probe = "/docket/FD-36873?x=1"
    bad = 0
    print(f"\nVerifying {len(hosts)} hostnames (expect 301 -> https://{CANONICAL}{probe})\n")
    for h in hosts:
        req = urllib.request.Request("https://" + h + probe, method="HEAD")

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None

        op = urllib.request.build_opener(NoRedirect,
                                         urllib.request.HTTPSHandler(context=ctx))
        try:
            op.open(req, timeout=20)
            print(f"  {h:34} NO REDIRECT (200)")
            bad += 1
        except urllib.error.HTTPError as e:
            loc = e.headers.get("Location", "")
            ok = e.code == 301 and loc.startswith("https://" + CANONICAL)
            print(f"  {h:34} {e.code} {loc[:64]}{'' if ok else '   <-- CHECK'}")
            bad += 0 if ok else 1
        except Exception as e:
            print(f"  {h:34} ERROR {type(e).__name__}: {str(e)[:60]}")
            bad += 1
    print(f"\n{'All good.' if not bad else str(bad) + ' hostname(s) need attention.'}")


def main():
    if "--verify" in sys.argv:
        verify()
        return
    print(("DRY RUN — nothing will change\n" if DRY else "Applying changes\n") +
          f"Canonical: https://{CANONICAL}")
    for zone in REDIRECT_DOMAINS:
        configure(zone, CANONICAL)
    # canonical zone: only www -> apex. Leave the apex record alone; it will
    # point at wherever the real site is hosted.
    print(f"\n  {CANONICAL}  (www -> apex only)")
    zid = zone_id(CANONICAL)
    upsert_record(zid, CANONICAL, "CNAME", "www." + CANONICAL, CANONICAL)
    set_redirect(zid, CANONICAL, CANONICAL,
                 match=f'http.host eq "www.{CANONICAL}"')
    always_https(zid)
    print("\nDone." + ("" if DRY else "  Now run:  python3 cf_redirects.py --verify"))


if __name__ == "__main__":
    main()
