#!/usr/bin/env python3
"""The pages dots refused, read once by Claude Sonnet 5 through the Message Batches API.

The operator's decision of 2026-09-15 (docs/deferred.md § that date): the 134 degraded pages the
fleet's `dots` pass failed FINALLY — 101 answers cut at the token limit, 33 sheets over the pass's
megapixel bound — get one paid batch, as its own pass with its own key, loaded only on his go.
The benchmark measured Claude Sonnet 5 at 10.5% CER on the degraded tier, the best of the engines
it ran (docs/research/ocr-benchmark/README.md), with the ground-truth caveat recorded there.

    python3 claude_refused.py pages --queue ~/docketyard/ocr/queue.sqlite > pages.tsv   # the NUC
    python3 claude_refused.py render --pages pages.tsv --blobs B [--blobs B2] --out R   # the box
    uv run --no-project --with anthropic python claude_refused.py submit --renders R \\
        --state state.json --confirm-spend                                           # anywhere
    uv run --no-project --with anthropic python claude_refused.py collect --renders R \\
        --state state.json --out OCR_ROOT

THE RENDER IS THE KEY (ADR 0023), and one profile names one rule: every page at 200 DPI, the
degraded tier's render, EXCEPT that a page whose long edge would pass the model's 2,576-pixel
limit is rendered at the DPI that makes it exactly that — the API would otherwise downscale it
out of sight. `200-max2576` says so; the DPI and pixels each page actually got are kept whole in
the engine payload, so a reader can tell a letter page from a shrunk plan sheet.

A PAGE THAT DID NOT READ IS A FAILURE, NEVER A BLANK. A result that errored, expired or was
cancelled, or a message that stopped for any reason but `end_turn` (a cut answer, a refusal), is
counted in `pages_failed` and left out, exactly as the fleet's collector treats a failed page.

The prompt is `ocr_run.PROMPT`, the one the benchmark sent every engine, and the request carries no
thinking or sampling parameter, as the benchmark's did — its conditions are the measured ones.
"""

import argparse
import base64
import json
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ocr_run import PROMPT  # noqa: E402 — the benchmark's own instruction, stdlib-only import
from ocr_wave import _write, now, reading_document, route_of, shard  # noqa: E402

MODEL = "claude-sonnet-5"
BASE_DPI = 200
MAX_EDGE = 2576
RENDER_PROFILE = f"{BASE_DPI}-max{MAX_EDGE}"
MAX_TOKENS = 16000
ROOT = "claude-refused"
PAYLOAD_KIND = "claude.json"
ROUTE_CLASS = "degraded"  # the dots pass reads only degraded pages (pagequeue.PASSES["dots"])


def final_failures(queue: Path, pass_: str = "dots") -> list[tuple[str, int, str]]:
    """(sha, page, reason) for every page the pass failed as the page's own fault."""
    con = sqlite3.connect(f"file:{queue.as_posix()}?mode=ro", uri=True)
    try:
        return [
            (sha, int(no), err)
            for sha, no, err in con.execute(
                "SELECT document_sha256, page_no, error FROM job WHERE pass = ?"
                " AND state = 'failed' AND error LIKE 'page:%' ORDER BY 1, 2",
                (pass_,),
            )
        ]
    finally:
        con.close()


def render_dpi(width_pt: float, height_pt: float) -> float:
    """200, or the lower DPI at which the page's long edge is exactly MAX_EDGE pixels."""
    long_pt = max(width_pt, height_pt)
    return min(float(BASE_DPI), MAX_EDGE * 72.0 / long_pt)


def custom_id(i: int) -> str:
    """The batch API allows [a-zA-Z0-9_-]{1,64}; a sha plus a page does not fit, so the
    state file maps each id back to its page."""
    return f"page-{i:04d}"


def request_params(png: bytes) -> dict:
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64.standard_b64encode(png).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    }


def reading_documents(manifest: dict, state: dict, results: list[dict]) -> list[dict]:
    """One reading document per document, from the batch's results as plain dicts
    (`result.model_dump()`), keyed back through the state file's id map."""
    by_id = {r["custom_id"]: r for r in results}
    docs: dict[str, dict] = {}
    for cid, page in state["ids"].items():
        sha, no = page["sha"], page["page_no"]
        d = docs.setdefault(sha, {"engine": [], "pages": [], "failed": 0, "versions": set()})
        got = by_id.get(cid)
        result = (got or {}).get("result") or {}
        message = result.get("message") if result.get("type") == "succeeded" else None
        if not message or message.get("stop_reason") != "end_turn":
            d["failed"] += 1
            continue
        text = "".join(
            b.get("text", "") for b in message.get("content", []) if b.get("type") == "text"
        )
        d["versions"].add(message.get("model") or MODEL)
        d["engine"].append({"page_no": no, "render": manifest[f"{sha}:{no}"], "message": message})
        d["pages"].append(
            {
                "page_no": no,
                "text": text,
                "member": f"engine/pages/{len(d['engine']) - 1}",
                "route": route_of(ROUTE_CLASS),
            }
        )
    out = []
    for sha, d in sorted(docs.items()):
        if len(d["versions"]) > 1:  # one document, one key: a batch served by two snapshots is two
            raise ValueError(f"{sha}: pages answered by {sorted(d['versions'])}")
        key = {
            "method": MODEL,
            "method_version": next(iter(d["versions"]), MODEL),
            "render_profile": RENDER_PROFILE,
        }
        out.append(
            reading_document(
                sha,
                key,
                "primary",
                PAYLOAD_KIND,
                d["engine"],
                d["pages"],
                pages_failed=d["failed"],
                outcome="read" if d["pages"] else "failed",
                ran_at=state["ended_at"],
            )
        )
    return out


