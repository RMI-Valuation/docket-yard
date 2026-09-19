#!/usr/bin/env python3
"""A `dots` worker: leased pages from the queue, read through a vLLM server on this box.

    ./.venv-paddle/bin/python dots_worker.py --db /data/docketyard/ocr/queue.sqlite \\
        --blobs /data/docketyard/blobs --scratch /data/docketyard/ocr/.render      # on the node
    python dots_worker.py --queue http://<node>:8131 --token-file fleet.token \\
        --scratch ./render                                              # on another machine

On the coordinator the worker opens the queue file and reads blobs from disk. Anywhere else
it holds `RemoteQueue` — the same six calls over `queue_server.py` — and reads blobs from its
own `--blobs` mirror if it has one, else fetches each document's bytes once per document (a
claim is usually one document's pages in order).

The worker declares its producer — the pass's key, this host, the engine and its version
as the server reports them — and the queue refuses it if the key is not the pass's
(ADR 0023, ADR 0024 § Owed 1). It then loops: claim a few pages, render each at 200 DPI,
ask the server, post the answer; extend the lease after every page.

WHOSE FAULT A FAILURE IS decides what happens to it, and the default is NOT the page's.
The 2026-09-06 run treated a refused connection like a cut answer and walked 32,849 pages
against a closed port; a worker whose default branch is "the page failed" reproduces that
for every cause nobody named — a missing blob, a venv without pymupdf, a 4xx from a changed
server — only faster, with no server round-trip to slow it. So:

    the page's own      a cut answer (`finish_reason` other than stop), a sheet over the
                        pass's megapixel bound, a page pymupdf opened but will not rasterise,
                        a timeout with the server healthy. Failed FINALLY as `page: ...`;
                        the document is whole with it failed
    the server's        a refused connection, a reset, a body cut off, a 5xx, a timeout with
                        the server unhealthy. The page in flight goes back with its attempt
                        spent (it may be the cause — the 12 MP sheet was); every other leased
                        page goes back unspent; the worker WAITS for the server, claiming
                        nothing, so the queue's read-age grows and the stall alarm can fire.
                        Gone longer than --server-wait: exit 2. Dying on two DIFFERENT pages
                        in a row: the server is the fault, exit 3
    the document's      the blob is missing on the node, or will not open, or has fewer
                        pages than the route says. Not the page's own, so not final: the
                        page goes back as `blob: ...` with its attempt spent, and the
                        document is re-read at a later seed once the blob is there. Not the
                        worker's either — a worker that exited here would be restarted onto
                        the same document, first in claim order, for ever
    nobody's we named   everything else — an import fails, the server answers 4xx or
                        nonsense, the queue stops answering. Every leased page goes back
                        unspent and the worker exits 4 with the traceback; the restart loop's
                        minute is the throttle, and the monitor sees a fleet not reading
    too many in a row   --max-consecutive-failures page-owned failures with no page read
                        between them is a cause nobody has named yet: release, exit 5

THE OVERSIZE GUARD is what the crash taught. The server died on a 20 x 15 inch plan sheet:
12 megapixels at 200 DPI against 3.7 for a letter page, an activation peak vLLM's profiling
never sized for. Measured over all 41,688 degraded pages on 2026-09-09: five exceed 5 MP
and 840 exceed 4 MP (legal size, 4.8 MP, which the run had read without incident). The
bound is the PASS's (`PASSES["dots"]["max_megapixels"]`, 6 MP), so `oversize` means the
same on every node. The page is not quietly read at another DPI — the render is the
reading's key — so a pass under another profile can read it later.
"""

import argparse
import http.client
import json
import socket
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

import fitz  # pymupdf; at the top so a venv without it fails here, not per page

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "rmi-ai-machine"))

from ocr_wave import DOTS, DOTS_MODEL, DOTS_SERVER, _dots_call  # noqa: E402 — the driver's own
from pagequeue import (  # noqa: E402
    PASSES,
    BlobCorrupt,
    BlobMissing,
    BlobUnavailable,
    Queue,
    RemoteQueue,
)
from stopping import Stop, yield_now  # noqa: E402

# The passes this worker can run: every pass whose key is dots.mocr's, since that is the engine
# it talks to. `dots` reads the routed degraded pages; `reread` reads the flagged text-layer
# pages from a page list and writes them as `second` (docs/research/text-quality/). One worker,
# one engine, one key — the pass chooses which queue it claims from, never what it declares.
PASSES_HERE = tuple(p for p, spec in PASSES.items() if spec["key"] == DOTS)
PASS = "dots"  # the default; --pass picks another of PASSES_HERE
DPI = int(PASSES[PASS]["key"]["render_profile"])  # the render IS the key; one source
EXIT_SERVER_GONE, EXIT_SERVER_DIES, EXIT_ENVIRONMENT, EXIT_BREAKER = 2, 3, 4, 5


