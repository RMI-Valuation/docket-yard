#!/usr/bin/env python3
"""Ask the broker for a reader when a pass owes pages and nothing is reading them.

    python3 resubmit.py --db /data/docketyard/ocr/queue.sqlite --pass tabular \\
        --jobd-url http://<broker>:8765 --jobd-token-file ~/.config/jobd/submit.token \\
        --cwd /home/<user>/docket-yard -- \\
        <venv>/bin/python tools/fleet/hunyuan_worker.py --queue http://<coordinator>:8131 ...

WHY THIS EXISTS (ADR 0025 addendum, proposal 2, Accepted 2026-09-19). A preempted job is
TERMINAL in jobd and is never requeued: the broker stops a reader and does not start another.
Nothing is lost — the reader yields its pages back to the queue (`stopping.py`) — but nothing
picks them up either, so one preempt ends a pass until a person notices. Resubmission is this
project's, never the broker's, because deciding to read again is deciding to spend the
record's money.

THERE IS NO WORK TO HAND OVER, which is what makes this small. The remainder lives in
`pagequeue` on this box; a submitted job carries only "start a reader". So "send it to another
machine, or wait for the one that has the model" is the broker's ordinary placement decision,
and this file never expresses a preference about where a reader runs.

**WHEN IN DOUBT, DO NOT SUBMIT.** A false submit costs a duplicate reader — no page is read
twice, since a claim is one atomic transaction and `done` is refused to a worker that lost its
lease, but two readers on one card is VRAM contention and an OOM the fleet blames on the page.
A false hold-off costs idle GPU until the next tick, and the stall alarm eventually pages a
person. The cheaper mistake is the second, so every unknown here resolves to "hold off":

    an unrecognised job state      counts as LIVE. Asking the broker only for the states this
                                   file knows would make a new one invisible, and invisible
                                   resolves to "submit" — the wrong way round. `assigned` was
                                   exactly this: a reader dispatched but not yet started
    an answer of the wrong shape   is an error, not an empty list. A 200 carrying something
                                   other than a list of jobs must never read as "nothing running"
    a job whose command we         counts as ours. Better to wait behind another pass's reader
    cannot parse                   than to put a second one on this pass
    the broker unreachable         submits nothing

THREE QUESTIONS, AND ALL THREE MATTER:

    pages owed       `claimable`, not `pending`: a reader killed after its grace leaves its
                     batch `leased` until the lease expires, and those pages are claimable now
                     (a claim reaps first) though `pending` is 0. Gating on `pending` would
                     idle the pass for up to the lease
    nothing reading  asked of the broker AND of the queue. The broker knows the jobs it
                     started; the queue sees every reader, including one `fleet-up.sh`'s
                     restart loop started, which the broker has never heard of. A worker counts
                     as reading when it HOLDS pages and was seen lately — a yield releases
                     everything, so `holding` drops to 0 and the next tick submits at once,
                     while a reader on a slow page keeps its pages and blocks a duplicate
    not dying on     a reader that exits in seconds (another process on the card, the server
    arrival          serving the wrong model) goes terminal at once, so the next tick sees
                     nothing running and submits again — for ever, with no signal. ADR 0025
                     addendum: the resubmitter owns every exit, not only a preempt

IT KEYS OFF THE BROKER'S STATE, NEVER AN EXIT CODE. Exit 0 now means three different things —
the queue drained, the operator's stop file, a preempt — and only the last prints a marker.

A BROKERED PLACEMENT AND `fleet-up.sh`'s RESTART LOOP MUST NOT BOTH MANAGE ONE READER, or the
loop puts it back on the card a minute after the broker took it away. The queue question makes
that visible rather than silent: a tmux-looped reader holds pages and this refuses, saying so.

`requires` IS DELIBERATELY NOT SENT. The broker RESOLVES it by replacement, not merge, so a
partial block silently discards the rest of the profile — including `idempotent`, which is what
decides whether a reader stranded on a dead worker is requeued or orphaned. A resubmitter that
opted its own readers out of requeue would be working against itself. The profile supplies it.

Standard library only: the broker is plain HTTP, so the coordinator needs no jobd client
installed. The token is read from a file the operator places and is never logged.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pagequeue import PASSES, Queue  # noqa: E402

# jobd's terminal states (`JobState`/`TERMINAL_STATES`). Everything else — `queued`,
# `assigned`, `running`, and anything jobd gains later — is a job the broker still owns.
TERMINAL = frozenset(
    {"completed", "failed", "cancelled", "preempted", "orphaned", "scheduling_timeout"}
)
WORKERS = ("dots_worker.py", "hunyuan_worker.py")
EXIT_ENVIRONMENT = 4


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + msg, flush=True)


def _call(url: str, token: str, payload=None, timeout: int = 30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body) if body else {}


def _why(e: Exception) -> str:
    """The broker's own reason, which `HTTPError.__str__` throws away. jobd answers a rejected
    payload with `{"detail": ...}`, and without it a bad submit fails every tick saying only
    "HTTP Error 422". The token rides in a header, so no body can carry it."""
    detail = ""
    if isinstance(e, urllib.error.HTTPError):
        try:
            detail = ": " + e.read().decode("utf-8", "replace")[:400]
        except Exception:  # noqa: BLE001 — a body that will not read is not the story
            detail = ""
    return f"{type(e).__name__}: {e}{detail}"


def for_pass(job: dict, pass_: str) -> bool:
    """Whether a job is a reader of THIS pass, read from the command line the pass is pinned
    in. A job we cannot parse counts as ours: waiting behind another pass's reader is cheaper
    than putting a second one on this pass."""
    cmd = job.get("cmd")
    if not isinstance(cmd, list):
        return True
    if pass_ in cmd:
        return True
    return not ({p for p in PASSES if p in cmd})


def broker_jobs(base: str, token: str, project: str, pass_: str) -> tuple[list, list]:
    """This pass's jobs the broker still owns, and its terminal ones newest-first."""
    url = f"{base}/jobs?project={urllib.parse.quote(project)}"
    rows = _call(url, token)
    if not isinstance(rows, list):
        raise ValueError(f"{url} did not answer with a list of jobs")
    mine = [j for j in rows if isinstance(j, dict) and for_pass(j, pass_)]
    return (
        [j for j in mine if j.get("state") not in TERMINAL],
        [j for j in mine if j.get("state") in TERMINAL],
    )


