"""`/review` — the one signed-in surface, and the only place this server sets a cookie.

ADR 0016: reviewing is writing to the record, and writing has a name. Reading does not. So
everything here is fenced off from every other path in `app.py`, and the fences are the
point:

  * **The cookie is scoped to `/review`** — `Path=/review`, `HttpOnly`, `SameSite=Strict`,
    `Secure` off localhost. It is never sent with a request for a docket sheet, so no read
    page can become identity-linked by accident, which is the promise ADR 0011 makes to
    readers and `app.py`'s own docstring repeats.
  * **No page view is counted.** `docs/traffic.md` counts every other path; ADR 0016 says
    the review surfaces "log the actions above and nothing else; no page views, no timing
    beyond the action's own timestamp". `app.py` excludes this prefix from the counter.
  * **A GET never signs anybody in and never decides anything.** Mail-security gateways
    fetch links on delivery — the subscription flow learned it at `/s/confirm/{token}` —
    so the link in the mail is a page with a button and the button is a POST.
  * **`SameSite=Strict` is the CSRF defence.** No cross-site form post carries the cookie,
    so no hidden form on another site can decide a queue item. It also means arriving from
    an emailed link lands signed-out on the first hop, which is why the sign-in link's own
    page is a POST to the same origin rather than a redirect.

Nothing here can subscribe, spend, or alter the ledger (ADR 0016). The two writable things
are a session row and a review decision.
"""

import secrets
import sqlite3

from fastapi import BackgroundTasks, Form, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse, Response

from docketyard.alerts import mail, vault
from docketyard.citator import review, signin

COOKIE = "dy_review"
# A second, short-lived cookie whose only job is to prove the sign-in POST came from the page
# this server rendered. `SameSite=Strict` covers every OTHER state-changing POST here because
# they all need the session cookie — but `POST /review/enter/{token}` needs no cookie at all,
# so Strict protects nothing there. Without this, someone who holds a grant can auto-submit
# THEIR OWN sign-in token from another site and plant their session in a victim reviewer's
# browser; the victim then works the queue and every decision is credited to the attacker.
# On a record whose whole point is that an assertion has an author, that is the attack that
# matters. (Found by /code-review, 2026-09-01.)
HANDSHAKE = "dy_review_enter"
PREFIX = "/review"


def _cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=signin.SESSION_TTL_HOURS * 3600,
        httponly=True,
        samesite="strict",
        secure=secure,
        path=PREFIX,  # never sent to a reader page: that is the fence, not a nicety
    )


