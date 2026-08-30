"""A status page for the benchmark batch on RMI-AI-MACHINE, served on the LAN.

    nohup python3 benchmark_status.py --port 8765 > /data/docketyard/benchmark/status.log 2>&1 &

Then open http://10.180.20.12:8765/ from the workstation. The page rebuilds on every
request from what is on disk — the batch log, the per-decision JSON each run writes, and
`nvidia-smi` — and refreshes itself every minute. It reads nothing else and writes nothing.
Bind is LAN-only by design: the box exposes nothing to the internet (infra/rmi-ai-machine.md).
"""

import argparse
import html
import json
import re
import subprocess
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BENCH = Path("/data/docketyard/benchmark")
RUNS = BENCH / "runs"
LOG = BENCH / "batch.log"
TEXT = BENCH / "text"
START_RE = re.compile(r"^===== (\S+)\s+(\S+)$", re.M)
DONE_RE = re.compile(r"^(\S+): finished in (\d+) min$", re.M)
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
FAIL_RE = re.compile(r"^(\S+): (pull failed.*|stopped at .*)$", re.M)


def gpu() -> str:
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        return out or "n/a"
    except Exception as e:  # noqa: BLE001 — a status page must not die on a probe
        return f"n/a ({e.__class__.__name__})"


def batch_alive() -> bool:
    try:
        return (
            subprocess.run(["pgrep", "-f", "benchmark_batch.sh"], capture_output=True).returncode
            == 0
        )
    except Exception:  # noqa: BLE001
        return False


def runs() -> list[dict]:
    log = LOG.read_text(encoding="utf-8", errors="replace") if LOG.exists() else ""
    started = {m.group(1): m.group(2) for m in START_RE.finditer(log)}
    finished = {m.group(1): int(m.group(2)) for m in DONE_RE.finditer(log)}
    failed = {m.group(1): m.group(2) for m in FAIL_RE.finditer(log)}
    total = len(list(TEXT.glob("*.txt"))) or 60
    out = []
    for d in sorted(RUNS.iterdir(), key=lambda p: p.stat().st_mtime):
        if not d.is_dir():
            continue
        files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime)
        model = d.name
        key = next((m for m in started if m.replace(":", "-") == model), model)
        n = len(files)
        secs = 0.0
        pages = 0
        for f in files:
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
                secs += float(
                    doc.get("seconds") or sum(p.get("seconds", 0) for p in doc.get("pages", []))
                )
                pages += len(doc.get("pages", []))
            except Exception:  # noqa: BLE001 — a half-written file mid-run
                pass
        first = datetime.fromtimestamp(files[0].stat().st_mtime) if files else None
        last = datetime.fromtimestamp(files[-1].stat().st_mtime) if files else None
        if key in finished:
            state = f"done in {finished[key]} min"
        elif key in failed:
            state = failed[key]
        elif key in started and n < total:
            state = "running" if batch_alive() else "stalled (batch process gone)"
        elif n >= total:
            state = "complete"
        else:
            state = "queued" if key not in started else "starting"
        eta = ""
        if state == "running" and n and n < total and first:
            now = datetime.now().astimezone()
            per = (now - datetime.fromisoformat(started[key])).total_seconds() / n
            eta = (now + timedelta(seconds=per * (total - n))).strftime("%H:%M")
        out.append(
            dict(
                model=model,
                done=n,
                total=total,
                state=state,
                pages=pages,
                sec_per_page=(secs / pages) if pages else 0,
                last=last,
                eta=eta,
                latest=files[-1].stem if files else "",
            )
        )
    return out


def page() -> str:
    try:
        rows = runs()
        err = ""
    except Exception as e:  # noqa: BLE001 — show it on the page rather than serve nothing
        rows, err = [], f"{e.__class__.__name__}: {e}"
    log_tail = ""
    if LOG.exists():
        raw = LOG.read_text(encoding="utf-8", errors="replace")
        raw = ANSI_RE.sub("", raw).replace("\r", "\n")  # ollama pull's progress bars
        lines = [
            ln
            for ln in raw.splitlines()
            if ln.strip() and not re.match(r"^(pulling|verifying|writing|success)", ln)
        ]
        log_tail = "\n".join(lines[-12:])
    alive = batch_alive()
    trs = "".join(
        "<tr>"
        f"<td>{html.escape(r['model'])}</td>"
        f"<td><progress value='{r['done']}' max='{r['total']}'></progress> "
        f"{r['done']}/{r['total']}</td>"
        f"<td class='{'run' if r['state'] == 'running' else ''}'>{html.escape(r['state'])}</td>"
        f"<td>{r['sec_per_page']:.1f}</td><td>{html.escape(r['eta'])}</td>"
        f"<td>{html.escape(r['latest'])}</td>"
        f"<td>{r['last'].strftime('%H:%M:%S') if r['last'] else ''}</td>"
        "</tr>"
        for r in rows
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="60"><title>benchmark batch — rmi-ai-machine</title>
<style>
body {{ font: 15px/1.5 system-ui, sans-serif; max-width: 64rem; margin: 2rem auto;
       padding: 0 1rem; color: #222 }}
table {{ border-collapse: collapse; width: 100% }}
td, th {{ padding: .4rem .6rem; border-bottom: 1px solid #ddd; text-align: left }}
progress {{ width: 8rem; vertical-align: middle }}
.run {{ color: #0a6; font-weight: 600 }}
pre {{ background: #f5f5f5; padding: 1rem; overflow-x: auto }}
.k {{ color: #666 }}
</style></head><body>
<h1>Extraction benchmark — local candidates</h1>
<p class="k">{datetime.now():%Y-%m-%d %H:%M:%S} on rmi-ai-machine · batch process
<b>{"running" if alive else "not running"}</b> · GPU {html.escape(gpu())} ·
refreshes every minute</p>
<table><tr><th>model</th><th>decisions</th><th>state</th><th>s/page</th><th>ETA</th>
<th>latest</th><th>at</th></tr>{trs}</table>
<p class="k">ETA is this model's own pace projected over its remaining decisions; the queue
after it adds roughly the same again per 14B model. Scores are computed on the workstation
against the checked sheet (<code>benchmark_score.py</code>), not here.</p>
{f'<p class="run" style="color:#b00">{html.escape(err)}</p>' if err else ""}
<h2>log</h2><pre>{html.escape(log_tail)}</pre>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 — http.server's name
        body = page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002 — http.server's signature; quiet
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--bind", default="0.0.0.0")
    args = ap.parse_args()
    print(f"serving on http://{args.bind}:{args.port}/ at {time.strftime('%H:%M:%S')}", flush=True)
    HTTPServer((args.bind, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
