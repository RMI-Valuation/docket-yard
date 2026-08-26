"""Subscriptions: an email address watching one docket family (ADR 0011, migration 0005).

Addresses are stored as an HMAC and a ciphertext under the vault key (alerts/vault.py);
nothing here ever writes a readable address. Tokens are 256 random bits, handed out once
and stored only as SHA-256. A confirmation link expires; an unsubscribe link never does
and a fresh one is minted for every alert, so the link in any alert ever sent still works
— and an unknown one is answered "already unsubscribed", which is true. Unsubscribing
DELETES: the subscription, its tokens, its alert history, and any alert row of that
address left with nothing in it.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from sqlite3 import Connection

from docketyard.alerts import vault

CONFIRM_TTL_HOURS = 48  # the one number the mail and the expired page both quote
CONFIRM_TTL = timedelta(hours=CONFIRM_TTL_HOURS)
CONFIRM_MAILS_PER_HOUR = 3  # per address, whatever the docket (ADR 0011: rate-limited)


@dataclass(frozen=True)
class Subscription:
    subscription_id: int
    email: str  # decrypted for the caller that needs to address the person
    docket_id: int
    cadence: str
    status: str


normalise_email = vault.normalise_email  # one definition; the vault hashes the same form


def plausible_email(email: str) -> bool:
    """Not validation — the confirmation mail is the validation — just enough to refuse
    what could never receive one."""
    local, at, domain = email.partition("@")
    return bool(at and local and "." in domain and " " not in email and len(email) <= 254)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="seconds")


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(UTC)


def is_suppressed(con: Connection, email_hash: str) -> bool:
    return bool(
        con.execute(
            "SELECT 1 FROM email_suppression WHERE email_hash = ?", (email_hash,)
        ).fetchone()
    )


def subscribe(
    con: Connection, email: str, docket_id: int, cadence: str, now: datetime | None = None
) -> str | None:
    """Create or refresh a pending subscription and return the confirmation token to mail —
    or None when nothing should be mailed: the address is already active on this docket,
    is suppressed, or has hit the per-hour confirmation limit. The web tier responds the
    same way in every case (no enumeration)."""
    v = vault.current()
    email = normalise_email(email)
    h = v.hash(email)
    t = _now(now)
    if is_suppressed(con, h):
        return None
    recent = con.execute(
        "SELECT COUNT(*) FROM subscription_token t JOIN subscription s USING (subscription_id)"
        " WHERE s.email_hash = ? AND t.purpose = 'confirm' AND t.created_at > ?",
        (h, _iso(t - timedelta(hours=1))),
    ).fetchone()[0]
    if recent >= CONFIRM_MAILS_PER_HOUR:
        return None
    row = con.execute(
        "SELECT subscription_id, status FROM subscription WHERE email_hash = ? AND docket_id = ?",
        (h, docket_id),
    ).fetchone()
    expires = _iso(t + CONFIRM_TTL)
    if row and row[1] == "active":
        return None
    if row:  # pending: another link (every link mailed stays live until it expires — the
        # rate limit counts them), the latest chosen cadence, a new expiry
        sid = row[0]
        con.execute(
            "UPDATE subscription SET cadence = ?, expires_at = ? WHERE subscription_id = ?",
            (cadence, expires, sid),
        )
    else:
        sid = con.execute(
            "INSERT INTO subscription (email_hash, email_enc, docket_id, cadence, status,"
            " created_at, expires_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
            (h, v.seal(email), docket_id, cadence, _iso(t), expires),
        ).lastrowid
    token = new_token()
    con.execute(
        "INSERT INTO subscription_token (token_sha256, subscription_id, purpose, created_at,"
        " expires_at) VALUES (?, ?, 'confirm', ?, ?)",
        (token_hash(token), sid, _iso(t), expires),
    )
    con.commit()
    return token


def confirm(con: Connection, token: str, now: datetime | None = None) -> Subscription | None:
    """Activate the subscription a live confirmation token points at. The high-water mark
    is set to the ledger's head in the same transaction: nothing before this moment is
    ever alerted (docs/alerts.md: no backfill)."""
    t = _iso(_now(now))
    row = con.execute(
        "SELECT s.subscription_id FROM subscription_token k"
        " JOIN subscription s USING (subscription_id)"
        " WHERE k.token_sha256 = ? AND k.purpose = 'confirm' AND k.expires_at > ?"
        " AND s.status = 'pending'",
        (token_hash(token), t),
    ).fetchone()
    if row is None:
        return None
    sid = row[0]
    head = con.execute("SELECT COALESCE(MAX(event_id), 0) FROM event").fetchone()[0]
    con.execute(
        "UPDATE subscription SET status = 'active', high_water_event_id = ?, confirmed_at = ?,"
        " expires_at = NULL WHERE subscription_id = ?",
        (head, t, sid),
    )
    con.execute(
        "DELETE FROM subscription_token WHERE subscription_id = ? AND purpose = 'confirm'", (sid,)
    )
    con.commit()
    return get(con, sid)


def get(con: Connection, subscription_id: int) -> Subscription | None:
    row = con.execute(
        "SELECT subscription_id, email_enc, docket_id, cadence, status FROM subscription"
        " WHERE subscription_id = ?",
        (subscription_id,),
    ).fetchone()
    if row is None:
        return None
    sid, enc, docket_id, cadence, status = row
    return Subscription(sid, vault.current().open(enc), docket_id, cadence, status)


def unsubscribe_token(con: Connection, subscription_id: int, now: datetime | None = None) -> str:
    """A never-expiring token for one alert; the hash is the only thing kept."""
    token = new_token()
    con.execute(
        "INSERT INTO subscription_token (token_sha256, subscription_id, purpose, created_at)"
        " VALUES (?, ?, 'unsubscribe', ?)",
        (token_hash(token), subscription_id, _iso(_now(now))),
    )
    return token


def withdraw_token(con: Connection, token: str) -> None:
    """A confirmation that could not be mailed does not count against the address."""
    con.execute("DELETE FROM subscription_token WHERE token_sha256 = ?", (token_hash(token),))
    con.commit()


def unsubscribe(con: Connection, token: str) -> bool:
    """Delete everything about the subscription the token names — and, for a daily
    digest, every daily subscription of the address, since the email it came from covered
    them all. Returns whether a row existed; the page says the same thing either way.
    Needs no key: everything is matched on the hash."""
    row = con.execute(
        "SELECT s.subscription_id, s.email_hash, s.cadence FROM subscription_token k"
        " JOIN subscription s USING (subscription_id)"
        " WHERE k.token_sha256 = ? AND k.purpose = 'unsubscribe'",
        (token_hash(token),),
    ).fetchone()
    if row is None:
        return False
    sid, h, cadence = row
    if cadence == "daily":
        con.execute("DELETE FROM subscription WHERE email_hash = ? AND cadence = 'daily'", (h,))
    else:
        con.execute("DELETE FROM subscription WHERE subscription_id = ?", (sid,))  # cascades
    _forget_empty_alerts(con, h)
    con.commit()
    return True


def _forget_empty_alerts(con: Connection, email_hash: str) -> None:
    con.execute(
        "DELETE FROM alert WHERE email_hash = ? AND NOT EXISTS"
        " (SELECT 1 FROM alert_event ae WHERE ae.alert_id = alert.alert_id)",
        (email_hash,),
    )


def suppress(con: Connection, email: str, reason: str, now: datetime | None = None) -> None:
    """Never mail this address again. The ciphertext is kept only so a key rotation can
    re-derive the hash; the address is never read back."""
    v = vault.current()
    email = normalise_email(email)
    con.execute(
        "INSERT OR IGNORE INTO email_suppression (email_hash, email_enc, reason, created_at)"
        " VALUES (?, ?, ?, ?)",
        (v.hash(email), v.seal(email), reason, _iso(_now(now))),
    )
    con.commit()


def sweep(con: Connection, now: datetime | None = None) -> int:
    """Delete pending subscriptions whose confirmation window has closed: a stranger's
    address pointed at a docket is not kept (ADR 0011)."""
    cur = con.execute(
        "DELETE FROM subscription WHERE status = 'pending' AND expires_at <= ?",
        (_iso(_now(now)),),
    )
    con.commit()
    return cur.rowcount


def for_docket(con: Connection, docket_id: int) -> int:
    """How many active subscriptions a family has — operator-only, never published
    (ADR 0011: no watcher counts)."""
    return con.execute(
        "SELECT COUNT(*) FROM subscription WHERE docket_id = ? AND status = 'active'",
        (docket_id,),
    ).fetchone()[0]