def register(app, *, db_path, connect, connect_rw, render, site_host, sender, secure_cookie):
    """Wire the six routes. `app.py` owns the connections and the renderer; this owns the
    rules."""

    def _signin_page(request: Request, *, sent: bool = False):
        # `signin_minutes` is passed HERE and nowhere else: the page quotes the link's own
        # lifetime, and a missing variable renders as "expires in  minutes"
        return render(
            request, "review_signin.html", sent=sent, signin_minutes=signin.SIGN_IN_TTL_MINUTES
        )

    def _who(request: Request):
        con = connect(db_path)
        try:
            return signin.whoami(con, request.cookies.get(COOKIE))
        finally:
            con.close()

    @app.get(PREFIX)
    def review_home(request: Request):
        """The queues, or the way in. ADR 0016's order of yield (0017 D5): the exposed class
        first, then repairs, then unresolved targets inside the held record."""
        who = _who(request)
        if who is None:
            return _signin_page(request)
        con = connect(db_path)
        try:
            queues = [
                {"queue": q, "note": note, "count": review.owed(con, q)}
                for q, note in con.execute(
                    "SELECT queue, note FROM review_queue_vocab WHERE queue LIKE 'citation_%'"
                    " ORDER BY CASE queue WHEN 'citation_exposed' THEN 0"
                    " WHEN 'citation_repaired' THEN 1 ELSE 2 END"
                ).fetchall()
            ]
        finally:
            con.close()
        return render(request, "review_home.html", who=who, queues=queues)

    def _mail_link(address: str, token: str) -> None:
        try:
            sender.send(
                mail.Outbound(
                    to=address,
                    subject="Sign in to review",
                    text=(
                        "Open this link and press Sign in. It works once and expires"
                        f" in {signin.SIGN_IN_TTL_MINUTES} minutes:\n"
                        f"https://{site_host}{PREFIX}/enter/{token}\n\n"
                        "If this was not you, ignore it — nothing happens until the"
                        " button is pressed.\n"
                    ),
                )
            )
        except Exception as e:  # noqa: BLE001 — a mail failure must never reach the page
            print(f"reviewer sign-in mail failed ({mail.describe_failure(e)})")

    @app.post(PREFIX + "/sign-in")
    def review_sign_in(request: Request, background: BackgroundTasks, email: str = Form("")):
        """Whatever happens — a grant, no grant, a withdrawn one — the answer is the same
        page. Anything else turns this form into an oracle for who holds a grant, and a
        reviewer's name is published beside their work while their address never is.

        THE MAIL GOES OUT AFTER THE RESPONSE, and that is the point rather than a nicety.
        `Sender.send` opens a fresh SMTP session — TCP, TLS, AUTH, DATA against SES — so
        sending it inside the handler made the granted branch take the better part of a
        second while the ungranted one returned in about a millisecond. Identical HTML,
        three orders of magnitude apart: one request per guess and the form tells you which
        address belongs to a reviewer, which is exactly what this page must not do. Found by
        `/security-review` 2026-09-01, in a handler whose own docstring claimed otherwise.
        """
        if vault.is_open() and sender is not None and email.strip():
            con = connect_rw(db_path)
            try:
                token = signin.request_link(con, email)
                if token:
                    con.commit()
            except Exception:  # noqa: BLE001 — a failure must not leak that a grant exists
                con.rollback()
                token = None
            finally:
                con.close()
            if token:
                background.add_task(_mail_link, vault.normalise_email(email), token)
        return _signin_page(request, sent=True)

    @app.get(PREFIX + "/enter/{token}")
    def review_enter(request: Request, token: str):
        """A page with a button. A mail gateway that fetches the link on delivery must not
        spend it — that would hand a session to nobody and lock the reviewer out of their
        own invitation (the lesson `/s/confirm/{token}` already carries).

        It also plants the handshake the POST below requires. Setting a cookie is allowed on
        a cross-site navigation like an email click; SENDING one is not, which is exactly the
        asymmetry that makes this work."""
        con = connect(db_path)
        try:
            who = signin.pending(con, token)
        finally:
            con.close()
        handshake = secrets.token_urlsafe(16)
        response = render(request, "review_enter.html", who=who, token=token, nonce=handshake)
        response.set_cookie(
            HANDSHAKE,
            handshake,
            max_age=signin.SIGN_IN_TTL_MINUTES * 60,
            httponly=True,
            samesite="strict",
            secure=secure_cookie,
            path=PREFIX,
        )
        return response

    @app.post(PREFIX + "/enter/{token}")
    def review_enter_post(request: Request, token: str, nonce: str = Form("")):
        # the cookie is not sent on a cross-site POST (SameSite=Strict), and the field cannot
        # be guessed, so a form on another site can satisfy neither
        planted = request.cookies.get(HANDSHAKE)
        if not planted or not nonce or not secrets.compare_digest(planted, nonce):
            return render(request, "review_enter.html", who=None, token=token, nonce="")
        con = connect_rw(db_path)
        try:
            session = signin.sign_in(con, token)
            if session:
                signin.sweep(con)  # the one regular write: expired rows go, on every sign-in
            con.commit()
        finally:
            con.close()
        if session is None:
            return render(request, "review_enter.html", who=None, token=token, nonce="")
        response = RedirectResponse(PREFIX, status_code=303)
        _cookie(response, session, secure=secure_cookie)
        response.delete_cookie(HANDSHAKE, path=PREFIX)
        return response

    @app.post(PREFIX + "/sign-out")
    def review_sign_out(request: Request):
        con = connect_rw(db_path)
        try:
            signin.sign_out(con, request.cookies.get(COOKIE))
            con.commit()
        finally:
            con.close()
        response = RedirectResponse(PREFIX, status_code=303)
        response.delete_cookie(COOKIE, path=PREFIX)
        response.delete_cookie(HANDSHAKE, path=PREFIX)
        return response

    @app.get(PREFIX + "/{queue}")
    def review_queue(request: Request, queue: str):
        """One queue, with THE EVIDENCE BESIDE THE QUESTION (ADR 0016): the citing passage,
        the page, and what the machine resolved it to."""
        who = _who(request)
        if who is None:
            return _signin_page(request)
        if queue not in review.QUEUES:
            # `render` takes **context, so `status_code` would have become a template
            # variable and an unknown queue would have answered 200. The app's own handler
            # owns 404, and it is the one that sets the status.
            raise HTTPException(status_code=404)
        con = connect(db_path)
        try:
            items = review.pending(con, queue, limit=50)
            note = con.execute(
                "SELECT note FROM review_queue_vocab WHERE queue = ?", (queue,)
            ).fetchone()
            for item in items:
                row = con.execute(
                    "SELECT raw_docket FROM docket WHERE docket_id = ?",
                    (item["cited_docket_id"],),
                ).fetchone()
                item["cited_docket"] = row[0] if row else None
        finally:
            con.close()
        return render(
            request,
            "review_queue.html",
            who=who,
            queue=queue,
            note=note[0] if note else "",
            items=items,
        )

    @app.post(PREFIX + "/{queue}/decide")
    def review_decide(
        request: Request,
        queue: str,
        key: str = Form(""),
        decision: str = Form(""),
        note: str = Form(""),
        docket: str = Form(""),
    ):
        """One decision, one row, one transaction. The assertion and the action land
        together or neither does (`schema-draft.md` § 7)."""
        who = _who(request)
        if who is None:
            return _signin_page(request)
        con = connect_rw(db_path)
        try:
            item = next(
                (
                    q
                    for q in review.pending(con, queue, limit=10_000)
                    if q["target_key_rendered"] == key
                ),
                None,
            )
            if item is None:
                return render(
                    request,
                    "message.html",
                    title="Not on this queue",
                    body="It may have been answered already. The queue below is current.",
                )
            # A CORRECTION NAMES A DOCKET THE WAY THE BOARD PRINTS IT, never an internal
            # id. The first draft passed the form field straight through as `cited_docket_id`
            # while no page ever showed one — so a reviewer had nothing to type, and a
            # plausible guess published a WRONG edge, resolved and confident, under their own
            # credit name. `find_docket` refuses anything the registry does not hold.
            corrected_to = None
            if decision == "corrected":
                found = review.find_docket(con, docket)
                if found is None:
                    return render(
                        request,
                        "message.html",
                        title="Refused",
                        body=(
                            f"{docket!r} is not a docket this record holds. Type it as the"
                            " Board prints it — AB 124, EP 445 (Sub-No. 1) — and try again."
                        ),
                    )
                corrected_to = found[0]
            review.decide(
                con,
                reviewer_id=who.reviewer_id,
                queue=queue,
                item=item,
                decision=decision,
                note=note,
                cited_docket_id=corrected_to,
            )
            con.commit()
        except (ValueError, KeyError, sqlite3.IntegrityError) as e:
            # IntegrityError too: a CHECK or a foreign key refusing the write is a refusal to
            # show the reviewer, not a 500 that loses the note they just typed
            con.rollback()
            return render(request, "message.html", title="Refused", body=str(e))
        finally:
            con.close()
        return RedirectResponse(f"{PREFIX}/{queue}", status_code=303)
