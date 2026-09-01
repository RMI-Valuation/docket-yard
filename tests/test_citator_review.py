"""Migration 0015 and `docketyard.citator.review` — the queue, and the gate it feeds.

The gate is the point: until 0015 the exposed class published itself, which is the one thing
ADR 0017's exposure test was defined to prevent.
"""

import sqlite3

import pytest

from docketyard.citator import keys, load, methods, project, resolve, review
from docketyard.store import db

STAMP = "2026-09-01T00:00:00+00:00"
SHA = "d" * 64


def _store(tmp_path):
    """`AB 124` and `AB 1242` both held: the fusion shape the exposure test exists for —
    `AB 124` followed by footnote `2`, read as a different, real proceeding."""
    con = db.connect(tmp_path / "s.sqlite")
    for did, prefix, seq in ((1, "FD", 36873), (2, "AB", 124), (3, "AB", 1242), (4, "EP", 445)):
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
    return con


def _scored(con):
    for stage in ("citation", "citation_resolution", "projection"):
        methods.measure(
            con,
            measured_target=stage,
            cls="docket",
            extractor_version="v1",
            score_file="test",
            benchmark_date="2026-09-01",
            recall=0.911,
            precision=0.981,
        )
    methods.declare(con, "v1")
    return methods.stamp(con)


def _reviewer(con, revoked=None):
    return con.execute(
        "INSERT INTO reviewer (email_hash, email_enc, credit_name, granted_at, granted_note,"
        " revoked_at) VALUES ('h', 'e', 'C. Rex', ?, 'reviewer zero', ?)",
        (STAMP, revoked),
    ).lastrowid


def _load(con, stamps, *findings):
    return load.load_document(
        con,
        {
            "document_sha256": SHA,
            "method": methods.EXTRACTOR,
            "method_version": "v1",
            "reading_channel": methods.CHANNEL_TEXT,
            "pages_read": 9,
            "findings": list(findings),
        },
        keys.registry(con),
        stamps,
    )


