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
from html.parser import HTMLParser
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


class _TableHTML(HTMLParser):
    """A `<table>` as a dense grid, expanding `rowspan`/`colspan`.

    PaddleOCR-VL returns table structure as HTML and the ground truth writes a dense grid,
    so a merged cell has to be written into every slot it covers — otherwise the columns
    after it shift left and every cell in the row scores as wrong.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.grid: list[list[str]] = []
        self._row = -1
        self._col = 0
        self._cell: list[str] | None = None
        self._span = (1, 1)
        self._taken: set[tuple[int, int]] = set()

    def _int(self, attrs: dict, name: str) -> int:
        try:
            return max(1, int(attrs.get(name, "1")))
        except (TypeError, ValueError):
            return 1

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "tr":
            self._row += 1
            self._col = 0
        elif tag in ("td", "th"):
            # A cell outside any row is malformed HTML a generative model can emit, and the
            # row index would still be -1: `self.grid[-1]` then writes into the LAST row, or
            # raises IndexError on the first cell. Either way the page was swallowed as a
            # failure and dropped from the score. It opens a row instead.
            if self._row < 0:
                self._row = 0
                self._col = 0
            a = dict(attrs)
            self._span = (self._int(a, "rowspan"), self._int(a, "colspan"))
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag not in ("td", "th") or self._cell is None:
            return
        text = " ".join("".join(self._cell).split())
        self._cell = None
        while (self._row, self._col) in self._taken:
            self._col += 1
        rows, cols = self._span
        for r in range(self._row, self._row + rows):
            for c in range(self._col, self._col + cols):
                self._taken.add((r, c))
                while len(self.grid) <= r:
                    self.grid.append([])
                while len(self.grid[r]) <= c:
                    self.grid[r].append("")
                self.grid[r][c] = text
        self._col += cols


def _table_block(html_text: str) -> list:
    """Every HTML table in one layout block, as the ground truth writes them: `[table]`,
    tab-separated rows, `[end table]`. An empty grid yields nothing rather than an empty
    block.

    EACH `<table>` GETS ITS OWN BLOCK. One layout block can carry two of them, and feeding
    both to a single parser continues the second table's rows into the first one's grid —
    one merged table with the wrong shape where the page has two.
    """
    out = []
    for part in re.split(r"(?=<table[\s>])", html_text):
        if "<table" not in part:
            continue
        parser = _TableHTML()
        parser.feed(part)
        width = max((len(r) for r in parser.grid), default=0)
        rows = [r + [""] * (width - len(r)) for r in parser.grid if any(c.strip() for c in r)]
        if rows:
            out += ["[table]", *["\t".join(r) for r in rows], "[end table]"]
    return out


def run_paddleocr_vl(image: Path, cfg: dict) -> str:
    """PaddleOCR-VL, through its own pipeline: PP-DocLayoutV3 detects the layout, and each
    element is recognised by the 0.9B model.

    IT MUST BE THE PIPELINE, NOT THE MODEL. The 0.9B alone is an element recogniser: fed a
    whole 150-DPI page through `transformers` it tokenises at native resolution, holds the
    GPU for over 27 minutes and then runs out of memory on a 12 GB card. The pipeline is
    what the weights are for.

    AND THE BACKEND MUST BE A SERVER. The pipeline's `native` generation backend needs over
    eight minutes a page on a 4070; the same page through a vLLM server takes 1.1 seconds.
    Start one with:

        vllm serve <PaddleOCR-VL-1.6 dir> --served-model-name PaddleOCR-VL-1.6-0.9B \\
            --trust-remote-code --port 8118 --gpu-memory-utilization 0.80

    `VLLM_USE_FLASHINFER_SAMPLER=0` is needed on a box with a driver but no CUDA toolkit:
    flashinfer JIT-compiles its kernels and wants `nvcc`, which a driver does not provide.
    """
    pipeline = cfg.get("_paddleocr_vl")
    if pipeline is None:
        from paddleocr import PaddleOCRVL  # noqa: PLC0415

        cfg["_paddleocr_vl"] = pipeline = PaddleOCRVL(
            vl_rec_backend=cfg.get("vl_backend", "vllm-server"),
            vl_rec_server_url=cfg.get("vl_server", "http://127.0.0.1:8118/v1"),
        )
    out = []
    for res in pipeline.predict(str(image)):
        for block in res.json["res"].get("parsing_res_list") or []:
            content = block.get("block_content") or ""
            if block.get("block_label") == "table" and "<table" in content:
                out += _table_block(content)
            elif content.strip():
                out.append(content)
    return "\n".join(out)


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


def _textract_grid(table: dict, by_id: dict) -> tuple[list[list[str]], set]:
    """One TABLE block as a dense grid of cell strings, plus the WORD ids it consumed.

    CELL blocks carry RowIndex/ColumnIndex from 1, and a merged cell appears as a separate
    MERGED_CELL block over the same CELLs — so reading CELL alone gives every cell once,
    which is what a cell-by-cell comparison wants.
    """
    cells, consumed = {}, set()
    for rel in table.get("Relationships", []):
        if rel.get("Type") != "CHILD":
            continue
        for cid in rel.get("Ids", []):
            cell = by_id.get(cid, {})
            if cell.get("BlockType") != "CELL":
                continue
            words = []
            for crel in cell.get("Relationships", []):
                if crel.get("Type") != "CHILD":
                    continue
                for wid in crel.get("Ids", []):
                    child = by_id.get(wid, {})
                    if child.get("BlockType") == "WORD":
                        words.append(child.get("Text", ""))
                        consumed.add(wid)
                    elif child.get("BlockType") == "SELECTION_ELEMENT":
                        # a tick box reads as its state, not as empty
                        words.append("[X]" if child.get("SelectionStatus") == "SELECTED" else "[ ]")
            cells[(cell.get("RowIndex", 0), cell.get("ColumnIndex", 0))] = " ".join(words)
    if not cells:
        return [], consumed
    rows = max(r for r, _ in cells)
    cols = max(c for _, c in cells)
    grid = [[cells.get((r, c), "") for c in range(1, cols + 1)] for r in range(1, rows + 1)]
    return grid, consumed


def _textract_page(blocks: list) -> str:
    """The page as the ground truth writes it: body lines in reading order, and each table
    as a tab-separated `[table]` block.

    A LINE whose words the table already consumed is dropped rather than printed twice —
    Textract returns both views of the same words, and emitting both would score every
    table cell as duplicated text.
    """
    by_id = {b["Id"]: b for b in blocks if "Id" in b}
    order = []
    for page in (b for b in blocks if b.get("BlockType") == "PAGE"):
        for rel in page.get("Relationships", []):
            if rel.get("Type") == "CHILD":
                order += rel.get("Ids", [])
    chosen = [by_id[i] for i in order if i in by_id] if order else blocks

    grids, consumed = {}, set()
    for b in chosen:
        if b.get("BlockType") == "TABLE":
            grid, used = _textract_grid(b, by_id)
            grids[b["Id"]] = grid
            consumed |= used

    out = []
    for b in chosen:
        kind = b.get("BlockType")
        if kind == "TABLE":
            grid = grids.get(b["Id"]) or []
            if grid:
                out.append("[table]")
                out += ["\t".join(row) for row in grid]
                out.append("[end table]")
        elif kind == "LINE":
            ids = [
                i
                for rel in b.get("Relationships", [])
                if rel.get("Type") == "CHILD"
                for i in rel.get("Ids", [])
            ]
            if ids and sum(1 for i in ids if i in consumed) * 2 >= len(ids):
                continue  # the table above already printed these words
            out.append(b.get("Text", ""))
    return "\n".join(out)


def _textract_call(image: Path, cfg: dict, args: list) -> list:
    """One Textract call through the AWS CLI, returning its Blocks.

    Through the CLI so that no new dependency is taken for a benchmark (the project prefers
    the standard library, and the credentials are already configured for it).
    """
    import base64  # noqa: PLC0415
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
                *args,
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
    return json.loads(out.stdout).get("Blocks", [])


def _textract_conf(blocks: list, image: Path, cfg: dict) -> list:
    """Record Textract's per-word confidence for the page and return the words.

    Textract returns a confidence per word, which is the signal a tiered pipeline would
    escalate on; it is kept per page so the threshold can be calibrated against the checked
    ground truth rather than guessed."""
    import statistics  # noqa: PLC0415

    words = [b["Confidence"] for b in blocks if b.get("BlockType") == "WORD"]
    cfg.setdefault("_conf", {})[image.stem] = {
        "words": len(words),
        "mean": round(statistics.mean(words), 3) if words else None,
        "min": round(min(words), 3) if words else None,
        # the tail is what a tiered pipeline escalates on, not the average
        "p10": round(sorted(words)[max(0, math.ceil(0.10 * len(words)) - 1)], 3) if words else None,
        "below_90": sum(1 for c in words if c < 90),
    }
    return words


def run_textract_tables(image: Path, cfg: dict) -> str:
    """Textract with its TABLES feature — `analyze-document`, not `detect-document-text`.

    THE PLAIN ENGINE BELOW CANNOT SCORE A TABLE AT ALL, and until 2026-09-01 nothing said
    so: `detect-document-text` returns no TABLE block, `_textract_lines` keeps only LINEs,
    and the ninety-page benchmark therefore scored 0 of 167 table cells for Textract — a
    harness result read for four days as an engine result. It costs ten times as much a
    page ($0.015 against $0.0015), which is why it is a separate engine rather than the
    default: the tabular tier is 4% of a random draw of pages.
    """
    blocks = _textract_call(image, cfg, ["analyze-document", "--feature-types", "TABLES"])
    _textract_conf(blocks, image, cfg)
    # THE RAW BLOCKS ARE KEPT, because the page above is one reading of them and the choice
    # of which TABLE to believe has to be answered from data rather than tuned against the
    # tier labels of the very sample being scored. Re-reading a saved response is free; a
    # second pass over 122 pages is not.
    out_dir = cfg.get("_out_dir")
    if out_dir is not None:
        (Path(out_dir) / f"{image.stem}.blocks.json").write_text(
            json.dumps(blocks), encoding="utf-8", newline="\n"
        )
    return _textract_page(blocks)


def run_textract(image: Path, cfg: dict) -> str:
    """Amazon Textract's plain text detection. Reads no table structure — see
    `run_textract_tables`, which does."""
    blocks = _textract_call(image, cfg, ["detect-document-text"])
    _textract_conf(blocks, image, cfg)
    return "\n".join(_textract_lines(blocks))


ENGINES = {
    "tesseract": run_tesseract,
    "doctr": run_doctr,
    "vlm": run_vlm,
    "claude": run_claude,
    "textract": run_textract,
    "textract-tables": run_textract_tables,
    "paddleocr-vl": run_paddleocr_vl,
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
    ap.add_argument("--vl-backend", default="vllm-server", help="paddleocr-vl only")
    ap.add_argument("--vl-server", default="http://127.0.0.1:8118/v1", help="paddleocr-vl only")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    images = sorted(args.pages.glob("*.png"))
    if args.limit:
        images = images[: args.limit]
    if not images:
        print(f"no page images in {args.pages}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    # NOT `_out`: that key is the Claude engine's output-token counter, and a Path under it
    # walks into the token summary's format string below
    cfg = {
        "model": args.model,
        "host": args.host,
        "_out_dir": args.out,
        "vl_backend": args.vl_backend,
        "vl_server": args.vl_server,
    }
    if args.engine == "claude":
        cfg["_key"] = _api_key()  # fails now, not on page 1 of 90
        if not args.model.startswith("claude"):
            print(f"--model {args.model} is not an Anthropic model id", file=sys.stderr)
            return 1
    fn = ENGINES[args.engine]
    done = failed = empty = 0
    started = time.time()
    for n, image in enumerate(images, 1):
        target = args.out / (image.stem + ".txt")
        if target.exists() and target.stat().st_size > 0:
            done += 1
            continue
        # AN EMPTY FILE IS RE-READ, NOT RESUMED PAST. Writing the empty read (below) is what
        # lets a genuinely blank page score, but a served model that returns nothing because
        # the server fell over produces the same file — and cached, that fault would score
        # as a perfect blank page for ever, at CER 0.0 and no invented text. Re-reading costs
        # one call and is deterministic on a page that really is blank.
        try:
            text = fn(image, cfg)
        except Exception as e:  # noqa: BLE001 — one bad page must not end the run
            print(f"  FAILED {image.name} ({type(e).__name__}: {e})", flush=True)
            failed += 1
            continue
        if not text.strip():
            # NOT A FAILURE, and calling it one cost the benchmark real pages. The sample's
            # blank page reads `[blank page]` in the ground truth, and a map that carries no
            # prose is a page whose right answer is nearly nothing — so an engine that emits
            # nothing there is CORRECT, and the safest engines are the ones that do. Dropping
            # the page instead scored the timid engine on a smaller, harder set than the
            # inventive one: Tesseract lost two of its nine graphic pages this way, which are
            # exactly the two it got right. The empty read is written and scored.
            print(f"  empty {image.name} (engine read nothing)", flush=True)
            empty += 1
        target.write_text(text, encoding="utf-8", newline="\n")
        done += 1
        if cfg.get("_conf") and n % 20 == 0:  # survive an interrupted run
            _write_conf(args.out, cfg["_conf"])
        if n % 10 == 0 or n == len(images):
            rate = (time.time() - started) / n
            print(f"  {n}/{len(images)}  {rate:.1f}s a page", flush=True)
    summary = f"{args.engine}: {done} pages read, {failed} failed"
    if empty:
        summary += f", {empty} read as blank"
    print(summary + f", in {time.time() - started:.0f}s")
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
