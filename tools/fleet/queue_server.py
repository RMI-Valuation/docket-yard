#!/usr/bin/env python3
"""The queue's transport: the six lease calls and the blobs, over HTTP, for a worker on
another machine (docs/compute-fleet.md § Joining a node).

    python3 queue_server.py --db /data/docketyard/ocr/queue.sqlite \\
        --blobs /data/docketyard/blobs --token-file /data/docketyard/fleet.token --port 8131
    DY_S3_BUCKET=docketyard-prod ...       # and a miss is refetched, not a failed page

    POST /register  {name, pass, producer}                 -> {}            (KeyMismatch: 409)
    POST /claim     {worker, pass, n, lease_seconds}       -> {jobs: [...]}
    POST /extend    {worker, job_ids, lease_seconds}       -> {}
    POST /release   {worker, job_ids}                      -> {}
    POST /done      {worker, job_id, raw}                  -> {accepted: bool}
    POST /fail      {worker, job_id, error, final}         -> {}            (ValueError: 400)
    GET  /blob/<sha256>                                    -> the document's bytes
    GET  /pending?pass=<pass>                              -> {pass, claimable}

Every request carries `Authorization: Bearer <token>`, the token being one line in a file
that exists on the node and on each joining machine and in no repository. The LAN is the
operator's, but a write API with no credential is a habit, not a boundary. `pagequeue.
RemoteQueue` is the client; it has the `Queue` methods a worker uses and nothing else, so the
worker does not know which it holds. Nothing here is the monitor: that stays read-only on
its own port. **Standard library only, the refetch included** — see below.

A BLOB MISS IS A FETCH, NOT A FAILURE (ADR 0025 addendum, proposals 5 and 6, Accepted
2026-09-19), when `DY_S3_BUCKET` and AWS credentials are in the environment. Without them
this 404s when the mirror does not hold a document, and that 404 is what a worker reports as
`blob: ...`: it failed 728 pages across 310 documents in the tabular pass of 2026-09-18,
every one of which was in the store the whole time. The mirror is a cache of the store, never
the store (ADR 0022 D2), so the coordinator refetches on a miss the way the instance's
document route already does, and the cache is then allowed to be cold, pruned or absent. What
this buys is not the bytes — it is that no box has to hold 109 GB to serve them, and that the
box owning the mirror can refill it, which until now only a DIFFERENT box could do.

**`docketyard.capture.s3`, not boto3, and the first draft of this was returned twice for
using boto3.** That module exists because "boto3 would be a 100 MB dependency for one signed
GET"; the credential is read from the environment exactly as the web tier reads it, so there
is one way to reach the store in this project and not two.

**NOTHING IS BUFFERED.** A document in this record reaches 1.07 GB (the CP–KCS application,
FD 36500) and reading one into memory is what OOM-killed the instance on 2026-08-26. The
store's answer is streamed to a temp file with a per-chunk digest, as `web/documents.py`
already does, and the mirror hit is streamed from disk too — which it was not before this
change, though it is the common path.

**The sha IS the identity** (ADR 0002), so a fetched object is verified before it is cached or
served, and a mismatch is loud and never written: that would be a corrupt object in the store
of record. Whose fault a miss is follows the queue's own grammar, and the classification is
STRUCTURAL — the store's status code, never the text of an exception:

  * **404, the document's** — absent from the store. The page goes back unspent.
  * **403, the environment's** — the credential is missing, expired or not scoped here. This
    is why the credential carries `s3:ListBucket` on the blob prefix as well as `s3:GetObject`
    (the operator, 2026-09-19): WITHOUT `ListBucket`, S3 answers 403 for a key that is simply
    absent, so a genuinely missing document and a broken credential become the same answer and
    this distinction cannot be made at all.
  * **any other status, or no answer, the environment's** — a 500, a 503, a reset, a timeout.
  * **a hash that does not match, the store's** — 502, and it is printed where the monitor
    sees it.

Nothing here mints, prints or logs a credential. **What DOES change is what `fleet.token` is
worth**: `/blob/<sha>` was "what this box holds" and is now a read-through proxy for every
object under the store's blob prefix, to anyone holding the token. ADR 0025 addendum item 6
anticipates this — the documents are the public record and a `GetObject` credential is not a
door into the store — but it is said here rather than left to be discovered. `_authorised()`
runs BEFORE the fetch, so a stranger on the LAN cannot make this box spend the store's egress.
"""

import argparse
import contextlib
import hashlib
import http.client
import json
import os
import secrets
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))  # the project's own signed GET; still standard library

from pagequeue import (  # noqa: E402
    HEX64,  # one definition: the client checks the same alphabet before it asks
    PASSES,
    BlobCorrupt,
    BlobMissing,
    BlobUnavailable,
    KeyMismatch,
    Queue,
)