EXPOSED = {"page": 4, "target": "AB 1242", "quoted": "See AB 1242, slip op. at 3."}
CLEAN = {"page": 5, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."}


def test_an_exposed_edge_does_not_reach_a_page_until_a_human_has_answered(tmp_path):
    """ADR 0017 D2: the exposed class "goes to review; everything else ships unreviewed".
    Before migration 0015 there was no queue, so it shipped unreviewed too — resolving
    confidently to a real but WRONG proceeding, indistinguishable from a clean edge."""
    con = _store(tmp_path)
    stamps = _scored(con)
    result = _load(con, stamps, EXPOSED, CLEAN)
    assert result.exposed == 1

    shown = {r[2] for r in project.projected(con)}
    assert shown == {"EP 445"}  # the clean edge publishes; the exposed one waits

    queue = review.pending(con, "citation_exposed")
    assert [q["target_key"] for q in queue] == ["AB 1242"]
    assert "slip op" in queue[0]["quoted_passage"]  # the evidence beside the question

    review.decide(
        con,
        reviewer_id=_reviewer(con),
        queue="citation_exposed",
        item=queue[0],
        decision="accepted",
        note="checked the page: the footnote is separate",
    )
    assert {r[2] for r in project.projected(con)} == {"AB 1242", "EP 445"}
    assert review.pending(con, "citation_exposed") == []  # the answer clears the item


def test_a_correction_moves_the_edge_and_the_old_answer_is_superseded(tmp_path):
    """A reviewer who finds the fusion real names the docket it should have been."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, EXPOSED)
    item = review.pending(con, "citation_exposed")[0]
    review.decide(
        con,
        reviewer_id=_reviewer(con),
        queue="citation_exposed",
        item=item,
        decision="corrected",
        note="footnote 2 fused onto AB 124",
        cited_docket_id=2,
    )
    rows = project.projected(con)
    assert len(rows) == 1 and rows[0][3] == 2  # cited_docket_id is now AB 124
    live = con.execute(
        "SELECT confidence_state FROM citation_resolution WHERE superseded_by IS NULL"
    ).fetchall()
    assert live == [("human",)]  # one live answer, and it is the human's
    assert con.execute("SELECT COUNT(*) FROM citation_resolution").fetchone()[0] == 2


def test_a_rejection_stops_the_edge_and_says_so_in_a_row(tmp_path):
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, EXPOSED)
    item = review.pending(con, "citation_exposed")[0]
    review.decide(
        con,
        reviewer_id=_reviewer(con),
        queue="citation_exposed",
        item=item,
        decision="rejected",
        note="not a citation at all",
    )
    assert project.projected(con) == []
    assert con.execute(
        "SELECT outcome FROM citation_resolution WHERE superseded_by IS NULL"
    ).fetchone() == ("unresolved",)


def test_an_escalation_is_the_only_decision_that_produces_no_assertion(tmp_path):
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, EXPOSED)
    item = review.pending(con, "citation_exposed")[0]
    review.decide(
        con,
        reviewer_id=_reviewer(con),
        queue="citation_exposed",
        item=item,
        decision="escalated",
        note="ask the Board's records staff",
    )
    row = con.execute("SELECT decision, produced_table, produced_key FROM review_action").fetchone()
    assert row == ("escalated", None, None)
    # it decided nothing, so the edge is still gated and the item is still owed
    assert project.projected(con) == []
    assert len(review.pending(con, "citation_exposed")) == 1


def test_the_credit_name_is_the_authoritative_join_and_is_never_optional(tmp_path):
    """schema-draft.md § 7: "who reviewed this?" reads produced_table + produced_key, and
    there is no backward pointer, because two pointers can disagree and one cannot."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, EXPOSED)
    item = review.pending(con, "citation_exposed")[0]
    assert review.credit(con, item["target_key_rendered"]) is None
    review.decide(
        con,
        reviewer_id=_reviewer(con),
        queue="citation_exposed",
        item=item,
        decision="accepted",
        note="fine",
    )
    assert review.credit(con, item["target_key_rendered"]) == "C. Rex"
    # ADR 0016, the operator's amendment on acceptance: there is no anonymous review
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO reviewer (email_hash, email_enc, credit_name, granted_at,"
            " granted_note) VALUES ('h2', 'e2', '', ?, 'n')",
            (STAMP,),
        )


def test_a_withdrawn_grant_ends_new_actions_and_leaves_past_rows_attributed(tmp_path):
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, EXPOSED)
    item = review.pending(con, "citation_exposed")[0]
    who = _reviewer(con)
    review.decide(
        con, reviewer_id=who, queue="citation_exposed", item=item, decision="accepted", note="ok"
    )
    con.execute("UPDATE reviewer SET revoked_at = ? WHERE reviewer_id = ?", (STAMP, who))
    assert review.credit(con, item["target_key_rendered"]) == "C. Rex"  # the past row stands
    _load(con, stamps, CLEAN)
    with pytest.raises(ValueError, match="revoked"):
        review.decide(
            con,
            reviewer_id=who,
            queue="citation_exposed",
            item=item,
            decision="rejected",
            note="no",
        )


def test_a_later_review_supersedes_and_does_not_sit_beside(tmp_path):
    """ADR 0016: append-only, a later review supersedes. One live action per (queue,
    target), which the partial unique index enforces and this exercises."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, EXPOSED)
    who = _reviewer(con)
    item = review.pending(con, "citation_exposed")[0]
    first = review.decide(
        con, reviewer_id=who, queue="citation_exposed", item=item, decision="accepted", note="a"
    )
    second = review.decide(
        con,
        reviewer_id=who,
        queue="citation_exposed",
        item=item,
        decision="corrected",
        note="b",
        cited_docket_id=2,
    )
    live = con.execute(
        "SELECT action_id, decision FROM review_action WHERE superseded_by IS NULL"
    ).fetchall()
    assert live == [(second, "corrected")]
    assert con.execute(
        "SELECT superseded_by FROM review_action WHERE action_id = ?", (first,)
    ).fetchone() == (second,)


def test_the_unresolved_queue_skips_a_number_outside_the_held_record(tmp_path):
    """ADR 0017 D5: an ICC-era number is EXPECTED to fail and is not queued. A queue full of
    expected failures trains a reviewer to skim past the real ones — the same argument the
    exposure test's own narrowing rests on."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(
        con,
        stamps,
        {"page": 6, "target": "AB 900", "quoted": "AB 900, slip op. at 2"},  # inside AB's range
        {"page": 7, "target": "AB 3", "quoted": "AB 3, an ICC-era number"},  # below it
    )
    queued = [q["target_key"] for q in review.pending(con, "citation_unresolved")]
    assert queued == ["AB 900"]


