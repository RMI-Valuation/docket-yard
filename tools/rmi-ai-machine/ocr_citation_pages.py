"""Render the OCR citation benchmark's labelled pages (docs/research/ocr-citation-benchmark/).

The labels are drafted from these images and checked against them, so both see the same
pixels. 150 DPI greyscale: the OCR benchmark's own render resolution
(`docs/research/ocr-benchmark/README.md`), at which a person reads a docket number without
zooming and a drafting agent reads a page image whole. Greyscale because the record is
monochrome (86 of the OCR benchmark's 90 pages are exactly R == G == B), so colour adds bytes
and no information.

    python tools/rmi-ai-machine/ocr_citation_pages.py <blobs dir> [--out data/ocr-citation/pages]

`<blobs dir>` is a blob store laid out as `<first two hex>/<sha256>`, which is how both the
instance cache and RMI-AI-MACHINE's mirror hold the Board's files. Every render is named
`<sha256[:12]>_p<page>.png`, the page being the store's 1-based `page_no`, which is the PDF's
own page index plus one. A page the PDF does not have is refused loudly, never skipped: it
would mean `labelled_pages` and the bytes disagree about which document this is.
"""

import json
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "docs" / "research" / "ocr-citation-benchmark" / "sample.json"
DPI = 150


def main(blobs: Path, out: Path) -> int:
    drawn = json.loads(SAMPLE.read_text(encoding="utf-8"))["drawn"]
    out.mkdir(parents=True, exist_ok=True)
    rendered = kept = 0
    for d in drawn:
        sha = d["document_sha256"]
        pdf = blobs / sha[:2] / sha
        if not pdf.is_file():
            raise SystemExit(f"{sha}: not in {blobs}")
        with pymupdf.open(pdf) as doc:
            for page_no in d["labelled_pages"]:
                if not 1 <= page_no <= doc.page_count:
                    raise SystemExit(f"{sha}: page {page_no} of a {doc.page_count}-page PDF")
                target = out / f"{sha[:12]}_p{page_no}.png"
                if target.exists():
                    kept += 1  # counted apart, so a re-run says whether it drew anything
                    continue
                pix = doc[page_no - 1].get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
                pix.save(target)
                rendered += 1
    print(f"{rendered} pages rendered, {kept} already there, {len(drawn)} documents, in {out}")
    return 0


USAGE = "usage: ocr_citation_pages.py <blobs dir> [--out <dir>]"

if __name__ == "__main__":
    argv = sys.argv[1:]
    out = ROOT / "data/ocr-citation/pages"
    if "--out" in argv:
        at = argv.index("--out")
        if at + 1 >= len(argv):
            raise SystemExit(USAGE)
        out = Path(argv[at + 1])
        del argv[at : at + 2]
    if len(argv) != 1:
        raise SystemExit(USAGE)
    raise SystemExit(main(Path(argv[0]), out))
