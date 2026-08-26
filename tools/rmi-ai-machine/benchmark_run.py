"""Benchmark step 2, the local candidate: ask an Ollama model for the citations and
deadlines in each of the sixty sampled decisions, page by page, and keep its answers.

Runs on RMI-AI-MACHINE (docs/extraction-benchmark.md § Step 2). Input is the text layer
step 0 produced (`--text-dir`, one file per decision with `===== page N =====` markers);
output is one JSON file per decision under `--out/<model>/`, the raw answers plus what
the model was asked, so a run is reproducible and scorable later against labels.csv —
which is the operator's to check first; this script never reads it.

The prompt is the labelling guide's own rules, so the model is held to the same standard
as the human sheet: quote exactly, never compute a date, page numbers from the file.
Thinking is disabled per request (Qwen3 thinks by default and pays for a monologue).

    python benchmark_run.py --model qwen3:14b --text-dir /data/docketyard/benchmark/text \\
        --out /data/docketyard/benchmark/runs
"""

import argparse
import json
import re
import time
import urllib.request
from pathlib import Path

PAGE_RE = re.compile(r"^===== page (\d+) =====$", re.M)
SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["citation", "deadline"]},
                    "quoted": {"type": "string"},
                    "target": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["kind", "quoted", "target", "note"],
            },
        }
    },
    "required": ["findings"],
}
PROMPT = """You are labelling one page of a Surface Transportation Board decision for a benchmark.
Find every CITATION and every DEADLINE on this page and return them as JSON.

A citation is any reference to a Board or ICC decision or docket other than the caption of
the decision itself: docket numbers ("Docket No. FD 36500", "EP 711 (Sub-No. 1)", "AB 290
(Sub-No. 414X)"), reporter citations ("1 S.T.B. 233 (1996)", "360 I.C.C. 91 (1979)"),
prior decisions in the same docket (even by date only: "decision served March 12, 2024"),
short forms ("Decision No. 44, 1 S.T.B. at 562", "Id. at 5"), and court cases (mark those
with note "court"). Statutes and CFR sections are NOT citations. For a citation, "quoted" is
the citation exactly as printed and "target" is the docket or decision cited (the part a
citator would resolve).

A deadline is a date, or a period, that this decision itself sets for someone to act by:
replies due, effective dates, comment periods, filing windows, "effective on its service
date". A date recited as history is NOT a deadline. For a deadline, "quoted" is the whole
sentence that sets it, exactly as printed, and "target" is the date exactly as printed
("October 15, 2024") — never computed; if the sentence gives only a period ("within 30
days"), leave target empty and say so in "note".

Rules: copy text exactly as printed, including em dashes and abbreviations; one finding per
distinct string on the page; use note "self" for a reference to this decision's own docket.
If the page has neither, return {{"findings": []}}.

Page {page} of decision {decision_id}:
<<<
{text}
>>>"""


def pages_of(text: str) -> list[tuple[int, str]]:
    parts = PAGE_RE.split(text)
    out = []
    for i in range(1, len(parts), 2):
        out.append((int(parts[i]), parts[i + 1].strip()))
    return out


def ask(host: str, model: str, prompt: str, timeout: float) -> tuple[dict, float]:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": SCHEMA,
            "think": False,
            "options": {"temperature": 0, "num_ctx": 16384},
        }
    ).encode()
    req = urllib.request.Request(
        f"{host}/api/generate", data=body, headers={"Content-Type": "application/json"}
    )
    t = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        answer = json.load(resp)
    elapsed = time.monotonic() - t
    try:
        parsed = json.loads(answer.get("response") or "{}")
    except json.JSONDecodeError:
        parsed = {"findings": [], "unparsed": answer.get("response")}
    return parsed, elapsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--text-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--only", nargs="*", help="decision ids to run (default: every file)")
    args = ap.parse_args()
    out_dir = Path(args.out) / args.model.replace(":", "-")
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(Path(args.text_dir).glob("*.txt"))
    for f in files:
        decision_id = f.stem.rsplit("-", 1)[-1]
        if args.only and decision_id not in args.only:
            continue
        target = out_dir / f"{decision_id}.json"
        if target.exists():
            print(f"{decision_id}: done already")
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        record = {
            "decision_id": decision_id,
            "model": args.model,
            "prompt_version": "2026-08-26",
            "pages": [],
        }
        started = time.monotonic()
        for page, body in pages_of(text):
            prompt = PROMPT.format(page=page, decision_id=decision_id, text=body[:24000])
            try:
                parsed, elapsed = ask(args.host, args.model, prompt, args.timeout)
                record["pages"].append({"page": page, "seconds": round(elapsed, 1), **parsed})
            except Exception as e:  # noqa: BLE001 — one page must not cost the run
                record["pages"].append({"page": page, "error": f"{type(e).__name__}: {e}"})
        record["seconds"] = round(time.monotonic() - started, 1)
        n = sum(len(p.get("findings", [])) for p in record["pages"])
        target.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{decision_id}: {len(record['pages'])} pages, {n} findings, {record['seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
