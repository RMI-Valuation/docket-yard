#!/usr/bin/env python3
"""A `tabular` worker: leased pages from the queue, read by HunyuanOCR-1.5 in this process.

    <hunyuan venv>/bin/python hunyuan_worker.py --db /data/docketyard/ocr/queue.sqlite \\
        --blobs /data/docketyard/blobs --scratch /data/docketyard/ocr/.render      # on the node
    python hunyuan_worker.py --queue http://<node>:8131 --token-file fleet.token \\
        --scratch ./render                                              # on another machine

ocr-plan.md decision 6: HunyuanOCR-1.5 reads the pages the router classed `tabular`. It runs
THE WAY THE BENCHMARK RAN IT — `ocr_run.run_hunyuan_ocr`, transformers in-process, bfloat16,
the shipped prompt with its one clause changed, greedy, 4,096 new tokens at most — at 150 DPI,
the router's render and the benchmark's pages. Not through vLLM: 0.28's HunYuanVL fails on
engine start, and the measured numbers are this path's. The interpreter is a venv with
transformers 5.x, torch with CUDA and pymupdf; it is not the paddle venv (`ocr_run`'s
docstring says why the two cannot share one).

THIS IS `dots_worker.py`'S TWIN, MINUS THE SERVER. The lease loop, the stop file, the breaker
and the failure taxonomy are the same, and are duplicated rather than factored out: the dots
loop is interleaved with its server's life (wait, die-twice, release) and moving it would
change a worker that is running. A change to either loop's rules belongs in both.

The model loads ONCE, before anything is claimed — a queue with nothing to claim loads
nothing, since the restart loop would otherwise load 2 GB of weights a minute — and a load
that fails (an import, no CUDA, weights not in the cache, a revision it cannot name) is the
environment's: exit 4, nothing held. Then the worker declares its producer — the pass's key,
this host, `transformers` and its version, the model and its snapshot revision, the page bound
— and the queue refuses it if the key is not the pass's (ADR 0023, ADR 0024 § Owed 1).

WHOSE FAULT A FAILURE IS:

    the page's own      a sheet over the pass's megapixel bound (`oversize: N MP at 150 DPI`);
                        a page pymupdf opened but will not rasterise; a generation that
                        produced max_new_tokens tokens and no EOS (`finish_reason length`, the
                        name dots uses for a cut answer); out of GPU memory TWICE on the page
                        (`oom`). Failed FINALLY as `page: ...`; the document is whole with it
    the document's      the blob is missing, will not open, or has fewer pages than the route
                        says: `blob: ...`, attempt spent, not final; re-read at a later seed
    nobody's we named   everything else — the queue, an import, a model that raises something
                        other than out-of-memory. Every leased page goes back unspent; exit 4
    too many in a row   --max-consecutive-failures page-owned failures with no page read
                        between: release, exit 5

WHY OUT-OF-MEMORY IS THE PAGE'S, after one retry. The model is 1B parameters in about 2 GB
and this process reads one page at a time, so what varies between pages is the page — its
image tokens and the length of its answer — and nothing else in the process. A first OOM may
be the allocator's fragmentation after an earlier large page, so the cache is emptied and the
page read again; a second on the same page with the cache empty is that page's size. Unlike
vLLM's engine, torch survives an OOM in the process, so there is no server to wait for. The
one cause this misnames is ANOTHER PROCESS on the card (the dots vLLM server holds 90% of the
4070): then every page fails `oom`, no page reads, and the breaker's exit 5 is what stops it.
Stop `dots-vllm` before starting this worker on a shared card (docs/compute-fleet.md).

THE OVERSIZE GUARD is the pass's (`PASSES["tabular"]["max_megapixels"]`, 6 MP): measured
2026-09-15 over the 26,294 tabular pages at 150 DPI, median 2.1 MP, p99 2.4, 29 over 6. The
page is not read at another DPI — the render is the key.
"""

import argparse
import os
import socket
import sys
import time
import traceback
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "rmi-ai-machine"))

from ocr_run import (  # noqa: E402 — the benchmark's own call, not a copy of it
    HUNYUAN_MAX_NEW_TOKENS,
    load_hunyuan,
    run_hunyuan_ocr,
)
from pagequeue import PASSES, Queue, RemoteQueue  # noqa: E402

PASS = "tabular"
DPI = int(PASSES[PASS]["key"]["render_profile"])  # the render IS the key; one source
MODEL = "tencent/HunyuanOCR"
EXIT_ENVIRONMENT, EXIT_BREAKER = 4, 5


class PageFailed(Exception):
    """The page's own fault; final."""


class DocumentFailed(Exception):
    """The document's — its bytes are not here or will not open; not final."""


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + msg, flush=True)


# --- pure: the classification, testable without torch ---------------------------------------


def generation_failure(new_tokens: int, max_new_tokens: int, ended_with_eos: bool) -> str | None:
    """`finish_reason length` when the generation was cut, else None. generate() stops at EOS
    or at max_new_tokens and reports neither, so a full budget without EOS is the evidence."""
    if new_tokens >= max_new_tokens and not ended_with_eos:
        return "finish_reason length"
    return None


