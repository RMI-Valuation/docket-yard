"""The panel over the REAL review queue (`docs/extraction-benchmark.md` § Local models as
reviewers, the operator's decision of 2026-09-11).

`benchmark_review.py` measured a panel over the sixty checked decisions and found that two
models agreeing on both halves settle about half of those pairs without an error. That is a
sample of the RECORD. This runs the same question over a sample of the QUEUE: the keys a
person is actually owed, which are held precisely because something about them was uncertain,
and which are therefore expected to be harder. The figures from one cannot be carried to the
other, and a clearing rule has to rest on this one.

EVERYTHING ABOUT THE QUESTION IS THE BENCHMARK'S. The prompt, the candidate lists, the
snippet width and the answer schema are imported rather than restated, so the two runs are
comparable and the measured precision of one prompt is not quietly read onto another.

THE TEXT IS THE CITATOR'S OWN. Pages come from `citator.walk._PAGES` verbatim and are then
narrowed to the machine channels exactly as `walk.documents` narrows them, so a page whose
live reading is `human` is skipped here because the finder skipped it. The panel reads the
words the finder read, not a second opinion assembled here.

    # a tunnel to the box holding the model, then:
    python tools/rmi-ai-machine/review_queue_panel.py --model qwen3:14b \\
        --store data/<a production copy>.sqlite --host http://127.0.0.1:11435 --tag mac
    python tools/rmi-ai-machine/review_queue_panel.py --panel \\
        data/benchmark/runs-queue/queue-gemma4-e4b@mac data/benchmark/runs-queue/queue-qwen3-14b@mac
"""

import argparse
import http.client
import json
import sqlite3
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from benchmark_review import (  # noqa: E402 — the question, unchanged
    PROMPT,
    SNIPPET,
    ask,
    decisions_on,
    docket_options,
    locate,
)

from docketyard.citator import keys, methods, resolve, review, walk  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PROMPT_VERSION = "review/2026-09-11"  # the same prompt, so the same version

# EVERY decision carrying a document, not one of them. `decision_attachment` is not unique by
# document, and `walk.own_by_document` takes the union for a stated reason (ADR 0005): a
# number that is the own proceeding of ANY carrier is a caption in these bytes. Naming one
# arbitrary carrier here would ask the model a different question than the finder answered.
_CARRIERS = """
SELECT a.document_sha256, r.stb_decision_id
  FROM decision_attachment a
  JOIN decision_record r ON r.decision_pk = a.decision_pk
"""


def carriers(con) -> dict[str, list[str]]:
    """document sha256 -> the ids of EVERY decision carrying it, in order."""
    out: dict[str, list[str]] = {}
    for sha, did in con.execute(_CARRIERS):
        out.setdefault(sha, []).append(str(did))
    return {sha: sorted(set(dids)) for sha, dids in out.items()}


def pages_of(con, sha: str, machine: set[str]) -> dict[int, str]:
    """The document's pages AS THE FINDER READ THEM, by page number.

    `walk._PAGES` gives the live reading per page; `walk.documents` then keeps only the
    machine channels, because a page whose live reading is `human` is never what a model pass
    read from and the finder skips it outright. Dropping that filter here would show the
    panel a corrected page the finder never saw (code review 2026-09-11)."""
    return {
        page: text for page, text, channel in con.execute(walk._PAGES, (sha,)) if channel in machine
    }


