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

# the suffix letter may be glued to the number (`AB 1296X`, an abandonment exemption) or sit
# in the sub-docket parenthetical (`AB 55 (Sub-No. 814X)`); both key the same way. The
# prefix is matched CASE-SENSITIVELY: `IS` and `SO` are English words, and a period
# deadline's quoted sentence ("the exemption is 30 days after ...") must not normalise to
# the docket key `IS 30` (code review, 2026-08-30).
DOCKET = re.compile(
    r"\b(FD|AB|EP|NOR|MCF|MCC|NOM|ISM|IS|SDM|WB|SO|DOP|STA|WCC|SUB)\s*[-\s]?\s*(\d{1,6})([A-Z])?\b",
)
# the document-versus-proceeding test, for placing findings from a run made before
# target_kind existed: a prior decision is a citation whatever docket it sits in
DOC_NAMED = re.compile(r"slip op\.|decision|order|served|NPRM|NITU|CITU", re.I)
DOCKET_KEY = re.compile(r"^[A-Z]{2,4} \d+")  # what norm_target emits for a docket
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
        if sub:
            return key + f" ({sub.group(1).upper()})"
        return key + (f" ({m.group(3).upper()})" if m.group(3) else "")
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


# A footnote marker fused to the sentence it annotates: the page prints "received, the"
# and the text layer holds "received,1 the". The rule labels_check_page.py uses, applied
# the same way (after whitespace is gone): a digit or two between a lower-case word's
# punctuation and a lower-case word, leaving "Sub-No. 5X" and "1 I.C.C.2d at 825" alone.
FOOTNOTE_MARK = re.compile(r"(?<=[a-z][,.;])\d{1,2}(?=[a-z])")


def flat(text: str) -> str:
    """Text reduced to what survives a PDF's wraps, its dashes, extraction's mojibake and
    a fused footnote marker: NFKC, whitespace gone, markers gone, then case-folded to
    alphanumerics. Both sides of a quote check go through this and nothing else.

    Order matters, and an earlier revision had it wrong: FOOTNOTE_MARK earns its
    exceptions from CASE — a digit before an upper-case letter is a sub-number or a
    reporter series, not a marker — so case-folding first made `Sub-No. 5X` and
    `Sub-No. 9X` the same string, and `1 I.C.C.2d` and `1 I.C.C.3d` too, defeating the
    check exactly where it was meant to bite (code review, 2026-08-30)."""
    s = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    return re.sub(r"[^a-z0-9]+", "", FOOTNOTE_MARK.sub("", s).casefold())


def load_text(text_dir: Path) -> dict:
    """{decision_id: flat text of the whole decision}, from step 0's per-decision files.
    What cannot be matched from this: a passage that runs over a page break, because
    extraction emits a page's body and then its footnotes, so the halves are not adjacent
    (16 of the sheet's 977 quotes, measured 2026-08-30; the queue sends those to the PDF)."""
    return {
        f.stem.rsplit("-", 1)[-1]: flat(f.read_text(encoding="utf-8", errors="replace"))
        for f in text_dir.glob("*.txt")
    }


MIN_QUOTE = 8  # alphanumerics; below this ("Id.", "id. at 4") the check says nothing


def on_page(quoted: str, doc_text: str) -> bool:
    """The rule extraction-benchmark.md § Step 2 states: a quoted passage that is not in the
    decision is wrong, whatever it targets. Checked against the whole decision rather than
    the page, because a passage that runs over a page break is genuine and a page-number
    slip is a different, lesser defect. A model copying the prompt's own worked examples
    onto a page (measured 2026-08-30: 13 of qwen3:14b's 26 docket-shaped extras) fails
    here and nowhere else — the docket it names is real, so the registry passes it.

    Two allowances. A quote too short to mean anything is passed — unless it carries a
    docket or reporter key, which is exactly the short quote the check exists for. And a
    quote whose halves are each in the decision is passed, because a passage that runs
    over a page break has a footnote block between its halves in the text layer."""
    raw = quoted or ""
    q = flat(raw)
    if len(q) < MIN_QUOTE and not (DOCKET.search(raw) or REPORTER.search(raw)):
        return True
    if q in doc_text:
        return True
    words = raw.split()
    if len(words) >= 4:
        mid = len(words) // 2
        a, b = flat(" ".join(words[:mid])), flat(" ".join(words[mid:]))
        if len(a) >= MIN_QUOTE and len(b) >= MIN_QUOTE:
            at = doc_text.find(a)
            # the second half must follow the first — two unrelated fragments stitched
            # into one "quote" must not pass just because each exists somewhere
            return at >= 0 and doc_text.find(b, at + len(a)) >= 0
    return False


