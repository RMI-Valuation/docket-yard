"""The benchmark corpus's file-name convention, read in one place (`docs/deferred.md`
§ Benchmark scorer, 2026-08-30): four tools parsed `<stratum>-<id>.txt` four ways."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "rmi-ai-machine"))

from benchmark_files import decision_id_of  # noqa: E402


def test_the_reader_gives_what_each_of_the_four_old_parses_gave():
    """The shared reader replaced them, so on every name the sampler writes it must answer
    as each did — or a re-scored run would key its decisions differently from the card."""
    for name in ("heavy-52526.txt", "routine-41234.txt", "short-7.txt", "52526.txt"):
        f = Path("data/benchmark/text") / name
        old = {
            f.stem.rsplit("-", 1)[-1],  # benchmark_score, benchmark_run
            re.sub(r"^.*-", "", f.stem),  # benchmark_ocr_text
            f.name.split("-")[-1].removesuffix(".txt"),  # labels_check_page
        }
        assert old == {decision_id_of(f)}, name
    assert decision_id_of(Path("heavy-52526.txt")) == "52526"
