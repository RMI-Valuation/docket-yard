"""The alert join and delivery: which events reach which subscriptions, as one message.

Alerts fire off the event ledger and nothing else (schema-draft.md § 6). An event reaches
a subscription when it is above the subscription's high-water mark, sits in the docket
family, came from a FORWARD capture, and is one of the record-bearing event types — a
caption change (`docket_observed`) is not an alert. The mark advances in the same
transaction that records the alert, so a crash between the two cannot double-send.

Lateness is derived, not declared: an event is late when the forward table captures
around its own are further apart than the heartbeat threshold (docs/alerts.md), so the
catch-up after an outage says so without waiting on anyone.
"""

import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from sqlite3 import Connection
from zoneinfo import ZoneInfo

from docketyard.alerts import mail, subscriptions, vault, webhooks
from docketyard.alerts.mail import Outbound, Sender
from docketyard.alerts.summary import event_summary
from docketyard.capture.stb import DECISIONS, FILINGS
from docketyard.ingest.dockets import parse_docket_id
from docketyard.parties import resolve
from docketyard.store import gaps
from docketyard.store.db import utcnow
from docketyard.web import urls

ALERTING_EVENT_TYPES = ("filing_observed", "decision_observed", "document_replaced")
LATE_AFTER = timedelta(hours=3)  # the heartbeat's own threshold for last_forward_capture
DAILY_AT_HOUR = 23  # Eastern, the Board's clock
EASTERN = ZoneInfo("America/New_York")
MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class Carried:
    subscription_id: int
    email_hash: str  # the address itself is never read while building
    event_id: int
    docket_raw: str
    late: bool
    captured_at: str = ""


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="seconds")


def pending_events(con: Connection, cadence: str, channel: str | None = None) -> list[Carried]:
    """The join, for every active subscription of one cadence. A docket subscription takes
    the family's record events; a party subscription takes filing events whose current
    cell has a live filed_for link into the party's same_as component (decisions carry no
    filer and so never reach a party subscription)."""
    marks = ",".join("?" for _ in ALERTING_EVENT_TYPES)
    rows = con.execute(
        f"""
        SELECT s.subscription_id, s.email_hash, e.event_id, d.raw_docket, c.captured_at
          FROM subscription s
          JOIN docket d ON d.docket_id = s.docket_id OR d.parent_docket_id = s.docket_id
          JOIN event e ON e.docket_id = d.docket_id AND e.event_id > s.high_water_event_id
          JOIN capture c ON c.capture_id = e.capture_id
         WHERE s.status = 'active' AND s.cadence = ? AND s.docket_id IS NOT NULL
           AND (? IS NULL OR s.channel = ?)
           AND c.ingest_mode = 'forward' AND e.event_type IN ({marks})
         ORDER BY s.subscription_id, e.event_id
        """,
        (cadence, channel, channel, *ALERTING_EVENT_TYPES),
    ).fetchall()
    party_subs = con.execute(
        "SELECT subscription_id, email_hash, party_id, high_water_event_id FROM subscription"
        " WHERE status = 'active' AND cadence = ? AND party_id IS NOT NULL"
        " AND (? IS NULL OR channel = ?)",
        (cadence, channel, channel),
    ).fetchall()
    if party_subs:
        comps = resolve.Components(con)
        for sid, h, party_id, mark in party_subs:
            rows += [
                (sid, h, eid, raw, captured)
                for eid, raw, captured in party_events(con, comps, party_id, after=mark)
            ]
    late_memo: dict[str, bool] = {}
    out = []
    seen: set[tuple[int, int]] = set()
    for sid, h, eid, raw, captured in sorted(rows, key=lambda r: (r[0], r[2])):
        if (sid, eid) in seen:  # one cell cut into two spans of one component
            continue
        seen.add((sid, eid))
        if captured not in late_memo:
            late_memo[captured] = _is_late(con, captured)
        out.append(Carried(sid, h, eid, raw, late_memo[captured], captured))
    return out


