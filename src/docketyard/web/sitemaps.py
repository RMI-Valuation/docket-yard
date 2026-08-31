"""Sitemaps, generated from the registry so that a deep page is found without a link.

An index at /sitemap.xml names one file per section per page of PAGE URLs (the protocol's
limit is 50,000; the record will pass that as the backfill lands), each rendered from the
store and memoised on the store's version stamp so crawlers do not re-run the queries.
`lastmod` is measured: the newest capture that touched the docket, or observed the record,
or (for a party, ADR 0015) the newest capture holding a filing resolved to its component.
Only a component's representative is listed: every other member id 301s to it.
"""

from sqlite3 import Connection
from xml.sax.saxutils import escape

from docketyard.ingest.dockets import parse_docket_id
from docketyard.parties import resolve
from docketyard.web import urls

PAGE = 40_000
SECTIONS = ("pages", "dockets", "decisions", "filings", "comments", "parties", "documents")
STATIC_PAGES = (
    "/",
    "/parties",
    "/search",
    "/stats",
    "/data",
    "/api",
    "/court",
    "/protective",
    "/about",
    "/about/prefixes",
    "/about/FD",
    "/about/AB",
    "/about/NOR",
    "/about/EP",
    "/about/MCF",
    "/contribute",
    "/coverage",
    "/methodology",
    "/corrections",
    "/privacy",
)
_RECORDS = {
    "decisions": ("decision_record", "stb_decision_id", urls.decision_path),
    "filings": ("filing", "stb_filing_id", urls.filing_path),
}
# a comment is addressed under its docket, so it cannot use the generic (table, id, path)
# shape above: the address needs two columns. Folded by (number, row ref) — one comment in
# a docket and its sub-docket is one address; two comments sharing a number are two.
_COMMENTS = """
    SELECT d.raw_docket, c.comment_number, MAX(x.at) AS at
      FROM enviro_comment c
      JOIN docket d ON d.docket_id = c.docket_id
      JOIN (SELECT c2.comment_pk, cap.captured_at AS at FROM enviro_comment c2
              JOIN event e ON e.event_id = c2.observed_in_event
              JOIN capture cap ON cap.capture_id = e.capture_id) x
        ON x.comment_pk = c.comment_pk
     WHERE c.comment_pk = (SELECT c3.comment_pk FROM enviro_comment c3
                             JOIN docket d3 ON d3.docket_id = c3.docket_id
                            WHERE c3.comment_number = c.comment_number
                              AND COALESCE(c3.stb_row_ref, '') = COALESCE(c.stb_row_ref, '')
                            ORDER BY COALESCE(d3.sub_sequence, -1), COALESCE(d3.suffix, ''),
                                     c3.comment_pk LIMIT 1)
     GROUP BY c.comment_pk ORDER BY c.comment_number, d.raw_docket LIMIT ? OFFSET ?
"""
_memo: dict[tuple, str] = {}
_parties_memo: dict[str, list[tuple[int, str | None]]] = {}  # stamp -> entries


def _count(con: Connection, name: str, stamp: str) -> int:
    if name == "pages":
        return len(STATIC_PAGES)
    if name == "dockets":
        return con.execute("SELECT COUNT(*) FROM docket").fetchone()[0]
    if name == "parties":
        return len(_party_entries(con, stamp))
    if name == "documents":
        return con.execute("SELECT COUNT(*) FROM document").fetchone()[0]
    if name == "comments":
        return con.execute(
            "SELECT COUNT(*) FROM (SELECT 1 FROM enviro_comment"
            " GROUP BY comment_number, COALESCE(stb_row_ref, ''))"
        ).fetchone()[0]
    table, col, _ = _RECORDS[name]
    return con.execute(f"SELECT COUNT(DISTINCT {col}) FROM {table}").fetchone()[0]


