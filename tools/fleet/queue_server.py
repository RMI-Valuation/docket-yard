#!/usr/bin/env python3
"""The queue's transport: the six lease calls and the blobs, over HTTP, for a worker on
another machine (docs/compute-fleet.md § Joining a node).

    python3 queue_server.py --db /data/docketyard/ocr/queue.sqlite \\
        --blobs /data/docketyard/blobs --token-file /data/docketyard/fleet.token --port 8131
    ... --s3-bucket docketyard-prod        # and a miss is refetched, not a failed page

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
its own port. Standard library only, unless `--s3-bucket` is given (below).

A BLOB MISS IS A FETCH, NOT A FAILURE — with `--s3-bucket`. Without it this 404s when the
mirror does not hold a document, and that 404 is what a worker reports as `blob: ...`: it
failed 728 pages across 310 documents in the tabular pass of 2026-09-18, every one of which
was in S3 the whole time. The mirror is a cache of the store, never the store (ADR 0022 D2),
so the coordinator refetches on a miss the way the instance's document route already does,
and the cache is then allowed to be cold, pruned or absent. What this buys is not the bytes
— it is that no box has to hold 109 GB to serve them, and that the box owning the mirror can
refill it, which until now only a different box could do.

**The sha IS the identity** (ADR 0002), so a fetched object is hashed before it is cached or
served, and a mismatch is loud and never written: that would be a corrupt object in the store
of record, which is worth an alarm rather than a quiet re-read. Whose fault a miss is follows
the queue's own taxonomy: absent in S3 is the document's (404), a refused or broken fetch is
the environment's (503), a hash that does not match is the store's (502).

The credential is read-only and the operator's to place, as `docketyard-reader` already is on
the reading box (`infra/deploy/README.md`). Nothing here mints, prints or logs one.
"""

import argparse
import hashlib
import json
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pagequeue import PASSES, KeyMismatch, Queue  # noqa: E402

HEX64 = frozenset("0123456789abcdef")


class BlobMissing(Exception):
    """Not in the mirror and not in the store: the document's own, and a 404 as before."""


class BlobCorrupt(Exception):
    """The store returned bytes that are not the sha asked for. Never cached, never served."""


class BlobUnavailable(Exception):
    """The fetch could not be made — no credential, a refusal, a broken connection. The
    environment's, so the worker should not spend the page's attempt on it."""


def s3_fetcher(bucket: str | None, profile: str | None, prefix: str):
    """Bytes for a sha from the store, or None when no bucket is named.

    It fetches and does nothing else. The sha is verified and the mirror filled by the server,
    so that invariant holds however the bytes arrive and whatever stands in for this.

    `boto3` is imported here and nowhere else, so a coordinator not using this stays standard
    library only — and a box without the package fails at start with a plain name, rather than
    on the first miss hours into a pass."""
    if not bucket:
        return None
    import boto3  # noqa: PLC0415 — only when the operator asked for S3

    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    client = session.client("s3")

    def fetch(sha: str) -> bytes:
        try:
            got = client.get_object(Bucket=bucket, Key=f"{prefix}{sha[:2]}/{sha}")
            return got["Body"].read()
        except Exception as e:  # noqa: BLE001 — botocore builds its errors at runtime
            text = f"{type(e).__name__}: {e}"
            if "NoSuchKey" in text or "404" in text:
                raise BlobMissing(f"{sha} is in neither the mirror nor the store") from e
            raise BlobUnavailable(text) from e

    return fetch


def cache_blob(blobs: Path, sha: str, data: bytes) -> None:
    """Fill the mirror, atomically and best effort. A mirror that cannot be written is not a
    reason to refuse bytes already in hand — the mirror is a cache, never the store."""
    path = blobs / sha[:2] / sha
    # a unique temp name per request: two workers may miss the same document at once, and a
    # shared `.part` would have one truncate the other's write under it
    tmp = path.with_name(f"{sha}.{secrets.token_hex(8)}.part")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic: a reader sees the whole document or none of it
    except OSError as e:  # a full disk, a read-only mount
        print(f"could not cache {sha[:12]}: {e}", file=sys.stderr, flush=True)
        tmp.unlink(missing_ok=True)


def serve(db: Path, blobs: Path, token: str, port: int, bind: str, fetch_missing=None) -> None:
    q = Queue(db, shared=True)  # one connection; the lock serialises the handler threads
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _authorised(self) -> bool:
            got = self.headers.get("Authorization", "")
            return got.startswith("Bearer ") and secrets.compare_digest(got[7:], token)

        def do_GET(self):  # noqa: N802
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
                sha = path[6:]
                if len(sha) != 64 or set(sha) - HEX64:
                    return self._json(400, {"error": "not a sha256"})
                f = blobs / sha[:2] / sha
                if f.is_file():
                    data = f.read_bytes()
                elif fetch_missing is None:
                    return self._json(404, {"error": "no such blob"})
                else:
                    # NOT under `lock`: the lock serialises the queue's one SQLite connection,
                    # and a download can take seconds. Holding it here would stall every claim
                    # on the fleet behind one document's bytes.
                    try:
                        data = fetch_missing(sha)
                    except BlobMissing as e:
                        return self._json(404, {"error": str(e)})
                    except BlobUnavailable as e:
                        return self._json(503, {"error": str(e)})
                    # the sha IS the identity (ADR 0002), so it is checked here rather than in
                    # the fetcher: it then holds however the bytes arrived
                    got = hashlib.sha256(data).hexdigest()
                    if got != sha:
                        print(
                            f"BLOB CORRUPT IN THE STORE: asked {sha}, got {got}",
                            file=sys.stderr,
                            flush=True,
                        )
                        return self._json(502, {"error": f"the store returned {got} for {sha}"})
                    cache_blob(blobs, sha, data)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return None
            return self._json(404, {"error": "not found"})

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
    ap.add_argument(
        "--s3-bucket",
        default=None,
        help="refetch a blob the mirror does not hold, instead of 404ing. Needs a read-only"
        " credential on this box; without it the mirror is all there is, as before",
    )
    ap.add_argument("--s3-profile", default="docketyard-reader")
    ap.add_argument("--s3-prefix", default="blobs/")
    args = ap.parse_args()
    token = args.token_file.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        print("the token is too short to be one; `openssl rand -hex 32 > file`", file=sys.stderr)
        return 2
    # built before the server binds: a missing package or an unusable profile is an exit, not a
    # 503 on the first miss hours into a pass
    fetch = s3_fetcher(args.s3_bucket, args.s3_profile, args.s3_prefix)
    if fetch:
        print(f"blob misses refetch from s3://{args.s3_bucket}/{args.s3_prefix}", flush=True)
    serve(args.db, args.blobs, token, args.port, args.bind, fetch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