def read_with_oom_retry(read, is_oom, empty_cache):
    """`read()`, once more after `empty_cache()` if it ran out of GPU memory; a second OOM is
    the page's (`PageFailed("oom")`). Any other exception is not classified here: it rises."""
    try:
        return read()
    except Exception as e:  # noqa: BLE001 — only an OOM is handled; the rest re-raises
        if not is_oom(e):
            raise
    empty_cache()
    try:
        return read()
    except Exception as e:  # noqa: BLE001
        if not is_oom(e):
            raise
        empty_cache()
        raise PageFailed("oom") from e


def hf_hub_cache() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def weights_revision(name: str, commit_hash: str | None, cache: Path) -> str | None:
    """The snapshot the weights came from: the hash transformers recorded on the loaded
    config, else the cache's `refs/main`. None when neither says — and then the worker does
    not claim, because a producer that cannot name its weights cannot declare itself."""
    if commit_hash:
        return commit_hash
    ref = cache / ("models--" + name.replace("/", "--")) / "refs" / "main"
    if not ref.exists():
        return None
    return ref.read_text(encoding="utf-8").strip() or None


# --- one page -------------------------------------------------------------------------------


def render_page(pdf, no: int, png: Path, mp: float) -> None:
    """The page at the pass's DPI, or the exception that says whose fault it is. Twin of the
    first half of `dots_worker.read_page`."""
    import fitz  # noqa: PLC0415 — imported at start by main(), so a venv without it fails there

    try:
        if isinstance(pdf, Path):
            if not pdf.exists():
                raise DocumentFailed("missing on the node")
            opened = fitz.open(pdf)
        else:
            opened = fitz.open(stream=pdf, filetype="pdf")
    except DocumentFailed:
        raise
    except Exception as e:  # noqa: BLE001 — a file that will not open at all
        raise DocumentFailed(f"will not open: {type(e).__name__}: {e}") from e
    with opened as doc:
        if no > doc.page_count:
            raise DocumentFailed(f"has {doc.page_count} pages, the route says {no}")
        page = doc[no - 1]
        r = page.rect
        megapixels = (r.width / 72 * DPI) * (r.height / 72 * DPI) / 1e6
        if megapixels > mp:
            raise PageFailed(f"oversize: {megapixels:.1f} MP at {DPI} DPI")
        try:
            page.get_pixmap(dpi=DPI).save(png)
        except Exception as e:  # noqa: BLE001 — opened, would not rasterise: the page's
            raise PageFailed(f"render: {type(e).__name__}: {e}") from e


def read_page(cfg: dict, pdf, no: int, png: Path, mp: float) -> str:
    """The model's raw answer for one page. The flattening to text is `collect`'s
    (`ocr_wave.hunyuan_page`), so the answer is posted whole."""
    import torch  # noqa: PLC0415

    render_page(pdf, no, png, mp)
    try:

        def once() -> dict:
            cfg.pop("_hunyuan_last", None)
            run_hunyuan_ocr(png, cfg)
            return cfg["_hunyuan_last"]

        last = read_with_oom_retry(
            once, lambda e: isinstance(e, torch.cuda.OutOfMemoryError), torch.cuda.empty_cache
        )
    finally:
        png.unlink(missing_ok=True)
    cut = generation_failure(last["new_tokens"], HUNYUAN_MAX_NEW_TOKENS, last["ended_with_eos"])
    if cut:
        raise PageFailed(cut)
    return last["raw"]


