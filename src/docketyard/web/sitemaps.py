"""Sitemaps, generated from the registry so that a deep page is found without a link.

An index at /sitemap.xml names one file per section; each stays under the protocol's
50,000-URL limit (the registry is 32,604 dockets today; a section splits by number when it
would exceed that). `lastmod` is measured: the newest capture that touched the docket, or
observed the record. Parties have no address (ADR 0013 addendum) and so no sitemap entry;
if ADR 0015 gives them one, a section is added here.
"""

from sqlite3 import Connection
from xml.sax.saxutils import escape

from docketyard.ingest.dockets import parse_docket_id
from docketyard.web import urls

LIMIT = 45_000
SECTIONS = ("pages", "dockets", "decisions", "filings")


def index(site: str) -> str:
    items = "".join(
        f"  <sitemap><loc>https://{site}/sitemap-{s}.xml</loc></sitemap>\n" for s in SECTIONS
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}</sitemapindex>\n"
    )


def _urlset(entries: list[tuple[str, str | None]]) -> str:
    rows = []
    for loc, lastmod in entries:
        mod = f"<lastmod>{escape(lastmod[:10])}</lastmod>" if lastmod else ""
        rows.append(f"  <url><loc>{escape(loc)}</loc>{mod}</url>\n")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{''.join(rows)}</urlset>\n"
    )


def section(con: Connection, site: str, name: str) -> str | None:
    base = f"https://{site}"
    if name == "pages":
        return _urlset(
            [
                (f"{base}{p}", None)
                for p in ("/", "/parties", "/stats", "/data", "/about", "/coverage", "/methodology")
            ]
        )
    if name == "dockets":
        rows = con.execute(
            """
            SELECT d.raw_docket, MAX(c.captured_at)
              FROM docket d
              LEFT JOIN event e ON e.docket_id = d.docket_id
              LEFT JOIN capture c ON c.capture_id = e.capture_id
             WHERE d.parent_docket_id IS NULL
             GROUP BY d.docket_id ORDER BY d.prefix, d.sequence LIMIT ?
            """,
            (LIMIT,),
        ).fetchall()
        out = []
        for raw, mod in rows:
            ident = parse_docket_id(raw)
            if ident is not None:
                out.append((f"{base}{urls.docket_path(ident)}", mod))
        return _urlset(out)
    if name in ("decisions", "filings"):
        table, col, path = (
            ("decision_record", "stb_decision_id", urls.decision_path)
            if name == "decisions"
            else ("filing", "stb_filing_id", urls.filing_path)
        )
        rows = con.execute(
            f"""
            SELECT r.{col}, MAX(c.captured_at)
              FROM {table} r
              JOIN event e ON e.event_id = r.observed_in_event
              JOIN capture c ON c.capture_id = e.capture_id
             GROUP BY r.{col} ORDER BY r.{col} LIMIT ?
            """,
            (LIMIT,),
        ).fetchall()
        return _urlset([(f"{base}{path(rid)}", mod) for rid, mod in rows])
    return None
