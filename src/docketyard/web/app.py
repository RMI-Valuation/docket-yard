"""The web tier: server-rendered pages over the projections, at the ADR 0013 addresses.

Every page is derived from the store at request time (the agency moves ~250 times a month;
caching is a later concern) and quotes the record as printed — captions and decision
summaries appear in the Board's own capitals until a casing method exists as a derived
assertion with provenance. No account, no cookie, no tracking on any read path (ADR 0011).

The server is a reader with one exception: it opens the store read-only for every page,
refuses a missing file or a store whose schema is not the one this code was built for, and
never runs a migration — that is ingest's job, in its own process. The exception is the
subscription flow (subscribe, confirm, unsubscribe), the one place a reader hands over an
address (ADR 0011); those three handlers open a writable connection and nothing else does.
"""

import hashlib
import sqlite3
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from importlib import resources
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Body, FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from docketyard import __version__
from docketyard.alerts import feedback, mail, subscriptions, vault, webhooks
from docketyard.ingest.dockets import find_docket, parse_docket_id
from docketyard.parties import resolve
from docketyard.store import coverage, dump, home, projections, search, sheet, stats
from docketyard.store.db import MIGRATIONS, utcnow
from docketyard.web import feeds, labels, sitemaps, urls

_PKG = resources.files("docketyard.web")
JSON_SHAPE = 1  # bumped when a field of the JSON twins changes meaning or name (docs/data.md)
PAGE_CACHE = 300  # seconds a reader page may be cached: a poll is 1800, a late entry costs one
NEVER_CACHE = ("/s/", "/subscribe", "/ses/", "/health", "/suggest")  # tokens, consent
MOUNTS = ("/static/", "/data/files/")  # StaticFiles: streams, validates and HEADs itself
DISCOVERY_CACHE = 86400  # robots and sitemaps: a day
PUBLIC_CACHE = {"Cache-Control": "public, max-age=1800"}  # the numbers move once a poll
# outside intake is GitHub Issues (CLAUDE.md); the form template carries the fields
CORRECTIONS_URL = (
    "https://github.com/RMI-Valuation/docket-yard/issues/new?template=data-correction.yml"
)
IDEA_URL = "https://github.com/RMI-Valuation/docket-yard/issues/new?template=idea.yml"


def _uri(db_path: str | Path) -> str:
    return Path(db_path).resolve().as_uri() + "?mode=ro"


def _connect(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(_uri(db_path), uri=True)
    con.execute("PRAGMA query_only = ON")
    return con


def _check_store(db_path: str | Path) -> None:
    if not Path(db_path).is_file():
        raise FileNotFoundError(f"store not found: {db_path} (the server never creates one)")
    con = _connect(db_path)
    try:
        version = con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()
    expected = MIGRATIONS[-1][0]
    if version != expected:
        raise RuntimeError(
            f"store schema version {version} != {expected}; run ingest to migrate, not serve"
        )


def fmt_date(value: str | None) -> str:
    """The same date the record printed, in the house form: 25 Aug 2026. A value that is
    not an ISO date is shown untouched rather than guessed at."""
    if not value:
        return ""
    try:
        d = date.fromisoformat(value[:10])
    except ValueError:
        return value
    return f"{d.day} {d.strftime('%b %Y')}"


def fmt_day_month(value: str | None) -> str:
    """25 Aug — for a column whose year is stated once above it."""
    if not value:
        return ""
    try:
        d = date.fromisoformat(value[:10])
    except ValueError:
        return value
    return f"{d.day} {d.strftime('%b')}"


def fmt_range(start: str, end: str) -> str:
    """18–25 August 2026, collapsing what the two dates share."""
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return f"{start} to {end}"
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day}–{b.day} {b.strftime('%B %Y')}"
    if a.year == b.year:
        return f"{a.day} {a.strftime('%B')} – {b.day} {b.strftime('%B %Y')}"
    return f"{a.day} {a.strftime('%B %Y')} – {b.day} {b.strftime('%B %Y')}"


def fmt_when(value: str | None) -> str:
    """A capture timestamp: 25 Aug 2026, 14:35 UTC."""
    if not value:
        return ""
    try:
        t = datetime.fromisoformat(value)
    except ValueError:
        return value
    if t.tzinfo is not None:
        t = t.astimezone(UTC)
    return f"{t.day} {t.strftime('%b %Y, %H:%M')} UTC"


def _path(request: Request) -> str:
    """The request path relative to any mount prefix, for canonical-address checks."""
    root = request.scope.get("root_path", "")
    path = request.url.path
    return path[len(root) :] if root and path.startswith(root) else path