class PageFailed(Exception):
    """The page's own fault; final."""


class DocumentFailed(Exception):
    """The document's — its bytes are not here or will not open; not final."""


class ServerDown(Exception):
    """The server did not answer; the page is not to blame, or not yet."""


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + msg, flush=True)


def _get(url: str, timeout: int = 10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        return None


def server_healthy(server: str) -> bool:
    """vLLM's /health answers only while the engine is alive; /models answers longer."""
    root = server.rsplit("/v1", 1)[0]
    try:
        with urllib.request.urlopen(root + "/health", timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, http.client.HTTPException, OSError):
        return False


def wait_for_server(server: str, seconds: int) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if server_healthy(server):
            return True
        time.sleep(15)
    return False


def read_page(pdf, no: int, png: Path, server: str, model: str, timeout: int, mp: float):
    """The engine's raw answer for one page, or the exception that says whose fault it is.
    `pdf` is a path on the node or the document's bytes fetched from it."""
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
    try:
        raw, _ = _dots_call(png, server, model, timeout)
        return raw
    except urllib.error.HTTPError as e:
        if e.code >= 500:
            raise ServerDown(f"HTTP {e.code}") from e
        raise  # a 4xx is a changed server or a changed request: the environment's
    except (urllib.error.URLError, http.client.HTTPException, ConnectionError) as e:
        raise ServerDown(f"{type(e).__name__}: {e}") from e
    except TimeoutError as e:
        if server_healthy(server):
            raise PageFailed(f"timeout: {timeout}s with the server healthy") from e
        raise ServerDown(f"timeout {timeout}s and the server unhealthy") from e
    except RuntimeError as e:  # `_dots_call`'s own refusal: a cut page
        if "finish_reason" in str(e):
            raise PageFailed(str(e)) from e
        raise
    finally:
        png.unlink(missing_ok=True)


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, help="the queue file, on the node")
    ap.add_argument("--blobs", type=Path, help="the blobs, on this machine's disk (else fetched)")
    ap.add_argument("--queue", help="the coordinator's queue server, from another machine")
    ap.add_argument("--token-file", type=Path, help="with --queue: the shared token")
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--server", default=DOTS_SERVER)
    ap.add_argument("--model", default=DOTS_MODEL)
    ap.add_argument("--name", default=None, help="worker name; default <host>/<pass>")
    ap.add_argument(
        "--pass",
        dest="pass_",
        default=PASS,
        choices=PASSES_HERE,
        help="which queue to claim from. Both passes here are dots.mocr at 200 DPI — the same"
        " key, so the same producer declaration — and differ in which pages they hold and what"
        " role their reading lands under. Default: dots",
    )
    ap.add_argument("--batch", type=int, default=4, help="pages claimed per lease")
    ap.add_argument("--lease", type=int, default=2700, help="seconds; extended after every page")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per page")
    ap.add_argument("--server-wait", type=int, default=1800, help="seconds to wait for a server")
    ap.add_argument("--max-consecutive-failures", type=int, default=25)
    ap.add_argument("--max-pages", type=int, default=0, help="stop after about this many")
    ap.add_argument(
        "--stop-file",
        type=Path,
        help="exit 0 before the next page when this file exists, releasing the rest unspent"
        " — how a gate stops a worker without waiting for its leases to expire",
    )
    args = ap.parse_args()
    # installed BEFORE the server wait: a reader can spend up to --server-wait here, and a
    # broker that signals during it should get a clean exit rather than a SIGKILL. Nothing is
    # leased yet, so the flag simply stops the first claim.
    stopping = Stop(args.stop_file).install()

    spec = PASSES[args.pass_]
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
    name = args.name or f"{socket.gethostname()}/{args.pass_}"
    if not server_healthy(args.server):
        log(f"no healthy server at {args.server}; waiting up to {args.server_wait}s")
        if not wait_for_server(args.server, args.server_wait):
            log(f"server never answered; exit {EXIT_SERVER_GONE}")
            return EXIT_SERVER_GONE
    models = _get(args.server + "/models") or {}
    served = {m.get("id"): m for m in models.get("data", [])}
    if args.model not in served:
        log(f"server serves {sorted(served)}, not {args.model!r}; exit {EXIT_ENVIRONMENT}")
        return EXIT_ENVIRONMENT
    version = _get(args.server.rsplit("/v1", 1)[0] + "/version") or {}
    producer = {
        **spec["key"],
        "host": socket.gethostname(),
        "engine": "vllm",
        "engine_version": version.get("version"),
        "engine_model": served[args.model].get("root") or args.model,
        "max_megapixels": spec["max_megapixels"],
        "worker": Path(__file__).name,
    }
    if (code := register_or_exit(q, name, args.pass_, producer)) is not None:
        return code
    log(f"{name} registered as {producer}")
    # logged HERE, not at the yield: a page that outruns the grace is SIGKILLed and never
    # reaches `why()`, which is exactly when the operator wants to know what the budget was
    log(f"stop: file {args.stop_file}, signal grace {stopping.grace:.0f}s")
    args.scratch.mkdir(parents=True, exist_ok=True)

    read = failed = streak = 0
    last_server_death: tuple[str, int] | None = None
    held: tuple[str, Path] | None = None  # the last document fetched, for a remote worker
    ids: list[int] = []

    try:
        while True:
            if args.max_pages and read + failed >= args.max_pages:
                log(f"--max-pages reached: {read} read, {failed} failed")
                return 0
            if stopping():
                # before the claim, not after: a stopped reader that claimed first would spend
                # two coordinator round trips inside the grace, and a reader started under the
                # operator's latch would claim and release a batch every restart
                log(stopping.why("nothing claimed"))
                stopping.checkpoint_complete()
                return 0
            jobs = q.claim(name, args.pass_, args.batch, args.lease)
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
                    raw = read_page(
                        pdf, no, png, args.server, args.model, args.timeout, spec["max_megapixels"]
                    )
                except PageFailed as e:
                    if stopping():
                        # A STOP MUST NOT LOOK LIKE A CUT PAGE. A broker signals the whole
                        # scope, so the server can be torn down under an in-flight request and
                        # answer `finish_reason: abort` — which `read_page` calls the page's
                        # own and this branch would fail FINALLY. The document then reads
                        # `whole` for ever and a good page is gone from the pass. Cost when
                        # this fires on a genuinely cut page: one re-render at the next
                        # placement, which fails it finally then.
                        return yield_now(
                            q,
                            name,
                            ids,
                            i,
                            stopping,
                            log,
                            f"stopped mid-page on {sha[:12]} p{no} ({e}); ",
                        )
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
                    q.fail(name, job["job_id"], f"blob: {e}", final=False)
                    failed += 1
                    log(f"  document {sha[:12]} {e}; p{no} back for a later seed")
                except ServerDown as e:
                    if stopping():  # a deliberate stop ended the request: nobody's fault
                        # the page in flight goes back UNSPENT: a stop did not fail it
                        return yield_now(
                            q,
                            name,
                            ids,
                            i,
                            stopping,
                            log,
                            f"stopped mid-page on {sha[:12]} p{no} ({e}); ",
                        )
                    log(f"  SERVER DOWN on {sha[:12]} p{no} ({e}); {len(ids) - i - 1} released")
                    q.fail(name, job["job_id"], f"server: {e}", final=False)
                    q.release(name, ids[i + 1 :])
                    if last_server_death and last_server_death != (sha, no):
                        log("the server died on two different pages in a row; exit 3")
                        return EXIT_SERVER_DIES
                    last_server_death = (sha, no)
                    if not wait_for_server(args.server, args.server_wait):
                        log(
                            f"server did not return in {args.server_wait}s; exit {EXIT_SERVER_GONE}"
                        )
                        return EXIT_SERVER_GONE
                    log("server is back")
                    break
                else:
                    if q.done(name, job["job_id"], raw):
                        read += 1
                        streak = 0
                        last_server_death = None
                    else:
                        log(f"  lease lost on {sha[:12]} p{no}; answer dropped")
                if ids[i + 1 :]:
                    q.extend(name, ids[i + 1 :], args.lease)
            if (read + failed) % 40 < args.batch:
                log(f"  {read} read, {failed} failed this session")
    except Exception:  # noqa: BLE001 — nobody's we named: the queue, the venv, a 4xx
        log(traceback.format_exc())
        try:
            if stopping.signal_name:
                # the twin's rule: a signal while something was in flight is the broker taking
                # the machine, so this exits 0 with its marker rather than as a fault
                return yield_now(q, name, ids, 0, stopping, log, "stopped mid-page; ")
            log("NOT THE PAGE'S FAULT; releasing what is held and exiting")
            q.release(name, ids)  # the whole batch: the page in flight is not to blame
        except Exception:  # noqa: BLE001 — the queue itself may be what failed
            log("could not release; the leases expire on their own")
        return EXIT_ENVIRONMENT
    finally:
        # THE LAST DOCUMENT FETCHED IS A FILE NOW, not bytes that vanish with the process
        # (code review). Up to 1.07 GB of it, on a scratch disk shared with the renders.
        if held is not None:
            held[1].unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
