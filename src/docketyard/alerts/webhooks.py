"""Webhooks: the same alert, as a signed JSON POST to an HTTPS URL the subscriber owns.

A webhook URL is a recipient and is treated exactly like an address (ADR 0011, 0014): it is
handed over once, stored sealed, confirmed before anything is sent to it, and deleted on
unsubscribe. Confirmation is a *ping* — a POST carrying the confirmation link and the
signing secret — so only whoever reads the endpoint's traffic can confirm, and the secret
is never shown on a page.

Every delivery is signed: `X-DocketYard-Signature: sha256=<HMAC-SHA256(secret, body)>`
over the exact bytes sent. Receivers should verify before trusting a payload.

The outbound request is the one place this service connects to an address a stranger
chose. It is limited to https, to public unicast hosts (resolved and checked before each
connection — a name that points into the instance's own network is refused), to one
request with no redirects, and to a short timeout.
"""

import hashlib
import hmac
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

TIMEOUT = 10
MAX_URL = 2048
USER_AGENT = "DocketYard-Webhook/1 (+https://docketyard.org/methodology)"


def normalise_url(url: str) -> str:
    return url.strip()


def plausible_url(url: str) -> bool:
    """https, a hostname, no credentials, no fragment — nothing else is judged here; the
    ping is the validation."""
    if not url or len(url) > MAX_URL or any(c.isspace() for c in url):
        return False
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return (
        u.scheme == "https"
        and bool(u.hostname)
        and u.username is None
        and u.password is None
        and not u.fragment
    )


class RefusedDestination(ValueError):
    """The URL's host resolves somewhere this service will not connect to."""


def public_addresses(host: str) -> list[str]:
    """Every address the host resolves to; raises unless all are public unicast."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise RefusedDestination(f"{host}: does not resolve") from e
    addrs = sorted({info[4][0] for info in infos})
    if not addrs:
        raise RefusedDestination(f"{host}: does not resolve")
    for a in addrs:
        ip = ipaddress.ip_address(a)
        if not ip.is_global or ip.is_multicast:
            raise RefusedDestination(f"{host}: resolves to a non-public address")
    return addrs


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(secret: str, body: bytes, signature: str) -> bool:
    """For receivers (and our tests): constant-time comparison against a fresh signature."""
    return hmac.compare_digest(sign(secret, body), signature or "")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


_opener = urllib.request.build_opener(_NoRedirect)


@dataclass(frozen=True)
class Result:
    status: int  # HTTP status, or 0 when no response was had
    detail: str = ""

    @property
    def accepted(self) -> bool:
        return 200 <= self.status < 300


def post(
    url: str, payload: dict, secret: str, *, delivery_id: str, timeout: int = TIMEOUT
) -> Result:
    """One signed POST. Never raises for the receiver's behaviour: the Result says what
    happened, and the caller decides whether to try again later."""
    host = urllib.parse.urlsplit(url).hostname or ""
    public_addresses(host)  # raises RefusedDestination
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": USER_AGENT,
            "X-DocketYard-Signature": sign(secret, body),
            "X-DocketYard-Delivery": delivery_id,
        },
    )
    try:
        with _opener.open(req, timeout=timeout) as resp:
            return Result(resp.status)
    except urllib.error.HTTPError as e:
        return Result(e.code, f"HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return Result(0, type(e).__name__)


def describe(url: str) -> str:
    """For logs: the host only, never the path (which may carry a private token)."""
    return urllib.parse.urlsplit(url).hostname or "?"
