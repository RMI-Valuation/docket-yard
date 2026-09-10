#!/usr/bin/env python3
"""The fleet monitor: one page and one scrape over the queue (docs/compute-fleet.md).

    python3 monitor.py --db /data/docketyard/ocr/queue.sqlite --port 8130

    /            the status page: each pass's counts, rate and ETA; each worker's producer,
                 pages and last sign of life; the failures by reason; a STALLED banner
    /status.json the same, as the queue reports it
    /metrics     Prometheus text exposition, the grammar ADR 0019 chose, for Alloy to scrape
    /health      200 while reading is under way or nothing is owed; 503 when STALLED

STALLED means pages are owed and no page has been READ in `--stall` seconds (default 30
minutes; the run reads one every 11–13 s). Read, not finished: a fleet failing every page
finishes pages briskly, and that was the 2026-09-06 shape — the run's server died at 14:39
and nothing said so for three days, because the walk kept printing progress lines against a
closed port. FAILING is the other half: pages owed and, in the last hour, more failed than
read (and at least ten failed, so a tail of five oversize sheets does not trip it).

A local banner is not detection — a dead box cannot report its own death (ADR 0012, 0019) —
so both facts go out on `/metrics` in production's grammar (an age series paired with a
`_known` series, the way `docket_yard_freshness_*` is shaped, never a sentinel in the age),
for rules evaluated off the box: stalled, failing, or the series absent altogether.

Standard library only; LAN only. The queue is opened READ-ONLY, and a path with no queue
file is a 503, never an empty queue reporting that nothing is owed.
"""

import argparse
import html
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pagequeue import STATES, Queue  # noqa: E402

MIN_FAILED = 10


def stalled(status: dict, stall_seconds: int) -> list[str]:
    """The passes that owe pages and have not READ one within the window."""
    out = []
    for pass_, c in status["passes"].items():
        owed = c["pending"] + c["leased"]
        age = c["last_read_age_seconds"]
        if owed and (age is None or age > stall_seconds):
            out.append(pass_)
    return out


def failing(status: dict) -> list[str]:
    """The passes that owe pages and failed more than they read in the last hour."""
    out = []
    for pass_, c in status["passes"].items():
        owed = c["pending"] + c["leased"]
        h = c["last_hour"]
        if owed and h["failed"] >= MIN_FAILED and h["failed"] > h["done"]:
            out.append(pass_)
    return out


def metrics(status: dict, stall_seconds: int) -> str:
    lines = [
        "# HELP docket_yard_fleet_jobs Pages of a pass in each state",
        "# TYPE docket_yard_fleet_jobs gauge",
    ]
    for pass_, c in status["passes"].items():
        for s in STATES:
            lines.append(f'docket_yard_fleet_jobs{{pass="{pass_}",state="{s}"}} {c[s]}')
    lines += [
        "# HELP docket_yard_fleet_last_read_known 1 when a page of the pass has ever been read",
        "# TYPE docket_yard_fleet_last_read_known gauge",
        "# HELP docket_yard_fleet_last_read_age_seconds Seconds since a page of the pass was"
        " last read; absent until one has been",
        "# TYPE docket_yard_fleet_last_read_age_seconds gauge",
    ]
    for pass_, c in status["passes"].items():
        age = c["last_read_age_seconds"]
        lines.append(f'docket_yard_fleet_last_read_known{{pass="{pass_}"}} {int(age is not None)}')
        if age is not None:
            lines.append(f'docket_yard_fleet_last_read_age_seconds{{pass="{pass_}"}} {age}')
    lines += [
        "# HELP docket_yard_fleet_pages_last_hour Pages finished in the last hour, by outcome",
        "# TYPE docket_yard_fleet_pages_last_hour gauge",
    ]
    for pass_, c in status["passes"].items():
        for k, v in c["last_hour"].items():
            lines.append(f'docket_yard_fleet_pages_last_hour{{pass="{pass_}",outcome="{k}"}} {v}')
    lines += [
        "# HELP docket_yard_fleet_stalled 1 when the pass owes pages and none was read within"
        f" {stall_seconds} s",
        "# TYPE docket_yard_fleet_stalled gauge",
        "# HELP docket_yard_fleet_failing 1 when the pass owes pages and the last hour failed"
        " more than it read",
        "# TYPE docket_yard_fleet_failing gauge",
    ]
    down, bad = set(stalled(status, stall_seconds)), set(failing(status))
    for pass_ in status["passes"]:
        lines.append(f'docket_yard_fleet_stalled{{pass="{pass_}"}} {int(pass_ in down)}')
        lines.append(f'docket_yard_fleet_failing{{pass="{pass_}"}} {int(pass_ in bad)}')
    lines += [
        "# HELP docket_yard_fleet_worker_last_seen_age_seconds Seconds since the worker"
        " touched the queue",
        "# TYPE docket_yard_fleet_worker_last_seen_age_seconds gauge",
        "# HELP docket_yard_fleet_worker_pages_done Pages the worker has read, all time",
        "# TYPE docket_yard_fleet_worker_pages_done gauge",
    ]
    for w in status["workers"]:
        label = f'worker="{w["name"]}",pass="{w["pass"]}",host="{w["producer"].get("host", "")}"'
        age = w["last_seen_age_seconds"]
        lines.append(f"docket_yard_fleet_worker_last_seen_age_seconds{{{label}}} {age}")
        lines.append(f"docket_yard_fleet_worker_pages_done{{{label}}} {w['done']}")
    return "\n".join(lines) + "\n"


def _age(seconds) -> str:
    if seconds is None:
        return "never"
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 5400:
        return f"{seconds / 60:.0f} min"
    if seconds < 172800:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} d"