def run_findings(run_dir: Path, texts: dict | None = None) -> tuple:
    """A run, in the same shape, plus a report dict. A finding without a `target_kind` (a
    run made before the conventions were settled) is placed by its own `kind` and note,
    so an older run can still be scored — imperfectly, and the summary says so. With
    `texts`, a finding whose quote is not in the decision is dropped and listed
    (`off_page`, auditable), and a decision the texts do not cover is listed
    (`unchecked`) rather than silently passed. `legacy` counts placed findings only."""
    out: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    sentences: dict = defaultdict(lambda: defaultdict(set))
    report: dict = {"legacy": 0, "off_page": [], "unchecked": []}
    for f in sorted(run_dir.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        did = str(doc.get("decision_id") or f.stem)
        doc_text = texts.get(did) if texts is not None else None
        if texts is not None and doc_text is None:
            report["unchecked"].append(did)
        for page in doc.get("pages", []):
            for fi in page.get("findings", []) or []:
                if doc_text is not None and not on_page(fi.get("quoted", ""), doc_text):
                    report["off_page"].append(
                        {
                            "decision": did,
                            "page": page.get("page"),
                            "kind": fi.get("kind"),
                            "target": fi.get("target"),
                            "quoted": (fi.get("quoted") or "")[:160],
                        }
                    )
                    continue
                kind = fi.get("kind") or "citation"
                tk = fi.get("target_kind")
                if not tk:
                    report["legacy"] += 1
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
    return out, sentences, report


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
    ap.add_argument(
        "--text-dir",
        type=Path,
        default=None,
        help="the text the run read; findings whose quote is not in it are dropped. "
        "Default: data/benchmark/text-ocr when the run path says 'ocr', else "
        "data/benchmark/text — an OCR run held to the text layer drops real findings "
        "(24 on claude-ocr, measured 2026-08-30). --no-page-check disables this.",
    )
    ap.add_argument("--no-page-check", action="store_true")
    args = ap.parse_args()

    text_dir = args.text_dir or ROOT / (
        "data/benchmark/text-ocr" if "ocr" in args.run.as_posix().lower() else "data/benchmark/text"
    )
    texts = None if args.no_page_check else load_text(text_dir)
    if texts is not None and not texts:
        raise SystemExit(f"no decision text under {text_dir}; pass --text-dir or --no-page-check")

    t, t_sent = truth()
    r, r_sent, report = run_findings(args.run, texts)
    name = args.label or args.run.name

    result = {
        "run": str(args.run),
        "label": name,
        "legacy_findings": report["legacy"],
        "page_check": texts is not None,
        "text_dir": None if texts is None else text_dir.as_posix(),
        "unchecked_decisions": report["unchecked"],
        "off_page_findings": len(report["off_page"]),
        "off_page": report["off_page"],
        "by_kind": {},
    }
    print(f"{name}: {len(r)} decisions in the run, {len(t)} in the sheet")
    if report["legacy"]:
        print(f"  {report['legacy']} findings carried no target_kind and were placed by note")
    if texts is not None:
        print(
            f"  page check against {text_dir.as_posix()}: {len(report['off_page'])} findings "
            "quoted text that is not in the decision and were dropped"
        )
        if report["unchecked"]:
            print(
                f"  NOT CHECKED — no text for {len(report['unchecked'])} decisions: "
                f"{report['unchecked']}"
            )

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

    # and the class a citator resolves (ADR 0017): targets whose key is a docket number,
    # scored apart, because reporter cites and `decision served ...` phrases dominate the
    # extras and none of them resolves to a docket
    def docket_only(sets: dict) -> dict:
        return {d: {k for k in v if DOCKET_KEY.match(k)} for d, v in sets.items()}

    s = score(
        docket_only(collect(t, "citation", "stb")), docket_only(collect(r, "citation", "stb"))
    )
    result["by_kind"]["citation/stb-docket"] = s
    if s["truth"]:
        pre = f"{s['precision']:6.1%}" if s["precision"] is not None else "   n/a"
        print(
            f"  docket-shaped: {s['hit']}/{s['truth']} found, {s['found']} emitted"
            f"  recall {s['recall']:6.1%}  precision {pre}"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"  -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
