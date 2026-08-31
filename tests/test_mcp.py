"""The machine-agent surface (F7): the protocol, and the two constraints that travel with it.

The protocol tests are ordinary. The two that matter are the constraints the capability map
attaches to this surface, because they are the ones a later change would quietly break:
**read-only**, and **every answer carries its caveats**. An assistant quoting this record
without them is worse than no source, so they are asserted, not trusted.
"""

import ast
import pathlib

import pytest
from fastapi.testclient import TestClient

from docketyard.store import db, search
from docketyard.web import mcp
from docketyard.web.app import create_app
from tests.test_enviro_ingest import comment_row
from tests.test_enviro_ingest import ingest as ingest_comment
from tests.test_web import build_store


@pytest.fixture
def client(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    ingest_comment(con, tmp_path, comment_row())
    search.rebuild(con)
    con.close()
    return TestClient(create_app(path))


def rpc(client, method, params=None, mid=1, version="2025-11-25"):
    body = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        body["params"] = params
    headers = {"MCP-Protocol-Version": version} if version else {}
    return client.post("/mcp", json=body, headers=headers)


def call(client, name, arguments=None):
    r = rpc(client, "tools/call", {"name": name, "arguments": arguments or {}})
    return r.json()["result"]


# --- the protocol ----------------------------------------------------------------------


def test_initialize_negotiates_and_hands_over_the_standing_caveats(client):
    r = rpc(
        client,
        "initialize",
        {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        },
    )
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["protocolVersion"] == "2025-11-25"
    assert result["serverInfo"]["name"] == "docketyard"
    assert result["capabilities"] == {"tools": {}}
    # the caveats reach the model BEFORE it asks anything, not only in each answer
    instructions = result["instructions"]
    for needle in ("NOT the STB", "Quote, do not infer", "never fill the gap from memory"):
        assert needle in instructions, needle


def test_an_older_client_is_answered_and_an_unknown_version_refused(client):
    # a client that asks for a version we speak gets it back
    r = rpc(client, "initialize", {"protocolVersion": "2025-06-18"}, version="2025-06-18")
    assert r.json()["result"]["protocolVersion"] == "2025-06-18"
    # no header at all: the spec's own default, answered rather than refused
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 200 and r.json()["result"] == {}
    # a version we do not speak is a 400, as the spec requires
    assert rpc(client, "ping", version="1999-01-01").status_code == 400


def test_the_transport_answers_the_shapes_the_spec_names(client):
    # a notification carries no id and gets 202 with no body
    assert (
        client.post(
            "/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        ).status_code
        == 202
    )
    # GET is the spec's out for a server that never pushes
    assert client.get("/mcp").status_code == 405
    # an unparseable body is a JSON-RPC parse error, not a stack trace
    r = client.post("/mcp", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700
    # an unknown method and an unknown tool are different errors
    assert rpc(client, "no/such/method").json()["error"]["code"] == -32601
    assert rpc(client, "tools/call", {"name": "nope"}).json()["error"]["code"] == -32602


def test_the_discovery_document_points_at_the_endpoint(client):
    r = client.get("/.well-known/mcp.json")
    assert r.status_code == 200
    d = r.json()
    assert d["transport"] == {"type": "streamable-http", "url": "https://docketyard.org/mcp"}
    assert d["readOnly"] is True
    assert {t["name"] for t in d["tools"]} == set(mcp.BY_NAME)


def test_every_tool_declares_a_closed_schema(client):
    tools = rpc(client, "tools/list").json()["result"]["tools"]
    assert {t["name"] for t in tools} == set(mcp.BY_NAME)
    for t in tools:
        assert t["description"] and t["title"]
        assert t["inputSchema"]["type"] == "object"
        # closed, so a client cannot smuggle a field past the handler
        assert t["inputSchema"]["additionalProperties"] is False


# --- the constraints -------------------------------------------------------------------


def test_the_surface_is_read_only(client):
    """No capability may write, subscribe, or spend on a reader's behalf. Asserted against
    the module's own imports and source, so a later tool that writes fails here."""
    source = pathlib.Path(mcp.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {(node.module or "") for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    forbidden = ("alerts", "subscriptions", "capture", "backfill", "poll", "dump")
    for module in imported:
        assert not any(f in module for f in forbidden), f"{module} is not a read path"
    # and no SQL that changes anything
    for verb in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "CREATE ", "ALTER "):
        assert verb not in source.upper().replace("CREATED", ""), verb
    # the server declares no capability beyond tools — no prompts, no sampling, no roots
    result = rpc(client, "initialize", {"protocolVersion": "2025-11-25"}).json()["result"]
    assert list(result["capabilities"]) == ["tools"]


def test_every_answer_carries_what_the_record_does_not_hold(client):
    """The caveats are the payload, not formatting: an assistant is handed a string and
    will quote it. Every tool, including the ones that find nothing."""
    answers = [
        call(client, "coverage")["content"][0]["text"],
        call(client, "search_the_record", {"query": "aquifer"})["content"][0]["text"],
        call(client, "search_the_record", {"query": "nothingmatchesthis"})["content"][0]["text"],
        call(client, "get_docket_sheet", {"docket": "FD 36873"})["content"][0]["text"],
        call(client, "get_docket_sheet", {"docket": "FD 99999"})["content"][0]["text"],
        call(client, "get_environmental_comment", {"number": "EI-34280"})["content"][0]["text"],
        call(client, "get_environmental_comment", {"number": "EI-00000"})["content"][0]["text"],
    ]
    for text in answers:
        assert "does not say what any party argued" in text, text[:80]
        assert "Coverage is not uniform" in text, text[:80]


def test_an_absence_is_reported_as_an_absence_not_filled_in(client):
    """The specific failure this surface exists to prevent is an assistant inventing a
    docket number. A miss must read as a miss."""
    text = call(client, "get_docket_sheet", {"docket": "FD 99999"})["content"][0]["text"]
    assert "holds no proceeding" in text and "may exist at the Board and not here" in text
    text = call(client, "search_the_record", {"query": "zzzznothing"})["content"][0]["text"]
    assert "holds nothing" in text and "not proof of absence at the Board" in text


def test_a_comment_is_handed_over_as_quotation(client):
    text = call(client, "get_environmental_comment", {"number": "ei-34280"})["content"][0]["text"]
    assert "Casper Aquifer" in text  # the commenter's own words, as printed
    assert "David Gertsch" in text and "Laramie, WY" in text
    assert "/d/FD-36873/comment/EI-34280" in text  # its permanent address
    # and it is framed as theirs, not ours
    assert "the commenter's own statement, quoted" in text
    assert "not this record's view" in text


def test_a_sheet_names_the_boards_own_file(client):
    text = call(client, "get_docket_sheet", {"docket": "fd 36873"})["content"][0]["text"]
    assert "the Board's file: https://dcms-external" in text
    assert "https://docketyard.org/d/FD-36873" in text
    assert "1 decision" in text and "1 decisions" not in text  # quoted back verbatim


def test_a_failing_tool_is_a_result_not_a_transport_error(client, monkeypatch):
    """A tool that raises comes back as isError so the client sees the failure in band
    rather than the connection breaking — and without the exception's text (see the
    disclosure test below)."""
    import dataclasses

    def boom(con, args, host):
        raise RuntimeError("the store went away")

    # the Tool is frozen on purpose, so the registry entry is replaced, not mutated
    monkeypatch.setitem(
        mcp.BY_NAME, "coverage", dataclasses.replace(mcp.BY_NAME["coverage"], run=boom)
    )
    r = rpc(client, "tools/call", {"name": "coverage", "arguments": {}})
    assert r.status_code == 200
    assert r.json()["result"]["isError"] is True
    assert "the store went away" not in r.json()["result"]["content"][0]["text"]


def test_robots_names_the_ai_crawlers_and_says_what_is_permitted(client):
    """Silence is not neutral — some crawlers read it as disallowed, and the audience asks
    assistants these questions either way. The policy is stated (operator, 2026-08-31)."""
    body = client.get("/robots.txt").text
    for agent in ("GPTBot", "ClaudeBot", "Google-Extended", "PerplexityBot", "CCBot"):
        assert f"User-agent: {agent}" in body, agent
    assert "training on the raw index is permitted" in body
    assert "CC0 1.0" in body
    # the reader-facing caveats travel with the permission
    assert "coverage is not uniform" in body and "what any party argued" in body
    # and the machine surfaces are named where a crawler will actually look
    for path in ("/llms.txt", "/.well-known/mcp.json", "/coverage", "/sitemap.xml"):
        assert path in body, path
    # Every named agent carries the disallows too. Naming an agent must not accidentally
    # hand it the paths the wildcard block keeps out — robots.txt gives a matching agent
    # ONLY its own block, so a named agent with no Disallow lines is allowed everything.
    blocks = [b for b in body.split("\n\n") if b.startswith("User-agent:")]
    assert len(blocks) >= 2
    for block in blocks:
        assert "Disallow: /subscribe" in block, block.splitlines()[0]
        assert "Disallow: /s/" in block, block.splitlines()[0]


def test_the_data_page_says_the_same_thing_to_a_person(client):
    body = client.get("/data").text
    assert "Machines are welcome" in body
    assert "/.well-known/mcp.json" in body and "/llms.txt" in body
    assert "worse than no source" in body


# --- what review found ------------------------------------------------------------------


def test_a_cross_posted_comment_is_one_comment_to_an_assistant(tmp_path):
    """Folding by number alone would tell an assistant a cross-posted comment was "two
    different people" — the same defect the web routes were already fixed for,
    reintroduced here and caught by review. The row ref is what folds."""
    path = build_store(tmp_path)
    con = db.connect(path)
    ingest_comment(
        con, tmp_path, comment_row(docket="AB_55") + comment_row(docket="AB_55_794_X"), total=2
    )
    con.close()
    c = TestClient(create_app(path))
    text = call(c, "get_environmental_comment", {"number": "EI-34280"})["content"][0]["text"]
    assert "different comments by different people" not in text
    assert text.count("Submitted by: David Gertsch") == 1
    assert "/d/AB-55/comment/EI-34280" in text  # the canonical address, not the sub-docket's


def test_two_comments_sharing_a_number_are_both_named(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    ingest_comment(con, tmp_path, comment_row(ref="190089", submitter="Helen"))
    ingest_comment(
        con, tmp_path, comment_row(docket="FD_36095", ref="190749", submitter="Elizabeth")
    )
    con.close()
    c = TestClient(create_app(path))
    text = call(c, "get_environmental_comment", {"number": "EI-34280"})["content"][0]["text"]
    assert "Helen" in text and "Elizabeth" in text
    assert "different comments by different people" in text


def test_a_comment_names_the_boards_own_file(client):
    text = call(client, "get_environmental_comment", {"number": "EI-34280"})["content"][0]["text"]
    assert "The Board's own file: https://dcms-external" in text


def test_a_truncated_sheet_says_which_end_it_kept(client):
    text = call(client, "get_docket_sheet", {"docket": "FD 36873", "limit": 1})["content"][0][
        "text"
    ]
    assert "newest first" in text
    assert "most recent, not the whole sheet" in text


def test_an_unknown_protocol_version_is_answered_with_the_newest_we_speak(client):
    r = rpc(client, "initialize", {"protocolVersion": "2024-11-05"}, version=None)
    assert r.json()["result"]["protocolVersion"] == mcp.PROTOCOL_VERSION


def test_the_discovery_document_does_not_call_the_whole_surface_cc0(client):
    """Search can return party-module hits, which are held back from the dedication
    pending a licence review. A flat `licence: CC0-1.0` would promise otherwise."""
    licence = client.get("/.well-known/mcp.json").json()["licence"]
    assert licence["record"] == "CC0-1.0"
    assert "NOT covered by that dedication" in licence["note"]
    assert licence["url"].endswith("/data")


def test_the_held_layer_is_disallowed_for_the_agents_the_policy_names(client):
    """The prose says the party module is not part of the dedication; the rule must say
    it too, or the named agents are handed exactly what the prose withholds."""
    body = client.get("/robots.txt").text
    blocks = [b for b in body.split("\n\n") if b.startswith("User-agent:")]
    wildcard = [b for b in blocks if b.startswith("User-agent: *")][0]
    named = [b for b in blocks if not b.startswith("User-agent: *")]
    assert named, "no AI agent is named"
    for block in named:
        assert "Disallow: /p/" in block, block.splitlines()[0]
        assert "Disallow: /parties" in block, block.splitlines()[0]
    # people and ordinary crawlers still read it: this is the dedication, not secrecy
    assert "Disallow: /p/" not in wildcard


def test_the_machine_surfaces_point_at_each_other(client):
    assert "/.well-known/mcp.json" in client.get("/llms.txt").text
    api = client.get("/api").text
    assert "/mcp" in api and "read-only" in api.lower()


def test_a_malformed_body_is_a_protocol_error_not_a_500(client):
    """The body is unauthenticated and arbitrary. `params` and `arguments` are dicts only
    because a client chose to send dicts, so they are checked — `params.get` on a list was
    an unhandled 500 from a one-line payload (security review)."""
    for params in ([1, 2], "x", 7):
        r = client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}
        )
        assert r.status_code == 200, params
        assert r.json()["error"]["code"] == -32602, params
    for arguments in ([1], "x", 7):
        r = rpc(client, "tools/call", {"name": "coverage", "arguments": arguments})
        assert r.status_code == 200 and r.json()["error"]["code"] == -32602, arguments
    # a non-string tool name is refused rather than looked up
    assert rpc(client, "tools/call", {"name": {"a": 1}}).json()["error"]["code"] == -32602


def test_an_internal_failure_does_not_describe_itself_to_the_caller(client, monkeypatch, capsys):
    """Echoing the exception handed an unauthenticated client internal detail — "no such
    table: …" names the schema. The operator's log gets it; the caller does not."""
    import dataclasses

    def boom(con, args, host):
        raise RuntimeError("no such table: enviro_comment")

    monkeypatch.setitem(
        mcp.BY_NAME, "coverage", dataclasses.replace(mcp.BY_NAME["coverage"], run=boom)
    )
    body = rpc(client, "tools/call", {"name": "coverage", "arguments": {}}).json()["result"]
    assert body["isError"] is True
    text = body["content"][0]["text"]
    assert "no such table" not in text and "enviro_comment" not in text
    assert "failed inside this record" in text
    assert "no such table" in capsys.readouterr().out  # the operator still sees it


def test_the_stores_own_connection_refuses_writes(tmp_path):
    """Read-only is enforced by SQLite, not only by convention or by review: the web
    tier's connection — the one the MCP handler is given — sets `PRAGMA query_only = ON`,
    so a tool that tried to write would raise rather than land."""
    import sqlite3

    from docketyard.web.app import _connect

    con = _connect(build_store(tmp_path))
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly|query_only"):
            con.execute("DELETE FROM docket")
    finally:
        con.close()
