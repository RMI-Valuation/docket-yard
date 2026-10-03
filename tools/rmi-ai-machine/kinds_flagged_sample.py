#!/usr/bin/env python3
"""Draw the kind sample from THE PAGES THE PROSE SCREEN ORDERS, not from the record at large.

    python3 kinds_flagged_sample.py --pages pages.csv.gz --text pool_text.json \\
        --out docs/research/text-quality/kinds-flagged-sample.json

`text_quality.looks_like_prose` decides the re-read's order (the operator's: prose first), and
its rate was measured off-population. Of the 166 pages labelled in `docs/research/text-quality/`
only **32** sit below the 0.5 cut and only **5 of those are prose**, so precision and recall on
the flagged set rest on five pages (`docs/deferred.md`, 2026-09-18). This draws ~40 more from
the flagged set itself.

THE POPULATION is a live **primary** reading of the publisher's own **text layer**, scoring
under 0.5 over the module's floor of 15 letter-bearing tokens: 31,798 pages, which is the
figure `README.md` states. Dropping the channel filter admits 6,806 `ocr` rows and gives 38,604
— pages no prose queue orders, and a population this sample would then not describe.

STRATIFIED ON THE SCREEN'S OWN VERDICT, which is what makes 40 labels enough for both figures:
20 pages it calls prose and 20 it does not. Precision reads off the first stratum directly;
recall needs the weights this file records, since a page in the second stratum stands for far
more of the record than one in the first. A simple random 40 would hold about six prose pages
and could not give a recall at all.

THE SCORE AND THE VERDICT ARE NEVER SHOWN TO THE CHECKER. They are written here because the
draw must be reproducible and because scoring needs them afterwards; the check sheet is built
from the page image and the stored text alone. Model labels are a screen, never a measurement —
these labels are the operator's, and only his make a rate.

`--text` is a JSON of `{text_id: text}` for the pool, read from production read-only, since the
screen reads a page's layout rather than the columns of the scored CSV. Two runs with the same
inputs and seeds are byte-identical.
"""

import argparse
import csv
import gzip
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import text_quality as tq  # noqa: E402

CUT = 0.5  # the flagged set: what the queue orders
FLOOR = 15  # letter-bearing tokens, the module's own floor
POOL = 400
PER_STRATUM = 20
SEED_POOL = 20260919
SEED_PICK = 2026091920


def labelled_already(research: Path) -> set[int]:
    """Every page already labelled here, so the draw cannot spend a label twice."""
    seen: set[int] = set()
    for name in ("sample.json", "topup-sample.json"):
        path = research / name
        if not path.exists():
            continue
        loaded = json.loads(path.read_text(encoding="utf-8"))
        rows = (
            loaded
            if isinstance(loaded, list)
            else [r for v in loaded.values() for r in (v if isinstance(v, list) else [v])]
        )
        seen.update(int(r["text_id"]) for r in rows if isinstance(r, dict) and "text_id" in r)
    return seen


def flagged(pages: Path, seen: set[int]) -> tuple[list[dict], int]:
    """The flagged population, and how many of it are already labelled."""
    out, total = [], 0
    with gzip.open(pages, "rt", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["channel"] != "text-layer" or row["role"] != "primary":
                continue
            lettered = int(row["lettered"])
            if lettered < FLOOR:
                continue
            good = int(row["hits"]) / lettered
            if good >= CUT:
                continue
            total += 1
            if int(row["text_id"]) in seen:
                continue
            out.append(
                {
                    "text_id": int(row["text_id"]),
                    "sha": row["sha"],
                    "page": int(row["page"]),
                    "year": row["year"],
                    "kinds": row["kinds"],
                    "good": round(good, 4),
                }
            )
    return out, total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pages", required=True, type=Path, help="the scored page set, gzipped CSV")
    ap.add_argument("--text", required=True, type=Path, help="{text_id: text} for the pool")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--research", type=Path, default=Path("docs/research/text-quality"))
    args = ap.parse_args()

    seen = labelled_already(args.research)
    eligible, population = flagged(args.pages, seen)
    already = population - len(eligible)
    print(f"flagged text-layer primaries: {population}; already labelled: {already}")

    pool = random.Random(SEED_POOL).sample(eligible, POOL)
    texts = json.loads(args.text.read_text(encoding="utf-8"))
    missing = [r["text_id"] for r in pool if str(r["text_id"]) not in texts]
    if missing:
        print(f"--text is missing {len(missing)} of the pool, e.g. {missing[:3]}", file=sys.stderr)
        return 2
    for r in pool:
        lay = tq.layout(texts[str(r["text_id"])])
        r["screen_prose"] = bool(tq.looks_like_prose(lay))
        r["layout"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in lay.items()}

    yes = [r for r in pool if r["screen_prose"]]
    no = [r for r in pool if not r["screen_prose"]]
    if len(yes) < PER_STRATUM or len(no) < PER_STRATUM:
        print(f"a stratum is too small: {len(yes)} prose, {len(no)} not", file=sys.stderr)
        return 2
    rnd = random.Random(SEED_PICK)
    drawn = rnd.sample(yes, PER_STRATUM) + rnd.sample(no, PER_STRATUM)
    pick = sorted(drawn, key=lambda r: r["text_id"])
    for n, r in enumerate(pick, 1):
        r["label_id"] = f"K{n:02d}"

    # newline="\n" explicitly: text mode on Windows would write CRLF, which the repository
    # pins against (.gitattributes) and which would make "two runs byte-identical" untrue
    # across platforms
    body = {
        "drawn": "2026-09-19",
        "seed_pool": SEED_POOL,
        "seed_pick": SEED_PICK,
        "question": (
            "Of the pages the prose screen ORDERS - the flagged set, good < 0.5 over "
            "the 15 letter-bearing-token floor - what kind is each page?"
        ),
        "population": population,
        "eligible": len(eligible),
        "pool": len(pool),
        "pool_screen_prose": len(yes),
        "pool_screen_not": len(no),
        "weight_prose_stratum": round(len(yes) / PER_STRATUM, 2),
        "weight_not_stratum": round(len(no) / PER_STRATUM, 2),
        "pages": pick,
    }
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(body, indent=1) + "\n")
    print(f"{len(pick)} pages -> {args.out}")
    print(f"  a prose-stratum page stands for {len(yes) / PER_STRATUM:.1f} flagged pages,")
    print(f"  one the screen passed over for {len(no) / PER_STRATUM:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
