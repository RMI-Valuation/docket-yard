"""Benchmark step 1: draw the sixty-decision sample (docs/extraction-benchmark.md).

Runs on RMI-AI-MACHINE beside the text layer step 0 produced. Input: a CSV of candidate
decisions from the store (id, docket, date, type, body, sha, url). For each, the per-page
text is read, pages and characters counted, and citations to Board matter counted with a
deliberately loose pattern — the count only ranks candidates; the labels decide truth.

Strata (20 each, drawn at random within the stratum with a fixed seed):
  heavy    decisions with the most citation-like strings — the rate-case / merger tier
  routine  notices of exemption and notices — the procedural tier
  short    decisions of one or two pages with few citations — the order tier

Output: sample.json (what was drawn and why, per decision) and labels.csv (the empty
labelling sheet the operator fills in: one row per citation or deadline found).
"""

import csv
import json
import random
import re
import sys
from pathlib import Path

TEXT_ROOT = Path("/data/docketyard/text")
SEED = 20260826
PER_STRATUM = 20

CITE = re.compile(
    r"\b(?:Docket\s+No\.|Finance\s+Docket|Ex\s+Parte|Sub-No\.|S\.T\.B\.|STB\s+(?:FD|EP|AB|NOR|MCF|WB))",
    re.I,
)
ROUTINE_TYPES = {"Notice of Exemption", "Notice", "Corrected Notice"}


def text_of(sha: str) -> dict | None:
    for candidate in (TEXT_ROOT / sha[:2] / f"{sha}.json", TEXT_ROOT / f"{sha}.json"):
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    hits = list(TEXT_ROOT.glob(f"**/{sha}*.json"))
    return json.loads(hits[0].read_text(encoding="utf-8")) if hits else None


def page_texts(doc: dict) -> list[str]:
    """extract_text.py writes `page_text` as one string per page (and `pages` as the count)."""
    return [str(p) for p in doc.get("page_text") or []]


def main(csv_path: Path, out_dir: Path) -> int:
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    measured = []
    missing = 0
    for r in rows:
        doc = text_of(r["sha"])
        if doc is None:
            missing += 1
            continue
        pages = page_texts(doc)
        text = "\n".join(pages)
        measured.append(
            {
                **r,
                "pages": len(pages),
                "chars": len(text),
                "cites": len(CITE.findall(text)),
                "image_only": bool(doc.get("image_only")),
            }
        )
    print(f"{len(rows)} candidates, {len(measured)} with text, {missing} without", file=sys.stderr)
    rng = random.Random(SEED)
    decisions = [m for m in measured if m["type"] in ("Decision", "Corrected Decision")]
    heavy_pool = sorted(decisions, key=lambda m: -m["cites"])[:60]
    routine_pool = [m for m in measured if m["type"] in ROUTINE_TYPES]
    short_pool = [m for m in decisions if m["pages"] <= 2 and m not in heavy_pool]
    sample = []
    for name, pool in (("heavy", heavy_pool), ("routine", routine_pool), ("short", short_pool)):
        pick = rng.sample(pool, min(PER_STRATUM, len(pool)))
        for m in pick:
            sample.append({"stratum": name, **m})
        print(f"{name}: {len(pick)} of {len(pool)}", file=sys.stderr)
    sample.sort(key=lambda m: (m["stratum"], m["date"], m["id"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sample.json").write_text(
        json.dumps({"seed": SEED, "per_stratum": PER_STRATUM, "drawn": sample}, indent=1),
        encoding="utf-8",
    )
    with open(out_dir / "labels.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")  # .gitattributes pins LF
        w.writerow(
            [
                "decision_id",
                "stratum",
                "docket",
                "date",
                "board_url",
                "kind",  # citation | caption | deadline
                "page",  # 1-based page of the Board's PDF
                "quoted",  # the reference as printed, or the sentence that sets the deadline
                "target",  # what a citator resolves, or the deadline date, as printed
                # citation: stb | court | record   caption: self
                # deadline: date | reference | period | indefinite
                "target_kind",
                "note",
            ]
        )
        for m in sample:
            w.writerow([m["id"], m["stratum"], m["docket"], m["date"], m["url"]] + [""] * 6)
    # the text of each sampled decision, per page, for labelling without leaving the box
    for m in sample:
        doc = text_of(m["sha"])
        pages = page_texts(doc) if doc else []
        body = "".join(f"\n\n===== page {i} =====\n{p}" for i, p in enumerate(pages, 1))
        (out_dir / "text" / f"{m['stratum']}-{m['id']}.txt").parent.mkdir(exist_ok=True)
        (out_dir / "text" / f"{m['stratum']}-{m['id']}.txt").write_text(
            f"{m['docket']}  {m['type']}  served {m['date']}\n{m['url']}\n{body}", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