def page(status: dict, stall_seconds: int) -> str:
    e = html.escape
    down, bad = stalled(status, stall_seconds), failing(status)
    parts = [
        "<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=60>",
        "<title>Docket Yard fleet</title>",
        "<style>body{font:14px/1.4 system-ui,sans-serif;margin:2em;max-width:70em}"
        "table{border-collapse:collapse;margin:1em 0}td,th{border:1px solid #ccc;padding:.3em .6em;"
        "text-align:left}th{background:#f3f3f3}.stalled{background:#c00;color:#fff;padding:1em;"
        "font-size:1.3em}.ok{background:#2a6;color:#fff;padding:.6em}code{font-size:.9em}</style>",
        "<h1>Docket Yard fleet</h1>",
    ]
    if down:
        parts.append(
            f"<div class=stalled>STALLED: {e(', '.join(down))} owes pages and none was read"
            f" within {stall_seconds // 60} minutes</div>"
        )
    if bad:
        parts.append(
            f"<div class=stalled>FAILING: {e(', '.join(bad))} failed more pages than it read"
            " in the last hour</div>"
        )
    if not down and not bad:
        parts.append("<div class=ok>reading, or nothing owed</div>")
    parts.append(f"<p>as of {e(status['at'])}; refreshes every minute</p>")
    parts.append(
        "<h2>Passes</h2><table><tr><th>pass<th>pending<th>leased<th>done<th>failed"
        "<th>last read<th>last hour<th>pages/s<th>ETA</tr>"
    )
    for pass_, c in status["passes"].items():
        lh = c["last_hour"]
        eta = f"{c['eta_hours']} h" if c["eta_hours"] is not None else "—"
        parts.append(
            f"<tr><td>{e(pass_)}<td>{c['pending']:,}<td>{c['leased']:,}<td>{c['done']:,}"
            f"<td>{c['failed']:,}<td>{_age(c['last_read_age_seconds'])} ago"
            f"<td>{lh['done']:,} read, {lh['failed']:,} failed<td>{c['pages_per_second']}"
            f"<td>{eta}</tr>"
        )
    parts.append("</table>")
    parts.append(
        "<h2>Workers</h2><table><tr><th>worker<th>pass<th>producer<th>pages read<th>holding"
        "<th>last seen</tr>"
    )
    for w in status["workers"]:
        parts.append(
            f"<tr><td>{e(w['name'])}<td>{e(w['pass'])}"
            f"<td><code>{e(json.dumps(w['producer'], sort_keys=True))}</code>"
            f"<td>{w['done']:,}<td>{w['holding']}<td>{_age(w['last_seen_age_seconds'])} ago</tr>"
        )
    parts.append("</table>")
    if status["collected"]:
        parts.append("<h2>Collected</h2><table><tr><th>pass<th>documents<th>read<th>pages failed")
        for pass_, c in status["collected"].items():
            parts.append(
                f"<tr><td>{e(pass_)}<td>{c['n']:,}<td>{c['read']:,}<td>{c['pages_failed']:,}"
            )
        parts.append("</table>")
    if status["errors"]:
        parts.append("<h2>Failures by reason</h2><table><tr><th>pass<th>reason<th>pages</tr>")
        for r in status["errors"]:
            parts.append(f"<tr><td>{e(r['pass'])}<td>{e(str(r['error']))}<td>{r['n']:,}</tr>")
        parts.append("</table>")
    parts.append(
        "<p><a href=/status.json>status.json</a> · <a href=/metrics>metrics</a> ·"
        " <a href=/health>health</a></p>"
    )
    return "\n".join(parts)


def serve(db: Path, port: int, stall_seconds: int, bind: str) -> None:
    local = threading.local()  # one read-only connection per serving thread

    def queue() -> Queue:
        if not hasattr(local, "q"):
            local.q = Queue(db, readonly=True)
        return local.q

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            try:
                status = queue().status()
            except Exception as e:  # noqa: BLE001 — the queue is what is being watched
                local.__dict__.pop("q", None)
                self._send(503, "text/plain", f"queue unreadable: {type(e).__name__}: {e}\n")
                return
            path = self.path.split("?", 1)[0]
            if path == "/metrics":
                self._send(
                    200, "text/plain; version=0.0.4; charset=utf-8", metrics(status, stall_seconds)
                )
            elif path == "/status.json":
                self._send(200, "application/json", json.dumps(status, indent=1))
            elif path == "/health":
                down, bad = stalled(status, stall_seconds), failing(status)
                body = ""
                if down:
                    body += f"stalled: {', '.join(down)}\n"
                if bad:
                    body += f"failing: {', '.join(bad)}\n"
                self._send(503 if body else 200, "text/plain", body or "ok\n")
            elif path == "/":
                self._send(200, "text/html; charset=utf-8", page(status, stall_seconds))
            else:
                self._send(404, "text/plain", "not found\n")

        def _send(self, code: int, ctype: str, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):  # noqa: A002 — the base class's own name
            pass  # one line per request is noise on a LAN page

    httpd = ThreadingHTTPServer((bind, port), Handler)
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} fleet monitor on {bind}:{port} over {db}")
    httpd.serve_forever()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--port", type=int, default=8130)
    ap.add_argument("--bind", default="0.0.0.0", help="the LAN interface; never a public one")
    ap.add_argument("--stall", type=int, default=1800, help="seconds without a page = stalled")
    args = ap.parse_args()
    serve(args.db, args.port, args.stall, args.bind)
    return 0


if __name__ == "__main__":
    sys.exit(main())
