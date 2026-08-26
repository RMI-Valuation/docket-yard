"""Sitemaps, generated from the registry so that a deep page is found without a link.

An index at /sitemap.xml names one file per section per page of PAGE URLs (the protocol's
limit is 50,000; the record will pass that as the backfill lands), each rendered from the
store and memoised on the store's version stamp so crawlers do not re-run the queries.
`lastmod` is measured: the newest capture that touched the docket, or observed the record.
Parties have no address (ADR 0013 addendum) and so no sitemap entry; ADR 0015, if
accepted, adds a section here.
"""

from sqlite3 import Connection
from xml.sax.saxutils import escape

from docketyard.ingest.dockets import parse_docket_id
from docketyard.web import urls

PAGE = 40_000
SECTIONS = ("pages", "dockets", "decisions", "filings")
STATIC_PAGES = (
    "/",
    "/parties",
    "/stats",
    "/data",
    "/about",
    "/coverage",
    "/methodology",
    "/corrections",
    "/privacy",
)
_RECORDS = {
    "decisions": ("decision_record", "stb_decision_id", urls.decision_path),
    "filings": ("filing", "stb_filing_id", urls.filing_path),
}
_memo: dict[tuple, str] = {}


def _count(con: Connection, name: str) -> int:
    if name == "pages":
        return len(STATIC_PAGES)
    if name == "dockets":
        return con.execute("SELECT COUNT(*) FROM docket WHERE parent_docket_id IS NULL").fetchone()[
            0
        ]
    table, col, _ = _RECORDS[name]
    return con.execute(f"SELECT COUNT(DISTINCT {col}) FROM {table}").fetchone()[0]


def index(con: Connection, site: str) -> str:
    items = []
    for s in SECTIONS:
        pages = max(1, -(-_count(con, s) // PAGE))
        items += [
            f"  <sitemap><loc>https://{site}/sitemap-{s}-{n}.xml</loc></sitemap>\n"
            for n in range(1, pages + 1)
        ]
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{''.join(items)}</sitemapindex>\n"
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


def section(con: Connection, site: str, name: str, page: int, stamp: str) -> str | None:
    """One page of one section, or None when there is no such page. Memoised on the
    store's stamp; the memo is tiny (a handful of strings) and cleared when the stamp moves."""
    if name not in SECTIONS or page < 1:
        return None
    key = (site, name, page, stamp)
    if key in _memo:
        return _memo[key]
    for k in [k for k in _memo if k[3] != stamp]:
        del _memo[k]
    base = f"https://{site}"
    offset = (page - 1) * PAGE
    if name == "pages":
        entries = [(f"{base}{p}", None) for p in STATIC_PAGES[offset : offset + PAGE]]
    elif name == "dockets":
        rows = con.execute(
            """
            SELECT d.raw_docket, MAX(c.captured_at)
              FROM docket d
              LEFT JOIN docket m ON m.docket_id = d.docket_id OR m.parent_docket_id = d.docket_id
              LEFT JOIN event e ON e.docket_id = m.docket_id
              LEFT JOIN capture c ON c.capture_id = e.capture_id
             WHERE d.parent_docket_id IS NULL
             GROUP BY d.docket_id ORDER BY d.prefix, d.sequence LIMIT ? OFFSET ?
            """,
            (PAGE, offset),
        ).fetchall()
        entries = []
        for raw, mod in rows:
            ident = parse_docket_id(raw)
            if ident is not None:
                entries.append((f"{base}{urls.docket_path(ident)}", mod))
    else:
        table, col, path = _RECORDS[name]
        rows = con.execute(
            f"""
            SELECT r.{col}, MAX(c.captured_at)
              FROM {table} r
              JOIN event e ON e.event_id = r.observed_in_event
              JOIN capture c ON c.capture_id = e.capture_id
             GROUP BY r.{col} ORDER BY r.{col} LIMIT ? OFFSET ?
            """,
            (PAGE, offset),
        ).fetchall()
        entries = [(f"{base}{path(rid)}", mod) for rid, mod in rows]
    if not entries and page > 1:
        return None
    body = _urlset(entries)
    _memo[key] = body
    return body
