"""Magic-link sign-in for a reviewer, and the session it mints.

ADR 0011 decided the shape and ADR 0016 inherits it: an account is an email address,
sign-in is a link in the post, and there is no password table. ADR 0016 adds the grant —
the operator gives it by hand and can withdraw it — and one hard limit: **nothing about what
a reviewer READS is stored**. This module writes two kinds of row and no third.

The two lives are different on purpose (migration 0017):

  'sign-in'   minted from an address, MAILED, single-use, twenty minutes. It proves someone
              reads that mailbox. Because it travels in a URL it lands in browser history,
              in a `Referer` and in a mail gateway's logs, so it is spent the moment it is
              used and it cannot become a session by being kept.
  'session'   minted from a consumed sign-in, never mailed, twelve hours. It proves the same
              thing without asking again, and it is revocable — which a signed cookie would
              not be, and which ADR 0016 requires because a grant can be withdrawn.

**A GET NEVER SIGNS ANYBODY IN.** Mail-security gateways fetch links on delivery; the
subscription flow learned this already (`/s/confirm/{token}` is a page with a button because
"a fetch must never count as consent"). A prefetched sign-in link that spent itself would
hand a session to nobody and lock the reviewer out of their own invitation.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from docketyard.alerts import vault
from docketyard.alerts.subscriptions import new_token, token_hash
from docketyard.store.db import utcnow

# Short, because it is in a URL and a URL is not a secret for long.
SIGN_IN_TTL_MINUTES = 20
# A working day at a queue, and no longer: the exposed class is a few items a month, so
# nobody needs to stay signed in overnight and a stolen laptop should not stay signed in.
SESSION_TTL_HOURS = 12


@dataclass(frozen=True)
class Reviewer:
    """Who is signed in. The ADDRESS IS NOT HERE — a review never needs it, so the review
    surfaces run on a box that cannot read one (ADR 0014's key opens the grant, not the
    queue)."""

    reviewer_id: int
    credit_name: str
    counts_public: bool


def _mint(con, reviewer_id: int, purpose: str, ttl: timedelta) -> str:
    token = new_token()
    now = datetime.now(UTC)
    con.execute(
        "INSERT INTO reviewer_token (token_hash, reviewer_id, purpose, expires_at, issued_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (
            token_hash(token),
            reviewer_id,
            purpose,
            (now + ttl).isoformat(timespec="seconds"),
            now.isoformat(timespec="seconds"),
        ),
    )
    return token


def request_link(con, email: str) -> str | None:
    """A sign-in token for a live grant, or None.

    THE CALLER MUST ANSWER THE SAME EITHER WAY. Returning None where there is no grant, and
    a token where there is, makes this function honest; a route that said "no such reviewer"
    would turn the form into an oracle for who holds a grant — and a reviewer's identity is
    published beside their work (ADR 0016) but their ADDRESS never is.

    Needs the vault key, because the grant is keyed by the HMAC of the address. `whoami` and
    `decide` do not, which is the split that lets a review happen on a box holding no key.
    """
    address = vault.normalise_email(email)
    row = con.execute(
        "SELECT reviewer_id FROM reviewer WHERE email_hash = ? AND revoked_at IS NULL",
        (vault.current().hash(address),),
    ).fetchone()
    if row is None:
        return None
    return _mint(con, row[0], "sign-in", timedelta(minutes=SIGN_IN_TTL_MINUTES))


def pending(con, token: str) -> Reviewer | None:
    """Who an unspent sign-in link names, WITHOUT spending it — so the page behind the link
    can say whose invitation it is before anybody presses anything."""
    row = con.execute(
        "SELECT r.reviewer_id, r.credit_name, r.counts_public FROM reviewer_token t"
        " JOIN reviewer r USING (reviewer_id)"
        " WHERE t.token_hash = ? AND t.purpose = 'sign-in' AND t.used_at IS NULL"
        " AND t.expires_at > ? AND r.revoked_at IS NULL",
        (token_hash(token), utcnow()),
    ).fetchone()
    return Reviewer(row[0], row[1], bool(row[2])) if row else None


def sign_in(con, token: str) -> str | None:
    """Spend a sign-in link and return a session token, or None if it will not spend.

    Single-use is enforced by the UPDATE's own WHERE: two requests racing the same link
    cannot both set `used_at`, so only one gets a session. Checking then updating would let
    both through.
    """
    now = utcnow()
    spent = con.execute(
        "UPDATE reviewer_token SET used_at = ? WHERE token_hash = ? AND purpose = 'sign-in'"
        " AND used_at IS NULL AND expires_at > ?",
        (now, token_hash(token), now),
    )
    if spent.rowcount != 1:
        return None
    row = con.execute(
        "SELECT t.reviewer_id FROM reviewer_token t JOIN reviewer r USING (reviewer_id)"
        " WHERE t.token_hash = ? AND r.revoked_at IS NULL",
        (token_hash(token),),
    ).fetchone()
    if row is None:  # the grant was withdrawn between the mail and the press
        return None
    session = _mint(con, row[0], "session", timedelta(hours=SESSION_TTL_HOURS))
    # AND THE SPENT LINK IS DELETED, not left to expire. Single use is just as strong either
    # way — a replay finds no row rather than a used one — and a spent row sitting out its
    # twenty minutes is a record of when somebody signed in, which `sign_out`'s own rule and
    # the privacy page both say is not kept. The claim should be true for the whole twenty
    # minutes too.
    con.execute("DELETE FROM reviewer_token WHERE token_hash = ?", (token_hash(token),))
    return session


def whoami(con, token: str | None) -> Reviewer | None:
    """The reviewer a live session names, or None.

    Read on every signed-in request, and it re-checks `revoked_at` every time rather than
    trusting the session: a withdrawal must end access now, not at the session's expiry.
    NOTHING IS WRITTEN HERE — no last-seen, no page, no count. ADR 0016: the review surfaces
    log the decision and nothing else.
    """
    if not token:
        return None
    row = con.execute(
        "SELECT r.reviewer_id, r.credit_name, r.counts_public FROM reviewer_token t"
        " JOIN reviewer r USING (reviewer_id)"
        " WHERE t.token_hash = ? AND t.purpose = 'session' AND t.expires_at > ?"
        " AND r.revoked_at IS NULL",
        (token_hash(token), utcnow()),
    ).fetchone()
    return Reviewer(row[0], row[1], bool(row[2])) if row else None


def sign_out(con, token: str | None) -> None:
    """Retire one session. The row is DELETED rather than expired: it holds no provenance,
    only a hash and two timestamps, and keeping it would be keeping a record of when
    somebody was signed in — which is exactly what ADR 0016 says is not stored."""
    if token:
        con.execute(
            "DELETE FROM reviewer_token WHERE token_hash = ? AND purpose = 'session'",
            (token_hash(token),),
        )


def end_all_sessions(con, reviewer_id: int) -> int:
    """Every live session for one reviewer. ADR 0016's "a role that can be withdrawn needs a
    way to be withdrawn": withdrawing the grant already stops `decide`, and this stops the
    queue being readable too, without waiting twelve hours."""
    cur = con.execute("DELETE FROM reviewer_token WHERE reviewer_id = ?", (reviewer_id,))
    return cur.rowcount


def sweep(con) -> int:
    """Drop every expired token. Not a security measure — an expired token is already
    refused by every read above — but a table that only grows is a table nobody prunes."""
    cur = con.execute("DELETE FROM reviewer_token WHERE expires_at <= ?", (utcnow(),))
    return cur.rowcount
