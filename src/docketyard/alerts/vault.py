"""Addresses at rest are not readable without a key that never leaves the serving machine.

Two derived forms of every address (ADR 0011, decided 2026-08-26):

- **`email_hash`** — HMAC-SHA256 under the key. What the store matches on: one live
  subscription per (address, docket), the suppression list, rate limits. Irreversible.
- **`email_enc`** — Fernet (AES-128-CBC + HMAC, authenticated) under the key. What the
  sender decrypts at send time. Reversible only with the key.

The key is `DY_EMAIL_KEY` in the instance environment and in the operator's password
manager — never in the store, never in S3, never in a backup. So every copy of the store
(Litestream replica, snapshot, a developer's restore) holds ciphertext. What this does not
change: the operator holds the key, so a lawful and specific demand can still produce the
addresses of people currently following a docket; the privacy page says so. Lose the key
and every subscription is unrecoverable — people subscribe again.

Without a key the vault is closed: nothing that stores or sends an address will run.
"""

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass, field

from cryptography.fernet import Fernet, InvalidToken


class VaultClosed(RuntimeError):
    """No DY_EMAIL_KEY: addresses can be neither stored nor read."""


def normalise_email(raw: str) -> str:
    """The one form an address is ever hashed in: trimmed, lower-cased."""
    return raw.strip().lower()


@dataclass(frozen=True, repr=False)
class Vault:
    _fernet: Fernet = field(repr=False)
    _mac_key: bytes = field(repr=False)  # the HMAC key: printed nowhere, ever

    def __repr__(self) -> str:
        return "Vault(open)"

    @classmethod
    def from_key(cls, key: str) -> "Vault":
        raw = base64.urlsafe_b64decode(key)
        if len(raw) != 32:
            raise ValueError("DY_EMAIL_KEY must be a 32-byte urlsafe-base64 key (Fernet)")
        # a separate MAC key derived from the same secret, so the two uses never share bytes
        return cls(Fernet(key), hashlib.sha256(b"docketyard-email-hash:" + raw).digest())

    @classmethod
    def from_env(cls, env=os.environ) -> "Vault | None":
        """None when unset. A malformed key also yields None, after a loud line: capture
        must not stop because the mail key has a typo; the vault simply stays closed."""
        key = env.get("DY_EMAIL_KEY")
        if not key:
            return None
        try:
            return cls.from_key(key)
        except (ValueError, TypeError) as e:
            print(f"DY_EMAIL_KEY invalid ({type(e).__name__}): the address vault stays closed")
            return None

    @staticmethod
    def new_key() -> str:
        return Fernet.generate_key().decode()

    def hash(self, email: str) -> str:
        """Normalises first, so no caller can mint a second identity for one address."""
        return hmac.new(self._mac_key, normalise_email(email).encode(), hashlib.sha256).hexdigest()

    def hash_recipient(self, channel: str, recipient: str) -> str:
        """The matching hash for any recipient. An address is normalised and hashed as
        before (production rows depend on it); a webhook URL keeps its case — the path
        is the endpoint owner's — and is domain-separated so no URL can share a hash
        with an address."""
        if channel == "email":
            return self.hash(recipient)
        data = f"{channel}:{recipient}".encode()
        return hmac.new(self._mac_key, data, hashlib.sha256).hexdigest()

    def seal(self, email: str) -> str:
        return self._fernet.encrypt(email.encode()).decode()

    def open(self, sealed: str) -> str:
        try:
            return self._fernet.decrypt(sealed.encode()).decode()
        except InvalidToken as e:
            raise VaultClosed("stored address does not decrypt under this key") from e


_current: Vault | None = None


def configure(vault: Vault | None) -> None:
    global _current
    _current = vault


def current() -> Vault:
    if _current is None:
        raise VaultClosed("DY_EMAIL_KEY is not set: the address vault is closed")
    return _current


def is_open() -> bool:
    return _current is not None