# --- the commands ---------------------------------------------------------------------------


def cmd_pages(args) -> int:
    for sha, no, err in final_failures(args.queue):
        print(f"{sha}\t{no}\t{err}")
    return 0


def cmd_render(args) -> int:
    import fitz  # noqa: PLC0415 — pymupdf, on the box

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for line in args.pages.read_text(encoding="utf-8").splitlines():
        sha, no, *_ = line.split("\t")
        no = int(no)
        blob = next((b / sha[:2] / sha for b in args.blobs if (b / sha[:2] / sha).exists()), None)
        if blob is None:
            raise SystemExit(f"{sha}: no blob under {[str(b) for b in args.blobs]}")
        with fitz.open(blob) as doc:
            page = doc[no - 1]
            dpi = render_dpi(page.rect.width, page.rect.height)
            # a matrix, not `dpi=`: the capped DPI is fractional, and pymupdf's `dpi` is an int
            zoom = dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            if max(pix.width, pix.height) > MAX_EDGE:  # rounding up by a pixel: shrink once more
                zoom *= MAX_EDGE / max(pix.width, pix.height)
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                dpi = zoom * 72.0
            pix.save(args.out / f"{sha}_p{no}.png")
            manifest[f"{sha}:{no}"] = {
                "dpi": round(dpi, 3),
                "width": pix.width,
                "height": pix.height,
            }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"rendered {len(manifest)} pages; profile {RENDER_PROFILE}")
    return 0


def _client():
    import os  # noqa: PLC0415

    import anthropic  # noqa: PLC0415

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        f = Path.home() / ".anthropic-key"
        key = f.read_text(encoding="utf-8").strip() if f.is_file() else ""
    if not key:
        raise SystemExit("no Anthropic key: set ANTHROPIC_API_KEY or write ~/.anthropic-key")
    return anthropic.Anthropic(api_key=key)


def cmd_submit(args) -> int:
    manifest = json.loads((args.renders / "manifest.json").read_text(encoding="utf-8"))
    if args.state.exists():
        raise SystemExit(f"{args.state} exists: this pass was already submitted")
    pages = sorted(manifest)
    ids = {
        custom_id(i): {"sha": k.split(":")[0], "page_no": int(k.split(":")[1])}
        for i, k in enumerate(pages)
    }
    print(f"{len(ids)} requests to {MODEL}, render {RENDER_PROFILE}, max_tokens {MAX_TOKENS}")
    if not args.confirm_spend:
        print("not submitted: pass --confirm-spend (a paid run)")
        return 0
    client = _client()
    requests = [
        {
            "custom_id": cid,
            "params": request_params(
                (args.renders / f"{p['sha']}_p{p['page_no']}.png").read_bytes()
            ),
        }
        for cid, p in ids.items()
    ]
    batch = client.messages.batches.create(requests=requests)
    state = {"batch_id": batch.id, "submitted_at": now(), "ids": ids, "model": MODEL}
    args.state.write_text(json.dumps(state, indent=1), encoding="utf-8")
    print(f"batch {batch.id} submitted; state in {args.state}")
    return 0


def cmd_collect(args) -> int:
    state = json.loads(args.state.read_text(encoding="utf-8"))
    manifest = json.loads((args.renders / "manifest.json").read_text(encoding="utf-8"))
    client = _client()
    while True:
        batch = client.messages.batches.retrieve(state["batch_id"])
        if batch.processing_status == "ended":
            break
        print(f"{batch.processing_status}: {batch.request_counts}", flush=True)
        time.sleep(args.poll)
    results = [r.model_dump(mode="json") for r in client.messages.batches.results(batch.id)]
    state["ended_at"] = state.get("ended_at") or now()
    args.state.write_text(json.dumps(state, indent=1), encoding="utf-8")
    (args.state.parent / f"{batch.id}.results.json").write_text(
        json.dumps(results), encoding="utf-8"
    )
    docs = reading_documents(manifest, state, results)
    usage = {"input_tokens": 0, "output_tokens": 0}
    for r in results:
        msg = (r.get("result") or {}).get("message") or {}
        for k in usage:
            usage[k] += (msg.get("usage") or {}).get(k) or 0
    for doc in docs:
        _write(shard(args.out / ROOT, doc["document_sha256"]), doc)
    _write(
        args.out / ROOT / "_manifest.json",
        {
            "batch_id": batch.id,
            "model": MODEL,
            "render_profile": RENDER_PROFILE,
            "documents": len(docs),
            "pages_read": sum(len(d["pages"]) for d in docs),
            "pages_failed": sum(d["pages_failed"] for d in docs),
            "usage": usage,
            "written_at": now(),
        },
    )
    print(f"{len(docs)} reading documents under {args.out / ROOT}; usage {usage}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pages")
    p.add_argument("--queue", required=True, type=Path)
    p = sub.add_parser("render")
    p.add_argument("--pages", required=True, type=Path)
    p.add_argument("--blobs", required=True, type=Path, action="append")
    p.add_argument("--out", required=True, type=Path)
    p = sub.add_parser("submit")
    p.add_argument("--renders", required=True, type=Path)
    p.add_argument("--state", required=True, type=Path)
    p.add_argument("--confirm-spend", action="store_true")
    p = sub.add_parser("collect")
    p.add_argument("--renders", required=True, type=Path)
    p.add_argument("--state", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--poll", type=int, default=60)
    args = ap.parse_args()
    return {"pages": cmd_pages, "render": cmd_render, "submit": cmd_submit, "collect": cmd_collect}[
        args.cmd
    ](args)


if __name__ == "__main__":
    sys.exit(main())
