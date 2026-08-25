"""The web tier: server-rendered pages over the projections, at the ADR 0013 addresses.

Every page is derived from the store at request time (the agency moves ~250 times a month;
caching is a later concern) and quotes the record as printed — captions and decision
summaries appear in the Board's own capitals until a casing method exists as a derived
assertion with provenance. No account, no cookie, no tracking on any read path (ADR 0011).

The server is strictly a reader: it opens the store read-only, refuses a missing file or a
store whose schema is not the one this code was built for, and never runs a migration —
that is ingest's job, in its own process.
"""

import sqlite3
from importlib import resources
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from docketyard import __version__
from docketyard.ingest.dockets import find_docket, parse_docket_id
from docketyard.store import home, sheet
from docketyard.store.db import MIGRATIONS
from docketyard.web import urls

_PKG = resources.files("docketyard.web")


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


def _path(request: Request) -> str:
    """The request path relative to any mount prefix, for canonical-address checks."""
    root = request.scope.get("root_path", "")
    path = request.url.path
    return path[len(root) :] if root and path.startswith(root) else path


def create_app(db_path: str | Path, *, site_name: str = "Docket Yard") -> FastAPI:
    _check_store(db_path)
    app = FastAPI(title=site_name, version=__version__, docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(_PKG / "templates"))
    templates.env.globals.update(
        site_name=site_name,
        docket_path=urls.docket_path,
        printed_docket=urls.printed_docket,
        cite_docket=urls.cite_docket,
        decision_path=urls.decision_path,
        filing_path=urls.filing_path,
        parse_docket_id=parse_docket_id,
    )
    app.mount("/static", StaticFiles(directory=str(_PKG / "static")), name="static")

    def render(request: Request, name: str, **context):
        return templates.TemplateResponse(request, name, context)

    @app.exception_handler(404)
    def not_found(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail != "Not Found" else ""
        return templates.TemplateResponse(request, "404.html", {"detail": detail}, status_code=404)

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
        return render(request, "sheet.html", sheet=s, identity=identity)

    @app.get("/")
    def home_page(request: Request):
        con = _connect(db_path)
        try:
            w = home.this_week(con)
        finally:
            con.close()
        return render(request, "home.html", week=w)

    @app.get("/d")
    def lookup(request: Request, q: str = ""):
        """The lookup box: whatever was typed, normalised to the one canonical address."""
        identity = urls.lookup(q)
        if identity is None:
            raise HTTPException(404, "not a docket number")
        return RedirectResponse(urls.docket_path(identity), status_code=303)

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

    @app.get("/decision/{stb_id}")
    def decision_page(request: Request, stb_id: str):
        return _record_page(request, db_path, render, "decision", stb_id)

    @app.get("/filing/{stb_id}")
    def filing_page(request: Request, stb_id: str):
        return _record_page(request, db_path, render, "filing", stb_id)

    return app


def _record_page(request, db_path, render, kind: str, stb_id: str):
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
    entry = next(e for e in s.entries if e.kind == kind and e.record_id == stb_id)
    return render(request, "record.html", sheet=s, entry=entry)
