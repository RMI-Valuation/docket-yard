"""The resolver's rules carry the served-date anchor's version (Codex on PR #32, 2026-09-14; the
operator's decision): a resolution written under an older rule version is retired onto the
current one, and a card measured on another rule is refused."""

import pytest

from docketyard.citator import methods, resolve
from tests.test_citator_pipeline import SHA, STAMP, _scored, _store
from tests.test_citator_retraction import _load, _walked


def test_an_older_rule_versions_resolution_is_retired_onto_the_current_one(tmp_path):
    con = _store(tmp_path)
    con.execute(
        "INSERT INTO decision_record (decision_pk, docket_id, stb_decision_id, service_date,"
        " observed_in_event) VALUES (2, 3, '77777', '2021-03-12', 1)"
    )
    con.execute("INSERT OR IGNORE INTO decision_work VALUES ('77777')")
    stamps = _scored(con)
    bare = {"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."}
    _load(con, _walked(bare), stamps)
    # as the rule before the bump wrote it, and a person's answer on the same key
    con.execute(
        "UPDATE citation_resolution SET method_version = 'rule-1' WHERE target_key = 'EP 445'"
    )
    human = con.execute(
        "INSERT INTO citation_resolution (citing_document, page, target_kind, target_key, method,"
        " method_version, reading_channel, outcome, asserted_at, confidence, confidence_state)"
        " VALUES (?, 4, 'stb', 'EP 445', 'human', 'v1', 'human', 'unresolved', ?, 1.0, 'human')",
        (SHA, STAMP),
    ).lastrowid

    served = {"page": 4, "target": "EP 445", "quoted": "See EP 445 (STB served Mar. 12, 2021)."}
    result = _load(con, _walked(served), stamps)
    assert (result.work_gained, result.work_lost) == (1, 0), "the prior is read at any version"

    live = con.execute(
        "SELECT resolution_id, method_version, cited_decision_id FROM citation_resolution"
        " WHERE target_key = 'EP 445' AND method = ? AND superseded_by IS NULL",
        (resolve.RESOLVER,),
    ).fetchall()
    assert [(v, d) for _, v, d in live] == [(resolve.RULE_1, "77777")], "one live answer"
    assert con.execute(
        "SELECT superseded_by FROM citation_resolution WHERE method_version = 'rule-1'"
    ).fetchone() == (live[0][0],), "the older row points at the one that replaced it"
    assert con.execute(
        "SELECT superseded_by FROM citation_resolution WHERE resolution_id = ?", (human,)
    ).fetchone() == (None,), "a person's answer is never retired by a machine pass"


def test_a_card_measured_on_another_rule_version_is_refused(tmp_path, monkeypatch):
    """`measure` writes the rule onto every resolution and projection card; a card declared
    under the rule before a bump must not stamp the new rule's rows (schema-critic)."""
    con = _store(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(resolve, "RULE_1", "rule-1")
        _scored(con)
    with pytest.raises(methods.Unscored, match="measured on resolver 'rule-1'"):
        methods.stamp(con)
