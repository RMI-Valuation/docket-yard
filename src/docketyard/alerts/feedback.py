"""Bounce and complaint feedback from SES, delivered by SNS over HTTPS.

SES publishes BOUNCE and COMPLAINT events for the `docketyard` configuration set to an SNS
topic; SNS POSTs each one to `/ses/feedback`. Nothing in a message is believed until it
has passed, in order: the topic ARN is the one configured (mandatory — without one the
endpoint is off), the signing certificate comes from SNS's own host over TLS with no
redirects and is in date, the signature covers the fields SNS says it covers, and the SES
event inside names this account as the sender. Only then does a permanent bounce or a
complaint put the address on `email_suppression` under its HMAC. SES's own account-level
list would otherwise swallow later sends silently (runbook § Mail).

Replays are harmless by construction: suppression is idempotent and a stale SubscribeURL
is just a dead fetch. No address is logged; the raw notification is not kept.
"""

import base64
import json
import re
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime
from sqlite3 import Connection

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from docketyard.alerts import subscriptions

# SNS signs with SHA1withRSA (SignatureVersion 1) or SHA256withRSA (2)
_HASHES = {"1": hashes.SHA1(), "2": hashes.SHA256()}
_SNS_HOST = r"https://sns\.[a-z0-9-]+\.amazonaws\.com/"
_CERT_URL = re.compile(_SNS_HOST + r"[\w./-]+\.pem\Z")
_SNS_URL = re.compile(_SNS_HOST + r"[^\s]*\Z")
MAX_BODY = 256 * 1024  # SNS's own message ceiling
MAX_CERT = 64 * 1024
_SIGNED_FIELDS = {
    "Notification": ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"),
    "SubscriptionConfirmation": (
        "Message",
        "MessageId",
        "SubscribeURL",
        "Timestamp",
        "Token",
        "TopicArn",
        "Type",
    ),
    "UnsubscribeConfirmation": (
        "Message",
        "MessageId",
        "SubscribeURL",
        "Timestamp",
        "Token",
        "TopicArn",
        "Type",
    ),
}


class Rejected(ValueError):
    """The message did not verify; nothing in it is believed."""


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


_opener = urllib.request.build_opener(_NoRedirects())


def _fetch(url: str) -> bytes:
    """GET from SNS's host only, no redirects, bounded size."""
    if not _SNS_URL.match(url):
        raise Rejected("URL not on SNS's host")
    with _opener.open(url, timeout=15) as r:
        return r.read(MAX_CERT)


_cert_cache: dict[str, rsa.RSAPublicKey] = {}
_cert_lock = threading.Lock()


def _public_key(url: str, fetch) -> rsa.RSAPublicKey:
    """SNS rotates its signing certificate rarely; one fetch per URL per process."""
    with _cert_lock:
        key = _cert_cache.get(url)
    if key is not None:
        return key
    cert = x509.load_pem_x509_certificate(fetch(url))
    if not (cert.not_valid_before_utc <= datetime.now(UTC) <= cert.not_valid_after_utc):
        raise Rejected("signing certificate out of date")
    key = cert.public_key()
    if not isinstance(key, rsa.RSAPublicKey):
        raise Rejected("signing certificate is not RSA")
    with _cert_lock:
        _cert_cache[url] = key
    return key


def _str(msg: dict, key: str) -> str:
    value = msg.get(key)
    if not isinstance(value, str):
        raise Rejected(f"{key} missing or not a string")
    return value


def string_to_sign(msg: dict) -> bytes:
    fields = _SIGNED_FIELDS.get(msg.get("Type", ""))
    if not fields:
        raise Rejected("unknown message type")
    lines = []
    for f in fields:
        if f in msg:  # Subject is optional
            lines += [f, _str(msg, f)]
    return ("\n".join(lines) + "\n").encode()


def verify(msg: dict, fetch, expected_topic: str) -> None:
    """Raise Rejected unless the message is signed by SNS for the expected topic."""
    if not expected_topic:
        raise Rejected("no feedback topic configured")
    if _str(msg, "TopicArn") != expected_topic:
        raise Rejected("unexpected topic")
    url = _str(msg, "SigningCertURL")
    if not _CERT_URL.match(url):
        raise Rejected("signing certificate not from SNS")
    algo = _HASHES.get(_str(msg, "SignatureVersion"))
    if algo is None:
        raise Rejected("unknown signature version")
    try:
        _public_key(url, fetch).verify(
            base64.b64decode(_str(msg, "Signature")),
            string_to_sign(msg),
            padding.PKCS1v15(),
            algo,
        )
    except Rejected:
        raise
    except Exception as e:  # noqa: BLE001 — any failure to verify is a rejection
        raise Rejected(f"signature did not verify ({type(e).__name__})") from e


def account_of(topic_arn: str) -> str:
    return topic_arn.split(":")[4] if topic_arn.count(":") >= 5 else ""


def handle(con: Connection, body: bytes, fetch=_fetch, expected_topic: str = "", log=print) -> str:
    """Process one SNS delivery. Returns what was done, for the response and the log."""
    if len(body) > MAX_BODY:
        raise Rejected("body too large")
    try:
        msg = json.loads(body)
    except ValueError as e:
        raise Rejected("not JSON") from e
    if not isinstance(msg, dict):
        raise Rejected("not an SNS message")
    verify(msg, fetch, expected_topic)
    kind = msg["Type"]
    if kind == "SubscriptionConfirmation":
        fetch(_str(msg, "SubscribeURL"))  # host-pinned by _fetch; signed by SNS
        log("ses feedback: SNS subscription confirmed")
        return "confirmed"
    if kind != "Notification":
        return "ignored"
    try:
        event = json.loads(_str(msg, "Message"))
    except ValueError as e:
        raise Rejected("SES event is not JSON") from e
    if not isinstance(event, dict):
        raise Rejected("SES event is not an object")
    # defence in depth against a permissive topic policy: the event must be about OUR mail
    sender_account = (event.get("mail") or {}).get("sendingAccountId")
    if sender_account != account_of(expected_topic):
        log("ses feedback: event from another account ignored")
        return "ignored"
    return apply_event(con, event, log)


def apply_event(con: Connection, event: dict, log=print) -> str:
    """A verified SES event: suppress on a permanent bounce or any complaint."""
    etype = (event.get("eventType") or event.get("notificationType") or "").lower()
    if etype == "bounce":
        bounce = event.get("bounce") or {}
        if bounce.get("bounceType") != "Permanent":
            log("ses feedback: transient bounce, no action")
            return "transient"
        recipients = bounce.get("bouncedRecipients") or []
        reason = "bounce"
    elif etype == "complaint":
        recipients = (event.get("complaint") or {}).get("complainedRecipients") or []
        reason = "complaint"
    else:
        return "ignored"
    n = 0
    for r in recipients:
        address = r.get("emailAddress") if isinstance(r, dict) else None
        if isinstance(address, str) and "@" in address:
            subscriptions.suppress(con, address, reason)
            n += 1
    log(f"ses feedback: {reason}, {n} address(es) suppressed")
    return f"{reason}:{n}"