def _seconds(job: dict) -> float | None:
    """How long a terminal job ran, or None when the broker did not say."""
    started, finished = job.get("started_at"), job.get("finished_at")
    if not started or not finished:
        return None
    try:
        a = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (b - a).total_seconds()


def dying_on_arrival(terminal: list[dict], min_run: float, how_many: int) -> int:
    """How many of the most recent readers died sooner than `min_run`. A reader that exits in
    seconds — another process on the card, the server serving the wrong model — goes terminal
    at once, so without this the next tick submits another, for ever."""
    quick = 0
    for job in terminal[:how_many]:
        ran = _seconds(job)
        if ran is None or ran >= min_run:
            break
        quick += 1
    return quick


def reading_now(status: dict, pass_: str, idle_for: int) -> dict | None:
    """A worker of this pass that HOLDS pages and was seen lately, whoever started it. Holding
    matters: a reader on a slow page does not touch the queue for up to its page timeout, and
    a yield releases everything, so `holding` is what separates "working" from "gone"."""
    for w in status.get("workers", []):
        if w.get("pass") != pass_ or not w.get("holding", 0):
            continue
        if w.get("last_seen_age_seconds", 1 << 30) <= idle_for:
            return w
    return None


def decide(status, pass_, idle_for, live, terminal, min_run, max_quick) -> tuple[bool, str]:
    """True and a reason to submit, or False and the reason not to. Pure, so the rule can be
    tested without a broker or a queue."""
    counts = status.get("passes", {}).get(pass_)
    if not counts:
        return False, f"the queue has no pass {pass_!r}"
    owed = counts.get("claimable", counts.get("pending", 0))
    if not owed:
        return False, f"{pass_}: nothing claimable"
    if live:
        ids = ", ".join(str(j.get("id", "?")) for j in live[:3])
        return False, f"{pass_}: {owed} owed, but the broker holds {len(live)} job(s) ({ids})"
    seen = reading_now(status, pass_, idle_for)
    if seen:
        return False, (
            f"{pass_}: {owed} owed, but {seen['name']} holds {seen['holding']} and was seen"
            f" {seen['last_seen_age_seconds']}s ago — two runners would double up"
        )
    quick = dying_on_arrival(terminal, min_run, max_quick)
    if quick >= max_quick:
        return False, (
            f"{pass_}: {owed} owed, but the last {quick} readers died inside {min_run:.0f}s."
            " Something is wrong with the reader or its card; not submitting another"
        )
    return True, f"{pass_}: {owed} owed and nothing reading"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", required=True, type=Path, help="the queue, on the coordinator")
    ap.add_argument("--pass", dest="pass_", required=True, choices=sorted(PASSES))
    ap.add_argument("--jobd-url", required=True)
    ap.add_argument("--jobd-token-file", required=True, type=Path)
    ap.add_argument("--project", default="docket-yard")
    ap.add_argument("--profile", default="dy-ocr")
    ap.add_argument("--cwd", required=True, help="the working directory ON THE READER")
    ap.add_argument(
        "--idle-for",
        type=int,
        default=900,
        help="seconds a worker may hold pages without being seen before it is not reading."
        " Above a page timeout (600s), below the stall alarm (1800s) and the lease (2700s)",
    )
    ap.add_argument("--min-run", type=float, default=120.0, help="a reader dying sooner is sick")
    ap.add_argument("--max-quick-deaths", type=int, default=3)
    ap.add_argument("--host", default="any", help="pin the reader; normally left to the broker")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- the reader's command line")
    args = ap.parse_args()

    # only the SEPARATOR is dropped: a reader command may legitimately contain a bare `--`
    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd
    if not cmd:
        log("give the reader's command line after --")
        return EXIT_ENVIRONMENT
    # the pass this gates on must be the pass the reader will claim. `dots_worker.py` defaults
    # to `dots`, so an omitted --pass would have this watch `reread` and launch a `dots` reader
    if "--pass" in cmd:
        named = cmd[cmd.index("--pass") + 1] if cmd.index("--pass") + 1 < len(cmd) else ""
        if named != args.pass_:
            log(f"the reader is given --pass {named!r} but this gates on {args.pass_!r}")
            return EXIT_ENVIRONMENT
    elif any(w in c for c in cmd for w in WORKERS) and args.pass_ != "dots":
        log(f"the reader names no --pass, so it would claim 'dots', not {args.pass_!r}")
        return EXIT_ENVIRONMENT

    token_file = args.jobd_token_file.expanduser()
    try:
        token = token_file.read_text(encoding="utf-8").strip()
    except OSError as e:
        log(f"cannot read {token_file} ({type(e).__name__}); exit {EXIT_ENVIRONMENT}")
        return EXIT_ENVIRONMENT
    if not token:
        log(f"{token_file} is empty; exit {EXIT_ENVIRONMENT}")
        return EXIT_ENVIRONMENT
    base = args.jobd_url.rstrip("/")

    try:
        # read-only, like the monitor: this watches a queue another process is serving, and a
        # write connection would run the schema script against a live database
        q = Queue(args.db, readonly=True)
        status = q.status()
        status["passes"].setdefault(args.pass_, {})["claimable"] = q.claimable(args.pass_)
    except (OSError, ValueError) as e:
        log(f"cannot read the queue at {args.db} ({type(e).__name__}: {e})")
        return EXIT_ENVIRONMENT
    try:
        live, terminal = broker_jobs(base, token, args.project, args.pass_)
    except (urllib.error.URLError, OSError, ValueError) as e:
        # the broker being unreachable is not a reason to submit blindly
        log(f"the broker did not answer ({_why(e)}); nothing submitted")
        return EXIT_ENVIRONMENT

    go, why = decide(
        status, args.pass_, args.idle_for, live, terminal, args.min_run, args.max_quick_deaths
    )
    log(why)
    if not go:
        return 0

    # no `requires`: the broker replaces rather than merges, so a partial block would discard
    # the profile's `idempotent` — which decides whether a stranded reader is requeued
    job = {
        "cmd": cmd,
        "cwd": args.cwd,
        "project": args.project,
        "profile": args.profile,
        "host_pin": args.host,
    }
    if args.dry_run:
        log(f"would submit: {json.dumps(job)}")
        return 0
    try:
        got = _call(f"{base}/submit", token, job)
    except (urllib.error.URLError, OSError, ValueError) as e:
        log(f"submit failed ({_why(e)}); exit {EXIT_ENVIRONMENT}")
        return EXIT_ENVIRONMENT
    log(f"submitted job {got.get('id', '?')} for {args.pass_}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