def test_a_human_answer_carries_a_human_reading_or_it_projects_nothing(tmp_path):
    """The projection's reading join is INNER and channel-matched. A review that wrote only
    a resolution would win the ranking and then show nothing — silently turning an accepted
    edge into no edge at all."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, EXPOSED)
    item = review.pending(con, "citation_exposed")[0]
    review.decide(
        con,
        reviewer_id=_reviewer(con),
        queue="citation_exposed",
        item=item,
        decision="accepted",
        note="ok",
    )
    channels = {r[0] for r in con.execute("SELECT reading_channel FROM citation_reading")}
    assert channels == {"text-layer", "human"}
    assert len(project.projected(con)) == 1


def test_the_queue_is_a_query_and_notices_the_registry_growing(tmp_path):
    """A stored queue would hold yesterday's answer. Waves 2-3 are still adding dockets, so a
    target that could not resolve last week resolves this week and leaves the queue."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, {"page": 6, "target": "AB 900", "quoted": "AB 900, slip op. at 2"})
    assert len(review.pending(con, "citation_unresolved")) == 1
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence)"
        " VALUES (9, 'AB_900', 'AB', 900)"
    )
    _load(con, stamps, {"page": 6, "target": "AB 900", "quoted": "AB 900, slip op. at 2"})
    assert review.pending(con, "citation_unresolved") == []  # it resolved; nobody was told
    assert len(project.projected(con)) == 1


def test_rendering_a_queue_writes_nothing(tmp_path):
    """ADR 0011's promise covers reviewers: the surfaces log the decision and nothing else —
    no page views, no timing beyond the action's own timestamp."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, EXPOSED)
    before = con.total_changes
    for queue in ("citation_exposed", "citation_repaired", "citation_unresolved"):
        review.pending(con, queue)
    assert con.total_changes == before


# --- what the schema-critic's pass on 0015 found ----------------------------------------


def test_a_rejected_edge_is_not_republished_by_the_next_extraction_pass(tmp_path):
    """THE DEFECT THIS TEST EXISTS FOR, reproduced 2026-09-01 before it was fixed. A
    rejection is written `outcome = 'unresolved'`, and the candidate filter drops that
    outcome BEFORE the rank — which ADR 0018 D7 requires, or every rule-2 repair is
    unreachable. So a human "no" did not lose the ranking, it ABSTAINED from it: the next
    pass wrote a fresh machine `resolved` row that won by default, while the exposure gate
    read the live human row and called the edge cleared. The rejected edge republished at
    the machine's answer, with the queue reporting it done."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, EXPOSED)
    item = review.pending(con, "citation_exposed")[0]
    review.decide(
        con,
        reviewer_id=_reviewer(con),
        queue="citation_exposed",
        item=item,
        decision="rejected",
        note="not a citation at all",
    )
    assert project.projected(con) == []
    _load(con, stamps, EXPOSED)  # the next backfill wave over the same document
    assert project.projected(con) == []  # a review undone by the next wave is not a review


def test_an_answer_in_one_queue_does_not_clear_another(tmp_path):
    """A key can sit in two queues, and `review_action.queue` records WHICH QUESTION was
    asked. Clearing on "any live human resolution" would let an unresolved answer authorise
    publication of a fusion nobody was ever shown."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, EXPOSED)
    item = review.pending(con, "citation_exposed")[0]
    # answer it on a DIFFERENT queue
    review.decide(
        con,
        reviewer_id=_reviewer(con),
        queue="citation_repaired",
        item=item,
        decision="accepted",
        note="answered the wrong question",
    )
    assert len(review.pending(con, "citation_exposed")) == 1  # still owed the fusion question


def test_accepting_on_the_unresolved_queue_keeps_it_unresolved(tmp_path):
    """`accepted` means "the stored answer is right", and on the unresolved queue the stored
    answer is `unresolved`. Mapping it to `resolved` wrote a NULL docket and tripped
    migration 0014's outcome CHECK mid-transaction, surfacing as a traceback."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, {"page": 6, "target": "AB 900", "quoted": "AB 900, slip op. at 2"})
    item = review.pending(con, "citation_unresolved")[0]
    review.decide(
        con,
        reviewer_id=_reviewer(con),
        queue="citation_unresolved",
        item=item,
        decision="accepted",
        note="the Board really has no such docket",
    )
    live = con.execute(
        "SELECT outcome, cited_docket_id FROM citation_resolution"
        " WHERE confidence_state = 'human' AND superseded_by IS NULL"
    ).fetchall()
    assert live == [("unresolved", None)]
    assert review.pending(con, "citation_unresolved") == []


