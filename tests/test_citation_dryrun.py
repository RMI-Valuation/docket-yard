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
