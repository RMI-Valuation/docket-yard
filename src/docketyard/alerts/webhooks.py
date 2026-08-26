"""Webhooks: the same alert, as a signed JSON POST to an HTTPS URL the subscriber owns.

A webhook URL is a recipient and is treated exactly like an address (ADR 0011, 0014): it is
handed over once, stored sealed, confirmed before anything is sent to it, and deleted on
unsubscribe. Confirmation is a *ping* — a POST carrying the confirmation link and the
signing secret — so only whoever reads the endpoint's traffic can confirm, and the secret
is never shown on a page.

Every delivery is signed: `X-DocketYard-Signature: sha256=<HMAC-SHA256(secret, body)>`
over the exact bytes sent. Receivers should verify before trusting a payload.

The outbound request is the one place this service connects to an address a stranger
chose. It is limited to https, to public unicast hosts, to one request with no redirects,
and to a short timeout. The host is resolved once, every address checked, and the
connection made to the checked address itself — with the certificate verified against the
name — so a name that answers differently on a second lookup (DNS rebinding) cannot steer
the request into the instance's own network.
"""

import hashlib
import hmac
import http.client
import ipaddress
import json
import socket
import ssl
import urllib.parse
from dataclasses import dataclass

TIMEOUT = 10
PING_TIMEOUT = 3  # a receiver that cannot answer a ping in 3 s will not answer deliveries
MAX_URL = 2048
USER_AGENT = "DocketYard-Webhook/1 (+https://docketyard.org/methodology)"


def normalise_url(url: str) -> str:
    """One spelling per endpoint: scheme and host lower-cased, whitespace trimmed. The
    path is the owner's and is kept as given."""
    url = url.strip()
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    if not u.scheme or not u.netloc:
        return url
    return urllib.parse.urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path, u.query, ""))


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
    """Every address the host resolves to (an IP literal resolves to itself); raises unless
    all are public unicast."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise RefusedDestination(f"{host}: does not resolve") from e
    addrs = sorted({str(info[4][0]) for info in infos})
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


class _PinnedHTTPS(http.client.HTTPSConnection):
    """Connects to the address that was checked, and verifies the certificate against
    the name the subscriber gave — so what was vetted is what is dialled."""

    def __init__(self, host: str, address: str, port: int, timeout: int, context):
        super().__init__(host, port, timeout=timeout, context=context)
        self._address = address

    def connect(self):  # noqa: D102
        sock = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(  # type: ignore[attr-defined]
            sock, server_hostname=self.host
        )


@dataclass(frozen=True)
class Result:
    status: int  # HTTP status, or 0 when no response was had
    detail: str = ""

    @property
    def accepted(self) -> bool:
        return 200 <= self.status < 300


def encode(payload: dict) -> bytes:
    """The exact bytes that are signed and sent."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def post(
    url: str, payload: dict, secret: str, *, delivery_id: str, timeout: int = TIMEOUT
) -> Result:
    """One signed POST, no redirects. Raises RefusedDestination for a host this service
    will not dial; never raises for the receiver's behaviour — the Result says what
    happened, and the caller decides whether to try again later."""
    u = urllib.parse.urlsplit(url)
    host = u.hostname or ""
    address = public_addresses(host)[0]
    body = encode(payload)
    path = urllib.parse.urlunsplit(("", "", u.path or "/", u.query, ""))
    conn = _PinnedHTTPS(host, address, u.port or 443, timeout, ssl.create_default_context())
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": USER_AGENT,
                "X-DocketYard-Signature": sign(secret, body),
                "X-DocketYard-Delivery": delivery_id,
            },
        )
        resp = conn.getresponse()
        resp.read(65536)  # drain a little so the connection closes cleanly; ignored
        return Result(resp.status, "" if 200 <= resp.status < 300 else f"HTTP {resp.status}")
    except (OSError, http.client.HTTPException, ssl.SSLError) as e:
        return Result(0, type(e).__name__)
    finally:
        conn.close()


def describe(url: str) -> str:
    """For pages and logs: the host only, never the path (which may carry a private token)."""
    return urllib.parse.urlsplit(url).hostname or "?"
