"""Run a local OCR engine over the benchmark's 90 pages (docs/research/ocr-benchmark).

Writes one `<page>.txt` per page image into an output directory, named as the ground truth
is, ready for `ocr_score.py`. Nothing here judges anything; it only records what the engine
read, verbatim, so that the scorer applies the one normaliser to both sides.

    python ocr_run.py --engine tesseract --pages <sample>/pages --out runs/tesseract
    python ocr_run.py --engine doctr --pages <sample>/pages --out runs/doctr
    python ocr_run.py --engine vlm --model qwen2.5vl:7b --pages <sample>/pages --out runs/qwen

Each engine is optional: the runner reports what it cannot find rather than failing late.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROMPT = (
    "Transcribe this scanned page verbatim. Reproduce the text exactly as printed: spelling, "
    "capitalisation, punctuation and numbers, one printed line per line. Do not correct, "
    "expand, summarise or complete anything. If a line runs off the edge of the page, stop "
    "where it stops. Output the transcription only, with no commentary."
)


def run_tesseract(image: Path, _: dict) -> str:
    out = subprocess.run(
        ["tesseract", str(image), "stdout", "--psm", "1", "-l", "eng"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:200])
    return out.stdout


def run_doctr(image: Path, cfg: dict) -> str:
    model = cfg.setdefault("_doctr", None)
    if model is None:
        from doctr.io import DocumentFile  # noqa: PLC0415
        from doctr.models import ocr_predictor  # noqa: PLC0415

        cfg["_doctr"] = model = ocr_predictor(pretrained=True)
        cfg["_docfile"] = DocumentFile
    doc = cfg["_docfile"].from_images([str(image)])
    result = model(doc)
    lines = []
    for page in result.pages:
        for block in page.blocks:
            for line in block.lines:
                lines.append(" ".join(w.value for w in line.words))
    return "\n".join(lines)


def run_vlm(image: Path, cfg: dict) -> str:
    """A vision model served by Ollama on the box."""
    import base64  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    body = json.dumps(
        {
            "model": cfg["model"],
            "prompt": PROMPT,
            "images": [base64.b64encode(image.read_bytes()).decode()],
            "stream": False,
            "options": {"temperature": 0, "num_ctx": 8192},
        }
    ).encode()
    req = urllib.request.Request(
        cfg.get("host", "http://127.0.0.1:11434") + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=cfg.get("timeout", 600)) as resp:
        return json.loads(resp.read())["response"]


ENGINES = {"tesseract": run_tesseract, "doctr": run_doctr, "vlm": run_vlm}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=sorted(ENGINES))
    ap.add_argument("--pages", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model", default="qwen2.5vl:7b", help="vlm only")
    ap.add_argument("--host", default="http://127.0.0.1:11434", help="vlm only")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    images = sorted(args.pages.glob("*.png"))
    if args.limit:
        images = images[: args.limit]
    if not images:
        print(f"no page images in {args.pages}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    cfg = {"model": args.model, "host": args.host}
    fn = ENGINES[args.engine]
    done = failed = 0
    started = time.time()
    for n, image in enumerate(images, 1):
        target = args.out / (image.stem + ".txt")
        if target.exists():
            done += 1
            continue
        try:
            text = fn(image, cfg)
        except Exception as e:  # noqa: BLE001 — one bad page must not end the run
            print(f"  FAILED {image.name} ({type(e).__name__}: {e})", flush=True)
            failed += 1
            continue
        target.write_text(text, encoding="utf-8", newline="\n")
        done += 1
        if n % 10 == 0 or n == len(images):
            rate = (time.time() - started) / n
            print(f"  {n}/{len(images)}  {rate:.1f}s a page", flush=True)
    print(f"{args.engine}: {done} pages read, {failed} failed, in {time.time() - started:.0f}s")
    print(f"  -> {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
