"""`/review` and magic-link sign-in — ADR 0016 over ADR 0011's account.

The fences are what these test. A cookie exists now, and every promise made to readers has
to survive it.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from docketyard.alerts import vault
from docketyard.citator import keys, load, methods, project, review, signin
from docketyard.ingest.dockets import parse_docket_id
from docketyard.store import db
from docketyard.web import urls
from docketyard.web.app import create_app

STAMP = "2026-09-01T00:00:00+00:00"
SHA = "d" * 64
EXPOSED = {"page": 4, "target": "AB 1242", "quoted": "See AB 1242, slip op. at 3."}


class _Sender:
    """A sender that keeps what it was asked to send, so a test can open the link."""

    def __init__(self):
        self.sent = []

    def send(self, out):
        self.sent.append(out)
        return "id"

    @property
    def link(self) -> str:
        body = self.sent[-1].text
        return [w for w in body.split() if "/review/enter/" in w][0].split("docketyard.org")[1]


@pytest.fixture
def store(tmp_path):
    vault.configure(vault.Vault.from_key(vault.Vault.new_key()))
    con = db.connect(tmp_path / "s.sqlite")
    for did, prefix, seq in ((1, "FD", 36873), (2, "AB", 124), (3, "AB", 1242)):
        con.execute(
            "INSERT INTO docket (docket_id, raw_docket, prefix, sequence) VALUES (?, ?, ?, ?)",
            (did, f"{prefix}_{seq}", prefix, seq),
        )
    con.execute(
        "INSERT INTO capture (capture_id, source_system, endpoint, request_params,"
        " response_sha256, http_status, filter_asserted, ingest_mode, captured_at,"
        " table_action) VALUES (1, 's', 'e', '{}', 'x', 200, 1, 'forward', ?, 't')",
        (STAMP,),
    )
    con.execute(
        "INSERT INTO event (event_id, event_type, docket_id, recorded_at, capture_id,"
        " source_key, payload, payload_version)"
        " VALUES (1, 'decision_observed', 1, ?, 1, 'k', '{}', 1)",
        (STAMP,),
    )
    con.execute(
        "INSERT INTO decision_record (decision_pk, docket_id, stb_decision_id, service_date,"
        " observed_in_event) VALUES (1, 1, '52526', '2021-03-12', 1)"
    )
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'pdf', ?)",
        (SHA, STAMP),
    )
    con.execute(
        "INSERT INTO decision_attachment (decision_pk, source_url, document_sha256)"
        " VALUES (1, 'u', ?)",
        (SHA,),
    )
    for stage in ("citation", "citation_resolution", "projection"):
        methods.measure(
            con,
            measured_target=stage,
            cls="docket",
            extractor_version="v1",
            score_file="t",
            benchmark_date="2026-09-01",
            recall=0.9,
            precision=0.98,
        )
    methods.declare(con, "v1")
    load.load_document(
        con,
        {
            "document_sha256": SHA,
            "method": methods.EXTRACTOR,
            "method_version": "v1",
            "reading_channel": methods.CHANNEL_TEXT,
            "pages_read": 9,
            "findings": [EXPOSED],
        },
        keys.registry(con),
        methods.stamp(con),
    )
    review.grant(con, "reviewer@example.com", "C. Rex", "reviewer zero")
    con.commit()
    con.close()
    return tmp_path / "s.sqlite"


@pytest.fixture
def client(store, tmp_path):
    sender = _Sender()
    app = create_app(
        store,
        sender=sender,
        traffic_path=tmp_path / "traffic.sqlite",
        public_dir=tmp_path / "public",
        secure_cookie=False,  # the test client speaks http
    )
    with TestClient(app) as c:
        c.sender = sender
        yield c


def _nonce(page_text: str) -> str:
    """The handshake the sign-in form carries. A browser submits it because the page it came
    from is same-site; a form on another site cannot, which is the point."""
    marker = 'name="nonce" value="'
    return page_text.split(marker, 1)[1].split('"', 1)[0] if marker in page_text else ""


def _sign_in(client) -> None:
    client.post("/review/sign-in", data={"email": "reviewer@example.com"})
    link = client.sender.link
    page = client.get(link)  # the page with the button; must not sign anybody in
    assert client.cookies.get("dy_review") is None
    client.post(link, data={"nonce": _nonce(page.text)})
    assert client.cookies.get("dy_review") is not None


def test_the_queue_is_not_readable_without_the_grant(client):
    for path in ("/review", "/review/citation_exposed"):
        page = client.get(path)
        assert page.status_code == 200
        assert "Send a sign-in link" in page.text
        assert "AB 1242" not in page.text


def test_a_get_never_signs_anybody_in(client):
    """Mail-security gateways fetch links on delivery. A prefetched link that spent itself
    would hand a session to nobody and lock the reviewer out of their own invitation — the
    lesson `/s/confirm/{token}` already carries."""
    client.post("/review/sign-in", data={"email": "reviewer@example.com"})
    link = client.sender.link
    page = client.get(link)
    assert "Sign in as C. Rex" in page.text
    assert client.cookies.get("dy_review") is None
    client.post(link, data={"nonce": _nonce(page.text)})
    assert client.cookies.get("dy_review") is not None


def test_a_sign_in_link_works_exactly_once(client):
    client.post("/review/sign-in", data={"email": "reviewer@example.com"})
    link = client.sender.link
    nonce = _nonce(client.get(link).text)
    client.post(link, data={"nonce": nonce})
    client.cookies.clear()
    nonce = _nonce(client.get(link).text)  # a fresh handshake; the LINK is what is spent
    again = client.post(link, data={"nonce": nonce}, follow_redirects=False)
    assert client.cookies.get("dy_review") is None
    assert "will not sign you in" in again.text


def test_the_form_says_the_same_thing_whether_or_not_a_grant_exists(client):
    """Anything else turns it into an oracle for who holds a grant. A reviewer's NAME is
    published beside their work (ADR 0016); their address never is."""
    held = client.post("/review/sign-in", data={"email": "reviewer@example.com"})
    stranger = client.post("/review/sign-in", data={"email": "nobody@example.com"})
    assert held.text == stranger.text
    assert len(client.sender.sent) == 1  # and only one of them was mailed


def test_the_cookie_is_fenced_to_the_review_path(client):
    """The promise ADR 0011 makes to readers survives the cookie because the cookie never
    reaches a reader page."""
    _sign_in(client)
    jar = [c for c in client.cookies.jar if c.name == "dy_review"][0]
    assert jar.path == "/review"
    assert jar.has_nonstandard_attr("HttpOnly")
    assert jar.get_nonstandard_attr("SameSite", "").lower() == "strict"


def test_no_page_view_of_a_review_surface_is_counted(client):
    """ADR 0016: the review surfaces "log the actions above and nothing else; no page views,
    no timing beyond the action's own timestamp"."""
    counter = client.app.state.traffic
    counter.drain()  # start from nothing
    _sign_in(client)
    client.get("/review")
    client.get("/review/citation_exposed")
    client.post("/review/sign-out")
    # the counter buckets by route class, not by path, so the assertion is that these
    # requests contributed NO ROW AT ALL — not that no row names them
    assert counter.drain() == []
    client.get("/about")  # and an ordinary page still IS counted, or this passes vacuously
    assert counter.drain(), "the counter recorded nothing at all"


