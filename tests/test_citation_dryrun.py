"""`tools/rmi-ai-machine/citation_dryrun.py`, the tool that builds the citator's score card:
what it records about itself beside the figures (`docs/deferred.md`, found 2026-09-01)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "rmi-ai-machine"))

import citation_dryrun  # noqa: E402


def test_a_run_records_the_registry_it_was_made_against(tmp_path):
    """`kind` is a function of `own`, which comes from the registry: a run that does not say
    which registry it read cannot be re-derived, which is ADR 0016's complaint about the old
    figures. And the record must not be a `.json`, or every reader of the run directory
    takes it for a decision."""
    path = citation_dryrun.record_registry(tmp_path, Path("data/prod-copy.sqlite"), 30123)
    assert path.read_text(encoding="utf-8").splitlines() == [
        f"registry {Path('data/prod-copy.sqlite')}",
        "dockets 30123",
    ]
    assert not list(tmp_path.glob("*.json"))


def test_an_orphan_decision_is_returned_and_said_beside_the_numbers(tmp_path):
    """A decision with no docket in the registry is not run, and its truth targets stay in
    the denominator, so every figure is lower than the rule's. It used to be a `print` fifty
    lines above them; now the caller gets the orphans and prints them where the numbers are,
    with how many truth targets they hold."""
    text = tmp_path / "text"
    text.mkdir()
    (text / "heavy-99999.txt").write_text("===== page 1 =====\nFD 36873\n", encoding="utf-8")
    run, orphans = citation_dryrun.run_the_finder(text, tmp_path / "run", own={})
    assert orphans == ["99999"]
    assert not list(run.glob("*.json")), "an orphan is not run with an empty `own`"

    note = citation_dryrun.orphan_note(orphans, {"99999": {"FD 36873", "EP 445"}})
    assert "1 decisions" in note and "2 truth targets" in note and "99999" in note
    assert citation_dryrun.orphan_note([], {"99999": {"FD 36873"}}) == ""


def test_only_a_key_never_emitted_as_a_citation_can_explain_a_projected_caption(tmp_path):
    """The agreement check's fourth legitimate difference (ADR 0017 D4): an in-family caption
    whose line names a document projects in SQL while the Python chain counts citations only.
    A key that is a citation on ANY page is already in the Python chain's sets, so it is not
    one of these — only a key the run emitted as nothing but captions."""
    import json

    def finding(key, kind):
        return {"key": key, "kind": kind, "target": key}

    doc = {
        "decision_id": "52526",
        "pages": [
            {"page": 1, "findings": [finding("FD 36873", "caption"), finding("EP 445", "caption")]},
            {"page": 2, "findings": [finding("EP 445", "citation")]},
        ],
    }
    (tmp_path / "52526.json").write_text(json.dumps(doc), encoding="utf-8")
    (tmp_path / citation_dryrun.REGISTRY_FILE).write_text("registry x\n", encoding="utf-8")
    assert citation_dryrun.caption_only(tmp_path) == {("52526", "FD 36873")}
