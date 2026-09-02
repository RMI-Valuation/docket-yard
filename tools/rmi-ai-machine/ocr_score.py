"""Score an OCR engine against the checked ground truth (docs/research/ocr-benchmark).

Everything the operator and I settled while building the ground truth is enforced here, so
that no engine is scored for a choice that is not a reading error:

- **one normaliser, both sides.** Whitespace collapses, a line-final hyphen joins to the
  next line, bracket annotations unwrap to their content. Tesseract preserves the printed
  lines and a vision model reflows into paragraphs; neither is reading better.
- **`[illegible]` spans are excluded** — no reading of them can be called wrong.
- **`[adjacent page]` blocks are excluded** from the page's own error rate, since reading a
  facing page's margin or ignoring it are both sensible — but an engine that emits a
  *completed* form of a `[cut]` line is counted as inventing text, which is the sharpest
  probe in the benchmark.
- **docket numbers and dates are scored on their own**, as sets. A transposed digit in
  "FD 32760" matters more than a hundred misread commas.
- **a graphic page is scored as a set, not a sequence**: labels scattered on a map have no
  reading order.
- **a table is compared cell by cell** inside its `[table]` block, because a grid is
  meaning, not layout preference.
- **false text** — prose asserted on a page that carries only labels, or none at all.

Usage:
    python ocr_score.py --engine tesseract --dir data/ocr/runs/tesseract
where the directory holds one <page>.txt per page image, named as the ground truth is.
"""

import argparse
import json
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

# The repository this file sits in, not a machine. It was an absolute Windows path until
# 2026-09-02, which meant the scorer ran on exactly one box and failed on RMI-AI-MACHINE with
# a FileNotFoundError naming a drive letter — so every run had to be copied back before it
# could be scored. `DY_ROOT` overrides it for a checkout somewhere else.
ROOT = Path(os.environ.get("DY_ROOT") or Path(__file__).resolve().parents[2])
TRUTH = ROOT / "docs/research/ocr-benchmark/ground-truth"
SAMPLE = ROOT / "docs/research/ocr-benchmark/sample.json"

BLOCK = re.compile(r"^\[(table|end table|adjacent page|end adjacent page)\]$", re.M)
MARKER = re.compile(
    r"\[(illegible(?:: [^\]]+)?|cut|stamp[^:\]]*: [^\]]+|handwritten(?: page|: [^\]]+)?"
    r"|signature(?:: [^\]]+)?|seal(?:: [^\]]+)?|logo: [^\]]+|struck through: [^\]]+"
    r"|graphic(?: page|: [^\]]+)|blank page|rotated page)\]"
)
DOCKET = re.compile(r"\b([A-Z]{2,4})[\s.]*(?:Docket\s+)?No?s?\.?\s*([0-9]{1,6})\b")
DOCKET_PLAIN = re.compile(
    r"\b(FD|AB|EP|NOR|MCF|MCC|NOM|ISM|IS|SDM|WB|SO|DOP|STA|WCC|SUB)\s*[-\s]?\s*([0-9]{1,6})\b"
)
SUBNO = re.compile(r"\(?\s*Sub[-\s]?No\.?\s*([0-9]+[A-Z]?)\s*\)?", re.I)
MONTHS = (
    "january february march april may june july august september october november december"
).split()
DATE_LONG = re.compile(
    r"\b("
    + "|".join(m[:3] for m in MONTHS)
    + r")[a-z]*\.?\s+([0-9]{1,2}),?\s+((?:19|20)[0-9]{2})\b",
    re.I,
)
DATE_NUM = re.compile(r"\b([01]?[0-9])/([0-3]?[0-9])/((?:19|20)?[0-9]{2})\b")


# ---------------------------------------------------------------- normalising


def strip_excluded(text: str) -> tuple[str, list[str]]:
    """Remove what may not be scored: [adjacent page] blocks and [illegible] spans.
    Returns the scorable text and the cut lines the block contained."""
    lines, keep, cuts, inside = text.splitlines(), [], [], False
    for line in lines:
        s = line.strip()
        if s == "[adjacent page]":
            inside = True
            continue
        if s == "[end adjacent page]":
            inside = False
            continue
        if inside:
            if "[cut]" in line:
                cuts.append(line.replace("[cut]", "").strip())
            continue
        keep.append(line)
    return "\n".join(keep), cuts