def party_events(
    con: Connection,
    comps: "resolve.Components",
    party_id: int,
    *,
    after: int = 0,
    limit: int | None = None,
) -> list[tuple[int, str, str]]:
    """(event_id, raw_docket, captured_at) for forward filing events whose current cell has
    a live filed_for link into the party's same_as component — the one definition of
    "a filing for this party", shared by alerts and feeds. Newest first when limited."""
    members = comps.members(party_id)
    pm = ",".join("?" for _ in members)
    order = "DESC" if limit else "ASC"
    return con.execute(
        f"""
        SELECT DISTINCT e.event_id, d.raw_docket, c.captured_at
          FROM filing f
          JOIN filing_party_span sp ON sp.filing_pk = f.filing_pk
               AND sp.raw_text = f.filed_for_raw AND sp.superseded_by IS NULL
               AND sp.role = 'filed_for'
          JOIN filing_party_link l ON l.span_id = sp.span_id AND l.superseded_by IS NULL
               AND l.party_id IN ({pm})
          JOIN event e ON e.event_id = f.observed_in_event AND e.event_id > ?
          JOIN capture c ON c.capture_id = e.capture_id AND c.ingest_mode = 'forward'
          JOIN docket d ON d.docket_id = f.docket_id
         ORDER BY e.event_id {order} LIMIT ?
        """,
        (*members, after, limit if limit else -1),
    ).fetchall()


def record_events(
    con: Connection, *, docket_id: int | None = None, after: int = 0, limit: int | None = None
) -> list[int]:
    """Forward record events — for one family, or agency-wide — the one definition shared
    by docket alerts and feeds. Newest first when limited."""
    marks = ",".join("?" for _ in ALERTING_EVENT_TYPES)
    family = ""
    params: list = [after, *ALERTING_EVENT_TYPES]
    if docket_id is not None:
        members = [
            r[0]
            for r in con.execute(
                "SELECT docket_id FROM docket WHERE docket_id = ? OR parent_docket_id = ?",
                (docket_id, docket_id),
            )
        ] or [docket_id]
        family = "AND e.docket_id IN (" + ",".join("?" for _ in members) + ")"
        params += members
    order = "DESC" if limit else "ASC"
    return [
        r[0]
        for r in con.execute(
            f"""
            SELECT e.event_id FROM event e
              JOIN capture c ON c.capture_id = e.capture_id
             WHERE e.event_id > ? AND c.ingest_mode = 'forward' AND e.event_type IN ({marks})
               {family}
             ORDER BY e.event_id {order} LIMIT ?
            """,
            (*params, limit if limit else -1),
        )
    ]


PASS_WIDTH = timedelta(minutes=15)  # captures closer than this belong to the same pass


def _is_late(con: Connection, captured_at: str) -> bool:
    """Late = the pass this capture belongs to came more than LATE_AFTER after the
    previous pass. Captures within one pass are seconds apart, so 'previous' means the
    newest table capture at least PASS_WIDTH older than this one."""
    try:
        this = datetime.fromisoformat(captured_at)
    except ValueError:
        return False
    previous = con.execute(
        "SELECT MAX(captured_at) FROM capture WHERE ingest_mode = 'forward'"
        " AND filter_asserted = 1 AND table_action IN (?, ?) AND captured_at < ?",
        (FILINGS, DECISIONS, _iso(this - PASS_WIDTH)),
    ).fetchone()[0]
    if not previous:
        return False
    try:
        return this - datetime.fromisoformat(previous) > LATE_AFTER
    except ValueError:
        return False


def build(
    con: Connection, cadence: str, now: datetime | None = None, channel: str | None = None
) -> list[int]:
    """Record alerts for everything pending under one cadence: one alert per subscription
    for 'pass', one per address for 'daily'. Returns the new alert ids."""
    t = _iso(now or datetime.now(UTC))
    carried = pending_events(con, cadence, channel)
    if not carried:
        return []
    # one alert per group: the address alone for a digest, the subscription otherwise
    groups: dict[tuple[str, str, int | None], list[Carried]] = {}
    channels = dict(con.execute("SELECT subscription_id, channel FROM subscription"))
    for c in carried:
        ch = channels[c.subscription_id]
        key = (c.email_hash, ch, None if cadence == "daily" else c.subscription_id)
        groups.setdefault(key, []).append(c)
    ids = []
    for (h, channel, _), items in groups.items():
        # the ciphertext is copied from the subscription; the alert never sees the address
        enc = con.execute(
            "SELECT email_enc FROM subscription WHERE subscription_id = ?",
            (items[0].subscription_id,),
        ).fetchone()[0]
        alert_id = con.execute(
            "INSERT INTO alert (email_hash, email_enc, cadence, status, created_at, channel)"
            " VALUES (?, ?, ?, 'pending', ?, ?)",
            (h, enc, cadence, t, channel),
        ).lastrowid
        marks: dict[int, int] = {}
        for c in items:
            gap_id = _gap_covering(con, c.captured_at) if c.late else None
            con.execute(
                "INSERT INTO alert_event (alert_id, subscription_id, event_id, late,"
                " late_gap_id) VALUES (?, ?, ?, ?, ?)",
                (alert_id, c.subscription_id, c.event_id, int(c.late), gap_id),
            )
            marks[c.subscription_id] = max(marks.get(c.subscription_id, 0), c.event_id)
        for sid, mark in marks.items():
            con.execute(
                "UPDATE subscription SET high_water_event_id = ? WHERE subscription_id = ?",
                (mark, sid),
            )
        ids.append(alert_id)
    con.commit()
    return ids


