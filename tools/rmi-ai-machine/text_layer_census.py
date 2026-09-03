#!/usr/bin/env python3
"""Count the pages and characters of the text layer, over every document already extracted.

Answers ADR 0021 § Owed item 1 and the sizing in ADR 0022 § What was measured: how many
pages does the text-layer record hold, and how many characters a page, split by whether the
document is image-only. Reads nothing but the header of each extraction JSON.

`extract_text.py` writes its keys in a fixed order and `page_text` is LAST, so the four
fields wanted here are inside the first few hundred bytes of every file. Reading a prefix
rather than parsing the whole object is what makes this a minute rather than an hour: the
directory holds the full text of the record.

    python3 text_layer_census.py /data/docketyard/text

Prints one JSON object. It writes nothing and touches no PDF.
"""

import json
import re
import sys
from pathlib import Path

HEAD = 2048
FIELDS = re.compile(r'"pages":\s*(\d+),\s*"chars":\s*(\d+),\s*"image_only":\s*(true|false)')


def quantiles(values: list[int]) -> dict:
    """Median and the deciles that matter. A mean of a skewed distribution is not a
    property of it (ocr-benchmark/README.md), so the spread is reported beside the total."""
    if not values:
        return {}
    v = sorted(values)
    at = lambda q: v[min(len(v) - 1, int(len(v) * q))]  # noqa: E731
    return {"min": v[0], "p10": at(0.10), "median": at(0.50), "p90": at(0.90), "max": v[-1]}


def main(root: Path) -> int:
    groups: dict[str, dict] = {
        "image_only": {"docs": 0, "pages": 0, "chars": 0, "per_doc": []},
        "text_layer": {"docs": 0, "pages": 0, "chars": 0, "per_doc": []},
    }
    unreadable = 0
    for path in root.glob("*/*.json"):
        try:
            head = path.open("rb").read(HEAD).decode("utf-8", "replace")
        except OSError:
            unreadable += 1
            continue
        m = FIELDS.search(head)
        if not m:
            unreadable += 1
            continue
        pages, chars, image_only = int(m.group(1)), int(m.group(2)), m.group(3) == "true"
        g = groups["image_only" if image_only else "text_layer"]
        g["docs"] += 1
        g["pages"] += pages
        g["chars"] += chars
        g["per_doc"].append(pages)

    out = {"root": str(root), "unreadable": unreadable}
    for name, g in groups.items():
        out[name] = {
            "docs": g["docs"],
            "pages": g["pages"],
            "chars": g["chars"],
            "pages_per_doc": quantiles(g["per_doc"]),
            # a total divided by a count IS what a mean is for; the spread above says how
            # unevenly it is made up
            "chars_per_page": round(g["chars"] / g["pages"], 1) if g["pages"] else None,
            "pages_per_doc_mean": round(g["pages"] / g["docs"], 2) if g["docs"] else None,
        }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "/data/docketyard/text")))
