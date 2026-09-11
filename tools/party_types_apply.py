"""Party types: apply the operator's Copy-findings block to a sheet.

The check page hands back one tab-separated block: `party_id, type, first, note` (the first
sheet's page, before 2026-09-10, handed back `party_id, type, note`, with no first pick).
This writes it into the sheet's `labels.csv`: `type` is the final pick, `first` the pick made
before the draft was shown on a blind sheet (the measurement the gate reads), `note` the
operator's note. A party the block does not name is left as it stands. A party the sheet does
not hold, or a type the vocabulary does not, is REFUSED, never appended or guessed at — the
block is the operator's words, and a row they did not write must not appear to be theirs.

    python tools/party_types_apply.py --sheet docs/research/party-types/held-out/labels.csv \\
        --verdicts data/heldout-verdicts.tsv
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from party_types_check_page import TYPES  # noqa: E402 — the page's buttons are the vocabulary


def read_block(path: Path) -> dict[str, tuple[str, str, str]]:
    """party_id -> (type, first, note). Three columns is the older page's block."""
    out: dict[str, tuple[str, str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("party_id"):
            continue
        cells = line.split("\t")
        if len(cells) == 3:
            pid, judged, note = cells
            first = judged
        elif len(cells) == 4:
            pid, judged, first, note = cells
        else:
            raise SystemExit(f"refused: {len(cells)} columns in {line[:60]!r}")
        out[pid.strip()] = (judged.strip(), (first or judged).strip(), note.strip())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True, type=Path)
    ap.add_argument("--verdicts", required=True, type=Path)
    args = ap.parse_args()
    with args.sheet.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    block = read_block(args.verdicts)
    held = {r["party_id"] for r in rows}
    strangers = sorted(set(block) - held)
    unknown = sorted({t for v in block.values() for t in v[:2]} - set(TYPES))
    if strangers or unknown:
        print(f"refused: {len(strangers)} parties not on this sheet {strangers[:5]},"
              f" types not in the vocabulary {unknown}")  # fmt: skip
        return 1
    if "first" not in fields:
        fields.insert(fields.index("type") + 1, "first")
    changed = 0
    for r in rows:
        if r["party_id"] in block:
            judged, first, note = block[r["party_id"]]
            r["type"], r["first"] = judged, first
            if note:
                r["note"] = note
            changed += first != judged
        r.setdefault("first", "")
    with args.sheet.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    blank = sum(1 for r in rows if not r["type"].strip())
    print(
        f"applied {len(block)} of {len(rows)}; {changed} changed after the draft was shown;"
        f" {blank} still unjudged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
