"""A GET from the blob bucket with the standard library: SigV4 over urllib, nothing else.

The web tier reads a document the instance has pruned (docs/adr/0013 addendum: a document
address answers forever; ADR 0012: S3 is the store, the instance a cache). boto3 would be
a 100 MB dependency for one signed GET, so the signature is written out here — the
algorithm is fixed and small. Credentials come from the environment the container already
carries; nothing here writes, and an empty key (a bucket listing) is refused.
"""

import datetime as dt
import functools
import hashlib
import hmac
import os
import urllib.parse
import urllib.request
from collections.abc import Callable

EMPTY_SHA = hashlib.sha256(b"").hexdigest()


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def signed_get(
    bucket: str,
    key: str,
    *,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str | None = None,
    timeout: float = 120.0,
):
    """Open a GET on s3://bucket/key with a SigV4 Authorization header; returns the
    urllib response (a file-like the caller streams and closes)."""
    if not key or key.startswith("/"):
        raise ValueError("an object key, never a listing")
    host = f"{bucket}.s3.{region}.amazonaws.com"
    path = "/" + urllib.parse.quote(key, safe="/~-_.")
    now = dt.datetime.now(dt.UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    stamp = now.strftime("%Y%m%d")
    headers = {"host": host, "x-amz-content-sha256": EMPTY_SHA, "x-amz-date": amz_date}
    if session_token:  # temporary credentials (an instance role, STS) carry a token
        headers["x-amz-security-token"] = session_token
    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
    canonical = f"GET\n{path}\n\n{canonical_headers}\n{signed_headers}\n{EMPTY_SHA}"
    scope = f"{stamp}/{region}/s3/aws4_request"
    to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()]
    )
    k = ("AWS4" + secret_key).encode()
    for part in (stamp, region, "s3", "aws4_request"):
        k = _sign(k, part)
    signature = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    auth = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed_headers},"
        f" Signature={signature}"
    )
    sent = {k: v for k, v in headers.items() if k != "host"} | {"Authorization": auth}
    req = urllib.request.Request(f"https://{host}{path}", headers=sent)
    return urllib.request.urlopen(req, timeout=timeout)


def from_env() -> Callable | None:
    """`signed_get` bound to the bucket and credentials the container carries — a
    `fetch(key)` — or None when it has none."""
    bucket = os.environ.get("DY_S3_BUCKET")
    access = os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not bucket:
        return None
    if not (access and secret):  # a store named but unreachable: refuse to start quietly
        raise RuntimeError(
            "DY_S3_BUCKET is set but AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY are not"
        )
    return functools.partial(
        signed_get,
        bucket,
        region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2",
        access_key=access,
        secret_key=secret,
        session_token=os.environ.get("AWS_SESSION_TOKEN") or None,
    )
