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


def test_smtp_signs_with_its_own_pair_when_one_is_set():
    """v2026.10.5: `web` reads the bucket with one key and may send through another account's
    SES with another, so SMTP has its own pair. Set, it wins; empty, AWS_* as before; half
    of one is refused, never mixed with the other identity (a 535 that names neither)."""
    own = mail.Sender.from_env(
        {**ENV, "DY_SMTP_ACCESS_KEY_ID": "AKIASMTP", "DY_SMTP_SECRET_ACCESS_KEY": "smtp-secret"}
    )
    assert own.username == "AKIASMTP"
    assert own.password == mail.smtp_password("smtp-secret", "us-east-2")
    default = mail.Sender.from_env(ENV)
    assert default.username == "AKIAEXAMPLE"
    assert default.password == mail.smtp_password("secret", "us-east-2")
    empty = {**ENV, "DY_SMTP_ACCESS_KEY_ID": "", "DY_SMTP_SECRET_ACCESS_KEY": ""}
    assert mail.Sender.from_env(empty).username == "AKIAEXAMPLE"  # compose passes empties
    for half in ({"DY_SMTP_ACCESS_KEY_ID": "AKIASMTP"}, {"DY_SMTP_SECRET_ACCESS_KEY": "s"}):
        with pytest.raises(ValueError, match="set both"):
            mail.Sender.from_env({**ENV, **half})
    # the store's pair is not needed when SMTP has its own
    alone = {
        "AWS_REGION": "us-east-2",
        "DY_SMTP_ACCESS_KEY_ID": "K",
        "DY_SMTP_SECRET_ACCESS_KEY": "S",
    }
    assert mail.Sender.from_env(alone).username == "K"
    # code review: a blank is unset on both pairs — compose passes an unset key as "", and a
    # stray space in a hand-edited .env must not count as half a pair, or as a whole one
    assert mail.Sender.from_env({**ENV, "DY_SMTP_ACCESS_KEY_ID": " "}).username == "AKIAEXAMPLE"
    for blank in ({"AWS_ACCESS_KEY_ID": ""}, {"AWS_SECRET_ACCESS_KEY": " "}):
        with pytest.raises(KeyError):
            mail.Sender.from_env({**ENV, **blank})


def test_half_an_smtp_pair_turns_mail_off_and_keeps_the_record(monkeypatch, capsys):
    """The poller builds its sender with cli._sender: a half pair must not crash it, or a
    mail setting would stop the record being kept (compose.yaml's own rule). The vault is
    left alone: this is about the sender, and the test's vault is conftest's."""
    from docketyard import cli

    monkeypatch.setattr(cli.vault, "configure", lambda v: None)
    monkeypatch.setattr(cli.vault, "is_open", lambda: True)
    for k in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "DY_SMTP_SECRET_ACCESS_KEY",
        "DY_SES_REGION",
        "AWS_DEFAULT_REGION",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    monkeypatch.setenv("DY_SMTP_ACCESS_KEY_ID", "AKIASMTP")
    assert cli._sender() is None
    assert "mail not configured: DY_SMTP_ACCESS_KEY_ID" in capsys.readouterr().out


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
        self.resets = 0

    def mail(self, addr):
        self.from_ = addr
        return 250, b"Ok"

    def rset(self):
        self.resets += 1

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
    assert fake.resets == 1  # the envelope is cleared for the next message
    refused = smtplib.SMTPRecipientsRefused({"refuse@example.org": (550, b"no")})
    assert mail.describe_failure(refused) == "SMTPRecipientsRefused: 550 no"  # no address
