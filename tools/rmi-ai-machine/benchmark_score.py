"""Score an extraction run against the checked labels (docs/research/benchmark/labels.csv).

The conventions settled 2026-08-29 decide what is compared, and each one changes the
arithmetic:

- **citations are compared as sets of `(decision, target)` pairs**, not as lists of
  occurrences. A repeat adds no edge to a citation graph, so an engine is neither rewarded
  for finding every short form nor punished for finding them.
- **each `target_kind` is scored on its own.** A court citation cannot be validated against
  the docket registry and stays out of the citator's first slice; folding it into one recall
  figure would flatter or punish an engine for something the product does not use.
- **captions are a precision test.** A decision's own docket, named as itself, is not an
  edge — the record already holds it from the Board's table. An engine that emits it as a
  citation is wrong, and that is what the caption rows catch.
- **deadlines whose target is a period or is indefinite are scored on the sentence**, not on
  a date, because the page prints no date and one may never be computed.

Targets are compared after normalising to what a citator would resolve: a docket key where
the string carries one (`Docket No. FD 36500` and `FD 36500` are the same edge), otherwise
a case-folded collapse. Nothing here reads a PDF; it compares a run to the sheet.

    python tools/rmi-ai-machine/benchmark_score.py --run data/benchmark/runs/qwen3-14b \\
        --label text-layer
"""

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "docs/research/benchmark/labels.csv"
OUT = ROOT / "docs/research/benchmark/runs"

DOCKET = re.compile(
    r"\b(FD|AB|EP|NOR|MCF|MCC|NOM|ISM|IS|SDM|WB|SO|DOP|STA|WCC|SUB)\s*[-\s]?\s*(\d{1,6})\b",
    re.I,
)
# the document-versus-proceeding test, for placing findings from a run made before
# target_kind existed: a prior decision is a citation whatever docket it sits in
DOC_NAMED = re.compile(r"slip op\.|decision|order|served|NPRM|NITU|CITU", re.I)
SUBNO = re.compile(r"\(?\s*Sub[-\s]?No\.?\s*(\d+[A-Z]?)\s*\)?", re.I)
REPORTER = re.compile(
    r"\b(\d{1,3})\s+(F\.?\s?\d?d|S\.?T\.?B\.?|I\.?C\.?C\.?(?:\.?2d)?|U\.?S\.?)\s+(\d{1,4})\b", re.I
)


def norm_target(raw: str) -> str:
    """What a citator would resolve, reduced to a comparable key.

    A docket wins over anything else in the string, because `Docket No. FD 36500`,
    `FD 36500` and `FD-36500` are one edge. A reporter citation is next. Anything else —
    a narrative reference like `decision served March 12, 2024`, or `service date` — falls
    back to a case-folded collapse, which is exact but forgiving of spacing."""
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", raw).replace("—", " ").replace("–", " ")
    m = DOCKET.search(text)
    if m:
        key = f"{m.group(1).upper()} {int(m.group(2))}"
        sub = SUBNO.search(text[m.end() : m.end() + 30])
        return key + (f" ({sub.group(1).upper()})" if sub else "")
    r = REPORTER.search(text)
    if r:
        series = re.sub(r"[.\s]", "", r.group(2)).upper()
        return f"{r.group(1)} {series} {r.group(3)}"
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def norm_targets(raw: str) -> set:
    """A target cell may be a list: `NOR 42144; NOR 42150; NOR 42152; NOR 42153` is one
    consolidated caption naming four proceedings. Taking the first match drops three of
    them from the truth set -- the same defect ADR 0004 was written for, one level down."""
    return {k for part in (raw or "").split(";") if (k := norm_target(part.strip()))}


def truth() -> tuple:
    """The sheet, as {decision: {kind: {target_kind: set(target)}}} plus the deadline
    sentences, which are compared as text where no date is printed."""
    rows = list(csv.DictReader(LABELS.open(encoding="utf-8")))
    out: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    sentences: dict = defaultdict(lambda: defaultdict(set))
    for r in rows:
        did, kind, tk = r["decision_id"], r["kind"], r["target_kind"]
        if kind == "deadline" and tk in ("period", "indefinite"):
            sentences[did][tk].add(norm_target(r["quoted"]))
            continue
        out[did][kind][tk].update(norm_targets(r["target"]))
    return out, sentences