def test_a_review_is_signed_in_and_the_edge_publishes(client, store):
    """The whole flow: sign in, see the evidence beside the question, decide, and the edge
    that was held reaches a page with a name attached."""
    con = db.connect(store)
    assert project.projected(con) == []  # the exposed edge waits (migration 0015)
    con.close()

    _sign_in(client)
    queue = client.get("/review/citation_exposed")
    assert "AB 1242" in queue.text and "slip op" in queue.text  # evidence beside the question

    con = db.connect(store)
    key = review.pending(con, "citation_exposed")[0]["target_key_rendered"]
    con.close()
    client.post(
        "/review/citation_exposed/decide",
        data={"key": key, "decision": "accepted", "note": "the footnote is separate"},
    )

    con = db.connect(store)
    rows = project.projected(con)
    assert len(rows) == 1 and rows[0][2] == "AB 1242"
    assert review.credit(con, key) == "C. Rex"
    con.close()


def test_signing_out_ends_the_session_in_the_store(client, store):
    _sign_in(client)
    client.post("/review/sign-out")
    assert "Send a sign-in link" in client.get("/review").text
    con = db.connect(store)
    assert (
        con.execute("SELECT COUNT(*) FROM reviewer_token WHERE purpose = 'session'").fetchone()[0]
        == 0
    )
    con.close()


def test_withdrawing_the_grant_ends_access_now(client, store):
    """ADR 0016: "a role that can be withdrawn needs a way to be withdrawn". A session that
    outlived the grant would be a grant that could not be withdrawn."""
    _sign_in(client)
    assert "Signed in as" in client.get("/review").text
    con = db.connect(store)
    review.revoke(con, 1)
    con.commit()
    con.close()
    assert "Send a sign-in link" in client.get("/review").text