from docketyard.capture import s3  # noqa: E402

BLOB_PREFIX = "blobs/"  # the store's layout, as `records.blob_path` and the web tier use it
CHUNK = 1 << 20  # what a document is streamed in, both from the store and from the mirror
SPOOL = "qs-"  # our spool files, so the sweep at start cannot take anything else's


def store_fetcher(fetch=None):
    """`fetch_into(sha, dest)` — stream the store's copy of a document into `dest`, verified —
    or None when this box has no store configured and a miss stays a miss.

    `fetch` is the signed GET, injected so the miss path is testable exactly as
    `web/documents.local_file` injects it; production passes `s3.from_env()`, which reads
    `DY_S3_BUCKET` and the AWS keys from the environment and raises if a bucket is named
    without them — a store named but unreachable refuses to start rather than 503ing on the
    first miss hours into a pass."""
    if fetch is None:
        return None

    def fetch_into(sha: str, dest: Path) -> int:
        digest = hashlib.sha256()
        size = 0
        declared = None
        try:
            with dest.open("wb") as out, fetch(f"{BLOB_PREFIX}{sha[:2]}/{sha}") as resp:
                # A TRUNCATED BODY IS NOT A CORRUPT ONE, and telling them apart needs this.
                # `HTTPResponse.read(amt)` does NOT raise on a short body — CPython's own
                # comment says it would "ideally ... raise IncompleteRead" and closes the
                # connection instead — so a reset mid-download reads as a clean EOF, the
                # digest then disagrees, and without this the coordinator would cry
                # BLOB CORRUPT IN THE STORE at an ordinary network drop (code review).
                declared = getattr(resp, "length", None)
                if declared is None and hasattr(resp, "getheader"):
                    got = resp.getheader("Content-Length")
                    declared = int(got) if got and got.isdigit() else None
                for chunk in iter(lambda: resp.read(CHUNK), b""):
                    out.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
        except urllib.error.HTTPError as e:
            e.close()  # it is a response: leaving it to GC holds the connection
            # STRUCTURAL, on the status code. The first draft matched "NoSuchKey" and "404" in
            # the text of a botocore exception, which is a classification that breaks whenever
            # the library rewords itself, and which read a 403 as an environment failure only
            # by accident of wording.
            if e.code == 404:
                raise BlobMissing(f"{sha} is in neither the mirror nor the store") from e
            if e.code == 403:
                raise BlobUnavailable(
                    "the store refused the credential (403): missing, EXPIRED, or not scoped"
                    " to this prefix. With `s3:ListBucket` on the blob prefix an absent"
                    " document answers 404 instead, so a 403 here is the credential, not the"
                    " document — and expiry is the first thing to check if it ever worked"
                ) from e
            raise BlobUnavailable(f"the store answered {e.code}") from e
        except (
            TimeoutError,
            urllib.error.URLError,
            ConnectionError,
            http.client.HTTPException,  # IncompleteRead and its kin: a transport fault
            OSError,
        ) as e:
            # THE TYPE, NOT THE MESSAGE. This string is forwarded to every worker and printed
            # in its log on every box, and an `SSLCertVerificationError`'s text carries the
            # bucket's hostname (ingest review). The name says as much as an operator needs.
            raise BlobUnavailable(f"the store could not be reached: {type(e).__name__}") from e
        if declared is not None and size != declared:
            raise BlobUnavailable(f"the store's answer stopped at {size} of {declared} bytes")
        got = digest.hexdigest()
        if got != sha:
            raise BlobCorrupt(f"the store answered {sha} with bytes hashing {got}")
        return size

    return fetch_into


def _serve_file(handler, path: Path) -> None:
    """Send a document from disk, streamed. Never `read_bytes()`: see the docstring."""
    size = path.stat().st_size
    with path.open("rb") as f:
        handler.send_response(200)
        handler.send_header("Content-Type", "application/octet-stream")
        handler.send_header("Content-Length", str(size))
        handler.end_headers()
        shutil.copyfileobj(f, handler.wfile, CHUNK)


def _spool_dir(blobs: Path) -> Path:
    """Where a fetch is streamed before it is verified. Beside the mirror when that is
    writable, so the landing is a rename on one filesystem and never a copy across two; the
    system temp otherwise, because a mirror that cannot be written is not a reason to refuse
    bytes the fleet is waiting for — the mirror is a cache, never the store."""
    staging = blobs / ".tmp"
    try:
        staging.mkdir(parents=True, exist_ok=True)
        return staging
    except OSError:
        return Path(tempfile.gettempdir())


_FETCHING: dict[str, threading.Lock] = {}
_FETCHING_GUARD = threading.Lock()


