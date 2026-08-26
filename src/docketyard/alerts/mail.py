"""Outbound mail through Amazon SES's SMTP interface, standard library only.

Why SMTP and not the SES API: the API needs SigV4 signing (a dependency or sixty lines of
it); SMTP needs `smtplib` and a password that AWS defines as a deterministic HMAC chain over
the IAM secret key — so the one bucket-scoped instance user, granted `ses:SendRawEmail`,
is also the sender. No second credential to keep. Because that derived password travels
over the SMTP session, the TLS upgrade verifies the server certificate — always.

What every message carries (ADR 0011): a plain-text body, no tracking pixel, no
per-recipient link tokens beyond the one unsubscribe link, and RFC 8058 one-click
unsubscribe headers so the mail client's own button works without a sign-in. Headers are
built under the SMTP policy, which refuses embedded line breaks: subjects are made from
captions the Board prints, and a caption is data, never a header.
"""

import base64
import hashlib
import hmac
import os
import smtplib
import ssl
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

SES_SMTP_VERSION = b"\x04"
SMTP_PORT = 587


def describe_failure(e: BaseException) -> str:
    """A log line for a failed send that names the error, never the recipient: a refused
    recipient's str() is the address itself, and the app log must hold no addresses."""
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        codes = ", ".join(
            f"{c} {r.decode(errors='replace') if isinstance(r, bytes) else r}"
            for c, r in e.recipients.values()
        )
        return f"SMTPRecipientsRefused: {codes}"
    if isinstance(e, smtplib.SMTPResponseException):
        msg = (
            e.smtp_error.decode(errors="replace")
            if isinstance(e.smtp_error, bytes)
            else e.smtp_error
        )
        return f"{type(e).__name__}: {e.smtp_code} {msg[:80]}"
    return type(e).__name__


def smtp_password(secret_access_key: str, region: str) -> str:
    """AWS's published derivation of an SES SMTP password from an IAM secret key."""

    def sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    signature = sign(("AWS4" + secret_access_key).encode(), "11111111")
    for part in (region, "ses", "aws4_request", "SendRawEmail"):
        signature = sign(signature, part)
    return base64.b64encode(SES_SMTP_VERSION + signature).decode()


@dataclass(frozen=True)
class Outbound:
    to: str
    subject: str
    text: str
    unsubscribe_url: str | None = None  # RFC 8058: one-click, works without signing in


class Session:
    """One authenticated SMTP session carrying many messages (a daily digest run is one
    session, not one login per subscriber). Returns the PROVIDER's message id for each
    send — SES reports bounces and complaints by that id, not by the header we minted."""

    def __init__(self, smtp: smtplib.SMTP, sender: "Sender"):
        self._smtp = smtp
        self._sender = sender

    def send(self, out: Outbound) -> str:
        msg = self._sender.build(out)
        code, resp = self._smtp.mail(parseaddr(self._sender.from_address)[1])
        if code != 250:
            self._smtp.rset()
            raise smtplib.SMTPSenderRefused(code, resp, self._sender.from_address)
        code, resp = self._smtp.rcpt(out.to)
        if code not in (250, 251):
            self._smtp.rset()  # clear the envelope so the next message starts clean
            raise smtplib.SMTPRecipientsRefused({out.to: (code, resp)})
        code, resp = self._smtp.data(msg.as_bytes())
        if code != 250:
            raise smtplib.SMTPDataError(code, resp)
        # SES answers "250 Ok <its id>"; fall back to our own header if the shape changes
        words = resp.decode("ascii", "replace").split()
        return words[-1] if len(words) >= 2 and words[0].lower() == "ok" else msg["Message-ID"]


@dataclass(frozen=True)
class Sender:
    """The sending identity and SES SMTP endpoint, from the environment on the instance."""

    from_address: str
    region: str
    username: str = field(repr=False)
    password: str = field(repr=False)  # never in a traceback or a log line

    @classmethod
    def from_env(cls, env=os.environ) -> "Sender":
        # SES lives in its own region; it happens to match the bucket's today, and need not
        region = env.get("DY_SES_REGION") or env.get("AWS_REGION") or env["AWS_DEFAULT_REGION"]
        return cls(
            from_address=env.get("DY_MAIL_FROM", "Docket Yard <alerts@docketyard.org>"),
            region=region,
            username=env["AWS_ACCESS_KEY_ID"],
            password=smtp_password(env["AWS_SECRET_ACCESS_KEY"], region),
        )

    @property
    def host(self) -> str:
        return f"email-smtp.{self.region}.amazonaws.com"

    @property
    def domain(self) -> str:
        return parseaddr(self.from_address)[1].partition("@")[2]

    def build(self, out: Outbound) -> EmailMessage:
        msg = EmailMessage(policy=policy.SMTP)  # refuses CR/LF inside a header value
        msg["From"] = self.from_address
        msg["To"] = out.to
        msg["Subject"] = out.subject
        msg["Date"] = formatdate(usegmt=True)
        msg["Message-ID"] = make_msgid(domain=self.domain)
        msg["Auto-Submitted"] = "auto-generated"
        if out.unsubscribe_url:
            msg["List-Unsubscribe"] = f"<{out.unsubscribe_url}>"
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        msg.set_content(out.text)
        return msg

    @contextmanager
    def session(self) -> Generator[Session]:
        with smtplib.SMTP(self.host, SMTP_PORT, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(self.username, self.password)
            yield Session(smtp, self)

    def send(self, out: Outbound) -> str:
        """One message in its own session; returns the provider's message id."""
        with self.session() as s:
            return s.send(out)
