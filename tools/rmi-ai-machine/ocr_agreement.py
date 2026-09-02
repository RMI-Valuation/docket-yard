#!/usr/bin/env python3
"""Does two engines disagreeing predict that either is wrong?

`ocr-plan.md` § The review layer proposes agreement-as-confidence: two engines read every
page, matching readings ship, differing readings are flagged for a human. The whole
two-engine design rests on it — it is why a second reading is worth 187 hours of box time,
why the winner has to be ranked, and why a page's confidence is a comparison rather than an
engine's own number. **It has never been measured**, and it is measurable for free: thirteen
engine runs already exist over the same ninety operator-checked pages.

Two things are reported and a third is deliberately refused.

    the flag rate      what share of pages the two readings differ on, as a CURVE over
                       thresholds — because the pages flagged are the operator's weekly
                       budget, and the budget is about fifty pages a week
    the discrimination whether that disagreement predicts error, as AUC against each page's
                       measured CER — a rank statistic, so it commits to no cut-off
    NOT a threshold    fitting one to the ninety pages it is scored on is how the party-type
                       rules reached 83.3% on their own sheet (docs/party-types.md), and how
                       ocr-benchmark/README.md § Step 4 refused to fit a column-count rule

Run on RMI-AI-MACHINE, where the engine outputs are:

    python3 ocr_agreement.py ~/ocr-bench/runs dots-mocr ppocr > agreement.json

It prints JSON; join it with the per-page `cer` in docs/research/ocr-benchmark/runs/*.json
to get the discrimination half.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "ocr-bench"))
from ocr_score import edit_distance, normalise  # noqa: E402 — the scorer is the reference


def read_run(root: Path, engine: str) -> dict[str, str]:
    """Every page one engine produced, normalised by the benchmark's own normaliser so this
    comparison sits on the same footing as every scored figure."""
    out = {}
    for path in sorted((root / engine).glob("*.txt")):
        out[path.name] = normalise(path.read_text(encoding="utf-8", errors="replace"))
    return out


def distance(a: str, b: str) -> float:
    """Normalised edit distance in [0, 1]. Two empty readings agree perfectly — a blank page
    read as blank by both is the strongest agreement there is, not a division by zero."""
    if not a and not b:
        return 0.0
    return edit_distance(a, b) / max(len(a), len(b))


def main(root: Path, left: str, right: str) -> int:
    a, b = read_run(root, left), read_run(root, right)
    shared = sorted(set(a) & set(b))
    pages = {p: round(distance(a[p], b[p]), 6) for p in shared}
    print(
        json.dumps(
            {
                "left": left,
                "right": right,
                "pages_compared": len(shared),
                "only_in_left": sorted(set(a) - set(b)),
                "only_in_right": sorted(set(b) - set(a)),
                "distance": pages,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), sys.argv[2], sys.argv[3]))