@contextlib.contextmanager
def _one_fetch(sha: str):
    """One download per document at a time, however many workers ask at once.

    THE FIRST DRAFT OF THIS ARGUED NO LOCK WAS NEEDED and the argument was wrong (ingest
    review). It said a worker asks once per document and holds it — true per worker, and
    irrelevant: `Queue.claim` orders `BY document_sha256, page_no`, so two workers claiming at
    the same moment take ADJACENT PAGES OF THE SAME DOCUMENT. Concurrent identical misses are
    the normal case for a multi-worker pass, not a rarity, and on the 1.07 GB document in this
    record that was four downloads, four spool files and four times the egress — money, in the
    ADR's own framing. `web/documents.py` has held this lock for the same reason since August.
    """
    with _FETCHING_GUARD:
        lock = _FETCHING.setdefault(sha, threading.Lock())
    with lock:
        yield
    with _FETCHING_GUARD:
        # last one out drops it, so the map does not grow by one entry per document read
        if not lock.locked() and _FETCHING.get(sha) is lock:
            del _FETCHING[sha]


def fetch_and_cache(blobs: Path, sha: str, fetch_into) -> tuple[Path, bool]:
    """The store's copy, verified, landed in the mirror if it can be. Returns the path to
    serve from and whether the caller must delete it afterwards.

    Each fetch streams to its OWN spool name and `replace` is atomic, so even without the lock
    above nothing could truncate another writer's file; the lock is about not paying for the
    same document N times."""
    dest = blobs / sha[:2] / sha
    with _one_fetch(sha):
        if dest.is_file():
            return dest, False  # another thread fetched it while this one waited
        fd, name = tempfile.mkstemp(dir=_spool_dir(blobs), prefix=f"{SPOOL}{sha[:12]}-")
        tmp = Path(name)
        try:
            with os.fdopen(fd, "wb"):  # close the descriptor mkstemp opened; keep the name
                pass
            fetch_into(sha, tmp)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp.replace(dest)  # atomic: a reader sees the whole document or none of it
        except OSError as e:  # a full disk, a read-only mount, a different filesystem
            print(f"could not cache {sha[:12]}: {e}", file=sys.stderr, flush=True)
            return tmp, True
        return dest, False


def sweep_spool(blobs: Path) -> int:
    """Delete what a killed fetch left behind, at start. A spool file is only ever in use by
    the request that made it, so anything here at start-up is an orphan of a SIGKILL or a
    restart — and an orphan can be most of a gigabyte. Nothing else sweeps it: the instance's
    pruner does not run on this box, and the blob sync excludes `.tmp` by design."""
    spool = blobs / ".tmp"
    gone = 0
    for stale in spool.glob(f"{SPOOL}*"):
        try:
            stale.unlink()
            gone += 1
        except OSError as e:
            print(f"could not remove the stale spool {stale.name}: {e}", file=sys.stderr)
    if gone:
        print(f"removed {gone} spool file(s) a previous run left behind", flush=True)
    return gone