def index(con: Connection, site: str, stamp: str) -> str:
    items = []
    for s in SECTIONS:
        pages = max(1, -(-_count(con, s, stamp) // PAGE))
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


def _party_entries(con: Connection, stamp: str) -> list[tuple[int, str | None]]:
    """(representative id, lastmod) for every same_as component, in id order. A thousand
    parties today, a few thousand after the backfill: one pass per store version — the
    index and every page of the section read the same list — not one query per party."""
    if stamp in _parties_memo:
        return _parties_memo[stamp]
    _parties_memo.clear()
    comps = resolve.Components(con)
    touched: dict[int, str] = {}
    for party_id, mod in con.execute(
        """
        SELECT l.party_id, MAX(c.captured_at)
          FROM filing_party_link l
          JOIN filing_party_span s ON s.span_id = l.span_id AND s.superseded_by IS NULL
               AND s.role = 'filed_for'
          JOIN filing f ON f.filing_pk = s.filing_pk AND f.filed_for_raw = s.raw_text
          JOIN event e ON e.event_id = f.observed_in_event
          JOIN capture c ON c.capture_id = e.capture_id
         WHERE l.superseded_by IS NULL
         GROUP BY l.party_id
        """
    ):
        rep = comps.rep(party_id)
        touched[rep] = max(touched.get(rep) or "", mod)
    reps = sorted({comps.rep(r[0]) for r in con.execute("SELECT party_id FROM party")})
    _parties_memo[stamp] = [(rep, touched.get(rep)) for rep in reps]
    return _parties_memo[stamp]


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
        # every docket address (ADR 0013): a parent's lastmod is the newest capture that
        # touched its family, a sub-docket's the newest that touched it. One grouped pass
        # into a dict — never a self-join on parent_docket_id (unindexed: the OR form
        # scanned docket × docket and hung). Sub-docket pages were left out until
        # 2026-08-27 (10,798 real pages invisible to crawlers; TODO's sitemap defect).
        touched: dict[int, str] = {}
        for docket_id, parent, mod in con.execute(
            """
            SELECT x.docket_id, x.parent_docket_id, MAX(c.captured_at)
              FROM docket x
              JOIN event e ON e.docket_id = x.docket_id
              JOIN capture c ON c.capture_id = e.capture_id
             GROUP BY x.docket_id
            """
        ):
            touched[docket_id] = max(touched.get(docket_id) or "", mod)
            if parent is not None:
                touched[parent] = max(touched.get(parent) or "", mod)
        rows = [
            (raw, touched.get(docket_id))
            for docket_id, raw in con.execute(
                "SELECT docket_id, raw_docket FROM docket"
                " ORDER BY prefix, sequence, COALESCE(sub_sequence, -1), COALESCE(suffix, '')"
                " LIMIT ? OFFSET ?",
                (PAGE, offset),
            )
        ]
        entries = []
        for raw, mod in rows:
            ident = parse_docket_id(raw)
            if ident is not None:
                entries.append((f"{base}{urls.docket_path(ident)}", mod))
    elif name == "parties":
        entries = [
            (f"{base}{urls.party_path(rep)}", mod)
            for rep, mod in _party_entries(con, stamp)[offset : offset + PAGE]
        ]
    elif name == "documents":
        # the bytes at a hash never change: lastmod is the day they were first held
        entries = [
            (f"{base}{urls.document_path(sha, kind)}", seen)
            for sha, seen, kind in con.execute(
                "SELECT document_sha256, first_seen_at, media_type FROM document"
                " ORDER BY document_sha256 LIMIT ? OFFSET ?",
                (PAGE, offset),
            )
        ]
    elif name == "comments":
        # the identity is guarded like every other caller: an unparseable docket must
        # drop its row, never 500 the whole sitemap page
        rows = [
            (parse_docket_id(raw), number, at)
            for raw, number, at in con.execute(_COMMENTS, (PAGE, offset))
        ]
        entries = [(f"{base}{urls.comment_path(i, number)}", at) for i, number, at in rows if i]
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