def _gap_covering(con: Connection, captured_at: str) -> int | None:
    """The operator-recorded capture gap the late capture falls in, if one exists yet."""
    row = con.execute(  # the same window as store/gaps.py: a catch-up runs after the end
        "SELECT gap_id FROM coverage_gap WHERE failure IN ('captures', 'events')"
        " AND started_at <= ? AND (ended_at IS NULL OR datetime(ended_at, ?) >= datetime(?))"
        " ORDER BY started_at DESC LIMIT 1",
        (captured_at, gaps.CATCH_UP, captured_at),
    ).fetchone()
    return row[0] if row else None


def daily_due(con: Connection, now: datetime | None = None, channel: str | None = None) -> bool:
    """True when no daily digest has been built since the most recent 23:00 Eastern —
    so a pass that misses the 23:00 hour still sends the day's digest, late, rather
    than folding it into tomorrow's. Per channel when asked, so a webhook digest built
    while mail was unconfigured does not cost the email digest its day."""
    local = (now or datetime.now(UTC)).astimezone(EASTERN)
    today_at = local.replace(hour=DAILY_AT_HOUR, minute=0, second=0, microsecond=0)
    boundary = today_at if local >= today_at else today_at - timedelta(days=1)
    last = con.execute(
        "SELECT MAX(created_at) FROM alert WHERE cadence = 'daily' AND (? IS NULL OR channel = ?)",
        (channel, channel),
    ).fetchone()[0]
    if not last:  # never built: the first digest waits for the first 23:00
        return local >= today_at
    return datetime.fromisoformat(last) < boundary


# --- rendering ---------------------------------------------------------------------------


def render(con: Connection, alert_id: int, unsubscribe_url: str, site: str) -> Outbound:
    enc = con.execute("SELECT email_enc FROM alert WHERE alert_id = ?", (alert_id,)).fetchone()[0]
    email = vault.current().open(enc)  # the only moment an address is readable: to send
    rows = con.execute(
        "SELECT ae.event_id, MAX(ae.late), MIN(cg.started_at), MAX(cg.ended_at)"
        " FROM alert_event ae LEFT JOIN coverage_gap cg ON cg.gap_id = ae.late_gap_id"
        " WHERE ae.alert_id = ? GROUP BY ae.event_id ORDER BY ae.event_id",
        (alert_id,),
    ).fetchall()  # an event two subscriptions of one address both carry appears once
    dockets = sorted({_docket_of(con, eid) for eid, *_ in rows})
    n = len(rows)
    party_name = _party_subject(con, alert_id)
    if party_name:
        subject = f"{party_name}: {n} new {'filing' if n == 1 else 'filings'}"
    elif len(dockets) == 1:
        subject = f"{dockets[0]}: {n} new {'entry' if n == 1 else 'entries'}"
    else:
        subject = f"Docket Yard daily: {n} new entries in {len(dockets)} proceedings"
    lines = [
        subject,
        "",
        "Filings and decisions the Surface Transportation Board posted to proceedings you"
        " follow. Dates are the Board's own; every entry links to the Board's file.",
        "",
    ]
    for eid, *_ in rows:
        lines.extend(event_summary(con, eid, site).lines())
        lines.append("")
    late = [(s, e) for _, is_late, s, e in rows if is_late]
    if late:
        spans = sorted({(s or "an unrecorded time", e or "recovery") for s, e in late})
        for s, e in spans:
            lines.append(
                f"Some of these entries were posted by the Board between {s} and {e},"
                " while Docket Yard was not keeping the record. They are delivered late."
            )
        lines.append("")
    lines += [
        "—",
        f"Docket Yard is an independent public record, not the Board. https://{site}/",
        f"Stop these emails (one click, no sign-in): {unsubscribe_url}",
    ]
    return Outbound(
        to=email, subject=subject, text="\n".join(lines), unsubscribe_url=unsubscribe_url
    )


def _party_subject(con: Connection, alert_id: int) -> str | None:
    """A pass-cadence alert carrying one party subscription is headed by the party."""
    rows = con.execute(
        "SELECT DISTINCT s.party_id FROM alert_event ae"
        " JOIN subscription s ON s.subscription_id = ae.subscription_id"
        " WHERE ae.alert_id = ?",
        (alert_id,),
    ).fetchall()
    if len(rows) == 1 and rows[0][0] is not None:
        return resolve.display_name(con, rows[0][0])
    return None


