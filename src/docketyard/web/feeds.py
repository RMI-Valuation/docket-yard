"""Atom feeds: the alert stream as a stateless page. No subscription, no address, nothing
stored about the reader (ADR 0011). A feed carries exactly what an alert would — record
events from forward captures, never a backfill wave — for one docket family, one party, or
the whole agency; each entry is the same `EventSummary` the email and the webhook render.
"""

from dataclasses import dataclass
from sqlite3 import Connection
from xml.sax.saxutils import escape

from docketyard.alerts.build import ALERTING_EVENT_TYPES
from docketyard.alerts.summary import EventSummary, event_summary
from docketyard.parties import resolve

LIMIT = 100


@dataclass(frozen=True)
class Feed:
    title: str
    self_url: str
    site_url: str
    entries: list[EventSummary]


def _events_for_family(con: Connection, docket_id: int, limit: int) -> list[int]:
    marks = ",".join("?" for _ in ALERTING_EVENT_TYPES)
    return [
        r[0]
        for r in con.execute(
            f"""
            SELECT e.event_id FROM event e
              JOIN docket d ON d.docket_id = e.docket_id
              JOIN capture c ON c.capture_id = e.capture_id
             WHERE (d.docket_id = ? OR d.parent_docket_id = ?)
               AND c.ingest_mode = 'forward' AND e.event_type IN ({marks})
             ORDER BY e.event_id DESC LIMIT ?
            """,
            (docket_id, docket_id, *ALERTING_EVENT_TYPES, limit),
        )
    ]


def _events_for_party(con: Connection, party_id: int, limit: int) -> list[int]:
    members = resolve.Components(con).members(party_id)
    pm = ",".join("?" for _ in members)
    return [
        r[0]
        for r in con.execute(
            f"""
            SELECT DISTINCT e.event_id FROM filing f
              JOIN filing_party_span sp ON sp.filing_pk = f.filing_pk
                   AND sp.raw_text = f.filed_for_raw AND sp.superseded_by IS NULL
                   AND sp.role = 'filed_for'
              JOIN filing_party_link l ON l.span_id = sp.span_id AND l.superseded_by IS NULL
                   AND l.party_id IN ({pm})
              JOIN event e ON e.event_id = f.observed_in_event
              JOIN capture c ON c.capture_id = e.capture_id AND c.ingest_mode = 'forward'
             ORDER BY e.event_id DESC LIMIT ?
            """,
            (*members, limit),
        )
    ]


def _events_agency_wide(con: Connection, limit: int) -> list[int]:
    marks = ",".join("?" for _ in ALERTING_EVENT_TYPES)
    return [
        r[0]
        for r in con.execute(
            f"""
            SELECT e.event_id FROM event e
              JOIN capture c ON c.capture_id = e.capture_id
             WHERE c.ingest_mode = 'forward' AND e.event_type IN ({marks})
             ORDER BY e.event_id DESC LIMIT ?
            """,
            (*ALERTING_EVENT_TYPES, limit),
        )
    ]


def family_feed(con: Connection, docket_id: int, printed: str, path: str, site: str) -> Feed:
    ids = _events_for_family(con, docket_id, LIMIT)
    return Feed(
        f"{printed} — Docket Yard",
        f"https://{site}{path}/feed",
        f"https://{site}{path}",
        [event_summary(con, i, site) for i in ids],
    )


def party_feed(con: Connection, party_id: int, site: str) -> Feed:
    ids = _events_for_party(con, party_id, LIMIT)
    name = resolve.display_name(con, party_id)
    return Feed(
        f"Filings for {name} — Docket Yard",
        f"https://{site}/feed/party/{party_id}",
        f"https://{site}/parties?name={name}",
        [event_summary(con, i, site) for i in ids],
    )


def agency_feed(con: Connection, site: str) -> Feed:
    ids = _events_agency_wide(con, LIMIT)
    return Feed(
        "Surface Transportation Board — every new filing and decision — Docket Yard",
        f"https://{site}/feed",
        f"https://{site}/",
        [event_summary(con, i, site) for i in ids],
    )


def _entry(e: EventSummary, site: str) -> str:
    body = "\n".join(e.lines()[1:]).strip()
    link = e.url or e.docket_url
    return (
        "  <entry>\n"
        f"    <id>tag:{site},2026:event/{e.event_id}</id>\n"
        f"    <title>{escape(e.title())}</title>\n"
        f'    <link rel="alternate" href="{escape(link, {chr(34): "&quot;"})}"/>\n'
        f"    <updated>{escape(e.observed_at)}</updated>\n"
        f'    <content type="text">{escape(body)}</content>\n'
        "  </entry>\n"
    )


def render(feed: Feed, site: str, updated_fallback: str) -> str:
    updated = feed.entries[0].observed_at if feed.entries else updated_fallback
    q = {chr(34): "&quot;"}
    head = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <title>{escape(feed.title)}</title>\n"
        f"  <id>{escape(feed.self_url)}</id>\n"
        f'  <link rel="self" href="{escape(feed.self_url, q)}"/>\n'
        f'  <link rel="alternate" href="{escape(feed.site_url, q)}"/>\n'
        f"  <updated>{escape(updated)}</updated>\n"
        "  <author><name>Docket Yard</name></author>\n"
        "  <subtitle>An independent public record of proceedings before the Surface"
        " Transportation Board. Not the Board. Every entry links to the Board's own"
        " file.</subtitle>\n"
    )
    return head + "".join(_entry(e, site) for e in feed.entries) + "</feed>\n"
