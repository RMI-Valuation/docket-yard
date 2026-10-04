"""The resolver's rules carry the served-date anchor's version (Codex on PR #32, 2026-09-14; the
operator's decision): a resolution written under an older rule version is retired onto the
current one, and a card measured on another rule is refused."""

import pytest

from docketyard.citator import judge, methods, resolve
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


# The `family` CTE as it stood when `methods.CLOSURE_VERSION` was last set, comments stripped
# and whitespace collapsed. A change to the closure fails here until both move together.
CLOSURE_FINGERPRINT = (
    "cite.py@2026-09-01",
    "ad47141e216ecdb7a7a0c62fabbc65022ce9df1a2fe9fccb86fe8e4b9bd58d59",
)


def test_the_family_closure_cannot_change_under_its_old_version():
    """`methods.PROJECTION_RULE` hardcoded `closure=cite.py@2026-09-01`, a date somebody had to
    remember to edit (code review, 2026-09-01). It is a constant now, and the closure it names —
    `project.py`'s `family` CTE, the one implementation — is fingerprinted against it, so a new
    closure under the old name fails a test instead of reaching a stored measurement."""
    import hashlib
    import re

    from docketyard.citator import project

    cte = re.search(r"^family AS \(.*?^\)", project._TERMS, re.S | re.M)
    assert cte, "the `family` CTE moved; point this test at it"
    body = " ".join(re.sub(r"--[^\n]*", "", cte.group(0)).split())
    digest = hashlib.sha256(body.encode()).hexdigest()
    assert (methods.CLOSURE_VERSION, digest) == CLOSURE_FINGERPRINT, (
        "the family closure changed: bump methods.CLOSURE_VERSION (it moves PROJECTION_RULE,"
        " ADR 0018 D8) and re-pin CLOSURE_FINGERPRINT with both"
    )
    # and the rule string is byte-identical to the one every stored measurement carries
    assert f";closure={methods.CLOSURE_VERSION};" in methods.PROJECTION_RULE
    assert methods.PROJECTION_RULE == (
        f"span={judge.SPAN_VERSION};closure=cite.py@2026-09-01;rank={methods.RANK_VERSION}"
        f";gate=exposed@{resolve.EXPOSURE_VERSION}"
    )
