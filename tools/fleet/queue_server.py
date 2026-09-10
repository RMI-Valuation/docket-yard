#!/usr/bin/env python3
"""The queue's transport: the six lease calls and the blobs, over HTTP, for a worker on
another machine (docs/compute-fleet.md § Joining a node).

    python3 queue_server.py --db /data/docketyard/ocr/queue.sqlite \\
        --blobs /data/docketyard/blobs --token-file /data/docketyard/fleet.token --port 8131

    POST /register  {name, pass, producer}                 -> {}            (KeyMismatch: 409)
    POST /claim     {worker, pass, n, lease_seconds}       -> {jobs: [...]}
    POST /extend    {worker, job_ids, lease_seconds}       -> {}
    POST /release   {worker, job_ids}                      -> {}
    POST /done      {worker, job_id, raw}                  -> {accepted: bool}
    POST /fail      {worker, job_id, error, final}         -> {}            (ValueError: 400)
    GET  /blob/<sha256>                                    -> the document's bytes

Every request carries `Authorization: Bearer <token>`, the token being one line in a file
that exists on the node and on each joining machine and in no repository. The LAN is the
operator's, but a write API with no credential is a habit, not a boundary. `pagequeue.
RemoteQueue` is the client; it has the `Queue` methods a worker uses and nothing else, so the
worker does not know which it holds. Nothing here is the monitor: that stays read-only on
its own port. Standard library only.
"""

import argparse
import json
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pagequeue import KeyMismatch, Queue  # noqa: E402

HEX64 = frozenset("0123456789abcdef")


def serve(db: Path, blobs: Path, token: str, port: int, bind: str) -> None:
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
            if path.startswith("/blob/"):
                sha = path[6:]
                if len(sha) != 64 or set(sha) - HEX64:
                    return self._json(400, {"error": "not a sha256"})
                f = blobs / sha[:2] / sha
                if not f.is_file():
                    return self._json(404, {"error": "no such blob"})
                data = f.read_bytes()
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
    args = ap.parse_args()
    token = args.token_file.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        print("the token is too short to be one; `openssl rand -hex 32 > file`", file=sys.stderr)
        return 2
    serve(args.db, args.blobs, token, args.port, args.bind)
    return 0


if __name__ == "__main__":
    sys.exit(main())
