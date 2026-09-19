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
that fails (an import, no CUDA, too little free GPU memory, weights not in the cache, a
revision it cannot name) is the environment's: exit 4, nothing held. Then the worker declares
its producer — the pass's key, this host, `transformers` and its version, the model and its
snapshot revision, the page bound — and the queue refuses it if the key is not the pass's
(ADR 0023, ADR 0024 § Owed 1).

WHOSE FAULT A FAILURE IS:

    the page's own      a sheet over the pass's megapixel bound (`oversize: N MP at 150 DPI`);
                        a page pymupdf opened but will not rasterise; a generation that
                        produced max_new_tokens tokens and no EOS (`finish_reason length`, the
                        name dots uses for a cut answer). Failed FINALLY as `page: ...`; the
                        document is whole with it failed
    the card's          out of GPU memory, twice on one page with the cache emptied between.
                        NOT the page's (below). The page goes back as `gpu: oom` with its
                        attempt spent, the rest of the batch unspent, and the batch is claimed
                        again; OOM on two DIFFERENT pages in a row is the card: exit 3
    the document's      the blob is missing, will not open, or has fewer pages than the route
                        says: `blob: ...`, attempt spent, not final; re-read at a later seed
    the engine's        the model raised anything else while reading a page: that page goes
                        back as `engine: <Exception>` with its attempt spent — it may be the
                        cause, and claims run in document order, so a refunded attempt would
                        bring it back first after every restart for ever — the pages after it
                        unspent; exit 4. After max_attempts it fails, not finally, and the
                        document is re-read at a later seed rather than counted whole
    no answer           the model answered '' (whitespace only). A tabular page is one the
                        layout model found a table on, and the PP-OCRv6 cache has text on all
                        but 6 of them, so '' is the model failing — a template or processor
                        drift, an immediate EOS — never a blank page. `engine: empty answer`,
                        attempt spent, not final, never posted as done; consecutive ones count
                        toward the breaker. Final, a systemic fault would mark every document
                        whole with no text and no alarm: the 2026-09-06 shape
    nobody's we named   the queue, an import, anything outside a page's read. Every leased
                        page goes back unspent; exit 4
    too little memory   free GPU memory under the floor before loading or before a claim:
                        exit 4 with nothing claimed
    too many in a row   --max-consecutive-failures page-owned failures with no page read
                        between: release, exit 5

WHY OUT-OF-MEMORY IS NOT THE PAGE'S. A 1B model reading one page at a time varies by the page,
so an OOM LOOKS like the page's — but the likeliest cause on this fleet is another process on
the card: the dots vLLM server holds 90% of the 4070. Failed finally, every such page would be
counted whole with no text, and a later seed would skip its document: the restart loop would
throw away a batch a minute. So memory is checked before the model loads (`MIN_FREE_TO_LOAD`)
and before every claim (`MIN_HEADROOM`), and an OOM that survives the retry is the card's. A
page that truly exceeds the card fails non-finally three times and its document is re-read at
a later seed, which costs a little box time and loses nothing.

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
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "rmi-ai-machine"))

from ocr_run import (  # noqa: E402 — the benchmark's own call, not a copy of it
    HUNYUAN_MAX_NEW_TOKENS,
    load_hunyuan,
    run_hunyuan_ocr,
)
from pagequeue import (  # noqa: E402
    PASSES,
    BlobCorrupt,
    BlobMissing,
    BlobUnavailable,
    Queue,
    RemoteQueue,
)
from stopping import Stop, yield_now  # noqa: E402

PASS = "tabular"
DPI = int(PASSES[PASS]["key"]["render_profile"])  # the render IS the key; one source
MODEL = "tencent/HunyuanOCR"
EXIT_CARD, EXIT_ENVIRONMENT, EXIT_BREAKER = 3, 4, 5

GIB = 1024**3
# The floors. The model is 2.0 GB of VRAM in bfloat16 (the benchmark's measurement,
# `ocr_run.run_hunyuan_ocr`); a page's activations and KV cache at up to 2.4 MP and 4,096 new
# tokens are given 2 GiB. The headroom is a bound, not a measurement: the parity probe on the
# GPU owes the real peak, and these follow it. The point is to refuse a card another process
# holds, not to size this one exactly.
MIN_HEADROOM = 2 * GIB
MIN_FREE_TO_LOAD = 2 * GIB + MIN_HEADROOM


class PageFailed(Exception):
    """The page's own fault; final."""


class DocumentFailed(Exception):
    """The document's — its bytes are not here or will not open; not final."""


