"""Draw the OCR citation benchmark's sample (docs/research/ocr-citation-benchmark/README.md).

The text-layer card was measured on sixty born-digital decisions, and a measurement is OF one
reading channel (ADR 0018 D8), so the OCR channel needs its own sheet. The operator decided
the instrument on 2026-09-13: whole documents labelled from their scans, about a hundred, in
four strata, because only a labelled document can show a citation the OCR destroyed.

RUNS AGAINST PRODUCTION'S OWN OUTPUT, not a re-implementation of it: the findings directory
the shipped `citator find --channel ocr` wrote, and the store it read. Read-only. Piped into
the web container, which holds the shipped package and the store:

    docker compose exec -T web python - /data/citation-findings-ocr-2026-09-13/ocr \\
        < tools/rmi-ai-machine/ocr_citation_sample.py > sample.json

Strata, drawn at random within each with a fixed seed:
  ppocr-2006   a citation found; served 2006 on; the citation pages mostly PP-OCRv6    30
  dots-2006    a citation found; served 2006 on; the citation pages mostly dots.mocr   25
  pre-2006     a citation found; served before 2006, whatever the engine             every one
  none-found   no citation found (captions may be)                                    20

A document's ENGINE is the engine of most of the pages its citations sit on, and a tie goes
to PP-OCRv6: the weaker reader of docket numbers on the OCR benchmark (91.2% against 100%),
so a tie can never flatter the measurement. Its ERA is the earliest service date of the
decisions carrying it. Both are recorded per document so the stratification can be checked.

A DOCUMENT OF MORE THAN TWENTY PAGES IS LABELLED ON TWENTY PAGES DRAWN AT RANDOM (the
operator, 2026-09-13), and the truth and the dry run are both restricted to `labelled_pages`.
The pre-2006 stratum holds Environmental Review volumes of up to 426 pages with a citation on
one to three, so every page was not labellable; drawing the pages where a citation was found
instead would inflate the recall a card stores. The pages are drawn from those the store holds
OCR text for, never from `range(pages_read)` (a document can print page 299 in a 212-page
reading), and each document is seeded with its own hash so its pages do not move when the
draw's order does. The STRATUM is still assigned from the whole document, since that is what
defines the population.

The labels are CITATIONS AND CAPTIONS ONLY. The card measures docket-shaped citations; the
sixty's deadline rows answered a different benchmark.
"""

import json
import random
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from docketyard.citator import keys

SEED = 20260913
STRATA = (("ppocr-2006", 30), ("dots-2006", 25), ("pre-2006", None), ("none-found", 20))
PAGE_CAP = 20
PPOCR, DOTS = "pp-ocrv6-medium", "dots.mocr"
SITE = "https://docketyard.org"
YEAR = re.compile(r"\b(19|20)\d{2}\b")


def carriers(con, sha: str) -> list[dict]:
    """Every decision carrying these bytes, with its docket as the registry keys it."""
    return [
        {
            "stb_decision_id": did,
            "docket": keys.registry_key(p, s, sub, suf),
            "service_date": served,
            "decision_type": dtype,
        }
        for did, served, dtype, p, s, sub, suf in con.execute(
            "SELECT r.stb_decision_id, r.service_date, r.decision_type,"
            "       d.prefix, d.sequence, d.sub_sequence, d.suffix"
            "  FROM decision_attachment a"
            "  JOIN decision_record r ON r.decision_pk = a.decision_pk"
            "  JOIN docket d ON d.docket_id = r.docket_id"
            " WHERE a.document_sha256 = ? ORDER BY r.stb_decision_id",
            (sha,),
        )
    ]


def earliest_year(decisions: list[dict]) -> int | None:
    years = [int(m.group(0)) for d in decisions if (m := YEAR.search(d["service_date"] or ""))]
    return min(years) if years else None


def describe(con, path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    sha = doc["document_sha256"]
    text_ids = {int(k): v for k, v in (doc.get("text_ids") or {}).items()}
    engine_of = {}
    for page, text_id in text_ids.items():
        row = con.execute("SELECT method FROM document_text WHERE text_id = ?", (text_id,))
        engine_of[page] = (row.fetchone() or ("unknown",))[0]
    cited = {
        (int(f["page"]), key)
        for f in doc.get("findings") or []
        if f.get("kind") == "citation"
        and (key := keys.normalise(f.get("target", ""))) is not None
        and keys.DOCKET_KEY.match(key)
    }
    by_engine = Counter(engine_of.get(page, "unknown") for page, _ in cited)
    decisions = carriers(con, sha)
    return {
        "document_sha256": sha,
        "board_pdf": f"{SITE}/document/{sha}.pdf",
        "decisions": decisions,
        "earliest_year": earliest_year(decisions),
        "pages_read": int(doc.get("pages_read") or 0),
        "text_pages": sorted(text_ids),
        "page_engines": dict(Counter(engine_of.values())),
        "citation_keys": len(cited),
        "citation_keys_by_page": {
            str(p): n for p, n in sorted(Counter(p for p, _ in cited).items())
        },
        "citation_page_engines": dict(by_engine),
        "captions": sum(1 for f in doc.get("findings") or [] if f.get("kind") == "caption"),
        # the tie rule of the module docstring: DOTS only on a strict majority
        "engine": DOTS if by_engine[DOTS] > by_engine[PPOCR] else PPOCR,
    }


def labelled(d: dict) -> dict:
    """The pages to label: all of them, or PAGE_CAP drawn at random with the document's own
    seed. `labelled_citation_keys` counts what the finder emitted on those pages only."""
    pages = d["text_pages"]
    if len(pages) > PAGE_CAP:
        pages = sorted(random.Random(f"{SEED}:{d['document_sha256']}").sample(pages, PAGE_CAP))
    chosen = set(pages)
    return {
        **d,
        "labelled_pages": pages,
        "labelled_citation_keys": sum(
            n for p, n in d["citation_keys_by_page"].items() if int(p) in chosen
        ),
    }


def stratum(d: dict) -> str | None:
    if not d["citation_keys"]:
        return "none-found"
    if d["earliest_year"] is None:
        return None  # no service date anywhere: reported, never guessed into an era
    if d["earliest_year"] < 2006:
        return "pre-2006"
    return "ppocr-2006" if d["engine"] == PPOCR else "dots-2006"


def main(findings_dir: Path) -> int:
    con = sqlite3.connect("file:/data/docketyard.sqlite?mode=ro", uri=True, timeout=5)
    described = [describe(con, p) for p in sorted(findings_dir.glob("*.json"))]
    con.close()
    pools: dict[str | None, list[dict]] = {}
    for d in described:
        pools.setdefault(stratum(d), []).append(d)
    rng = random.Random(SEED)
    drawn = []
    for name, size in STRATA:
        pool = sorted(pools.get(name, []), key=lambda d: d["document_sha256"])
        pick = pool if size is None else rng.sample(pool, min(size, len(pool)))
        drawn += [{"stratum": name, **labelled(d)} for d in pick]
    report = {
        "seed": SEED,
        "page_cap": PAGE_CAP,
        "findings_dir": str(findings_dir),
        "population": {str(k): len(v) for k, v in pools.items()},
        "strata": {name: size for name, size in STRATA},
        "labelled_pages": sum(len(d["labelled_pages"]) for d in drawn),
        "labelled_citation_keys": sum(d["labelled_citation_keys"] for d in drawn),
        "drawn": sorted(drawn, key=lambda d: (d["stratum"], d["document_sha256"])),
    }
    json.dump(report, sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