def _connect_rw(db_path: str | Path) -> sqlite3.Connection:
    """The one writable path: subscriptions (ADR 0011). Everything else reads."""
    # a rebuild of the search index or a wave's commit may hold the write lock for seconds
    con = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=rw", uri=True, timeout=30)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def create_app(
    db_path: str | Path,
    *,
    site_name: str = "Docket Yard",
    site_host: str = "docketyard.org",
    sender: mail.Sender | None = None,
    feedback_topic: str | None = None,  # the SNS topic ARN SES feedback must come from
    public_dir: str | Path | None = None,  # where `docketyard dump` writes (M9)
) -> FastAPI:
    _check_store(db_path)
    public_dir = Path(public_dir) if public_dir else Path(db_path).parent / "public"
    app = FastAPI(title=site_name, version=__version__, docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(_PKG / "templates"))
    templates.env.filters["fmt_date"] = fmt_date
    templates.env.filters["fmt_when"] = fmt_when
    templates.env.filters["fmt_day_month"] = fmt_day_month
    templates.env.filters["plural"] = labels.plural
    templates.env.filters["commas"] = "{:,}".format
    templates.env.globals.update(
        fmt_range=fmt_range,
        prefix_name=labels.prefix_name,
        display_filed_for=labels.display_filed_for,
    )
    # The stylesheet is cached a week; its URL carries its content hash so a deploy is seen.
    css_hash = hashlib.sha256((_PKG / "static" / "site.css").read_bytes()).hexdigest()[:12]
    templates.env.globals.update(
        site_name=site_name,
        site_host=site_host,
        asset_v=css_hash,
        docket_path=urls.docket_path,
        printed_docket=urls.printed_docket,
        cite_docket=urls.cite_docket,
        decision_path=urls.decision_path,
        filing_path=urls.filing_path,
        party_path=urls.party_path,
        party_feed_path=urls.party_feed_path,
        parse_docket_id=parse_docket_id,
        kind_label=labels.kind_label,
        filter_key=labels.filter_key,
        confirm_ttl_hours=subscriptions.CONFIRM_TTL_HOURS,  # the privacy page quotes it
    )
    app.mount("/static", StaticFiles(directory=str(_PKG / "static")), name="static")
    # the dump timer owns this directory; the web tier only reads it, and may start first
    app.mount(
        "/data/files", StaticFiles(directory=str(public_dir), check_dir=False), name="data-files"
    )

    def render(request: Request, name: str, **context):
        context.setdefault("canonical", _path(request))
        return templates.TemplateResponse(request, name, context)

    def atom(feed: feeds.Feed) -> Response:
        body = feeds.render(feed, site_host, utcnow())
        return Response(
            body,
            media_type="application/atom+xml; charset=utf-8",
            headers=PUBLIC_CACHE,
        )

    def stamp() -> str:
        """The store's version as one cheap number: the newest capture and event ids. Every
        reader page is a function of the store, so this is a valid validator for all of
        them — and it costs two primary-key lookups, not a render."""
        con = _connect(db_path)
        try:
            c, e, r, k, s = con.execute(
                "SELECT (SELECT MAX(capture_id) FROM capture), (SELECT MAX(event_id) FROM event),"
                " (SELECT MAX(edge_id) FROM party_relationship),"
                " (SELECT MAX(correction_id) FROM correction),"
                " (SELECT build FROM search_meta WHERE key = 'built')"
            ).fetchone()
        finally:
            con.close()
        # an operator's join or unjoin (ADR 0015) moves addresses without a capture, and a
        # search rebuild changes result pages: both are part of the version
        return f"{c or 0}.{e or 0}.{r or 0}.{k or 0}.{s or 0}"

    @app.middleware("http")
    async def http_hygiene(request: Request, call_next):
        """Reader pages carry a validator and a short public cache life; a matching
        If-None-Match answers 304 before anything is rendered. Consent, token and telemetry
        paths are marked no-store. Mounted files (static assets, the snapshot) are left to
        StaticFiles, which streams and validates them itself. No cookie is ever set, so
        caching is safe everywhere else (ADR 0011). HEAD is registered on every GET route
        (below), so nothing here rewrites the method."""
        path = _path(request)
        if request.method not in ("GET", "HEAD") or path.startswith(MOUNTS):
            return await call_next(request)
        if path.startswith(NEVER_CACHE) or (path == "/search" and request.query_params.get("q")):
            # a result page's address carries what was typed: no validator, no cache
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        etag = f'W/"{stamp()}"'
        if request.headers.get("if-none-match") and etag in [
            v.strip() for v in request.headers["if-none-match"].split(",")
        ]:
            return Response(status_code=304, headers={"ETag": etag})
        response = await call_next(request)
        if response.status_code == 200:
            response.headers.setdefault("Cache-Control", f"public, max-age={PAGE_CACHE}")
            response.headers["ETag"] = etag
        return response

    def public(body: str, media_type: str, max_age: int = DISCOVERY_CACHE) -> Response:
        return Response(
            body, media_type=media_type, headers={"Cache-Control": f"public, max-age={max_age}"}
        )

    # --- discovery: robots.txt and sitemaps, generated from the registry --------------

    @app.get("/robots.txt")
    def robots():
        # the paths a cache must not keep are the paths a crawler must not index
        lines = ["User-agent: *"] + [f"Disallow: {p}" for p in NEVER_CACHE if p != "/health"]
        return public(
            "\n".join(lines) + f"\nSitemap: https://{site_host}/sitemap.xml\n", "text/plain"
        )

    XML = "application/xml; charset=utf-8"

    @app.get("/sitemap.xml")
    def sitemap_index():
        con = _connect(db_path)
        try:
            return public(sitemaps.index(con, site_host, stamp()), XML)
        finally:
            con.close()

    @app.get("/sitemap-{section}-{page}.xml")
    def sitemap_section(section: str, page: int):
        con = _connect(db_path)
        try:
            body = sitemaps.section(con, site_host, section, page, stamp())
        finally:
            con.close()
        if body is None:
            raise HTTPException(404)
        return public(body, XML)

    @app.exception_handler(404)
    def not_found(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail != "Not Found" else ""
        return templates.TemplateResponse(
            request, "404.html", {"detail": detail, "canonical": None}, status_code=404
        )

    def family_sheet(identity):
        """The family a docket address belongs to (ADR 0005: a sheet folds its sub-dockets)
        and its sheet, or 404 — one resolution for the page, the feed and the JSON."""
        family = identity.parent() or identity
        con = _connect(db_path)
        try:
            docket_id = find_docket(con, family)
            s = sheet.docket_sheet(con, docket_id) if docket_id is not None else None
        finally:
            con.close()
        if s is None:
            raise HTTPException(404)
        return family, s

    def sheet_response(request: Request, identity):
        canonical = urls.docket_path(identity)
        if _path(request) != canonical:  # any case resolves; one address is served
            return RedirectResponse(canonical, status_code=301)
        con = _connect(db_path)
        try:
            docket_id = find_docket(con, identity)
            s = sheet.docket_sheet(con, docket_id) if docket_id is not None else None
        finally:
            con.close()
        if s is None:
            raise HTTPException(404)
        order = "oldest" if request.query_params.get("order") == "oldest" else "newest"
        if order == "oldest":
            s = replace(s, entries=list(reversed(s.entries)))
        # the filter chips offered are the kinds this docket actually contains
        kinds = sorted(
            {
                (labels.filter_key(e.kind, e.type), labels.kind_label(e.kind, e.type))
                for e in s.entries
                if e.kind == "filing"
            },
            key=lambda k: k[1],
        )
        return render(request, "sheet.html", sheet=s, identity=identity, order=order, kinds=kinds)

    @app.get("/")
    def home_page(request: Request):
        con = _connect(db_path)
        try:
            w = home.this_week(con)
        finally:
            con.close()
        return render(request, "home.html", week=w)

    # --- parties: /parties is the search; /p/<id> is the party's permanent address ----
    # (ADR 0015): the id is never reused, every member of a same_as component resolves,
    # and a member that is not the representative answers 301 to the representative.

    @app.get("/parties")
    def parties_page(request: Request, name: str = ""):
        con = _connect(db_path)
        try:
            found, truncated = resolve.search(con, name) if name.strip() else ([], False)
        finally:
            con.close()
        return render(request, "parties.html", query=name.strip(), found=found, truncated=truncated)

    def party_id_of(text: str) -> int:
        """An address is ASCII digits only; anything else is not a party address (404)."""
        pid = urls.parse_party_id(text)
        if pid is None:
            raise HTTPException(404)
        return pid

    def party_address(request: Request, party_id: str, path) -> int | Response:
        """One resolution for the page and the feed: the id the address answers for, or
        the 301 that gets there — to the canonical spelling (no leading zeros) and to the
        component's representative — or 404."""
        pid = party_id_of(party_id)
        con = _connect(db_path)
        try:
            rep = resolve.address_of(con, pid)
        finally:
            con.close()
        if rep is None:
            raise HTTPException(404)
        if rep != pid or _path(request) != path(pid):
            return RedirectResponse(path(rep), status_code=301)
        return rep

    @app.get("/p/{party_id}")
    def party_page(request: Request, party_id: str):
        rep = party_address(request, party_id, urls.party_path)
        if isinstance(rep, Response):
            return rep
        con = _connect(db_path)
        try:
            page = resolve.party_page(con, rep)
        finally:
            con.close()
        return render(request, "party.html", p=page)

    @app.get("/p/{party_id}/feed")
    def party_feed(request: Request, party_id: str):
        rep = party_address(request, party_id, urls.party_feed_path)
        if isinstance(rep, Response):
            return rep
        con = _connect(db_path)
        try:
            return atom(feeds.party_feed(con, rep, site_host))
        finally:
            con.close()

    @app.get("/p/{party_id}/{rest:path}")
    def party_page_slug(party_id: str, rest: str):
        """A pasted "pretty" link — /p/1234/union-pacific — still works: the address is
        the id alone (ADR 0015 § 4). A feed path with a trailing slash goes to the feed."""
        pid = party_id_of(party_id)
        if rest.strip("/") == "feed":
            return RedirectResponse(urls.party_feed_path(pid), status_code=301)
        return RedirectResponse(urls.party_path(pid), status_code=301)

    @app.get("/feed/party/{party_id}")
    def old_party_feed(party_id: str):
        """The M8 path, kept as a 301 forever (ADR 0015)."""
        return RedirectResponse(urls.party_feed_path(party_id_of(party_id)), status_code=301)

    # --- past weeks: fixed Monday–Sunday weeks at permanent addresses --------------------

    @app.get("/week")
    def latest_week(request: Request):
        """The most recent complete calendar week."""
        con = _connect(db_path)
        try:
            latest = home.latest_activity_date(con)
        finally:
            con.close()
        monday = home.monday_of(latest) - timedelta(days=7)
        return RedirectResponse(urls.week_path(monday), status_code=303)

    @app.get("/week/{day}")
    def week_page(request: Request, day: str):
        try:
            d = date.fromisoformat(day)
        except ValueError as e:
            raise HTTPException(404) from e
        monday = home.monday_of(d)
        if d != monday:  # any day of the week resolves to the week's one address
            return RedirectResponse(urls.week_path(monday), status_code=301)
        con = _connect(db_path)
        try:
            w = home.calendar_week(con, monday)
            is_covered = home.covered(con, monday, monday + timedelta(days=6))
            latest = home.latest_activity_date(con)
        finally:
            con.close()
        nxt = monday + timedelta(days=7)
        return render(
            request,
            "week.html",
            week=w,
            monday_iso=monday.isoformat(),
            covered=is_covered,
            prev_path=urls.week_path(monday - timedelta(days=7)),
            next_path=urls.week_path(nxt) if nxt <= latest else None,
        )

    # --- the trust pages: about, coverage, corrections, methodology, privacy ------------
    # Reachable now, linked from the footer only once the operator has signed them off
    # (ADR 0011: a public promise ships on explicit sign-off). Every number is measured.

    @app.get("/about")
    def about_page(request: Request):
        return render(request, "about.html")

    @app.get("/contribute")
    def contribute_page(request: Request):
        """Two lanes — ideas and code — and what helping does not buy (docs/contribute.md).
        No money lane: tabled by the operator 2026-08-26 until the entity question is
        settled."""
        return render(request, "contribute.html", idea_url=IDEA_URL)

    @app.get("/coverage")
    def coverage_page(request: Request):
        con = _connect(db_path)
        try:
            cov = coverage.coverage(con)
        finally:
            con.close()
        return render(request, "coverage.html", cov=cov)

    @app.get("/stats")  # the numbers move once a poll; the page may be cached that long
    def stats_page(request: Request):
        con = _connect(db_path)
        try:
            s = stats.stats(con)
        finally:
            con.close()
        response = render(request, "stats.html", s=s)
        response.headers.update(PUBLIC_CACHE)
        return response

    @app.get("/corrections")
    def corrections_page(request: Request):
        return render(request, "corrections.html", issues_url=CORRECTIONS_URL)

    @app.get("/methodology")
    def methodology_page(request: Request):
        return render(request, "methodology.html")

    @app.get("/privacy")
    def privacy_page(request: Request):
        return render(request, "privacy.html")

    @app.get("/health")
    def health():
        """Freshness for the off-box heartbeat (docs/alerts.md). Always 200: the monitor
        applies the thresholds, so a stale store is visible rather than a 5xx that a
        restart loop could mask. No reader data, no identifiers."""
        con = _connect(db_path)
        try:
            fresh = projections.freshness(con)
        finally:
            con.close()
        now = datetime.now(UTC)
        ages = {}
        for key, value in fresh.items():
            try:
                ages[key] = int((now - datetime.fromisoformat(value)).total_seconds())
            except (TypeError, ValueError):
                ages[key] = None
        return JSONResponse(
            {"version": __version__, "schema": MIGRATIONS[-1][0], **fresh, "age_seconds": ages},
            headers={"Cache-Control": "no-store"},
        )

    # --- feeds: the alert stream as a page; nothing is stored about the reader ---------

    @app.get("/feed")
    def agency_feed():
        con = _connect(db_path)
        try:
            return atom(feeds.agency_feed(con, site_host))
        finally:
            con.close()

    @app.get("/d/{ident}/feed")
    def docket_feed(ident: str):
        identity = urls.parse_docket_path(ident)
        if identity is None:
            raise HTTPException(404)
        family, s = family_sheet(identity)
        con = _connect(db_path)
        try:
            return atom(
                feeds.family_feed(
                    con,
                    s.docket_id,
                    urls.printed_docket(family),
                    urls.docket_path(family),
                    site_host,
                )
            )
        finally:
            con.close()

    # --- JSON: the same addresses, as data (M9). CC0; envelope names the source ----------

    def as_json(body: dict) -> JSONResponse:
        return JSONResponse(
            {
                "source": f"https://{site_host}/",
                "licence": dump.LICENCE,
                "licence_url": dump.LICENCE_URL,
                "shape_version": JSON_SHAPE,
                "held": {"enriched": dump.HELD_REASON},
                "generated_at": utcnow(),
                **body,
            },
            headers=PUBLIC_CACHE,
        )

    def docket_ref(s) -> dict:
        ident = parse_docket_id(s.raw_docket)
        return {
            "raw_docket": s.raw_docket,
            "printed": urls.printed_docket(ident) if ident else s.raw_docket,
            "title": s.title,
            "url": f"https://{site_host}{urls.docket_path(ident)}" if ident else None,
        }

    def entry_json(e) -> dict:
        d = asdict(e)
        d.pop("parties", None)  # the enriched layer is held (dump.HELD_REASON)
        d["url"] = f"https://{site_host}{urls.record_path(e.kind, e.record_id)}"
        return d

    def sheet_json(request: Request, identity) -> Response:
        canonical = urls.docket_path(identity) + ".json"
        if _path(request) != canonical:  # any case resolves; one address is served
            return RedirectResponse(canonical, status_code=301)
        family, s = family_sheet(identity)
        d = asdict(s)
        d.pop("parties", None)  # the enriched layer is held (dump.HELD_REASON)
        d.update(docket_ref(s))
        d["sub_dockets"] = [
            {"docket_id": i, "raw_docket": raw, "title": title} for i, raw, title in s.sub_dockets
        ]
        d["entries"] = [entry_json(e) for e in s.entries]
        body = {"docket": d}
        if identity != family:  # a sub-docket address answers with its family, and says so
            body["requested"] = {
                "raw_docket": identity.canonical(),
                "printed": urls.printed_docket(identity),
                "url": f"https://{site_host}{urls.docket_path(identity)}",
            }
        return as_json(body)

    @app.get("/d/{ident}.json")
    def docket_json(request: Request, ident: str):
        identity = urls.parse_docket_path(ident)
        if identity is None:
            raise HTTPException(404)
        return sheet_json(request, identity)

    @app.get("/d/{ident}/sub/{sub}.json")
    def sub_docket_json(request: Request, ident: str, sub: str):
        identity = urls.parse_docket_path(ident, sub)
        if identity is None:
            raise HTTPException(404)
        return sheet_json(request, identity)

    def record_json(kind: str, stb_id: str) -> JSONResponse:
        s, entry = _record_entry(db_path, kind, stb_id)
        d = entry_json(entry)
        d["docket"] = docket_ref(s)
        return as_json({kind: d})

    @app.get("/filing/{stb_id}.json")
    def filing_json(stb_id: str):
        return record_json("filing", stb_id)

    @app.get("/decision/{stb_id}.json")
    def decision_json(stb_id: str):
        return record_json("decision", stb_id)

    @app.get("/data")
    def data_page(request: Request):
        return render(request, "data.html", manifest=dump.read_manifest(public_dir))

    @app.get("/d")
    def lookup(request: Request, q: str = ""):
        """The old lookup box: whatever was typed, normalised to the one canonical address;
        anything that is not a docket number is now a search."""
        identity = urls.lookup(q)
        if identity is None:
            return RedirectResponse(f"/search?{urlencode({'q': q.strip()})}", status_code=303)
        return RedirectResponse(urls.docket_path(identity), status_code=303)

    # --- search: a docket number is never a search; everything else is the index -------
    # (docs/search.md). Nothing about the query is stored; Caddy drops it from the log.

    @app.get("/search")
    def search_page(request: Request, q: str = ""):
        """A docket number the record holds is a 303 to its sheet; anything else is a result
        page — never cached or indexed, because its address carries what was typed."""
        q = q.strip()[: search.MAX_QUERY]
        if not q:
            return render(request, "search.html", query="", hits=[])
        con = _connect(db_path)
        try:
            docket = search.held_docket(con, q)
            if docket is not None:
                return RedirectResponse(docket.path, status_code=303)
            hits = search.search(con, q)
        finally:
            con.close()
        return render(request, "search.html", query=q, hits=hits, canonical=None)

    @app.get("/suggest")
    def suggest(q: str = ""):
        """As-you-type: a few rows, the same fields, never cached, never stored. A docket
        number the record holds leads, once."""
        q = q.strip()[: search.MAX_QUERY]
        hits: list[dict] = []
        if q:
            con = _connect(db_path)
            try:
                docket = search.held_docket(con, q)
                found = search.search(con, q, limit=search.SUGGEST, prefix=True)
            finally:
                con.close()
            if docket is not None:
                hits.append(asdict(docket))
            hits += [asdict(h) for h in found if docket is None or h.path != docket.path]
        return JSONResponse({"hits": hits[: search.SUGGEST]}, headers={"Cache-Control": "no-store"})

    @app.get("/d/{ident}")
    def docket_page(request: Request, ident: str):
        identity = urls.parse_docket_path(ident)
        if identity is None:
            raise HTTPException(404)
        return sheet_response(request, identity)

    @app.get("/d/{ident}/sub/{sub}")
    def sub_docket_page(request: Request, ident: str, sub: str):
        identity = urls.parse_docket_path(ident, sub)
        if identity is None:
            raise HTTPException(404)
        return sheet_response(request, identity)

    # --- subscriptions: the one place a reader may hand over an address (ADR 0011) ------

    def message(request: Request, title: str, body: str, status_code: int = 200):
        return templates.TemplateResponse(
            request, "message.html", {"title": title, "body": body}, status_code=status_code
        )

    @app.post("/subscribe")
    def subscribe(
        request: Request,
        email: str = Form(""),
        docket: str = Form(""),
        cadence: str = Form("pass"),
        party: str = Form(""),
        webhook_url: str = Form(""),
    ):
        """Whatever happens — new, pending, already active, suppressed, rate-limited — the
        answer is the same page, so nothing about an address can be learned here."""
        channel = "webhook" if webhook_url.strip() else "email"
        if not vault.is_open() or (channel == "email" and sender is None):
            # never pretend a mail (or a ping) is on its way
            return message(
                request,
                "Subscriptions are not available right now",
                "Docket Yard cannot send email at the moment. Nothing was stored; please"
                " try again later.",
                503,
            )
        address = (
            webhooks.normalise_url(webhook_url)
            if channel == "webhook"
            else subscriptions.normalise_email(email)
        )
        plausible = (
            webhooks.plausible_url(address)
            if channel == "webhook"
            else subscriptions.plausible_email(address)
        )
        identity = urls.lookup(docket) if docket.strip() else None
        party_id = int(party) if party.strip().isdigit() else None
        if (identity is None and party_id is None) or not plausible:
            return message(
                request,
                "That did not work",
                "Enter an email address — or an https:// webhook URL — and a docket number"
                " (or choose a party).",
                400,
            )
        if cadence not in ("pass", "daily"):
            cadence = "pass"
        con = _connect_rw(db_path)
        try:
            if identity is not None:
                family = identity.parent() or identity
                docket_id = find_docket(con, family)
                if docket_id is None:
                    raise HTTPException(404)
                printed = urls.printed_docket(family)
                token = subscriptions.subscribe(con, address, docket_id, cadence, channel=channel)
            else:
                if not resolve.party_exists(con, party_id):
                    raise HTTPException(404)
                printed = f"filings for {resolve.display_name(con, party_id)}"
                token = subscriptions.subscribe(
                    con, address, None, cadence, party_id=party_id, channel=channel
                )
        finally:
            con.close()
        if channel == "webhook":  # one page whatever happened, as for an address
            return _ping_webhook(request, address, token, printed)
        if token:
            hours = subscriptions.CONFIRM_TTL_HOURS
            out = mail.Outbound(
                to=address,
                subject=f"Confirm: follow {printed} on {site_name}",
                text=(
                    f"Someone — we hope you — asked {site_name} to email {address} when the"
                    f" Surface Transportation Board posts to {printed}.\n\n"
                    f"To confirm, open this link within {hours} hours and press Confirm:\n"
                    f"{urls.confirm_url(site_host, token)}\n\n"
                    "If that was not you, do nothing: the request expires and the address"
                    " is deleted.\n\n"
                    f"{site_name} is an independent public record, not the Board."
                    f" https://{site_host}/"
                ),
            )
            try:
                sender.send(out)
            except Exception as e:  # noqa: BLE001 — the page is the same; the slot is given back
                con = _connect_rw(db_path)
                try:
                    subscriptions.withdraw_token(con, token)
                finally:
                    con.close()
                print(f"confirmation mail failed ({mail.describe_failure(e)})")
        return message(
            request,
            "Check your inbox",
            f"If {address} can be followed up, a confirmation link is on its way for"
            f" {printed}. Nothing is sent until you open it.",
        )

    def _ping_webhook(request: Request, url: str, token: str | None, printed: str):
        """Confirmation for a webhook is a ping carrying the confirmation link and the
        signing secret: whoever reads the endpoint's traffic can confirm, nobody else.
        Without a token (already following, rate-limited, suppressed) nothing is sent
        and the page is the same."""
        page = message(
            request,
            "Check the endpoint",
            f"If {webhooks.describe(url)} accepted a ping just now, it holds a confirmation"
            f" link and the signing secret for {printed}. Nothing is sent until the link is"
            " opened and confirmed.",
        )
        if token is None:
            return page
        con = _connect(db_path)
        try:
            sub = subscriptions.for_confirm_token(con, token)
        finally:
            con.close()
        if sub is None or not sub.secret:
            return page
        hours = subscriptions.CONFIRM_TTL_HOURS
        # the ping itself: no store handle is held across the network wait
        ping = {
            "type": "subscription.confirm",
            "source": f"https://{site_host}/",
            "what": printed,
            "confirm_url": urls.confirm_url(site_host, token),
            "expires_in_hours": hours,
            "secret": sub.secret,
            "note": f"Someone asked {site_name} to POST new filings and decisions for"
            f" {printed} to this URL. To confirm, open confirm_url within {hours} hours"
            " and press Confirm. Every later delivery is signed with `secret` as"
            " X-DocketYard-Signature (HMAC-SHA256 over the body). If this was not you,"
            " do nothing: the request expires and the URL is deleted.",
        }
        # A ping that is not accepted still counts against the three-an-hour limit and
        # its token simply expires: withdrawing it would let a URL that never answers be
        # pinged without limit. The endpoint's owner sees nothing either way.
        try:
            webhooks.post(
                url, ping, sub.secret, delivery_id="confirm", timeout=webhooks.PING_TIMEOUT
            )
        except webhooks.RefusedDestination:
            pass
        return page

    @app.get("/s/confirm/{token}")
    def confirm_page(request: Request, token: str):
        """A page with a button: mail-security gateways fetch links on delivery, and a
        fetch must never count as consent (ADR 0011). The POST below is the consent."""
        con = _connect(db_path)
        try:
            sub = subscriptions.for_confirm_token(con, token) if vault.is_open() else None
            what = None
            if sub and sub.docket_id is not None:
                raw = con.execute(
                    "SELECT raw_docket FROM docket WHERE docket_id = ?", (sub.docket_id,)
                ).fetchone()[0]
                what = urls.printed_docket(parse_docket_id(raw))
            elif sub:
                what = f"filings for {resolve.display_name(con, sub.party_id)}"
        finally:
            con.close()
        return templates.TemplateResponse(
            request,
            "confirm.html",
            {
                "token": token,
                "channel": sub.channel if sub else "email",
                "what": what,
                "endpoint": webhooks.describe(sub.email)
                if sub and sub.channel == "webhook"
                else None,
            },
        )

    @app.post("/s/confirm/{token}")
    def confirm_subscription(request: Request, token: str):
        con = _connect_rw(db_path)
        try:
            sub = subscriptions.confirm(con, token)
            raw = None
            what = None
            if sub and sub.docket_id is not None:
                raw = con.execute(
                    "SELECT raw_docket FROM docket WHERE docket_id = ?", (sub.docket_id,)
                ).fetchone()[0]
            elif sub:
                what = f"filings for {resolve.display_name(con, sub.party_id)}"
        finally:
            con.close()
        if sub is None:
            return message(
                request,
                "That link has expired",
                f"Confirmation links last {subscriptions.CONFIRM_TTL_HOURS} hours. Ask again"
                " from the docket's page.",
                404,
            )
        what = what or urls.printed_docket(parse_docket_id(raw))
        if sub.channel == "webhook":
            when = "as they happen" if sub.cadence == "pass" else "once a day"
            return message(
                request,
                "You are following " + what,
                f"New filings and decisions will be POSTed to {webhooks.describe(sub.email)}"
                f" {when}, signed. Every delivery carries an unsubscribe link.",
            )
        when = "as they happen" if sub.cadence == "pass" else "in one daily email"
        return message(
            request,
            "You are following " + what,
            f"New filings and decisions will reach {sub.email} {when}. Every email carries a"
            " one-click link to stop.",
        )

    @app.get("/s/unsubscribe/{token}")
    def unsubscribe_page(request: Request, token: str):
        """A page with a button, so a link scanner cannot unsubscribe someone by fetching.
        The RFC 8058 one-click POST below needs no page."""
        return templates.TemplateResponse(
            request, "unsubscribe.html", {"token": token}, status_code=200
        )

    @app.post("/s/unsubscribe/{token}")
    def unsubscribe_now(request: Request, token: str):
        con = _connect_rw(db_path)
        try:
            subscriptions.unsubscribe(con, token)
        finally:
            con.close()
        return message(
            request,
            "Unsubscribed",
            "That subscription and everything about it has been deleted.",
        )

    @app.post("/ses/feedback")
    def ses_feedback(request: Request, body: bytes = Body(...)):
        """SNS delivers SES bounce/complaint events here. Off (503) until a topic is
        configured; verified by signature and topic; an unverifiable message is a 400 and
        nothing more. A plain def: the certificate fetch and RSA check run in the
        threadpool, never on the event loop. Never any address in the log."""
        if not feedback_topic:
            raise HTTPException(503, "feedback not configured")
        if len(body) > feedback.MAX_BODY:
            raise HTTPException(413)
        con = _connect_rw(db_path)
        try:
            outcome = feedback.handle(con, body, expected_topic=feedback_topic)
        except feedback.Rejected as e:
            raise HTTPException(400, str(e)) from e
        finally:
            con.close()
        return JSONResponse({"ok": outcome})

    @app.get("/decision/{stb_id}")
    def decision_page(request: Request, stb_id: str):
        return _record_page(request, db_path, render, "decision", stb_id)

    @app.get("/filing/{stb_id}")
    def filing_page(request: Request, stb_id: str):
        return _record_page(request, db_path, render, "filing", stb_id)

    for route in app.routes:  # HEAD answers as GET without a body, on every page
        if isinstance(route, APIRoute) and "GET" in route.methods:
            route.methods.add("HEAD")
    return app


def _record_entry(db_path, kind: str, stb_id: str):
    """A record's family sheet and its entry, or 404 — one lookup for the page and JSON."""
    table, column = (
        ("decision_record", "stb_decision_id")
        if kind == "decision"
        else ("filing", "stb_filing_id")
    )
    con = _connect(db_path)
    try:
        # a record entered in a docket and its sub-docket is one record: headline the parent
        row = con.execute(
            f"SELECT r.docket_id FROM {table} r JOIN docket d ON d.docket_id = r.docket_id"
            f" WHERE r.{column} = ?"
            " ORDER BY COALESCE(d.sub_sequence, -1), COALESCE(d.suffix, '') LIMIT 1",
            (stb_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404)
        s = sheet.docket_sheet(con, row[0])
    finally:
        con.close()
    assert s is not None
    entry = next((e for e in s.entries if e.kind == kind and e.record_id == stb_id), None)
    if entry is None:
        raise HTTPException(404)
    return s, entry


def _record_page(request, db_path, render, kind: str, stb_id: str):
    s, entry = _record_entry(db_path, kind, stb_id)
    return render(request, "record.html", sheet=s, entry=entry)