class GpuOutOfMemory(Exception):
    """Out of GPU memory after the retry: the card's, not the page's; not final."""


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
    """`read()`, once more after `empty_cache()` if it ran out of GPU memory; a second OOM
    raises `GpuOutOfMemory`. Any other exception is not classified here: it rises."""
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
        raise GpuOutOfMemory("oom") from e


def short_of_memory(free: int, reserved: int, allocated: int, need: int) -> str | None:
    """Why the card cannot take work, or None. What this process could use is the device's
    free memory plus what torch has cached and is not using — its own cache is not a
    stranger's — so a worker that has read large pages is not refused for its own cache."""
    usable = free + max(reserved - allocated, 0)
    if usable < need:
        return f"{usable / GIB:.1f} GiB usable on the card, {need / GIB:.1f} GiB needed"
    return None


def claim_if_room(q, name: str, batch: int, lease: int, memory, need: int = MIN_HEADROOM):
    """The next batch, or `(None, why)` without claiming when the card is short. `memory()`
    answers `(free, reserved, allocated)` in bytes."""
    why = short_of_memory(*memory(), need)
    if why:
        return None, why
    return q.claim(name, PASS, batch, lease), None


def give_back(q, name: str, ids: list[int], i: int, error: str) -> None:
    """The page in flight at `ids[i]` goes back with its attempt SPENT — it may be the cause —
    and every page after it unspent. `error` must not be the page's own (`page:`), so the
    queue never counts its document whole on this failure."""
    q.fail(name, ids[i], error, final=False)
    q.release(name, ids[i + 1 :])


def card_at_fault(last_oom: tuple[str, int] | None, here: tuple[str, int]) -> bool:
    """Two OOMs on DIFFERENT pages in a row: the card, not a page (dots' server-dies rule)."""
    return last_oom is not None and last_oom != here


EMPTY_ANSWER = "engine: empty answer"


def post_answer(q, name: str, job_id: int, raw: str) -> str:
    """Posts a page's answer: `done`, `lost` (the lease expired; the answer is dropped) or
    `empty` — an answer with no text is the model failing on a page that has a table, so it
    goes back not finally with its attempt spent and is never posted as done."""
    if not raw.strip():
        q.fail(name, job_id, EMPTY_ANSWER, final=False)
        return "empty"
    return "done" if q.done(name, job_id, raw) else "lost"


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


def page_index(no: int, page_count: int) -> int:
    """The 0-based index of page `no` of a document of `page_count` pages, or DocumentFailed.
    Both ends: page 0 would index the LAST page (`doc[-1]`) and read the wrong one silently
    (Copilot on PR #34, 2026-09-17)."""
    if not 1 <= no <= page_count:
        raise DocumentFailed(f"has {page_count} pages, the route says {no}")
    return no - 1


def register_or_exit(q, name: str, pass_: str, producer: dict) -> int | None:
    """Register with the queue, or the environment exit code with the reason logged. A queue
    that is locked, unreachable or refuses the key is the environment's failure, not an
    unclassified crash (Copilot on PR #34, 2026-09-17)."""
    try:
        q.register(name, pass_, producer)
    except Exception as e:  # noqa: BLE001 — every way registration fails is the environment's
        log(f"could not register with the queue ({type(e).__name__}: {e}); exit {EXIT_ENVIRONMENT}")
        return EXIT_ENVIRONMENT
    return None


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
        page = doc[page_index(no, doc.page_count)]
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

    try:
        render_page(pdf, no, png, mp)  # inside: the finally removes a half-written PNG too

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