def test_the_session_row_is_deleted_and_not_kept(store):
    """Keeping a spent session would be keeping a record of when somebody was signed in,
    which is what ADR 0016 says is not stored."""
    con = db.connect(store)
    token = signin._mint(con, 1, "session", signin.timedelta(hours=1))
    assert signin.whoami(con, token) is not None
    signin.sign_out(con, token)
    assert signin.whoami(con, token) is None
    assert con.execute("SELECT COUNT(*) FROM reviewer_token").fetchone()[0] == 0
    con.close()


def test_a_session_token_is_not_a_sign_in_link(store):
    """Migration 0017's whole reason: a session value pasted into an address bar must not
    work, because a sign-in link travels in a URL and a session cookie must not."""
    con = db.connect(store)
    session = signin._mint(con, 1, "session", signin.timedelta(hours=1))
    assert signin.pending(con, session) is None
    assert signin.sign_in(con, session) is None
    con.close()


def test_an_expired_link_and_an_expired_session_both_refuse(store):
    con = db.connect(store)
    stale = signin._mint(con, 1, "sign-in", signin.timedelta(minutes=-1))
    assert signin.pending(con, stale) is None and signin.sign_in(con, stale) is None
    dead = signin._mint(con, 1, "session", signin.timedelta(hours=-1))
    assert signin.whoami(con, dead) is None
    assert signin.sweep(con) == 2
    con.close()


def test_the_purpose_column_refuses_a_third_kind(store):
    con = db.connect(store)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO reviewer_token (token_hash, reviewer_id, purpose, expires_at,"
            " issued_at) VALUES ('h', 1, 'password', ?, ?)",
            (STAMP, STAMP),
        )
    con.close()


# --- what /security-review found -------------------------------------------------------


def test_the_mail_cannot_reach_the_page_that_says_a_link_was_sent(client):
    """`Sender.send` opens a fresh SMTP session — TCP, TLS, AUTH, DATA — so sending inside
    the handler made the granted branch take the better part of a second while the ungranted
    one returned in about a millisecond. Identical HTML, three orders of magnitude apart:
    one request per guess and the form told you which address belongs to a reviewer.

    THE TIMING ITSELF IS NOT TESTABLE HERE — Starlette's TestClient runs background tasks
    before it hands back the response, so both branches block either way in a test. What IS
    testable is the property the fix rests on: the send happens outside the handler, so
    NOTHING it does can reach the page. A sender that raises proves it; an inline send in a
    try/except would too, which is why the structural check below sits beside it."""
    import inspect

    from docketyard.web import review_routes

    class _Broken(_Sender):
        def send(self, out):
            raise RuntimeError("SES said no")

    client.sender.__class__ = _Broken
    page = client.post("/review/sign-in", data={"email": "reviewer@example.com"})
    assert page.status_code == 200 and "on its way" in page.text

    # and the handler really does hand the send away rather than awaiting it: without the
    # BackgroundTasks parameter the response cannot be produced before the SMTP round trip
    source = inspect.getsource(review_routes.register)
    assert "background: BackgroundTasks" in source
    assert "background.add_task(_mail_link" in source
    assert "sender.send(" not in source.split("def _mail_link")[0]


def test_the_sign_in_page_quotes_the_links_own_lifetime(client):
    """A missing template variable renders as "expires in  minutes"."""
    page = client.post("/review/sign-in", data={"email": "nobody@example.com"})
    assert f"expires in {signin.SIGN_IN_TTL_MINUTES} minutes" in page.text


def test_an_unknown_queue_is_a_404_and_not_a_200(client):
    """`render` takes **context, so `status_code=404` became a template variable."""
    _sign_in(client)
    assert client.get("/review/citation_nonsense").status_code == 404


def test_revoking_ends_the_session_rows_too(client, store):
    _sign_in(client)
    con = db.connect(store)
    # one row: the spent link is deleted the moment it mints a session, so the only token
    # left is the session itself
    assert con.execute("SELECT COUNT(*) FROM reviewer_token").fetchone()[0] == 1
    assert review.revoke(con, 1) == 1
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM reviewer_token").fetchone()[0] == 0
    con.close()
    assert "Send a sign-in link" in client.get("/review").text


