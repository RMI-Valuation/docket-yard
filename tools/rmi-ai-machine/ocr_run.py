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
import math
import os
import re
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


def _api_key() -> str:
    """The key comes from the environment, or from a file outside the repo. It is never
    placed on a command line and never printed — a process list and a shell history are
    both readable, and this key is short-lived by policy, not by mechanism."""
    key = _clean(os.environ.get("ANTHROPIC_API_KEY", ""))
    if key:
        return key
    for name in (".anthropic-key", ".anthropic_key"):
        f = Path(os.path.expanduser("~")) / name
        if f.is_file():
            key = _clean(f.read_text(encoding="utf-8"))
            if key:
                return key
    raise RuntimeError("no Anthropic key: set ANTHROPIC_API_KEY or write it to ~/.anthropic-key")


def _clean(raw: str) -> str:
    """First line only, and refuse anything that is not a plausible key. An interior
    newline would make http.client raise ValueError(...%r) with the key in the message,
    which main()'s catch-all would print once per page — so it is rejected here, and the
    rejection never quotes the value."""
    key = raw.split("\n", 1)[0].strip()
    if key and not re.fullmatch(r"[A-Za-z0-9_-]{20,200}", key):
        raise RuntimeError("the Anthropic key contains characters a key cannot contain")
    return key


