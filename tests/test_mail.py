"""The SES SMTP sender: password derivation shape, the headers every message must and
must not carry (ADR 0011), header-injection refusal, and the provider id from the 250."""

import base64
import smtplib

import pytest

from docketyard.alerts import mail

ENV = {
    "AWS_REGION": "us-east-2",
    "AWS_ACCESS_KEY_ID": "AKIAEXAMPLE",
    "AWS_SECRET_ACCESS_KEY": "secret",
}


def test_smtp_password_shape():
    """Version byte 0x04 + 32-byte HMAC, base64: 44 characters. The derivation itself is
    pinned by shape and region-sensitivity here and was proven by a real SES login from
    the instance (runbook § Mail); AWS publishes no known-answer vector to pin against."""
    pw = mail.smtp_password("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1")
    raw = base64.b64decode(pw)
    assert len(pw) == 44 and raw[0] == 4 and len(raw) == 33
    assert pw != mail.smtp_password("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-2")


def test_ses_region_is_its_own_setting():
    assert mail.Sender.from_env(ENV).host == "email-smtp.us-east-2.amazonaws.com"
    other = mail.Sender.from_env({**ENV, "DY_SES_REGION": "us-west-2"})
    assert other.host == "email-smtp.us-west-2.amazonaws.com"
    assert other.password != mail.Sender.from_env(ENV).password  # derived per region


def test_message_headers():
    sender = mail.Sender.from_env(ENV)
    msg = sender.build(
        mail.Outbound(
            to="a@example.org",
            subject="FD 36873: 2 new entries",
            text="Body.",
            unsubscribe_url="https://docketyard.org/u/abc",
        )
    )
    assert msg["From"] == "Docket Yard <alerts@docketyard.org>"
    assert msg["List-Unsubscribe"] == "<https://docketyard.org/u/abc>"
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert msg["Auto-Submitted"] == "auto-generated"
    assert msg.get_content_type() == "text/plain"  # no HTML, so nothing to hide a pixel in
    assert msg["Message-ID"].endswith("@docketyard.org>")
    plain = sender.build(mail.Outbound(to="a@example.org", subject="s", text="t"))
    assert "List-Unsubscribe" not in plain  # a confirmation mail has nothing to unsubscribe
    staging = mail.Sender.from_env({**ENV, "DY_MAIL_FROM": "DY <alerts@staging.example>"})
    assert staging.build(plain_out()).get("Message-ID").endswith("@staging.example>")


def plain_out():
    return mail.Outbound(to="a@example.org", subject="s", text="t")


def test_a_caption_with_a_line_break_cannot_become_a_header():
    sender = mail.Sender.from_env(ENV)
    with pytest.raises(ValueError):
        sender.build(mail.Outbound(to="a@example.org", subject="FD 1\r\nBcc: x@y", text="t"))


class FakeSmtp:
    def __init__(self):
        self.sent = []

    def mail(self, addr):
        self.from_ = addr

    def rcpt(self, addr):
        return (250, b"Ok") if "refuse" not in addr else (550, b"no")

    def data(self, body):
        self.sent.append(body)
        return 250, b"Ok 0100018f-provider-id-000000"


def test_session_returns_the_providers_message_id():
    sender = mail.Sender.from_env(ENV)
    fake = FakeSmtp()
    session = mail.Session(fake, sender)
    assert session.send(plain_out()) == "0100018f-provider-id-000000"
    assert fake.from_ == "alerts@docketyard.org" and b"Subject: s" in fake.sent[0]
    with pytest.raises(smtplib.SMTPRecipientsRefused):
        session.send(mail.Outbound(to="refuse@example.org", subject="s", text="t"))