def test_a_cross_site_post_cannot_plant_a_session(client):
    """`SameSite=Strict` covers every other state-changing POST because they all need the
    session cookie — but `POST /review/enter/{token}` needs no cookie at all, so Strict
    protected nothing there. Someone holding a grant could auto-submit THEIR OWN sign-in
    token from another site and plant their session in a victim reviewer's browser; the
    victim's decisions would then be credited to the attacker. On a record whose whole point
    is that an assertion has an author, that is the attack that matters."""
    client.post("/review/sign-in", data={"email": "reviewer@example.com"})
    link = client.sender.link
    page = client.get(link)
    good = _nonce(page.text)
    assert good

    # a form on another site carries neither the handshake cookie nor the field
    client.cookies.clear()
    planted = client.post(link, data={}, follow_redirects=False)
    assert client.cookies.get("dy_review") is None
    assert "will not sign you in" in planted.text
    # and the token is NOT spent, so the real reviewer's link still works
    page = client.get(link)
    client.post(link, data={"nonce": _nonce(page.text)})
    assert client.cookies.get("dy_review") is not None


def test_a_correction_names_a_docket_the_way_the_board_prints_it(client, store):
    """The form used to take an internal docket id that no page ever showed, and passed it
    through unchecked — so a plausible guess published a WRONG edge, resolved and confident,
    under the reviewer's own credit name."""
    _sign_in(client)
    con = db.connect(store)
    key = review.pending(con, "citation_exposed")[0]["target_key_rendered"]
    con.close()

    refused = client.post(
        "/review/citation_exposed/decide",
        data={"key": key, "decision": "corrected", "note": "n", "docket": "AB 99999"},
    )
    assert "not a docket this record holds" in refused.text
    con = db.connect(store)
    assert project.projected(con) == []  # nothing published on a guess
    con.close()

    client.post(
        "/review/citation_exposed/decide",
        data={
            "key": key,
            "decision": "corrected",
            "note": "footnote 2 fused on",
            "docket": "AB 124",
        },
    )
    con = db.connect(store)
    rows = project.projected(con)
    assert len(rows) == 1 and rows[0][3] == 2  # AB 124's docket_id, resolved by its printed form
    con.close()


def test_the_form_a_reviewer_copies_off_this_site_finds_the_docket_it_names(store):
    """`keys.normalise` alone answered three ways a reviewer could not see: the site's own
    printed form of a suffixed parent found the PARENT silently, a docket outside the
    citation class could not be named at all, and the site's own long citation form carried
    no prefix token to match. All three name a proceeding the record holds."""
    con = db.connect(store)
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence, suffix)"
        " VALUES (4, 'AB_1182_0_X', 'AB', 1182, 'X')"
    )
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence) VALUES (5, 'AB_1182',"
        " 'AB', 1182)"
    )
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence, suffix)"
        " VALUES (6, 'S5M_1_0_A', 'S5M', 1, 'A')"
    )

    suffixed = parse_docket_id("AB_1182_0_X")
    # the two forms this site itself prints for it, and the Board's own spelling
    assert review.find_docket(con, urls.printed_docket(suffixed))[0] == 4  # 'AB 1182-X'
    assert review.find_docket(con, urls.cite_docket(suffixed))[0] == 4
    assert review.find_docket(con, "AB 1182 (Sub-No. 0X)")[0] == 4
    assert review.find_docket(con, "AB 1182")[0] == 5  # the parent is still its own docket

    # outside the citation class (13 prefixes, 655 dockets) but inside the record
    assert keys.normalise("S5M 1-A") is None
    assert review.find_docket(con, urls.printed_docket(parse_docket_id("S5M_1_0_A")))[0] == 6

    # the long form `cite_docket` prints for FD and EP, which carries no `FD` token
    assert review.find_docket(con, "STB Finance Docket No. 36873")[0] == 1

    # a shape only the citation grammar takes still resolves, and a miss is still a miss
    assert review.find_docket(con, "AB124")[0] == 2
    assert review.find_docket(con, "AB 99999") is None
    assert review.find_docket(con, "AB 1182-Q") is None  # parses, not held: never the parent
    con.close()


def test_an_unknown_reviewer_cannot_be_revoked_silently(store):
    con = db.connect(store)
    with pytest.raises(ValueError, match="no reviewer"):
        review.revoke(con, 999)
    con.close()


def test_signing_in_sweeps_expired_tokens(client, store):
    """`sign_out`'s docstring and the privacy page both say no record of when somebody was
    signed in is kept. An expired row keeps `issued_at` for ever unless something sweeps."""
    con = db.connect(store)
    signin._mint(con, 1, "session", signin.timedelta(hours=-5))
    signin._mint(con, 1, "sign-in", signin.timedelta(minutes=-5))
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM reviewer_token").fetchone()[0] == 2
    con.close()
    _sign_in(client)
    con = db.connect(store)
    purposes = [r[0] for r in con.execute("SELECT purpose FROM reviewer_token")]
    assert purposes == ["session"]  # the two stale rows are gone; the spent link went too
    con.close()