def run(args) -> int:
    con = sqlite3.connect(f"file:{args.store}?mode=ro", uri=True)
    held = keys.registry(con)
    own = walk.own_by_document(con)  # the shipped union, not a re-derivation
    who = carriers(con)
    machine = methods.machine_channels(con)
    label = args.model.replace(":", "-").replace("/", "-")
    # THE HOST IS PART OF THE RUN, as it is for the benchmark: the same weights answer
    # differently on Metal, CUDA and CPU (measured 2026-09-11), so two machines never share
    # a directory and a stored judgement would carry the host in its method key.
    if args.tag:
        label += f"@{args.tag}"
    with urllib.request.urlopen(f"{args.host}/api/version", timeout=30) as resp:
        engine = f"ollama {json.load(resp).get('version')}"
    out_dir = args.out / f"queue-{label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    items = review.pending(con, args.queue, limit=None)
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        by_doc[item["citing_document"]].append(item)
    shas = sorted(by_doc)[: args.limit or None]
    print(f"{len(items):,} items in {args.queue} over {len(by_doc):,} documents", flush=True)

    for sha in shas:
        target = out_dir / f"{sha[:16]}.json"
        if target.exists() and not errored(target):
            continue
        if sha not in own:
            # the queue holds a key on a document that carries no decision: the question
            # cannot be asked fairly without its own dockets. Loudly, never silently.
            print(f"{sha[:16]}: no citing decision in the record, skipped", flush=True)
            continue
        mine = own[sha]
        pages, started = pages_of(con, sha, machine), time.monotonic()
        record = {
            "citing_document": sha,
            "decision_ids": who.get(sha, []),
            "queue": args.queue,
            "model": f"review:{label}",
            "prompt_version": PROMPT_VERSION,
            "host": args.tag or None,
            "engine": engine,
            "items": [],
        }
        for item in by_doc[sha]:
            page_no, key = item["page"], item["target_key"]
            body = pages.get(page_no)
            if body is None:
                # The queue names a page the citator's own reading does not hold. Two
                # different findings, kept apart: no text at all, or text without the key.
                record["items"].append({**_key_of(item), "skipped": "the page has no reading"})
                continue
            where = locate(body, key)
            if where is None:
                record["items"].append({**_key_of(item), "skipped": "not found on its page"})
                continue
            s, e = where
            snippet = f"{body[max(0, s - SNIPPET) : s]}<<{body[s:e]}>>{body[e : e + SNIPPET]}"
            dockets = docket_options(key, held)
            # THE RAW FORM, NOT THE KEY. `resolve._anchored` anchors on the number AS THE PAGE
            # PRINTED IT, which is what `resolve.resolve` and `benchmark_review` both pass.
            # Handing it the normalised key loses the date on every hyphenated printing —
            # measured 2026-09-11 as 43 of the 1,476 exposed items, whose decision list then
            # collapsed to "none" and which could never have cleared (code review).
            served = resolve.served_date(
                resolve._anchored(item["quoted_passage"], item["cited_raw"])
            )
            offered = [
                (dec, f"{kind} in {k}, served {served}")
                for k, _ in dockets
                if served and k in held
                for dec, kind in decisions_on(con, held[k], served)
            ]
            prompt = PROMPT.format(
                own=", ".join(sorted(mine)),
                printed=item["cited_raw"],
                dockets="; ".join(f'"{k}" ({why})' for k, why in dockets),
                decisions="; ".join([f'"{d}" ({why})' for d, why in offered] + ['"none"']),
                snippet=snippet,
            )
            try:
                answer, error = ask(args.host, args.model, prompt, args.timeout), None
            except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
                answer, error = None, f"{type(exc).__name__}: {exc}"
            record["items"].append(
                {
                    **_key_of(item),
                    "offered": {"dockets": dockets, "decisions": offered},
                    "answer": answer,
                    **({"error": error} if error else {}),
                }
            )
        record["seconds"] = round(time.monotonic() - started, 1)
        target.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(
            f"{sha[:16]} ({','.join(record['decision_ids']) or '?'}):"
            f" {len(record['items'])} items in {record['seconds']}s",
            flush=True,
        )
    return 0


def _key_of(item: dict) -> dict:
    return {
        "page": item["page"],
        "target_kind": item["target_kind"],
        "target_key": item["target_key"],
        "cited_raw": item["cited_raw"],
        "rendered": item["target_key_rendered"],
    }


def errored(path: Path) -> int:
    """Mentions that never reached the model. A resume over one of these bakes the gap in and
    the clearing rate is then read as a fact when it is a floor (benchmark_review.py)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    return sum(1 for i in doc["items"] if i.get("error"))


def load_run(run_dir: Path) -> dict[tuple, dict]:
    """The queue's OWN four-column key -> the model's answer, for every item it answered.

    `target_kind` belongs in the key: it is one of `review._KEY_COLS`, and dropping it
    collapses two items that share a page and a number into one, so an item disappears from
    both sides of the rate without a word (code review 2026-09-11)."""
    out = {}
    for path in sorted(run_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for item in doc["items"]:
            if item.get("skipped") or item.get("error") or not item.get("answer"):
                continue
            key = (doc["citing_document"], item["page"], item["target_kind"], item["target_key"])
            out[key] = item
    return out


def queues_of(run_dir: Path) -> set[str]:
    """Which queue a run was drawn from. Stored on every record rather than inferred from the
    directory's name, which anyone can rename."""
    return {
        json.loads(p.read_text(encoding="utf-8")).get("queue", "")
        for p in sorted(run_dir.glob("*.json"))
    }