def normalise(text: str) -> str:
    """The one normaliser, applied to ground truth and engine output alike."""
    text = unicodedata.normalize("NFKC", text)
    text = MARKER.sub(
        lambda m: "" if m.group(1).startswith("illegible") else _content(m.group(1)), text
    )
    text = BLOCK.sub(" ", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # a line-final hyphen joins
    text = re.sub(r"[\u2018\u2019]", "'", text)
    text = re.sub(r"[\u201c\u201d]", '"', text)
    text = re.sub(r"[\u2013\u2014]", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _content(marker: str) -> str:
    """A bracket annotation scores as its content: an engine that reads a stamp is neither
    rewarded nor punished for not knowing it was a stamp."""
    if ":" in marker:
        return " " + marker.split(":", 1)[1].strip() + " "
    return " "


# ---------------------------------------------------------------- distances


def edit_distance(a: str, b: str, band: int | None = None) -> int:
    """Levenshtein with a band: the two strings are usually close, so most of the matrix is
    never reached. Falls back to the full computation when the band is exceeded."""
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    if band is None:
        band = max(64, int(0.35 * max(len(a), len(b))))
    n, m = len(a), len(b)
    if abs(n - m) > band:
        band = abs(n - m) + 64
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        lo, hi = max(1, i - band), min(m, i + band)
        if lo > 1:
            cur[lo - 1] = band + 1
        for j in range(lo, hi + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        for j in range(hi + 1, m + 1):
            cur[j] = band + 1
        prev = cur
    return prev[m]


def rate(truth: str, out: str) -> float:
    return 0.0 if not truth else min(1.0, edit_distance(truth, out) / len(truth))


def word_rate(truth: str, out: str) -> float:
    t, o = truth.split(), out.split()
    if not t:
        return 0.0
    return min(1.0, _seq_distance(t, o) / len(t))


def _seq_distance(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[len(b)]


# ---------------------------------------------------------------- what is scored apart


def dockets(text: str) -> Counter:
    found: Counter = Counter()
    for m in DOCKET_PLAIN.finditer(text):
        tail = text[m.end() : m.end() + 24]
        sub = SUBNO.search(tail)
        found[
            f"{m.group(1)} {int(m.group(2))}" + (f" ({sub.group(1).upper()})" if sub else "")
        ] += 1
    return found


def dates(text: str) -> Counter:
    found: Counter = Counter()
    for m in DATE_LONG.finditer(text):
        mon = next(i for i, name in enumerate(MONTHS, 1) if name.startswith(m.group(1).lower()[:3]))
        found[f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"] += 1
    for m in DATE_NUM.finditer(text):
        y = m.group(3)
        y = y if len(y) == 4 else ("19" + y if int(y) > 50 else "20" + y)
        found[f"{y}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"] += 1
    return found


def set_scores(truth: Counter, out: Counter) -> dict:
    hit = sum((truth & out).values())
    return {
        "truth": sum(truth.values()),
        "found": sum(out.values()),
        "hit": hit,
        "recall": hit / sum(truth.values()) if truth else None,
        "precision": hit / sum(out.values()) if out else None,
    }


def labels_of(text: str) -> Counter:
    """A graphic page is a set of labels, one per line, order meaningless."""
    return Counter(
        normalise(line)
        for line in text.splitlines()
        if normalise(line) and not line.strip().startswith("[")
    )


def tables_of(text: str) -> list[list[list[str]]]:
    out, rows, inside = [], [], False
    for line in text.splitlines():
        s = line.strip()
        if s == "[table]":
            inside, rows = True, []
        elif s == "[end table]":
            if rows:
                out.append(rows)
            inside = False
        elif inside and line.strip():
            rows.append([c.strip() for c in line.split("\t")])
    return out


def table_cells(text: str) -> Counter:
    return Counter(cell for grid in tables_of(text) for row in grid for cell in row if cell)


def completed_cut(cuts: list[str], truth_norm: str, out_norm: str) -> int:
    """An engine that finishes a line the page cut off has invented text.

    A fragment that already appears in the page's own body cannot be attributed: the
    facing page of FD 33700 begins "Burlington Nor", and page one says "Burlington
    Northern" in its own right, so a continuation there proves nothing. Only a fragment
    absent from the body counts, and only when the output carries it with several words
    running on.
    """
    invented = 0
    for cut in cuts:
        tail = normalise(cut)
        if len(tail) < 12 or tail in truth_norm:
            continue
        at = out_norm.find(tail)
        if at < 0:
            continue
        after = out_norm[at + len(tail) : at + len(tail) + 40].strip()
        if after and after[0] not in ".,;:)-" and len(after.split()) >= 3:
            invented += 1
    return invented


# ---------------------------------------------------------------- the run


def score_page(truth_raw: str, out_raw: str, tier: str) -> dict:
    truth_body, cuts = strip_excluded(truth_raw)
    out_body, _ = strip_excluded(out_raw)
    t, o = normalise(truth_body), normalise(out_body)
    row = {
        "tier": tier,
        "chars": len(t),
        "cer": rate(t, o),
        "wer": word_rate(t, o),
        "dockets": set_scores(dockets(truth_body), dockets(out_body)),
        "dates": set_scores(dates(truth_body), dates(out_body)),
        "cut_completed": completed_cut(cuts, t, o),
    }
    if tier == "graphic":
        row["labels"] = set_scores(labels_of(truth_body), labels_of(out_body))
        row.pop("cer")  # a set, not a sequence
        row.pop("wer")
    if tier in ("graphic", "blank"):
        row["false_chars"] = max(0, len(o) - len(t))
    if tier == "tabular":
        row["cells"] = set_scores(table_cells(truth_body), table_cells(out_body))
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--dir", required=True, type=Path, help="one <page>.txt per page")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    tiers = {p["png"].replace(".png", ".txt"): p["tier"] for p in sample["pages"] if p["selected"]}

    pages, missing = {}, []
    for name, tier in sorted(tiers.items()):
        got = args.dir / name
        if not got.exists():
            missing.append(name)
            continue
        pages[name] = score_page(
            (TRUTH / name).read_text(encoding="utf-8"),
            got.read_text(encoding="utf-8", errors="replace"),
            tier,
        )

    by_tier: dict[str, list] = {}
    for row in pages.values():
        by_tier.setdefault(row["tier"], []).append(row)

    def agg(rows, field):
        vals = [r[field] for r in rows if field in r]
        return sum(vals) / len(vals) if vals else None

    def pooled(rows, field):
        t = sum(r[field]["truth"] for r in rows if field in r)
        h = sum(r[field]["hit"] for r in rows if field in r)
        f = sum(r[field]["found"] for r in rows if field in r)
        return {
            "truth": t,
            "found": f,
            "hit": h,
            "recall": h / t if t else None,
            "precision": h / f if f else None,
        }

    # WHAT PRODUCED THIS FIGURE TRAVELS WITH IT. `ocr_run.py` writes `run.json` beside the
    # text it read — the weights it named, the flags, the package versions — and it is
    # copied in here so a published number can be checked against the engine that made it
    # rather than against an engine label whose package default has since moved.
    run_file = args.dir / "run.json"
    provenance = None
    if run_file.is_file():
        try:
            provenance = json.loads(run_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"  {run_file.name} unreadable ({type(e).__name__}); scoring without it")

    report = {
        "engine": args.engine,
        "run": provenance,
        "pages_scored": len(pages),
        "pages_missing": missing,
        "by_tier": {
            tier: {
                "pages": len(rows),
                "cer": agg(rows, "cer"),
                "wer": agg(rows, "wer"),
                "dockets": pooled(rows, "dockets"),
                "dates": pooled(rows, "dates"),
                "labels": pooled(rows, "labels") if tier == "graphic" else None,
                "cells": pooled(rows, "cells") if tier == "tabular" else None,
                "false_chars": agg(rows, "false_chars"),
                "cut_completed": sum(r.get("cut_completed", 0) for r in rows),
            }
            for tier, rows in sorted(by_tier.items())
        },
        "overall": {
            "cer": agg([r for r in pages.values() if "cer" in r], "cer"),
            "wer": agg([r for r in pages.values() if "wer" in r], "wer"),
            "dockets": pooled(list(pages.values()), "dockets"),
            "dates": pooled(list(pages.values()), "dates"),
            "cut_completed": sum(r.get("cut_completed", 0) for r in pages.values()),
        },
        "pages": pages,
    }
    out = args.out or (ROOT / f"docs/research/ocr-benchmark/runs/{args.engine}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8", newline="\n")

    print(
        f"{args.engine}: {len(pages)} pages scored"
        + (f", {len(missing)} missing" if missing else "")
    )
    o = report["overall"]
    print(f"  CER {fmt(o['cer'])}   WER {fmt(o['wer'])}")
    print(
        f"  dockets recall {fmt(o['dockets']['recall'])} precision {fmt(o['dockets']['precision'])}"
    )
    print(f"  dates   recall {fmt(o['dates']['recall'])} precision {fmt(o['dates']['precision'])}")
    print(f"  cut lines completed (invention): {o['cut_completed']}")
    for tier, t in report["by_tier"].items():
        extra = ""
        if t["labels"]:
            extra = f" labels recall {fmt(t['labels']['recall'])}"
        if t["cells"]:
            extra = f" cells recall {fmt(t['cells']['recall'])}"
        if t["false_chars"]:
            extra += f" false chars {t['false_chars']:.0f}"
        print(f"  {tier:9s} {t['pages']:3d} pages  CER {fmt(t['cer'])}  WER {fmt(t['wer'])}{extra}")
    print(f"  -> {out}")


def fmt(v) -> str:
    return "  n/a" if v is None else f"{v * 100:5.1f}%"


if __name__ == "__main__":
    main()