def _docket_of(con: Connection, event_id: int) -> str:
    row = con.execute(
        "SELECT d.raw_docket FROM event e JOIN docket d ON d.docket_id = e.docket_id"
        " WHERE e.event_id = ?",
        (event_id,),
    ).fetchone()
    return urls.printed_docket(parse_docket_id(row[0])) if row else "?"


def payload(con: Connection, alert_id: int, unsubscribe_url: str, site: str) -> dict:
    """The webhook body: the same events the email carries, structured."""
    rows = con.execute(
        "SELECT ae.event_id, MAX(ae.late), MIN(cg.started_at), MAX(cg.ended_at)"
        " FROM alert_event ae LEFT JOIN coverage_gap cg ON cg.gap_id = ae.late_gap_id"
        " WHERE ae.alert_id = ? GROUP BY ae.event_id ORDER BY ae.event_id",
        (alert_id,),
    ).fetchall()
    events = []
    for eid, late, gap_start, gap_end in rows:
        d = event_summary(con, eid, site).as_dict()
        d["late"] = bool(late)  # posted while this record was not being kept
        d["late_between"] = [gap_start, gap_end] if late else None  # the recorded gap, if any
        events.append(d)
    return {
        "source": f"https://{site}/",
        "alert_id": alert_id,
        "party": _party_subject(con, alert_id),
        "events": events,
        "note": "Docket Yard is an independent public record, not the Board. Dates are the"
        " Board's own; every entry links to the Board's file.",
        "unsubscribe_url": unsubscribe_url,
    }


# --- delivery ----------------------------------------------------------------------------


def _claim(con: Connection, alert_id: int) -> None:
    con.execute(
        "UPDATE alert SET attempts = attempts + 1, status = CASE WHEN attempts + 1"
        " >= ? THEN 'failed' ELSE 'pending' END WHERE alert_id = ?",
        (MAX_ATTEMPTS, alert_id),
    )
    con.commit()  # the claim: whatever happens next, this attempt is on the record


def _carrier(con: Connection, alert_id: int) -> int | None:
    """The subscription an alert is delivered for — or None, deleting the alert, when the
    recipient unsubscribed after it was built: nothing is left to carry."""
    sid = con.execute(
        "SELECT MIN(subscription_id) FROM alert_event WHERE alert_id = ?", (alert_id,)
    ).fetchone()[0]
    if sid is None:
        con.execute("DELETE FROM alert WHERE alert_id = ?", (alert_id,))
        con.commit()
    return sid


def deliver_webhooks(con: Connection, site: str, log=print) -> dict:
    """POST every pending webhook alert, signed. Same claim-before-send discipline as
    mail; a refused or unreachable endpoint is retried on a later pass up to MAX_ATTEMPTS.
    A URL that resolves into a private network is failed outright and logged. The
    suppression list applies to a URL's hash as it does to an address's, so an operator
    can stop an endpoint the same way."""
    stats = {"sent": 0, "failed": 0, "suppressed": 0}
    pending = con.execute(
        "SELECT alert_id, email_hash FROM alert WHERE status = 'pending' AND channel = 'webhook'"
        " AND attempts < ? ORDER BY alert_id",
        (MAX_ATTEMPTS,),
    ).fetchall()
    for alert_id, h in pending:
        if subscriptions.is_suppressed(con, h):
            con.execute("UPDATE alert SET status = 'failed' WHERE alert_id = ?", (alert_id,))
            con.commit()
            stats["suppressed"] += 1
            continue
        sid = _carrier(con, alert_id)
        if sid is None:
            continue
        sub = subscriptions.get(con, sid)
        if sub is None or sub.channel != "webhook" or not sub.secret:
            con.execute("UPDATE alert SET status = 'failed' WHERE alert_id = ?", (alert_id,))
            con.commit()
            stats["failed"] += 1
            log(f"alert {alert_id}: no webhook subscription to deliver for")
            continue
        token = subscriptions.unsubscribe_token(con, sid)
        body = payload(con, alert_id, urls.unsubscribe_url(site, token), site)
        _claim(con, alert_id)
        try:
            result = webhooks.post(sub.email, body, sub.secret, delivery_id=str(alert_id))
        except webhooks.RefusedDestination as e:
            subscriptions.withdraw_token(con, token)
            con.execute("UPDATE alert SET status = 'failed' WHERE alert_id = ?", (alert_id,))
            con.commit()
            stats["failed"] += 1
            log(f"alert {alert_id}: webhook refused ({e})")
            continue
        if not result.accepted:
            subscriptions.withdraw_token(con, token)  # nobody received the link it carried
            stats["failed"] += 1
            log(
                f"alert {alert_id}: webhook to {webhooks.describe(sub.email)} answered"
                f" {result.status} {result.detail}".rstrip()
            )
            continue
        con.execute(
            "UPDATE alert SET status = 'sent', sent_at = ?, message_id = ? WHERE alert_id = ?",
            (utcnow(), f"http-{result.status}", alert_id),
        )
        con.commit()
        stats["sent"] += 1
    return stats


