#!/usr/bin/env python3
"""A `dots` worker: leased pages from the queue, read through a vLLM server on this box.

    ./.venv-paddle/bin/python dots_worker.py --db /data/docketyard/ocr/queue.sqlite \\
        --blobs /data/docketyard/blobs --scratch /data/docketyard/ocr/.render      # on the node
    python dots_worker.py --queue http://<node>:8131 --token-file fleet.token \\
        --scratch ./render                                              # on another machine

On the node the worker opens the queue file and reads blobs from disk. Anywhere else it
holds `RemoteQueue` — the same six calls over `queue_server.py` — and fetches each document's
bytes from the node once per document (a claim is usually one document's pages in order).

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

from ocr_wave import DOTS_MODEL, DOTS_SERVER, _dots_call  # noqa: E402 — the driver's own
from pagequeue import PASSES, Queue, RemoteQueue  # noqa: E402

PASS = "dots"
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, help="the queue file, on the node")
    ap.add_argument("--blobs", type=Path, help="the blobs directory, on the node")
    ap.add_argument("--queue", help="the node's queue server, from another machine")
    ap.add_argument("--token-file", type=Path, help="with --queue: the shared token")
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--server", default=DOTS_SERVER)
    ap.add_argument("--model", default=DOTS_MODEL)
    ap.add_argument("--name", default=None, help="worker name; default <host>/dots")
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

    spec = PASSES[PASS]
    if args.queue:
        if not args.token_file:
            log(f"--queue needs --token-file; exit {EXIT_ENVIRONMENT}")
            return EXIT_ENVIRONMENT
        q = RemoteQueue(args.queue, args.token_file.read_text(encoding="utf-8").strip())
    elif args.db and args.blobs and args.blobs.is_dir():
        q = Queue(args.db)
    else:
        log(f"give --db and --blobs (on the node) or --queue (elsewhere); exit {EXIT_ENVIRONMENT}")
        return EXIT_ENVIRONMENT
    name = args.name or f"{socket.gethostname()}/{PASS}"
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
    q.register(name, PASS, producer)
    log(f"{name} registered as {producer}")
    args.scratch.mkdir(parents=True, exist_ok=True)

    read = failed = streak = 0
    last_server_death: tuple[str, int] | None = None
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
                    if isinstance(q, Queue):
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
                    raw = read_page(
                        pdf, no, png, args.server, args.model, args.timeout, spec["max_megapixels"]
                    )
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
                except ServerDown as e:
                    if stopping():  # a deliberate stop ended the request: nobody's fault
                        q.release(name, ids[i:])
                        log(f"stopped mid-page on {sha[:12]} p{no}; {len(ids) - i} released")
                        return 0
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
        log("NOT THE PAGE'S FAULT; releasing what is held and exiting")
        log(traceback.format_exc())
        try:
            q.release(name, ids)  # the whole batch: the page in flight is not to blame
        except Exception:  # noqa: BLE001 — the queue itself may be what failed
            log("could not release; the leases expire on their own")
        return EXIT_ENVIRONMENT


if __name__ == "__main__":
    sys.exit(main())