def serve(db: Path, blobs: Path, token: str, port: int, bind: str, fetch_missing=None) -> None:
    q = Queue(db, shared=True)  # one connection; the lock serialises the handler threads
    lock = threading.Lock()
    sweep_spool(blobs)

    class Handler(BaseHTTPRequestHandler):
        def _authorised(self) -> bool:
            got = self.headers.get("Authorization", "")
            return got.startswith("Bearer ") and secrets.compare_digest(got[7:], token)

        def do_GET(self):  # noqa: N802
            try:
                return self._get()
            except Exception as e:  # noqa: BLE001 — see below
                # `do_POST` has ended in a 500 since it was written and this did not, so
                # anything unforeseen here dropped the connection with NO STATUS LINE at all
                # and a traceback on the console (ingest review). A worker reads a dropped
                # connection as the environment's and exits, so one transient local fault
                # took down every reader. 503: it is the node's, and no page pays.
                print(f"blob/pending failed: {type(e).__name__}: {e}", file=sys.stderr)
                return self._json(503, {"error": f"the node failed: {type(e).__name__}"})

        def _get(self):
            if not self._authorised():
                return self._json(401, {"error": "unauthorised"})
            path = self.path.split("?", 1)[0]
            if path == "/pending":
                # what a claim could lease now, so a gate asks before it loads a model for an
                # empty queue (2026-09-11). A pass the queue does not know is refused, not zero.
                pass_ = parse_qs(urlsplit(self.path).query).get("pass", [""])[0]
                if pass_ not in PASSES:
                    return self._json(400, {"error": "unknown pass"})
                with lock:
                    return self._json(200, {"pass": pass_, "claimable": q.claimable(pass_)})
            if path.startswith("/blob/"):
                return self._blob(path[6:])
            return self._json(404, {"error": "not found"})

        def _blob(self, sha: str):
            if len(sha) != 64 or set(sha) - HEX64:
                return self._json(400, {"error": "not a sha256"})
            held = blobs / sha[:2] / sha
            if held.is_file():
                _serve_file(self, held)
                return None
            if fetch_missing is None:
                return self._json(404, {"error": "no such blob"})
            # NOT under `lock`: the lock serialises the queue's one SQLite connection, and a
            # download can take minutes. Holding it here would stall every claim on the fleet
            # behind one document's bytes.
            try:
                path, temporary = fetch_and_cache(blobs, sha, fetch_missing)
            except BlobMissing as e:
                return self._json(404, {"error": str(e)})
            except BlobUnavailable as e:
                return self._json(503, {"error": str(e)})
            except BlobCorrupt as e:
                # A CORRUPT OBJECT IN THE STORE OF RECORD, and the loudest thing available
                # here is this line. **It is not an alarm**: `config.alloy` scrapes
                # `/metrics` and no logs, and `backup.py` excludes `ocr/logs` — so nothing
                # pages anyone on it (ingest review; an earlier draft of this comment claimed
                # the monitor sees it, which was simply untrue). A counter the monitor can
                # serve is owed in `docs/deferred.md`. What DOES surface is the worker's
                # non-final `blob:` failure, in `status()["errors"]`.
                print(f"BLOB CORRUPT IN THE STORE: {e}", file=sys.stderr, flush=True)
                return self._json(502, {"error": str(e)})
            try:
                _serve_file(self, path)
            finally:
                if temporary:
                    path.unlink(missing_ok=True)
            return None

        def do_POST(self):  # noqa: N802
            if not self._authorised():
                return self._json(401, {"error": "unauthorised"})
            path = self.path.split("?", 1)[0]
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            except (ValueError, TypeError):
                return self._json(400, {"error": "body is not JSON"})
            try:
                with lock:
                    return self._dispatch(path, body)
            except KeyMismatch as e:
                return self._json(409, {"error": str(e)})
            except (ValueError, TypeError) as e:
                return self._json(400, {"error": str(e)})
            except KeyError as e:
                return self._json(400, {"error": f"missing {e}"})
            except Exception as e:  # noqa: BLE001 — a locked queue, anything: still an answer
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})

        def _dispatch(self, path: str, body: dict):
            if path == "/register":
                q.register(body["name"], body["pass"], body["producer"])
                return self._json(200, {})
            if path == "/claim":
                jobs = q.claim(body["worker"], body["pass"], body["n"], body["lease_seconds"])
                return self._json(200, {"jobs": jobs})
            if path == "/extend":
                q.extend(body["worker"], body["job_ids"], body["lease_seconds"])
                return self._json(200, {})
            if path == "/release":
                q.release(body["worker"], body["job_ids"])
                return self._json(200, {})
            if path == "/done":
                return self._json(
                    200, {"accepted": q.done(body["worker"], body["job_id"], body["raw"])}
                )
            if path == "/fail":
                q.fail(body["worker"], body["job_id"], body["error"], final=body["final"])
                return self._json(200, {})
            return self._json(404, {"error": "not found"})

        def _json(self, code: int, obj) -> None:
            data = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):  # noqa: A002 — the base class's own name
            pass

    httpd = ThreadingHTTPServer((bind, port), Handler)
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} queue server on {bind}:{port}", flush=True)
    httpd.serve_forever()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--blobs", required=True, type=Path)
    ap.add_argument("--token-file", required=True, type=Path)
    ap.add_argument("--port", type=int, default=8131)
    ap.add_argument("--bind", default="0.0.0.0", help="the LAN interface; never a public one")
    args = ap.parse_args()
    token = args.token_file.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        print("the token is too short to be one; `openssl rand -hex 32 > file`", file=sys.stderr)
        return 2
    # THE SWITCH IS THE ENVIRONMENT, not a flag, so this box is configured the way the web tier
    # is and a credential never reaches an argv anyone can read in `ps`. Built before the server
    # binds: a bucket named without keys raises here, rather than 503ing on the first miss hours
    # into a pass.
    try:
        fetch_into = store_fetcher(s3.from_env())
    except RuntimeError as e:
        print(f"{e}; exit", file=sys.stderr)
        return 2
    if fetch_into:
        bucket = os.environ["DY_S3_BUCKET"]
        print(f"blob misses refetch from s3://{bucket}/{BLOB_PREFIX}", flush=True)
    else:
        print("no DY_S3_BUCKET: a blob the mirror does not hold is a 404, as before", flush=True)
    serve(args.db, args.blobs, token, args.port, args.bind, fetch_into)
    return 0


if __name__ == "__main__":
    sys.exit(main())
