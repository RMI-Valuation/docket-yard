"""A GET from the blob bucket with the standard library: SigV4 over urllib, nothing else.

The web tier reads a document the instance has pruned (docs/adr/0013 addendum: a document
address answers forever; ADR 0012: S3 is the store, the instance a cache). boto3 would be
a 100 MB dependency for one signed GET, so the signature is written out here — the
algorithm is fixed and small. Credentials come from the environment the container already
carries; nothing here writes.
"""

import datetime as dt
import hashlib
import hmac
import os
import urllib.parse
import urllib.request

EMPTY_SHA = hashlib.sha256(b"").hexdigest()


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def signed_get(
    bucket: str, key: str, *, region: str, access_key: str, secret_key: str, timeout: float = 120.0
):
    """Open a GET on s3://bucket/key with a SigV4 Authorization header; returns the
    urllib response (a file-like the caller streams and closes)."""
    host = f"{bucket}.s3.{region}.amazonaws.com"
    path = "/" + urllib.parse.quote(key, safe="/~-_.")
    now = dt.datetime.now(dt.UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    stamp = now.strftime("%Y%m%d")
    headers = {"host": host, "x-amz-content-sha256": EMPTY_SHA, "x-amz-date": amz_date}
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
    req = urllib.request.Request(
        f"https://{host}{path}",
        headers={
            "Authorization": auth,
            "x-amz-content-sha256": EMPTY_SHA,
            "x-amz-date": amz_date,
        },
    )
    return urllib.request.urlopen(req, timeout=timeout)


def from_env() -> dict | None:
    """The bucket and credentials the container carries, or None when it has none."""
    bucket = os.environ.get("DY_S3_BUCKET")
    access = os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    region = os.environ.get("AWS_REGION", "us-east-2")
    if not (bucket and access and secret):
        return None
    return {"bucket": bucket, "region": region, "access_key": access, "secret_key": secret}
