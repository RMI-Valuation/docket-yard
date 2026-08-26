"""Atom feeds: the alert stream as a stateless page. No subscription, no address, nothing
stored about the reader (ADR 0011). A feed carries exactly what an alert would — record
events from forward captures, never a backfill wave — for one docket family, one party, or
the whole agency; each entry is the same `EventSummary` the email and the webhook render.
"""

import re
from dataclasses import dataclass
from sqlite3 import Connection
from xml.sax.saxutils import escape

from docketyard.alerts import build
from docketyard.alerts.summary import EventSummary, event_summary
from docketyard.parties import resolve
from docketyard.web import urls

LIMIT = 100


@dataclass(frozen=True)
class Feed:
    title: str
    self_url: str
    site_url: str
    entries: list[EventSummary]


def _feed(con: Connection, title: str, self_url: str, site_url: str, ids, site: str) -> Feed:
    return Feed(title, self_url, site_url, [event_summary(con, i, site) for i in ids])


def family_feed(con: Connection, docket_id: int, printed: str, path: str, site: str) -> Feed:
    ids = build.record_events(con, docket_id=docket_id, limit=LIMIT)
    return _feed(
        con,
        f"{printed} — Docket Yard",
        f"https://{site}{path}/feed",
        f"https://{site}{path}",
        ids,
        site,
    )


def party_feed(con: Connection, party_id: int, site: str) -> Feed:
    comps = resolve.Components(con)
    ids = [eid for eid, _, _ in build.party_events(con, comps, party_id, limit=LIMIT)]
    name = comps.display_name(party_id)
    return _feed(
        con,
        f"Filings for {name} — Docket Yard",
        f"https://{site}{urls.party_feed_path(party_id)}",
        f"https://{site}{urls.party_path(party_id)}",
        ids,
        site,
    )


def agency_feed(con: Connection, site: str) -> Feed:
    ids = build.record_events(con, limit=LIMIT)
    return _feed(
        con,
        "Surface Transportation Board — every new filing and decision — Docket Yard",
        f"https://{site}/feed",
        f"https://{site}/",
        ids,
        site,
    )


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _text(s: str) -> str:
    """XML 1.0 cannot carry C0 control characters, whatever the Board printed."""
    return escape(_CONTROL.sub("", s))


def _entry(e: EventSummary, site: str, updated_fallback: str) -> str:
    body = "\n".join(e.lines()[1:]).strip()
    link = e.url or e.docket_url
    return (
        "  <entry>\n"
        f"    <id>tag:{site},2026:event/{e.event_id}</id>\n"
        f"    <title>{_text(e.title())}</title>\n"
        f'    <link rel="alternate" href="{escape(link, {chr(34): "&quot;"})}"/>\n'
        f"    <updated>{escape(e.observed_at or updated_fallback)}</updated>\n"
        f'    <content type="text">{_text(body)}</content>\n'
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
    return head + "".join(_entry(e, site, updated_fallback) for e in feed.entries) + "</feed>\n"