def deliver(con: Connection, sender: Sender, site: str, log=print) -> dict:
    """Send every pending email alert in one SMTP session. The attempt is claimed and
    committed BEFORE the send, so a crash after the provider accepted the message cannot
    re-send it without limit. A suppressed address is marked failed without a send; a
    provider rejection is retried on a later call up to MAX_ATTEMPTS; a dropped
    connection ends the session without charging the alerts still waiting."""
    stats = {"sent": 0, "failed": 0, "suppressed": 0}
    pending = con.execute(
        "SELECT alert_id, email_hash FROM alert WHERE status = 'pending' AND channel = 'email'"
        " AND attempts < ? ORDER BY alert_id",
        (MAX_ATTEMPTS,),
    ).fetchall()
    if not pending:
        return stats
    with sender.session() as session:
        for alert_id, h in pending:
            if subscriptions.is_suppressed(con, h):
                con.execute("UPDATE alert SET status = 'failed' WHERE alert_id = ?", (alert_id,))
                stats["suppressed"] += 1
                con.commit()
                continue
            sid = _carrier(con, alert_id)
            if sid is None:
                continue
            if (
                con.execute(
                    "SELECT channel FROM subscription WHERE subscription_id = ?", (sid,)
                ).fetchone()[0]
                != "email"
            ):  # never mail a URL
                con.execute("UPDATE alert SET status = 'failed' WHERE alert_id = ?", (alert_id,))
                con.commit()
                stats["failed"] += 1
                continue
            token = subscriptions.unsubscribe_token(con, sid)
            out = render(con, alert_id, urls.unsubscribe_url(site, token), site)
            _claim(con, alert_id)
            try:
                message_id = session.send(out)
            except smtplib.SMTPServerDisconnected as e:
                # transport, not this message: give the attempt back and stop the session
                con.execute(
                    "UPDATE alert SET attempts = attempts - 1, status = 'pending'"
                    " WHERE alert_id = ?",
                    (alert_id,),
                )
                con.commit()
                log(f"alert {alert_id}: connection lost ({e}); delivery resumes next pass")
                break
            except Exception as e:  # noqa: BLE001 — this message was refused; retried later
                subscriptions.withdraw_token(con, token)  # the link it carried went nowhere
                stats["failed"] += 1
                log(f"alert {alert_id}: send failed ({mail.describe_failure(e)})")
                continue
            con.execute(
                "UPDATE alert SET status = 'sent', sent_at = ?, message_id = ? WHERE alert_id = ?",
                (utcnow(), message_id, alert_id),
            )
            con.commit()
            stats["sent"] += 1
    return stats


def run_after_pass(con: Connection, sender: Sender | None, site: str, now=None, log=print) -> dict:
    """What the poller calls after every pass: sweep, build pass-cadence alerts, build the
    daily digest when it is due, deliver — email through the sender, webhooks directly.
    Without the vault key nothing is built — the marks stay put, so the first keyed pass
    folds the backlog into one alert per subscription instead of one per historical pass.
    Without a mail sender, webhooks still go out and email subscriptions wait, unbuilt."""
    swept = subscriptions.sweep(con, now)
    if not vault.is_open():
        return {"swept": swept, "built": 0, "skipped": "no DY_EMAIL_KEY"}
    # without a mail sender only webhook alerts are built: the email marks stay put, so the
    # first pass with a sender folds the backlog into one alert per subscription
    channels = ("email", "webhook") if sender is not None else ("webhook",)
    built = []
    for channel in channels:
        built += build(con, "pass", now, channel)
        if daily_due(con, now, channel):
            built += build(con, "daily", now, channel)
    hooks = deliver_webhooks(con, site, log)
    out = {
        "swept": swept,
        "built": len(built),
        "webhooks_sent": hooks["sent"],
        "webhooks_failed": hooks["failed"] + hooks["suppressed"],
    }
    if sender is None:  # email subscriptions wait, unbuilt, until a sender is configured
        return {**out, "sent": 0, "failed": 0, "suppressed": 0, "skipped": "no sender"}
    return {**out, **deliver(con, sender, site, log)}