def gpu_memory() -> tuple[int, int, int]:
    """(free on the device, reserved by this process, allocated by this process), bytes."""
    import torch  # noqa: PLC0415

    free, _ = torch.cuda.mem_get_info()
    return free, torch.cuda.memory_reserved(), torch.cuda.memory_allocated()


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
    # installed BEFORE the model loads: 2 GB of weights takes long enough that a broker can
    # signal us during it, and a reader that ignored that would be SIGKILLed having read
    # nothing. Nothing is leased yet, so the flag simply stops the first claim.
    stopping = Stop(args.stop_file).install()

    spec = PASSES[PASS]
    if args.model != MODEL:  # the key names HunyuanOCR-1.5; another model is another pass
        log(f"--model {args.model!r} is not {MODEL!r}, which the {PASS} key names; exit 4")
        return EXIT_ENVIRONMENT
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
        claimable = q.claimable(PASS)
    except Exception:  # noqa: BLE001 — the queue, not the model
        log(f"the queue did not answer; nothing loaded or claimed; exit {EXIT_ENVIRONMENT}")
        log(traceback.format_exc())
        return EXIT_ENVIRONMENT
    if not claimable:
        log("queue empty; the model is not loaded")
        return 0
    try:
        import fitz  # noqa: F401, PLC0415 — here, so a venv without pymupdf fails before a claim
        import torch  # noqa: PLC0415
        import transformers  # noqa: PLC0415

        if not torch.cuda.is_available():
            log(f"torch sees no CUDA device; exit {EXIT_ENVIRONMENT}")
            return EXIT_ENVIRONMENT
        why = short_of_memory(*gpu_memory(), MIN_FREE_TO_LOAD)
        if why:
            log(f"the card is short before loading ({why}); another process holds it? exit 4")
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
    if (code := register_or_exit(q, name, PASS, producer)) is not None:
        return code
    log(f"{name} registered as {producer}")
    # logged HERE, not at the yield: a page that outruns the grace is SIGKILLed and never
    # reaches `why()`, which is exactly when the operator wants to know what the budget was
    log(f"stop: file {args.stop_file}, signal grace {stopping.grace:.0f}s")
    args.scratch.mkdir(parents=True, exist_ok=True)

    read = failed = streak = 0
    last_oom: tuple[str, int] | None = None
    held: tuple[str, Path] | None = None  # the last document fetched, for a remote worker
    ids: list[int] = []
    in_flight: int | None = None  # the index in `ids` of the page the model is reading

    try:
        while True:
            if args.max_pages and read + failed >= args.max_pages:
                log(f"--max-pages reached: {read} read, {failed} failed")
                return 0
            ids = []
            if stopping():
                # before the claim, not after: a stopped reader that claimed first would spend
                # two coordinator round trips inside the grace, and a reader started under the
                # operator's latch would claim and release a batch every restart
                log(stopping.why("nothing claimed"))
                stopping.checkpoint_complete()
                return 0
            jobs, why = claim_if_room(q, name, args.batch, args.lease, gpu_memory)
            if jobs is None:
                log(f"the card is short ({why}); nothing claimed; exit {EXIT_ENVIRONMENT}")
                return EXIT_ENVIRONMENT
            if not jobs:
                log(f"queue empty: {read} read, {failed} failed this session")
                return 0
            ids = [j["job_id"] for j in jobs]
            for i, job in enumerate(jobs):
                if stopping():
                    return yield_now(q, name, ids, i, stopping, log)
                sha, no = job["document_sha256"], job["page_no"]
                png = args.scratch / f"{name.replace('/', '_')}_{sha[:12]}_p{no}.png"
                try:
                    if args.blobs:  # on the node, or a mirror of its blobs: read the disk
                        pdf = args.blobs / sha[:2] / sha
                    else:
                        if held is None or held[0] != sha:
                            # STREAMED TO DISK, NEVER INTO RAM. `read_page` takes a path as
                            # readily as bytes, and the documents this change newly makes
                            # reachable (a pruned mirror used to be a flat 404) reach 1.07 GB
                            # in this record — which is what OOM-killed the instance in August,
                            # and the smallest box that leases pages has 8 GB (code review).
                            if held is not None:
                                held[1].unlink(missing_ok=True)  # the previous document
                                held = None
                            spool = args.scratch / f"doc-{sha}.pdf"
                            try:
                                held = (sha, q.blob_into(sha, spool))
                            except BlobMissing as e:
                                raise DocumentFailed(f"not in the store: {e}") from e
                            except BlobCorrupt as e:
                                # the store's, not the page's, and it will not fix itself on a
                                # retry — but it is not final either: a document is never
                                # written off on one answer from a store having a bad day. The
                                # coordinator has already printed the alarm.
                                raise DocumentFailed(f"the store is corrupt here: {e}") from e
                        pdf = held[1]
                    in_flight = i
                    raw = read_page(cfg, pdf, no, png, spec["max_megapixels"])
                    in_flight = None
                except PageFailed as e:
                    in_flight = None
                    q.fail(name, job["job_id"], f"page: {e}", final=True)
                    failed += 1
                    streak += 1
                    log(f"  page failed {sha[:12]} p{no} ({e})")
                    if streak >= args.max_consecutive_failures:
                        q.release(name, ids[i + 1 :])
                        log(f"{streak} page failures in a row, no page read; exit {EXIT_BREAKER}")
                        return EXIT_BREAKER
                except BlobUnavailable as e:
                    # THE ENVIRONMENT'S, SO NO PAGE PAYS. The node is unreachable or its
                    # credential is: every page in the fleet would fail identically, so this
                    # one and every one after it go back UNSPENT and the worker exits for the
                    # resubmitter to bring back (ADR 0025 addendum, proposal 2). Retrying here
                    # is the loop the old bare re-raise produced, minus the traceback.
                    in_flight = None
                    # THE RELEASE GOES TO THE SAME NODE THAT JUST FAILED, so it may fail
                    # too — and an exception here would escape as the traceback this whole
                    # mapping exists to prevent (ingest review). If it does not land, the
                    # leases expire instead, and `_reap` SPENDS the attempt rather than
                    # refunding it: the pages are not lost and no document is counted whole,
                    # but they are not free either. Said plainly in the log rather than
                    # claiming "unspent" when that may not be what happened.
                    try:
                        q.release(name, ids[i:])
                        back = f"{len(ids) - i} released unspent"
                    except Exception as release_failed:  # noqa: BLE001 — the node is the fault
                        back = (
                            f"{len(ids) - i} could NOT be released"
                            f" ({type(release_failed).__name__}); they wait for lease expiry,"
                            " which spends an attempt each"
                        )
                    log(f"the node cannot serve documents ({e}); {back}; exit {EXIT_ENVIRONMENT}")
                    return EXIT_ENVIRONMENT
                except DocumentFailed as e:
                    in_flight = None
                    q.fail(name, job["job_id"], f"blob: {e}", final=False)
                    failed += 1
                    log(f"  document {sha[:12]} {e}; p{no} back for a later seed")
                except GpuOutOfMemory:
                    in_flight = None
                    if stopping():
                        # THE CARD WAS TAKEN, NOT LOST. A broker starting the other workload
                        # before we exit makes our generate OOM; charging the page an attempt
                        # for that is the "default is not the page's" rule inverted, and two
                        # such pages in a row would exit 3 calling a healthy card faulty.
                        return yield_now(
                            q,
                            name,
                            ids,
                            i,
                            stopping,
                            log,
                            f"stopped mid-page on {sha[:12]} p{no}; ",
                        )
                    give_back(q, name, ids, i, "gpu: oom")
                    log(f"  OUT OF GPU MEMORY on {sha[:12]} p{no}; {len(ids) - i - 1} released")
                    if card_at_fault(last_oom, (sha, no)):
                        log(f"out of memory on two different pages in a row; exit {EXIT_CARD}")
                        return EXIT_CARD
                    last_oom = (sha, no)
                    break  # claim again: the page comes back first while it has attempts
                else:
                    posted = post_answer(q, name, job["job_id"], raw)
                    if posted == "done":
                        read += 1
                        streak = 0
                        last_oom = None
                    elif posted == "empty":
                        failed += 1
                        streak += 1
                        log(f"  EMPTY ANSWER on {sha[:12]} p{no}; back with its attempt spent")
                        if streak >= args.max_consecutive_failures:
                            q.release(name, ids[i + 1 :])
                            log(f"{streak} failures in a row, no page read; exit {EXIT_BREAKER}")
                            return EXIT_BREAKER
                    else:
                        log(f"  lease lost on {sha[:12]} p{no}; answer dropped")
                if ids[i + 1 :]:
                    q.extend(name, ids[i + 1 :], args.lease)
            if (read + failed) % 40 < args.batch:
                log(f"  {read} read, {failed} failed this session")
    except Exception as exc:  # noqa: BLE001 — the engine's on a page, else nobody's we named
        log(traceback.format_exc())
        try:
            if stopping.signal_name:
                # A SIGNAL, not the stop file. A broker taking the card makes the engine raise
                # on the way down, so the page is innocent. The FILE says nothing of the kind:
                # a page that breaks the engine while the operator happens to have written it
                # would be refunded and claimed first after every restart for ever, which is
                # what the branch below exists to prevent.
                return yield_now(q, name, ids, 0, stopping, log, "stopped mid-page; ")
            if in_flight is not None:
                # the model raised on this page: its attempt stays spent, or a page that
                # breaks the engine is claimed first after every restart for ever
                log("THE ENGINE RAISED ON A PAGE; that page's attempt spent, the rest released")
                give_back(q, name, ids, in_flight, f"engine: {type(exc).__name__}: {exc}")
            else:
                log("NOT THE PAGE'S FAULT; releasing what is held and exiting")
                q.release(name, ids)
        except Exception:  # noqa: BLE001 — the queue itself may be what failed
            log("could not give the pages back; the leases expire on their own")
        return EXIT_ENVIRONMENT
    finally:
        # THE LAST DOCUMENT FETCHED IS A FILE NOW, not bytes that vanish with the process
        # (code review). Up to 1.07 GB of it, on a scratch disk shared with the renders.
        if held is not None:
            held[1].unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
