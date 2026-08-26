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

import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from importlib import resources
from pathlib import Path

from fastapi import Body, FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from docketyard import __version__
from docketyard.alerts import feedback, mail, subscriptions, vault
from docketyard.ingest.dockets import find_docket, parse_docket_id
from docketyard.parties import resolve
from docketyard.store import coverage, home, projections, sheet, stats
from docketyard.store.db import MIGRATIONS
from docketyard.web import labels, urls

_PKG = resources.files("docketyard.web")
# outside intake is GitHub Issues (CLAUDE.md); the form template carries the fields
CORRECTIONS_URL = (
    "https://github.com/RMI-Valuation/docket-yard/issues/new?template=data-correction.yml"
)


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
    con = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=rw", uri=True)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def create_app(
    db_path: str | Path,
    *,
    site_name: str = "Docket Yard",
    site_host: str = "docketyard.org",
    sender: mail.Sender | None = None,
    feedback_topic: str | None = None,  # the SNS topic ARN SES feedback must come from
) -> FastAPI:
    _check_store(db_path)
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
    templates.env.globals.update(
        site_name=site_name,
        docket_path=urls.docket_path,
        printed_docket=urls.printed_docket,
        cite_docket=urls.cite_docket,
        decision_path=urls.decision_path,
        filing_path=urls.filing_path,
        parse_docket_id=parse_docket_id,
        kind_label=labels.kind_label,
        filter_key=labels.filter_key,
        confirm_ttl_hours=subscriptions.CONFIRM_TTL_HOURS,  # the privacy page quotes it
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

    # --- parties: a facet of the record, reached by query, never an address --------------

    @app.get("/parties")
    def parties_page(request: Request, name: str = ""):
        con = _connect(db_path)
        try:
            found, truncated = resolve.search(con, name) if name.strip() else ([], False)
        finally:
            con.close()
        return render(request, "parties.html", query=name.strip(), found=found, truncated=truncated)

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
        response.headers["Cache-Control"] = "public, max-age=1800"
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
    ):
        """Whatever happens — new, pending, already active, suppressed, rate-limited — the
        answer is the same page, so nothing about an address can be learned here."""
        if sender is None or not vault.is_open():  # never pretend a mail is on its way
            return message(
                request,
                "Subscriptions are not available right now",
                "Docket Yard cannot send email at the moment. Nothing was stored; please"
                " try again later.",
                503,
            )
        address = subscriptions.normalise_email(email)
        identity = urls.lookup(docket) if docket.strip() else None
        party_id = int(party) if party.strip().isdigit() else None
        if (identity is None and party_id is None) or not subscriptions.plausible_email(address):
            return message(
                request,
                "That did not work",
                "Enter an email address and a docket number (or choose a party).",
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
                token = subscriptions.subscribe(con, address, docket_id, cadence)
            else:
                if not con.execute(
                    "SELECT 1 FROM party WHERE party_id = ?", (party_id,)
                ).fetchone():
                    raise HTTPException(404)
                printed = f"filings for {resolve.display_name(con, party_id)}"
                token = subscriptions.subscribe(con, address, None, cadence, party_id=party_id)
        finally:
            con.close()
        if token:
            hours = subscriptions.CONFIRM_TTL_HOURS
            out = mail.Outbound(
                to=address,
                subject=f"Confirm: follow {printed} on {site_name}",
                text=(
                    f"Someone — we hope you — asked {site_name} to email {address} when the"
                    f" Surface Transportation Board posts to {printed}.\n\n"
                    f"To confirm, open this link within {hours} hours and press Confirm:\n"
                    f"https://{site_host}/s/confirm/{token}\n\n"
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

    @app.get("/s/confirm/{token}")
    def confirm_page(request: Request, token: str):
        """A page with a button: mail-security gateways fetch links on delivery, and a
        fetch must never count as consent (ADR 0011). The POST below is the consent."""
        return templates.TemplateResponse(request, "confirm.html", {"token": token})

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
