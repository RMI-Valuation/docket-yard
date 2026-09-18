"""The machine-agent surface (F7): the protocol, and the two constraints that travel with it.

The protocol tests are ordinary. The two that matter are the constraints the capability map
attaches to this surface, because they are the ones a later change would quietly break:
**read-only**, and **every answer carries its caveats**. An assistant quoting this record
without them is worse than no source, so they are asserted, not trusted.
"""

import ast
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from docketyard.store import db, search, sheet
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
        # and says it only reads, so a client does not ask the reader to confirm each call
        assert t["annotations"]["readOnlyHint"] is True
        assert t["annotations"]["destructiveHint"] is False


# --- the constraints -------------------------------------------------------------------


def test_the_surface_is_read_only(client):
    """No capability may write, subscribe, or spend on a reader's behalf. Asserted against
    the module's own imports and source, so a later tool that writes fails here."""
    source = pathlib.Path(mcp.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    # BOTH import forms: the walk checked only `from X import Y`, so `import
    # docketyard.subscriptions` — an ast.Import, whose names live on node.names — would
    # have slipped past the check this test exists to be (ultrareview)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
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
    answers += [
        call(client, "count_filings", {"filing_type": "motion"})["content"][0]["text"],
        call(client, "count_filings", {"filing_type": "nitu"})["content"][0]["text"],
        call(client, "count_filings", {"prefix": "ZZ"})["content"][0]["text"],
    ]
    for text in answers:
        assert "does not say what any party argued" in text, text[:80]
        assert "Coverage is not uniform" in text, text[:80]


def test_coverage_names_every_limit_the_page_names(client):
    """The `coverage` tool is what an assistant repeats when it cannot read the page, and
    the server's instructions tell it to. A grader found it naming the counts and the
    unfinished months but none of the limits (the independent graders, 2026-09-16), so an
    assistant answered as if the record were uniform, complete and unbroken.

    The by-design limits are asserted from the SAME constant the page renders, so this
    passes only while the two cannot drift — adding a fourth limit to the page without the
    tool fails here."""
    from docketyard.store import coverage

    text = call(client, "coverage")["content"][0]["text"]
    for head, rest in coverage.BY_DESIGN_LIMITS:
        assert f"{head}{rest}" in text, f"the tool drops the page's limit {head!r}"
    # measured, and each is a different kind of not-covered: history, and time the watch
    # was down. Silence about an outage reads as "there were none".
    assert "complete history" in text, "the tool claims no limit on how far back it reaches"
    assert "outage" in text.lower(), "the tool says nothing about outages either way"


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
    it too, or the named agents are handed exactly what the prose withholds. Since
    2026-09-16 (the operator) that means the agents that index or train: the three that fetch
    on a person's request may read what a person may."""
    from docketyard.web.app import USER_DIRECTED_AGENTS

    body = client.get("/robots.txt").text
    blocks = [b for b in body.split("\n\n") if b.startswith("User-agent:")]
    wildcard = [b for b in blocks if b.startswith("User-agent: *")][0]
    named = [b for b in blocks if not b.startswith("User-agent: *")]
    assert named, "no AI agent is named"
    for block in named:
        agent = block.splitlines()[0].removeprefix("User-agent: ")
        held = ("/p/", "/parties", "/filing/*/text", "/decision/*/text", "/d/*/comment/*/text")
        for path in held:
            refused = f"Disallow: {path}" in block
            assert refused is (agent not in USER_DIRECTED_AGENTS), (agent, path)
        assert "Disallow: /search" in block, agent  # bulk, for every named agent
    assert {"ChatGPT-User", "Claude-User", "Perplexity-User"} <= set(USER_DIRECTED_AGENTS)
    # people and ordinary crawlers still read it: this is the dedication, not secrecy
    assert "Disallow: /p/" not in wildcard
    # and the prose says what the rule does
    assert "allowed to the three that fetch a page because" in body


def _named_rules(robots: str) -> tuple[list[str], list[str]]:
    """(the wildcard block's Disallow paths, the strictest named agent's) — every agent that
    indexes or trains has the same block; the user-directed three refuse a subset of it."""
    from docketyard.web.app import USER_DIRECTED_AGENTS

    blocks = [b for b in robots.split("\n\n") if b.startswith("User-agent:")]

    def rules(block):
        return [
            line.removeprefix("Disallow: ") for line in block.splitlines() if "Disallow" in line
        ]

    wildcard = [b for b in blocks if b.startswith("User-agent: *")][0]
    named = [b for b in blocks if not b.startswith("User-agent: *")]
    strict = [
        b for b in named if b.splitlines()[0][len("User-agent: ") :] not in USER_DIRECTED_AGENTS
    ]
    assert all(rules(b) == rules(strict[0]) for b in strict)
    assert all(set(rules(b)) <= set(rules(strict[0])) for b in named)
    return rules(wildcard), rules(strict[0])


def _refused(rules: list[str], path: str) -> bool:
    """robots.txt matching as the named crawlers document it: a prefix, `*` any run."""
    return any(re.match(re.escape(r).replace(r"\*", ".*"), path) for r in rules)


def test_search_is_disallowed_for_the_named_agents_and_no_one_else(client):
    """A result page prints page-text snippets and party names, so an agent refused /text
    and /p/ could read both from it (the operator, 2026-09-10, machine-surface.md)."""
    wildcard, named = _named_rules(client.get("/robots.txt").text)
    assert "/search" in named and "/search" not in wildcard
    assert _refused(named, "/search?q=union+pacific")


def test_llms_txt_never_links_what_robots_refuses_the_agents_it_is_written_for(client):
    """The prose must agree with the rule. Until 2026-09-10 llms.txt linked /parties to the
    assistants robots.txt refused it to, and it linked /search as well."""
    _, named = _named_rules(client.get("/robots.txt").text)
    links = re.findall(r"\]\(https://docketyard\.org(/[^)]*)\)", client.get("/llms.txt").text)
    assert len(links) > 10
    for path in links:
        assert not _refused(named, path), path
    assert client.get("/d?q=FD%2036873", follow_redirects=False).status_code in (301, 302, 303)


def test_the_machine_surfaces_point_at_each_other(client):
    assert "/.well-known/mcp.json" in client.get("/llms.txt").text
    api = client.get("/api").text
    assert "/mcp" in api and "read-only" in api.lower()


def test_a_malformed_body_is_a_protocol_error_not_a_500(client):
    """The body is unauthenticated and arbitrary. `params` and `arguments` are dicts only
    because a client chose to send dicts, so they are checked — `params.get` on a list was
    an unhandled 500 from a one-line payload (security review)."""
    # BOTH branches that reach into params — the fix landed on tools/call and initialize
    # was left with the same defect, which this loop would have caught (ultrareview)
    for method in ("tools/call", "initialize"):
        for params in ([1, 2], "x", 7):
            r = client.post(
                "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            )
            assert r.status_code == 200, (method, params)
            assert r.json()["error"]["code"] == -32602, (method, params)
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


# --- what the cloud review found --------------------------------------------------------


def test_the_boards_placeholder_never_becomes_a_name_or_a_place(tmp_path):
    """`--` is what the Board prints for a cell it has nothing for, and it is truthy. The
    sheet strips it before any page renders; this surface re-queried the store and would
    have handed an assistant "Location: --" as though it were a place."""
    path = build_store(tmp_path)
    con = db.connect(path)
    ingest_comment(con, tmp_path, comment_row(org="--", location="--", text="--"))
    con.close()
    c = TestClient(create_app(path))
    text = call(c, "get_environmental_comment", {"number": "EI-34280"})["content"][0]["text"]
    assert "--" not in text
    assert "Location:" not in text and "Organisation:" not in text
    assert "David Gertsch" in text  # what WAS printed survives
    # and the no-text branch fires rather than quoting the placeholder as the words
    assert "printed no text for this comment" in text


def test_a_comment_with_neither_words_nor_file_does_not_contradict_itself(tmp_path):
    path = build_store(tmp_path)
    con = db.connect(path)
    ingest_comment(con, tmp_path, comment_row(text="--", pdf=""))
    con.execute("DELETE FROM enviro_comment_attachment")
    con.commit()
    con.close()
    c = TestClient(create_app(path))
    text = call(c, "get_environmental_comment", {"number": "EI-34280"})["content"][0]["text"]
    assert "its words are in the file below" not in text  # nothing to point at
    assert "printed no text for this comment and lists no file" in text


def test_a_cross_posting_is_named_in_the_form_a_person_could_look_up(tmp_path):
    """`also_in` carries the store's own ids (AB_55_785_X). Handed to an assistant they
    resolve nowhere — the failure this surface exists to prevent, delivered by it."""
    path = build_store(tmp_path)
    con = db.connect(path)
    ingest_comment(
        con, tmp_path, comment_row(docket="AB_55") + comment_row(docket="AB_55_794_X"), total=2
    )
    con.close()
    c = TestClient(create_app(path))
    text = call(c, "get_docket_sheet", {"docket": "AB 55"})["content"][0]["text"]
    assert "AB_55_794_X" not in text and "AB_55" not in text.replace("AB 55", "")
    if "also entered in" in text:
        assert "AB 55 (Sub-No. 794X)" in text


def test_the_caveats_are_appended_once_by_the_handler_not_by_each_tool(client):
    """Three return paths skipped them while a test claimed every tool carried them. They
    are appended centrally now, so a tool cannot forget what it does not do."""
    empty_query = call(client, "search_the_record", {"query": "   "})["content"][0]["text"]
    unparseable = call(client, "get_docket_sheet", {"docket": "not a docket"})["content"][0]["text"]
    for text in (empty_query, unparseable):
        assert "does not say what any party argued" in text, text[:60]
    # and exactly once — the tools no longer add their own
    assert empty_query.count("Coverage is not uniform") == 1


def test_initialize_falls_back_to_the_version_the_header_negotiated(client):
    """A client that sets MCP-Protocol-Version and omits protocolVersion from params gets
    its own version back, not ours — which is what threading `version` in was for."""
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers={"MCP-Protocol-Version": "2025-06-18"},
    )
    assert r.json()["result"]["protocolVersion"] == "2025-06-18"


def test_the_machine_surface_answers_a_series_with_its_index(tmp_path):
    """The page and the JSON both gained an `is_index` branch; this surface did not, so an
    assistant asking about a series was handed "N filings … held" followed by "Entries,
    newest first:" and nothing after it (code review, 2026-09-01)."""
    path = build_store(tmp_path)
    con = db.connect(path)
    parent = con.execute(
        "INSERT INTO docket (raw_docket, prefix, sequence) VALUES ('AB_167', 'AB', 167)"
    ).lastrowid
    for sub in range(1, sheet.SERIES_SUBS + 2):
        con.execute(
            "INSERT INTO docket (raw_docket, prefix, sequence, sub_sequence, suffix,"
            " parent_docket_id) VALUES (?, 'AB', 167, ?, 'X', ?)",
            (f"AB_167_{sub}_X", sub, parent),
        )
    con.commit()
    out = mcp._docket(con, {"docket": "AB 167"}, "docketyard.org")
    con.close()
    assert "it holds no record of its own" in out
    assert "Proceedings under this number:" in out
    assert "Entries, newest first:" not in out
    assert "/d/AB-167/sub/1X" in out
    assert out.rstrip().endswith(mcp._NOT_HELD)  # the caveats still travel with the answer


# --- counting (asked for 2026-09-16, when an assistant could not say how many) ------------


def _abandonments(tmp_path):
    """Two AB proceedings and a parent: one holds a consummation notice and a trail-use
    agreement, one only a trail-use request, and one consummation notice is entered in both
    the parent and its sub-docket — the cross-posting that counts rows twice."""
    path = build_store(tmp_path)
    con = db.connect(path)
    (event,) = con.execute("SELECT MIN(observed_in_event) FROM filing").fetchone()
    parent = con.execute(
        "INSERT INTO docket (raw_docket, prefix, sequence) VALUES ('AB_55', 'AB', 55)"
    ).lastrowid
    subs = {}
    for sub in (794, 800):
        subs[sub] = con.execute(
            "INSERT INTO docket (raw_docket, prefix, sequence, sub_sequence, suffix,"
            " parent_docket_id) VALUES (?, 'AB', 55, ?, 'X', ?)",
            (f"AB_55_{sub}_X", sub, parent),
        ).lastrowid
    for docket_id, fid, ftype, filed in (
        (subs[794], "9001", "Trail Use Agreement Reached", "2019-03-02"),
        (subs[794], "9002", "Consummation Notice", "2021-06-01"),
        (parent, "9002", "Consummation Notice", "2021-06-01"),  # the same filing, cross-posted
        (subs[800], "9003", "Trail Use Request", "2024-01-15"),
    ):
        con.execute(
            "INSERT INTO filing (docket_id, stb_filing_id, filing_type, filed_date,"
            " observed_in_event) VALUES (?, ?, ?, ?, ?)",
            (docket_id, fid, ftype, filed, event),
        )
    con.commit()
    return con


def count(con, **arguments):
    return mcp._count(con, arguments, "docketyard.org")


def test_a_count_is_of_filings_and_proceedings_not_rows(tmp_path):
    con = _abandonments(tmp_path)
    text = count(con, filing_type="consummation notice", prefix="ab")
    # two rows, one filing, entered in two proceedings — and the answer says how it counted
    assert "'Consummation Notice' in AB proceedings: 1 filing entered in 2 proceedings" in text
    assert "counts once among filings and once in each proceeding" in text
    assert "does not say what was consummated" in text
    con.close()


def test_words_in_a_type_count_every_type_they_match_and_name_each(tmp_path):
    con = _abandonments(tmp_path)
    text = count(con, filing_type="trail use", prefix="AB")
    assert "'Trail Use Agreement Reached', 'Trail Use Request'" in text
    assert "2 filings entered in 2 proceedings" in text
    assert "- Trail Use Request: 1 filing in 1 proceeding" in text
    # no consummation was counted, so the note about one is not handed over
    assert "consummated" not in text
    con.close()


def test_proceedings_holding_both_types_are_counted_without_implying_order(tmp_path):
    con = _abandonments(tmp_path)
    text = count(con, filing_type="Consummation Notice", also_has="trail use")
    assert ": 1 (of 2 holding the first and 2 holding the second)" in text
    assert "says nothing about which came first" in text
    # a date range applies to both halves of the pair, and the answer says so
    text = count(
        con, filing_type="Consummation Notice", also_has="trail use", filed_from="2020-01-01"
    )
    assert (
        ": 0 (of 2 holding the first and 1 holding the second; both filed inside the range)" in text
    )
    con.close()


def test_one_filing_matching_both_phrases_is_not_a_pair(tmp_path):
    """`trail use` contains `Trail Use Request`, so AB 55 (Sub-No. 800X)'s one request matched
    both halves and was counted as holding both (code review)."""
    con = _abandonments(tmp_path)
    text = count(con, filing_type="trail use", also_has="Trail Use Request")
    # 794X holds an agreement and no request; 800X holds one request, which is one filing
    assert ": 0 (of 2 holding the first and 1 holding the second)" in text
    con.close()


def test_a_decisions_act_is_not_a_filing_type_and_the_miss_says_so(tmp_path):
    """The question that asked for this tool was about NITUs, which a decision issues."""
    con = _abandonments(tmp_path)
    text = count(con, filing_type="NITU")
    assert "No filing type the Board uses matches 'NITU'" in text
    assert "is not a filing type" in text
    con.close()


def test_without_a_type_the_boards_vocabulary_is_listed(tmp_path):
    con = _abandonments(tmp_path)
    text = count(con, prefix="AB")
    assert "The Board's filing types in AB proceedings" in text
    assert "- Consummation Notice: 1" in text and "Motion" not in text  # FD's, not AB's
    con.close()


def test_a_bad_argument_is_answered_not_raised(tmp_path):
    con = _abandonments(tmp_path)
    assert "must be a date written YYYY-MM-DD" in count(con, filed_from="June 2021")
    assert "must be a real day" in count(con, filed_to="2026-02-30")
    assert "nothing can fall between" in count(con, filed_from="2024-01-01", filed_to="2023-01-01")
    assert "holds no docket prefix 'ZZ'" in count(con, prefix="zz")
    assert "holds no filings the Board typed" in count(con, filing_type="motion", prefix="AB")
    con.close()


def test_unfinished_months_inside_the_range_are_named_in_the_count(tmp_path, monkeypatch):
    """A count is only as complete as the months under it; the ones outside the range say
    nothing about it and are left out."""
    from docketyard.store import coverage

    monkeypatch.setattr(
        coverage, "filings_incomplete", lambda con: ("2019-03", "2019-04", "2025-07")
    )
    con = _abandonments(tmp_path)
    text = count(con, filing_type="Consummation Notice", filed_to="2021-12-31")
    assert "has not finished for filings, inside the range counted" in text
    assert "2019-03 to 2019-04" in text and "2025-07" not in text
    con.close()


def test_a_month_no_wave_has_begun_is_unfinished_not_silently_complete(tmp_path):
    """`_incomplete` reads the ledger, so a month no slice names was not in its list at all,
    and a count over it read as complete (code review, 2026-09-16)."""
    from docketyard.capture.stb import FILINGS
    from docketyard.store import coverage

    con = db.connect(build_store(tmp_path))
    for month in ("2019-01", "2019-03"):
        con.execute(
            "INSERT INTO walk_slice (slice_key, table_action, criteria, status, rows, captures,"
            " completed_at) VALUES (?, ?, '[]', 'done', 0, 1, '2026-09-01T00:00:00+00:00')",
            (f"{FILINGS}:{month}", FILINGS),
        )
    con.commit()
    months = coverage.filings_incomplete(con)
    assert "2019-02" in months and "2019-04" in months  # between walked months, and after
    assert "2019-01" not in months and "2019-03" not in months and "2018-12" not in months
    text = count(con, filing_type="motion", filed_from="2019-01-01", filed_to="2019-12-31")
    assert "2019-02, 2019-04 to 2019-12" in text
    text = count(con, filing_type="motion")
    assert "walk of filings begins at 2019-01" in text
    assert "begins at" not in count(con, filing_type="motion", filed_from="2020-01-01")
    con.close()


def test_a_month_the_watch_left_unasked_after_an_outage_is_unfinished(tmp_path):
    """A month after the watch began has no slice — waves walk backward from where it began —
    so an outage longer than the re-ask window left days no one asked for, and the count
    over them read as complete (the high review pass, 2026-09-16)."""
    from datetime import timedelta

    from docketyard.capture.stb import FILINGS
    from docketyard.store import coverage

    con = db.connect(build_store(tmp_path))
    start = coverage._watch_starts(con.execute, (FILINGS,))[FILINGS]
    month = lambda d: d.strftime("%Y-%m")  # noqa: E731
    later = start + timedelta(days=150)
    assert coverage.filings_incomplete(con, today=later) == (
        (month(start),) if start.day > 1 else ()
    )  # watched every day since, no slice: finished; its first month only from `start`
    lo, hi = start + timedelta(days=45), start + timedelta(days=75)
    con.execute(
        "INSERT INTO coverage_gap (started_at, ended_at, failure) VALUES (?, ?, 'captures')",
        (f"{lo.isoformat()}T00:00", f"{hi.isoformat()}T00:00"),
    )
    con.commit()
    months = coverage.filings_incomplete(con, today=later)
    assert month(lo) in months and month(start + timedelta(days=120)) not in months
    con.close()


def test_a_decision_is_handed_over_with_its_body_and_summary_as_printed(client):
    """`[decision] 53210 — Decision` told an assistant nothing it could say; the JSON twin and
    the page carried the summary all along (the independent graders, 2026-09-16)."""
    text = call(client, "get_docket_sheet", {"docket": "FD 36873"})["content"][0]["text"]
    line = next(x for x in text.splitlines() if "[decision] 53210" in x)
    assert 'the Board\'s summary, as printed: "ORDERED REPLIES DUE"' in line
    # and a search row says why a decision matched, in the Board's words, marked
    text = call(client, "search_the_record", {"query": "replies"})["content"][0]["text"]
    line = next(x for x in text.splitlines() if x.startswith("[decision]"))
    assert 'matched: "ORDERED «REPLIES» DUE"' in line  # the Board's words, not our spellings
    assert "\x02" not in text and "\x03" not in text
    # a search by number matches only this record's own spellings: nothing quoted as matched
    text = call(client, "search_the_record", {"query": "36873"})["content"][0]["text"]
    assert "matched:" not in text, text


def test_the_wording_an_assistant_repeats_says_what_is_true(client, tmp_path):
    """Found by the independent graders, 2026-09-16: `1 filings`; `last` meaning the last
    filing; "raise `limit`" at the cap; a comment miss with no hedge."""
    text = call(client, "search_the_record", {"query": "FD 36873"})["content"][0]["text"]
    assert "1 filings" not in text
    text = call(client, "search_the_record", {"query": "control"})["content"][0]["text"]
    assert "2 filings, last filed 2026-08-25" in text  # the last FILING's date, said so
    text = call(client, "get_environmental_comment", {"number": "EI-00000"})["content"][0]["text"]
    assert "may exist at the Board and not here" in text
    out = mcp._docket(_many_entries(tmp_path), {"docket": "FD 36873", "limit": 100}, "h")
    assert "Raise `limit`" not in out and "at most 100; the rest are on the sheet" in out


def _many_entries(tmp_path):
    con = db.connect(build_store(tmp_path / "many"))
    (event,) = con.execute("SELECT MIN(observed_in_event) FROM filing").fetchone()
    (docket_id,) = con.execute(
        "SELECT docket_id FROM docket WHERE raw_docket = 'FD_36873'"
    ).fetchone()
    con.executemany(
        "INSERT INTO filing (docket_id, stb_filing_id, filing_type, filed_date, observed_in_event)"
        " VALUES (?, ?, 'Letter', '2026-01-01', ?)",
        [(docket_id, str(900000 + i), event) for i in range(120)],
    )
    con.commit()
    return con