def panel(runs: list[Path], out: Path | None = None) -> int:
    """What the panel would CLEAR, and what it leaves to a person. No precision is printed:
    nothing here is scored against a truth, because the queue has none until the operator
    judges a slice. Claiming one would be the inversion he refused on the work card."""
    runs = list(dict.fromkeys(r.resolve() for r in runs))
    if len(runs) < 2:
        print("a panel is two or more runs; one run agrees with itself on everything")
        return 2
    sets: dict[str, dict] = {}
    seen_queues: set[str] = set()
    for r in runs:
        if r.name in sets:
            print(f"two runs are both named {r.name}: rename or score them apart")
            return 2
        sets[r.name] = load_run(r)
        seen_queues |= queues_of(r)
    # TWO QUEUES ARE TWO QUESTIONS. `citation_exposed` asks which of two docket numbers the
    # page means; `citation_unresolved` asks something else entirely. Agreement across them
    # is not agreement, and the sheet that judges the cleared keys joins on one queue's query.
    if len(seen_queues) != 1:
        print(f"the runs are not from one queue: {sorted(seen_queues)}")
        return 2
    queue = seen_queues.pop()
    for name, s in sets.items():
        print(f"  {name:36s} answered {len(s):,} items")
    shared = set.intersection(*(set(s) for s in sets.values()))
    print(f"\nanswered by every member of the panel: {len(shared):,}")
    if not shared:
        print("no item was answered by every member; there is nothing to compare")
        return 2

    agreed_all = agreed_cite = 0
    rows = []
    for k in sorted(shared):
        answers = [sets[n][k]["answer"] for n in sets]
        kinds = {a.get("names") for a in answers}
        if len(kinds) != 1:
            continue
        agreed_all += 1
        if kinds != {"document"}:
            continue  # agreed, but not a citation to a document
        dockets = {a.get("docket") for a in answers}
        decisions = {a.get("decision") for a in answers}
        if len(dockets) == 1 and len(decisions) == 1 and "none" not in decisions:
            agreed_cite += 1
            rows.append((k, next(iter(dockets)), next(iter(decisions))))
    print(f"the panel agrees on the KIND for      {agreed_all:,} ({agreed_all / len(shared):.1%})")
    print(
        f"agrees it is a document AND on which: {agreed_cite:,} ({agreed_cite / len(shared):.1%})"
    )
    print(f"left to a person:                     {len(shared) - agreed_cite:,}")
    if out:
        # The keys the panel WOULD clear, written out rather than counted away: a clearing
        # rule cannot be accepted on a rate alone, and a slice of these is what the operator
        # judges to give the rule a measured precision (ADR 0017 D3).
        out.write_text(
            json.dumps(
                {
                    "panel": sorted(sets),
                    "queue": queue,
                    "answered_by_all": len(shared),
                    "would_clear": [
                        {
                            "citing_document": k[0],
                            "page": k[1],
                            "target_kind": k[2],
                            "target_key": k[3],
                            "docket": docket,
                            "decision": decision,
                        }
                        for k, docket, decision in rows
                    ],
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\n{len(rows):,} keys the panel would clear written to {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--store", type=Path, help="a copy of production, with the citator loaded")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--queue", default="citation_exposed", choices=sorted(review.QUEUES))
    ap.add_argument("--out", type=Path, default=ROOT / "data/benchmark/runs-queue")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--limit", type=int, default=0, help="documents, for a smoke test")
    ap.add_argument("--tag", default="", help="the host, so two machines never share a run")
    ap.add_argument("--panel", type=Path, nargs="+")
    ap.add_argument("--clears", type=Path, help="write the keys the panel would clear here")
    args = ap.parse_args()
    if args.panel:
        return panel(args.panel, args.clears)
    if not (args.model and args.store):
        ap.error("--model and --store are needed to run; --panel to read the runs together")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
