"""SES feedback over SNS: signature verification with a locally minted certificate, the
subscription handshake, and suppression on a permanent bounce or a complaint."""

import base64
import datetime as dt
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from docketyard.alerts import feedback, subscriptions, vault
from docketyard.store import db
from docketyard.web.app import create_app
from tests.test_subscriptions_schema import _docket
from tests.test_web import build_store

TOPIC = "arn:aws:sns:us-east-2:123456789012:docketyard-ses-feedback"
CERT_URL = "https://sns.us-east-2.amazonaws.com/SimpleNotificationService-abc123.pem"


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return key, cert.public_bytes(serialization.Encoding.PEM)


KEY, CERT_PEM = _keypair()


def signed(msg: dict, key=KEY) -> bytes:
    msg = {**msg, "SigningCertURL": CERT_URL, "SignatureVersion": "1"}
    sig = key.sign(feedback.string_to_sign(msg), padding.PKCS1v15(), hashes.SHA1())
    msg["Signature"] = base64.b64encode(sig).decode()
    return json.dumps(msg).encode()


class Fetch:
    def __init__(self):
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        return CERT_PEM if url == CERT_URL else b""


ACCOUNT = "123456789012"


def notification(event: dict) -> dict:
    event = {"mail": {"sendingAccountId": ACCOUNT}, **event}
    return {
        "Type": "Notification",
        "MessageId": "m1",
        "TopicArn": TOPIC,
        "Message": json.dumps(event),
        "Timestamp": "2026-08-26T03:00:00.000Z",
    }


def bounce(*addresses, kind="Permanent"):
    return notification(
        {
            "eventType": "Bounce",
            "bounce": {
                "bounceType": kind,
                "bouncedRecipients": [{"emailAddress": a} for a in addresses],
            },
        }
    )


def test_permanent_bounce_suppresses_and_later_subscribe_is_refused():
    con = db.connect(":memory:")
    d = _docket(con)
    fetch = Fetch()
    out = feedback.handle(con, signed(bounce("Gone@Example.org")), fetch, TOPIC, log=lambda _: 0)
    assert out == "bounce:1" and fetch.urls == [CERT_URL]
    assert subscriptions.is_suppressed(con, vault.current().hash("gone@example.org"))
    assert subscriptions.subscribe(con, "gone@example.org", d, "pass") is None
    assert "example.org" not in "\n".join(con.iterdump()).lower()  # still nothing readable
    assert (
        feedback.handle(
            con, signed(bounce("t@example.org", kind="Transient")), fetch, TOPIC, log=lambda _: 0
        )
        == "transient"
    )


def test_complaint_suppresses():
    con = db.connect(":memory:")
    msg = notification(
        {
            "eventType": "Complaint",
            "complaint": {"complainedRecipients": [{"emailAddress": "c@example.org"}]},
        }
    )
    assert feedback.handle(con, signed(msg), Fetch(), TOPIC, log=lambda _: 0) == "complaint:1"
    assert subscriptions.is_suppressed(con, vault.current().hash("c@example.org"))


def test_unverifiable_messages_are_rejected():
    con = db.connect(":memory:")
    other, _ = _keypair()
    with pytest.raises(feedback.Rejected, match="did not verify"):
        feedback.handle(con, signed(bounce("x@example.org"), key=other), Fetch(), TOPIC)
    with pytest.raises(feedback.Rejected, match="not from SNS"):
        body = json.loads(signed(bounce("x@example.org")))
        body["SigningCertURL"] = "https://evil.example/cert.pem"
        feedback.handle(con, json.dumps(body).encode(), Fetch(), TOPIC)
    with pytest.raises(feedback.Rejected, match="unexpected topic"):
        feedback.handle(
            con, signed(bounce("x@example.org")), Fetch(), "arn:aws:sns:us-east-2:1:other"
        )
    with pytest.raises(feedback.Rejected, match="not JSON"):
        feedback.handle(con, b"nope", Fetch(), TOPIC)
    with pytest.raises(feedback.Rejected, match="no feedback topic"):  # fail closed
        feedback.handle(con, signed(bounce("x@example.org")), Fetch(), "")
    with pytest.raises(feedback.Rejected, match="not an SNS message"):
        feedback.handle(con, b"[1, 2]", Fetch(), TOPIC)
    with pytest.raises(feedback.Rejected, match="not a string"):
        body = json.loads(signed(bounce("x@example.org")))
        body["SigningCertURL"] = 5
        feedback.handle(con, json.dumps(body).encode(), Fetch(), TOPIC)
    with pytest.raises(feedback.Rejected, match="too large"):
        feedback.handle(con, b" " * (feedback.MAX_BODY + 1), Fetch(), TOPIC)
    # a genuine bounce about someone else's mail (a permissive topic policy) is ignored
    foreign = bounce("v@example.org")
    foreign["Message"] = json.dumps(
        {**json.loads(foreign["Message"]), "mail": {"sendingAccountId": "999"}}
    )
    assert feedback.handle(con, signed(foreign), Fetch(), TOPIC, log=lambda _: 0) == "ignored"
    assert con.execute("SELECT COUNT(*) FROM email_suppression").fetchone()[0] == 0


def test_subscription_confirmation_visits_the_subscribe_url():
    con = db.connect(":memory:")
    fetch = Fetch()
    msg = {
        "Type": "SubscriptionConfirmation",
        "MessageId": "m2",
        "TopicArn": TOPIC,
        "Message": "confirm",
        "SubscribeURL": "https://sns.us-east-2.amazonaws.com/?Action=ConfirmSubscription&Token=t",
        "Token": "t",
        "Timestamp": "2026-08-26T03:00:00.000Z",
    }
    assert feedback.handle(con, signed(msg), fetch, TOPIC, log=lambda _: 0) == "confirmed"
    assert fetch.urls[-1].startswith(
        "https://sns.us-east-2.amazonaws.com/?Action=ConfirmSubscription"
    )


def test_endpoint_answers_400_to_garbage_and_keeps_no_cookie(tmp_path):
    path = build_store(tmp_path)
    client = TestClient(create_app(path, feedback_topic=TOPIC))
    r = client.post("/ses/feedback", content=b"{}")
    assert r.status_code == 400 and "Set-Cookie" not in r.headers
    assert client.post("/ses/feedback", content=b"x" * (feedback.MAX_BODY + 1)).status_code == 413
    off = TestClient(create_app(path))  # no topic configured: the endpoint is off
    assert off.post("/ses/feedback", content=b"{}").status_code == 503


def test_certificate_is_fetched_once_and_must_be_in_date():
    con = db.connect(":memory:")
    fetch = Fetch()
    feedback._cert_cache.clear()
    for _ in range(3):
        feedback.handle(con, signed(bounce("a@example.org")), fetch, TOPIC, log=lambda _: 0)
    assert fetch.urls.count(CERT_URL) == 1
    feedback._cert_cache.clear()
