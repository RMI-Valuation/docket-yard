"""Check the OCR ground truth against its own conventions (docs/research/ocr-benchmark).

The rules a transcription must keep are few, and every one of them exists because a draft
broke it: real tabs inside a `[table]` block, a square grid per block, no completed `[cut]`
line, brackets that close. Run before a scoring pass, and after any re-draft.

    python check_ground_truth.py docs/research/ocr-benchmark/ground-truth
"""

import re
import sys
from pathlib import Path

BLOCKS = {"[table]": "[end table]", "[adjacent page]": "[end adjacent page]"}
# A page prints bracketed text of its own — the Federal Register sets its docket line as
# "[STB Finance Docket No. 33700]" — so only a line whose first word is one of ours is
# judged as a marker; anything else in brackets is what the page says.
VOCAB = (
    "illegible",
    "cut",
    "stamp",
    "handwritten",
    "signature",
    "seal",
    "logo",
    "struck",
    "graphic",
    "blank",
    "rotated",
    "table",
    "end",
    "adjacent",
)
KNOWN = re.compile(
    r"^\[(illegible(: .+)?|cut|stamp[^:]*: .+|handwritten( page|: .+)?|signature(: .+)?"
    r"|seal(: .+)?|logo: .+|struck through: .+|graphic( page|: .+)|blank page|rotated page"
    r"|table|end table|adjacent page|end adjacent page)\]$"
)


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[str] = []

    if "\\t" in text:
        out.append("writes the two characters \\t; cells are separated by a real tab")

    for opener, closer in BLOCKS.items():
        if lines.count(opener) != lines.count(closer):
            out.append(f"{lines.count(opener)} {opener} against {lines.count(closer)} {closer}")

    # a line that opens with one of our keywords must be a well-formed marker
    for n, line in enumerate(lines, 1):
        s = line.strip()
        if not (s.startswith("[") and s.endswith("]")):
            continue
        first = s[1:].split(":")[0].split()[0].lower() if len(s) > 2 else ""
        if first in VOCAB and not KNOWN.match(s):
            out.append(f"line {n}: malformed marker {s[:60]}")

    # a table block is a square grid of tab-separated cells
    inside, start, widths = False, 0, []
    for n, line in enumerate(lines, 1):
        if line.strip() == "[table]":
            inside, start, widths = True, n, []
        elif line.strip() == "[end table]":
            if inside and len(set(widths)) > 1:
                out.append(f"table at line {start}: rows of {sorted(set(widths))} cells")
            if inside and not widths:
                out.append(f"table at line {start}: no rows")
            inside = False
        elif inside and line.strip():
            widths.append(line.count("\t") + 1)

    # a cut line ends the transcription of that line: nothing may follow it
    for n, line in enumerate(lines, 1):
        if "[cut]" in line and not line.rstrip().endswith("[cut]"):
            out.append(f"line {n}: text after [cut]")

    # tabs outside a table block are cells with no grid
    inside = False
    for n, line in enumerate(lines, 1):
        if line.strip() == "[table]":
            inside = True
        elif line.strip() == "[end table]":
            inside = False
        elif "\t" in line and not inside:
            out.append(f"line {n}: tab outside a [table] block")
    return out


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    files = sorted(root.glob("*.txt"))
    bad = 0
    for f in files:
        problems = check(f)
        if problems:
            bad += 1
            print(f"{f.name}")
            for p in problems:
                print(f"    {p}")
    print(f"\n{len(files)} transcriptions, {bad} with a problem")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