def test_a_repair_is_owed_a_human_and_is_not_also_called_unresolved(tmp_path):
    """ADR 0018 D7 provides for live resolutions accumulating per (method, version, channel),
    because rule 1 writes a row WHEN IT FAILS and rule 2 writes a separate one — so "a live
    row with outcome unresolved" would not be "the row that currently decides". TODAY that
    cannot arise: `resolve.resolve` returns ONE answer per key. The queue carries the guard
    anyway, because a rule 3 brings the case back and a stale row claiming the registry
    cannot resolve a projecting edge says nothing about itself."""
    con = _store(tmp_path)
    stamps = _scored(con)
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence) VALUES (9, 'AB_9000',"
        " 'AB', 9000)"
    )
    # `AB 90001` fails rule 1, and rule 2 repairs it to `AB 9000`
    _load(con, stamps, {"page": 6, "target": "AB 90001", "quoted": "AB 90001, slip op. at 2"})
    live = con.execute(
        "SELECT outcome, method_version FROM citation_resolution WHERE superseded_by IS NULL"
    ).fetchall()
    assert live == [("repaired", resolve.RULE_2)]
    assert review.pending(con, "citation_unresolved") == []
    assert len(review.pending(con, "citation_repaired")) == 1  # the repair is owed a human
    # and the guard holds the day a second rule writes a stale unresolved row beside it
    con.execute(
        "INSERT INTO citation_resolution (citing_document, page, target_kind, target_key,"
        " method, method_version, reading_channel, outcome, asserted_at, confidence,"
        " confidence_state) SELECT citing_document, page, target_kind, target_key,"
        " 'registry-match', 'rule-3', reading_channel, 'unresolved', asserted_at, 0.9,"
        " 'unmeasured' FROM citation_resolution WHERE superseded_by IS NULL"
    )
    assert review.pending(con, "citation_unresolved") == []


def test_the_human_rows_carry_adr_0007s_block(tmp_path):
    """schema-draft.md § 7: "the produced row's ADR 0007 block is method='human', its
    source_location keeps ADR 0007's meaning". ADR 0016 wants the reviewer's id as method
    detail, and there is no column for it."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _load(con, stamps, EXPOSED)
    item = review.pending(con, "citation_exposed")[0]
    who = _reviewer(con)
    review.decide(
        con, reviewer_id=who, queue="citation_exposed", item=item, decision="accepted", note="ok"
    )
    doc, loc = con.execute(
        "SELECT asserted_from_document, source_location FROM citation_resolution"
        " WHERE confidence_state = 'human'"
    ).fetchone()
    assert doc == SHA and f'"reviewer_id": {who}' in loc and '"queue"' in loc
    # and the human reading shows what the page PRINTED, not the normalised key
    raw = con.execute(
        "SELECT cited_raw FROM citation_reading WHERE reading_channel = 'human'"
    ).fetchone()[0]
    assert raw == "AB 1242" and raw == item["cited_raw"]


def test_the_projection_rule_names_the_gate(tmp_path):
    """ADR 0018 D8: the string names what the projection is a PRODUCT of. The gate is a
    fourth thing, and without bumping it a measurement from before and one from after would
    carry the same version with different numbers — and collide on one benchmark_date."""
    assert "gate=exposed@" in methods.PROJECTION_RULE
    con = _store(tmp_path)
    _scored(con)
    stored = con.execute(
        "SELECT projection_rule_version FROM class_measurement WHERE measured_target = 'projection'"
    ).fetchone()[0]
    assert stored == methods.PROJECTION_RULE


def test_a_grant_is_by_hand_and_a_re_grant_keeps_the_id(tmp_path):
    """ADR 0016: no self-service, and the id is permanent because provenance points at it for
    ever. A withdrawal ends new actions; a re-grant clears it without minting a second id."""
    from docketyard.alerts import vault

    vault.configure(vault.Vault.from_key(vault.Vault.new_key()))
    con = _store(tmp_path)
    who = review.grant(con, "Reviewer@Example.COM ", "C. Rex", "reviewer zero")
    assert con.execute("SELECT credit_name FROM reviewer").fetchone() == ("C. Rex",)
    # the address is sealed, never stored in the clear
    row = con.execute("SELECT email_hash, email_enc FROM reviewer").fetchone()
    assert "reviewer@example.com" not in row[0] and "reviewer@example.com" not in row[1]
    assert vault.current().open(row[1]) == "reviewer@example.com"

    review.revoke(con, who)
    again = review.grant(con, "reviewer@example.com", "C. Rex", "back again")
    assert again == who  # the same id, and the withdrawal is cleared
    assert con.execute("SELECT revoked_at FROM reviewer").fetchone() == (None,)
    with pytest.raises(ValueError, match="credit name"):
        review.grant(con, "b@example.com", "   ", "no name")