def run_claude(image: Path, cfg: dict) -> str:
    """The reference candidate: a frontier vision model, read through the public API.

    Sent the same PROMPT every other engine gets, so the scorer compares like with like.
    Retries on 429 and 5xx with backoff — a 90-page run trips rate limits otherwise."""
    import base64  # noqa: PLC0415
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    body = json.dumps(
        {
            "model": cfg["model"],
            "max_tokens": 8192,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64.b64encode(image.read_bytes()).decode(),
                            },
                        },
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": cfg["_key"],
        },
    )
    wait = 2.0
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=cfg.get("timeout", 300)) as resp:
                answer = json.loads(resp.read())
            stop = answer.get("stop_reason")
            if stop not in (None, "end_turn"):
                # max_tokens truncates mid-page and refusal returns almost nothing; either
                # one scored as a real read would understate the engine, silently
                raise RuntimeError(f"stop_reason {stop}")
            cfg["_in"] = cfg.get("_in", 0) + answer.get("usage", {}).get("input_tokens", 0)
            cfg["_out"] = cfg.get("_out", 0) + answer.get("usage", {}).get("output_tokens", 0)
            cfg["_sent"] = cfg.get("_sent", 0) + 1
            return "".join(b.get("text", "") for b in answer.get("content", []))
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < 4:
                e.close()
                time.sleep(wait)
                wait *= 2
                continue
            detail = e.read(400).decode("utf-8", "replace").strip()
            raise RuntimeError(f"HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            if attempt < 4:
                time.sleep(wait)
                wait *= 2
                continue
            raise RuntimeError(f"transport: {e.reason}") from None
        except OSError as e:  # urllib wraps the send, not the read: a stalled or reset
            if attempt < 4:  # response surfaces here, and must retry like any transport fault
                time.sleep(wait)
                wait *= 2
                continue
            raise RuntimeError(f"transport: {type(e).__name__}") from None
    raise RuntimeError("retries exhausted")


def _textract_lines(blocks: list) -> list:
    """LINE blocks in the order the PAGE block declares them. The Blocks array itself is
    not documented as reading order, and on a two-column caption or certificate of service
    the two diverge — which would score as a reading error Textract did not make."""
    by_id = {b["Id"]: b for b in blocks if "Id" in b}
    order = []
    for page in (b for b in blocks if b.get("BlockType") == "PAGE"):
        for rel in page.get("Relationships", []):
            if rel.get("Type") == "CHILD":
                order += rel.get("Ids", [])
    chosen = [by_id[i] for i in order if i in by_id] if order else blocks
    return [b.get("Text", "") for b in chosen if b.get("BlockType") == "LINE"]


def run_textract(image: Path, cfg: dict) -> str:
    """Amazon Textract, the managed candidate — through the AWS CLI so that no new
    dependency is taken for a benchmark (the project prefers the standard library, and the
    credentials are already configured for the CLI).

    Two things are kept besides the text: Textract returns a confidence per word, which is
    the signal a tiered pipeline would escalate on, and it is recorded per page so that the
    threshold can be calibrated against the checked ground truth rather than guessed."""
    import base64  # noqa: PLC0415
    import statistics  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    payload = json.dumps({"Document": {"Bytes": base64.b64encode(image.read_bytes()).decode()}})
    fd, name = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        out = subprocess.run(
            [
                "aws",
                "textract",
                "detect-document-text",
                "--region",
                cfg.get("region", "us-east-2"),
                "--cli-input-json",
                f"file://{Path(name).as_posix()}",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            # the CLI is itself a Python program: without this it writes its JSON through
            # the Windows console codepage and dies on any non-ASCII the page contains
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        )
    finally:
        Path(name).unlink(missing_ok=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:300])
    blocks = json.loads(out.stdout).get("Blocks", [])
    words = [b["Confidence"] for b in blocks if b.get("BlockType") == "WORD"]
    lines = _textract_lines(blocks)
    cfg.setdefault("_conf", {})[image.stem] = {
        "words": len(words),
        "mean": round(statistics.mean(words), 3) if words else None,
        "min": round(min(words), 3) if words else None,
        # the tail is what a tiered pipeline escalates on, not the average
        "p10": round(sorted(words)[max(0, math.ceil(0.10 * len(words)) - 1)], 3) if words else None,
        "below_90": sum(1 for c in words if c < 90),
    }
    return "\n".join(lines)


ENGINES = {
    "tesseract": run_tesseract,
    "doctr": run_doctr,
    "vlm": run_vlm,
    "claude": run_claude,
    "textract": run_textract,
}


def _write_conf(out: Path, conf: dict) -> Path:
    """Merge over whatever is already recorded and replace the file atomically. A resumed
    run only fetches the pages missing their text, so the rest of the confidence data
    exists only in the file; losing it means paying for those pages again."""
    path = out / "confidence.json"
    if path.is_file():
        try:
            conf = {**json.loads(path.read_text(encoding="utf-8")), **conf}
        except (OSError, json.JSONDecodeError) as e:
            print(f"  existing {path.name} unreadable ({type(e).__name__}), replacing it")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(conf, indent=1), encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=sorted(ENGINES))
    ap.add_argument("--pages", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model", default="qwen2.5vl:7b", help="vlm and claude")
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
    if args.engine == "claude":
        cfg["_key"] = _api_key()  # fails now, not on page 1 of 90
        if not args.model.startswith("claude"):
            print(f"--model {args.model} is not an Anthropic model id", file=sys.stderr)
            return 1
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
        if not text.strip():
            print(f"  FAILED {image.name} (engine returned nothing)", flush=True)
            failed += 1
            continue
        target.write_text(text, encoding="utf-8", newline="\n")
        done += 1
        if cfg.get("_conf") and n % 20 == 0:  # survive an interrupted run
            _write_conf(args.out, cfg["_conf"])
        if n % 10 == 0 or n == len(images):
            rate = (time.time() - started) / n
            print(f"  {n}/{len(images)}  {rate:.1f}s a page", flush=True)
    print(f"{args.engine}: {done} pages read, {failed} failed, in {time.time() - started:.0f}s")
    if cfg.get("_in") or cfg.get("_out"):
        print(
            f"  tokens: {cfg.get('_in', 0):,} in, {cfg.get('_out', 0):,} out"
            f"  over {cfg.get('_sent', 0)} pages sent"
            f" ({cfg.get('_in', 0) / max(cfg.get('_sent', 0), 1):.0f} in a page)"
        )
    if cfg.get("_conf"):
        print(f"  per-word confidence recorded: {_write_conf(args.out, cfg['_conf'])}")
    print(f"  -> {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
