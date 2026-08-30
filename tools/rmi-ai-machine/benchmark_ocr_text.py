"""Build an OCR-derived text layer for the sixty labelled decisions, so that extraction
can be scored over what OCR produces rather than over the publisher's own text.

Neither benchmark covers the path the scanned backfill actually runs. The OCR benchmark
measures transcription, on pages drawn from image-only files — which are overwhelmingly
filings, and carry almost no citations (seven cited dockets across ninety pages). The
extraction benchmark measures citation finding, on clean text layers. Nothing measures
scanned page -> OCR -> citation, where the errors compound and a docket misread by one
digit becomes a citation to a proceeding that does not exist.

This closes half of that. Each of the sixty labelled decisions is rendered to greyscale
at the benchmark's own dpi, read by Textract, and reassembled with the same page markers
the text layer uses, so `benchmark_run.py` can be pointed at either and scored against the
same `labels.csv`. The difference between the two runs is what OCR costs the citator.

**It is a lower bound, and must be reported as one.** The sixty are born-digital PDFs, so
a render of one is far cleaner than a real scan: no skew, no speckle, no bleed-through, no
stamps. Whatever citation accuracy is lost here is the least that would be lost on the
13,604 image-only files.

    python tools/rmi-ai-machine/benchmark_ocr_text.py --out data/benchmark/text-ocr
"""

import argparse
import importlib.util
import re
import time
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
DPI = 150  # the OCR benchmark's own render resolution (docs/research/ocr-benchmark)
PAGE_MARK = "\n\n===== page {n} =====\n"


def _engine():
    """Borrow the runner's Textract engine rather than restating the call."""
    path = Path(__file__).parent / "ocr_run.py"
    spec = importlib.util.spec_from_file_location("ocr_run", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run_textract


def head_of(text_file: Path) -> str:
    """The two-line header the text layer carries, kept so the two sides differ only in
    how the page bodies were obtained."""
    lines = text_file.read_text(encoding="utf-8", errors="replace").split("\n")
    return "\n".join(lines[:2])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", type=Path, default=ROOT / "data/benchmark/pdf")
    ap.add_argument("--text", type=Path, default=ROOT / "data/benchmark/text")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    run_textract = _engine()
    args.out.mkdir(parents=True, exist_ok=True)
    scratch = args.out / ".pages"
    scratch.mkdir(exist_ok=True)

    # the text layer names files <stratum>-<id>.txt; the PDFs are named <id>.pdf
    by_id = {re.sub(r"^.*-", "", f.stem): f for f in args.text.glob("*.txt")}
    pdfs = sorted(args.pdfs.glob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]

    cfg: dict = {}
    done = failed = pages_read = 0
    started = time.time()
    for pdf in pdfs:
        did = pdf.stem
        target = args.out / (by_id[did].name if did in by_id else f"{did}.txt")
        if target.exists():
            done += 1
            continue
        try:
            body = []
            with pymupdf.open(pdf) as doc:
                for n in range(doc.page_count):
                    img = scratch / f"{did}_p{n + 1}.png"
                    if not img.exists():
                        doc[n].get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY).save(img)
                    body.append(PAGE_MARK.format(n=n + 1) + run_textract(img, cfg))
                    pages_read += 1
        except Exception as e:  # noqa: BLE001 — one bad decision must not end the run
            print(f"  FAILED {did} ({type(e).__name__}: {e})", flush=True)
            failed += 1
            continue
        head = head_of(by_id[did]) if did in by_id else f"{did}\n"
        target.write_text(head + "".join(body), encoding="utf-8", newline="\n")
        done += 1
        print(f"  {done}/{len(pdfs)}  {did}  {pages_read} pages", flush=True)

    took = time.time() - started
    print(f"{done} decisions, {pages_read} pages read, {failed} failed, in {took:.0f}s")
    print(f"  -> {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
