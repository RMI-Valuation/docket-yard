"""OCR benchmark step 1 (docs/ocr-plan.md): draw the candidate pages for the ground truth.

Runs on RMI-AI-MACHINE over the text layer's output (`extract_text.py`: one JSON per
document with `image_only`) and the record's metadata (`ocr_docs.csv`, exported from the
store). Draws, by seed, a pool of image-only pages stratified by era — the scans differ by
decade far more than by anything else — renders each page to PNG, and records why each was
drawn. The plan's three tiers (clean typescript, degraded, tabular) are assigned by looking
at the rendered pages in the next step and recorded beside the transcription; the pool is
larger than ninety so that each tier can reach thirty.

    python ocr_sample.py --text /data/docketyard/text --blobs /data/docketyard/blobs \\
        --docs ocr_docs.csv --out /data/docketyard/ocr/sample --per-era 50 --seed 20260828
"""

import argparse
import csv
import json
import random
import time
from pathlib import Path

ERAS = (("to-1995", None, 1995), ("1996-2005", 1996, 2005), ("2006-on", 2006, None))
DPI = 150


def era_of(date: str) -> str | None:
    if not date or len(date) < 4 or not date[:4].isdigit():
        return None
    year = int(date[:4])
    for name, lo, hi in ERAS:
        if (lo is None or year >= lo) and (hi is None or year <= hi):
            return name
    return None


def image_only_documents(text_dir: Path) -> dict[str, int]:
    """sha -> page count, for every document the text layer found image-only."""
    out: dict[str, int] = {}
    for f in text_dir.glob("*/*.json"):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if rec.get("image_only") and rec.get("pages"):
            out[rec["document_sha256"]] = int(rec["pages"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True, type=Path)
    ap.add_argument("--blobs", required=True, type=Path)
    ap.add_argument("--docs", required=True, type=Path, help="ocr_docs.csv from the store")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--per-era", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20260828)
    args = ap.parse_args()

    import fitz  # pymupdf, in the box's venv

    pages = image_only_documents(args.text)
    meta = {r["sha256"]: r for r in csv.DictReader(args.docs.open(encoding="utf-8"))}
    pool: dict[str, list[tuple[str, dict]]] = {name: [] for name, _, _ in ERAS}
    for sha in pages:
        m = meta.get(sha)
        if not m or m.get("media_type") != "pdf":
            continue
        era = era_of(m.get("date", ""))
        if era:
            pool[era].append((sha, m))
    rng = random.Random(args.seed)
    drawn = []
    for era, docs in pool.items():
        docs.sort()
        rng.shuffle(docs)
        for sha, m in docs[: args.per_era]:
            page = rng.randrange(pages[sha])  # any page, not only the first: bodies and tables
            drawn.append(
                {
                    "sha256": sha,
                    "page": page,
                    "pages": pages[sha],
                    "era": era,
                    "kind": m["kind"],
                    "record_id": m["record_id"],
                    "raw_docket": m["raw_docket"],
                    "date": m["date"],
                    "type": m["type"],
                    "tier": None,  # assigned by inspection in step 1b
                }
            )
    (args.out / "pages").mkdir(parents=True, exist_ok=True)
    rendered = 0
    for d in drawn:
        src = args.blobs / d["sha256"][:2] / d["sha256"]
        png = args.out / "pages" / f"{d['sha256'][:12]}_p{d['page'] + 1}.png"
        d["png"] = png.name
        if png.exists():
            rendered += 1
            continue
        try:
            with fitz.open(src) as doc:
                pix = doc[d["page"]].get_pixmap(dpi=DPI)
                pix.save(png)
            rendered += 1
        except Exception as e:  # noqa: BLE001 — one unreadable scan must not stop the draw
            d["render_error"] = f"{type(e).__name__}: {e}"
    (args.out / "sample.json").write_text(
        json.dumps(
            {
                "drawn_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                "seed": args.seed,
                "per_era": args.per_era,
                "pool": {era: len(docs) for era, docs in pool.items()},
                "image_only_documents": len(pages),
                "dpi": DPI,
                "pages": drawn,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    by_era = {era: len(docs) for era, docs in pool.items()}
    print(f"image-only documents: {len(pages)}; pool by era: {by_era}")
    print(f"drawn {len(drawn)}, rendered {rendered}")


if __name__ == "__main__":
    main()