def run_findings(run_dir: Path) -> tuple:
    """A run, in the same shape. A finding without a `target_kind` (a run made before the
    conventions were settled) is placed by its own `kind` and note, so an older run can
    still be scored — imperfectly, and the summary says so."""
    out: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    sentences: dict = defaultdict(lambda: defaultdict(set))
    legacy = 0
    for f in sorted(run_dir.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        did = str(doc.get("decision_id") or f.stem)
        for page in doc.get("pages", []):
            for fi in page.get("findings", []) or []:
                kind = fi.get("kind") or "citation"
                tk = fi.get("target_kind")
                if not tk:
                    legacy += 1
                    note = (fi.get("note") or "").lower()
                    if (
                        kind == "citation"
                        and "self" in note
                        and not DOC_NAMED.search(fi.get("quoted", ""))
                    ):
                        kind, tk = "caption", "self"
                    elif kind == "citation":
                        tk = "court" if "court" in note else "stb"
                    else:
                        tk = "date" if fi.get("target") else "period"
                if kind == "deadline" and tk in ("period", "indefinite"):
                    sentences[did][tk].add(norm_target(fi.get("quoted", "")))
                    continue
                out[did][kind][tk].update(norm_targets(fi.get("target", "")))
    return out, sentences, legacy


def score(t_sets: dict, r_sets: dict) -> dict:
    hit = sum(len(t_sets[d] & r_sets.get(d, set())) for d in t_sets)
    truth_n = sum(len(v) for v in t_sets.values())
    found_n = sum(len(v) for v in r_sets.values())
    return {
        "truth": truth_n,
        "found": found_n,
        "hit": hit,
        "recall": hit / truth_n if truth_n else None,
        "precision": hit / found_n if found_n else None,
    }


def collect(sets: dict, kind: str, tk: str) -> dict:
    return {d: sets[d][kind][tk] for d in sets if sets[d][kind][tk]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, type=Path, help="a directory of per-decision JSON")
    ap.add_argument("--label", default=None, help="name for the result file")
    args = ap.parse_args()

    t, t_sent = truth()
    r, r_sent, legacy = run_findings(args.run)
    name = args.label or args.run.name

    result = {"run": str(args.run), "label": name, "legacy_findings": legacy, "by_kind": {}}
    print(f"{name}: {len(r)} decisions in the run, {len(t)} in the sheet")
    if legacy:
        print(f"  {legacy} findings carried no target_kind and were placed by note (older run)")

    for kind, kinds in (
        ("citation", ("stb", "court", "record")),
        ("caption", ("self",)),
        ("deadline", ("date", "reference")),
    ):
        for tk in kinds:
            s = score(collect(t, kind, tk), collect(r, kind, tk))
            result["by_kind"][f"{kind}/{tk}"] = s
            if not s["truth"]:
                continue
            rec = f"{s['recall']:6.1%}" if s["recall"] is not None else "   n/a"
            pre = f"{s['precision']:6.1%}" if s["precision"] is not None else "   n/a"
            print(f"  {kind:8s} {tk:9s} truth {s['truth']:4d}  recall {rec}  precision {pre}")

    for tk in ("period", "indefinite"):
        s = score(
            {d: t_sent[d][tk] for d in t_sent if t_sent[d][tk]},
            {d: r_sent[d][tk] for d in r_sent if r_sent[d][tk]},
        )
        result["by_kind"][f"deadline/{tk}"] = s
        if s["truth"]:
            rec = f"{s['recall']:6.1%}" if s["recall"] is not None else "   n/a"
            print(f"  deadline {tk:9s} truth {s['truth']:4d}  recall {rec}  (sentence match)")

    # the headline a citator cares about: STB edges, deduplicated
    stb = result["by_kind"]["citation/stb"]
    print(f"\n  STB edges: {stb['hit']}/{stb['truth']} found, {stb['found']} emitted")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(result, indent=1), encoding="utf-8", newline="\n")
    print(f"  -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