# --- the loop -------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, help="the queue file, on the node")
    ap.add_argument("--blobs", type=Path, help="the blobs, on this machine's disk (else fetched)")
    ap.add_argument("--queue", help="the coordinator's queue server, from another machine")
    ap.add_argument("--token-file", type=Path, help="with --queue: the shared token")
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--model", default=MODEL, help="the Hugging Face name; the cache must hold it")
    ap.add_argument("--name", default=None, help="worker name; default <host>/tabular")
    ap.add_argument("--batch", type=int, default=4, help="pages claimed per lease")
    ap.add_argument("--lease", type=int, default=2700, help="seconds; extended after every page")
    ap.add_argument("--max-consecutive-failures", type=int, default=25)
    ap.add_argument("--max-pages", type=int, default=0, help="stop after about this many")
    ap.add_argument(
        "--stop-file",
        type=Path,
        help="exit 0 before the next page when this file exists, releasing the rest unspent",
    )
    args = ap.parse_args()

    spec = PASSES[PASS]
    if args.blobs and not args.blobs.is_dir():
        log(f"--blobs {args.blobs} is not a directory; exit {EXIT_ENVIRONMENT}")
        return EXIT_ENVIRONMENT
    if args.queue:
        if not args.token_file:
            log(f"--queue needs --token-file; exit {EXIT_ENVIRONMENT}")
            return EXIT_ENVIRONMENT
        q = RemoteQueue(args.queue, args.token_file.read_text(encoding="utf-8").strip())
    elif args.db and args.blobs:
        q = Queue(args.db)
    else:
        log(f"give --db and --blobs (the coordinator) or --queue; exit {EXIT_ENVIRONMENT}")
        return EXIT_ENVIRONMENT
    name = args.name or f"{socket.gethostname()}/{PASS}"

    try:
        if not q.claimable(PASS):
            log("queue empty; the model is not loaded")
            return 0
        import fitz  # noqa: F401, PLC0415 — here, so a venv without pymupdf fails before a claim
        import torch  # noqa: PLC0415
        import transformers  # noqa: PLC0415

        if not torch.cuda.is_available():
            log(f"torch sees no CUDA device; exit {EXIT_ENVIRONMENT}")
            return EXIT_ENVIRONMENT
        cfg: dict = {"hunyuan_model": args.model}
        model = load_hunyuan(cfg)
    except Exception:  # noqa: BLE001 — nothing is claimed yet: the environment's
        log(f"the model did not load; exit {EXIT_ENVIRONMENT}")
        log(traceback.format_exc())
        return EXIT_ENVIRONMENT
    revision = weights_revision(
        args.model, getattr(model.config, "_commit_hash", None), hf_hub_cache()
    )
    if not revision:
        log(f"cannot name the weights' revision of {args.model}; exit {EXIT_ENVIRONMENT}")
        return EXIT_ENVIRONMENT
    producer = {
        **spec["key"],
        "host": socket.gethostname(),
        "engine": "transformers",
        "engine_version": transformers.__version__,
        "engine_model": args.model,
        "weights_revision": revision,
        "max_new_tokens": HUNYUAN_MAX_NEW_TOKENS,
        "max_megapixels": spec["max_megapixels"],
        "worker": Path(__file__).name,
    }
    q.register(name, PASS, producer)
    log(f"{name} registered as {producer}")
    args.scratch.mkdir(parents=True, exist_ok=True)

    read = failed = streak = 0
    held: tuple[str, bytes] | None = None  # the last document fetched, for a remote worker
    ids: list[int] = []

    def stopping() -> bool:
        return bool(args.stop_file and args.stop_file.exists())

    try:
        while True:
            if args.max_pages and read + failed >= args.max_pages:
                log(f"--max-pages reached: {read} read, {failed} failed")
                return 0
            jobs = q.claim(name, PASS, args.batch, args.lease)
            if not jobs:
                log(f"queue empty: {read} read, {failed} failed this session")
                return 0
            ids = [j["job_id"] for j in jobs]
            for i, job in enumerate(jobs):
                if stopping():
                    q.release(name, ids[i:])
                    log(f"stop file present; {len(ids) - i} pages released; exit 0")
                    return 0
                sha, no = job["document_sha256"], job["page_no"]
                png = args.scratch / f"{name.replace('/', '_')}_{sha[:12]}_p{no}.png"
                try:
                    if args.blobs:  # on the node, or a mirror of its blobs: read the disk
                        pdf = args.blobs / sha[:2] / sha
                    else:
                        if held is None or held[0] != sha:
                            try:
                                held = (sha, q.blob(sha))
                            except urllib.error.HTTPError as e:
                                if e.code == 404:
                                    raise DocumentFailed("not on the node") from e
                                raise
                        pdf = held[1]
                    raw = read_page(cfg, pdf, no, png, spec["max_megapixels"])
                except PageFailed as e:
                    q.fail(name, job["job_id"], f"page: {e}", final=True)
                    failed += 1
                    streak += 1
                    log(f"  page failed {sha[:12]} p{no} ({e})")
                    if streak >= args.max_consecutive_failures:
                        q.release(name, ids[i + 1 :])
                        log(f"{streak} page failures in a row, no page read; exit {EXIT_BREAKER}")
                        return EXIT_BREAKER
                except DocumentFailed as e:
                    q.fail(name, job["job_id"], f"blob: {e}", final=False)
                    failed += 1
                    log(f"  document {sha[:12]} {e}; p{no} back for a later seed")
                else:
                    if q.done(name, job["job_id"], raw):
                        read += 1
                        streak = 0
                    else:
                        log(f"  lease lost on {sha[:12]} p{no}; answer dropped")
                if ids[i + 1 :]:
                    q.extend(name, ids[i + 1 :], args.lease)
            if (read + failed) % 40 < args.batch:
                log(f"  {read} read, {failed} failed this session")
    except Exception:  # noqa: BLE001 — nobody's we named: the queue, the venv, the model
        log("NOT THE PAGE'S FAULT; releasing what is held and exiting")
        log(traceback.format_exc())
        try:
            q.release(name, ids)  # the whole batch: the page in flight is not to blame
        except Exception:  # noqa: BLE001 — the queue itself may be what failed
            log("could not release; the leases expire on their own")
        return EXIT_ENVIRONMENT


if __name__ == "__main__":
    sys.exit(main())
