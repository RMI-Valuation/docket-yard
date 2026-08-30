"""The regex-first design's second half: a model classifies each regex hit's ROLE.

`benchmark_regex.py` measured that finding docket numbers needs no model (94.7% of
docket-shaped targets, registry-validated) and that the keyword window is a poor judge of
what a hit *is*. This harness measures the judgement alone: for every registry-validated
hit, a small model answers one forced-choice question — does the surrounding text name a
DOCUMENT (a citation), only the PROCEEDING (a caption), or a FILING in this record (a
record cite)? The question is the labelling guide's own test (`docs/citator-gate.md`).

Output is a run in benchmark_run.py's shape, one finding per (page, target), so
benchmark_score.py scores it beside the extractors. Because the finder is fixed, recall is
capped at the regex's own; what this measures is the classifier's precision on the caption
split — the sharpest probe the sheet has.

    # on RMI-AI-MACHINE, after the extraction batch drains:
    python3 benchmark_roles.py --model qwen3:14b --text-dir /data/docketyard/benchmark/text \\
        --registry /path/to/store.sqlite --out /data/docketyard/benchmark/runs-roles

    # anywhere, no model — the keyword heuristic through identical plumbing:
    python benchmark_roles.py --backend mock ...

The prompt states the test and quotes the snippet; it names no real docket in its
examples — a smaller model copies worked examples onto pages where they do not exist
(measured 2026-08-30: 13 of qwen3:14b's 26 docket-shaped extras were the extraction
prompt's own examples), so the examples here are placeholders the registry can never hold.
"""

import argparse
import json
import time
import urllib.request
from pathlib import Path

from benchmark_regex import (
    DOC_WORDS,
    DOCKET,
    PAGE_RE,
    WINDOW,
    key_of,
    own_dockets,
    printed,
    registry,
)

PROMPT_VERSION = "roles/2026-08-30"
SCHEMA = {
    "type": "object",
    "properties": {"role": {"type": "string", "enum": ["citation", "caption", "record"]}},
    "required": ["role"],
}
PROMPT = """You are classifying ONE docket-number mention in a Surface Transportation \
Board decision. The test: does the text around the number name a DOCUMENT, or only the \
PROCEEDING, or a FILING a party submitted?

- citation - the text points at a specific decision or order: words like "slip op.", \
"Decision No.", "served", "NPRM", "order", or a case name followed by a pin cite. \
Example shape: "Decision No. 9, XX 99999 et al., slip op. at 6".
- caption - the number names only the proceeding itself: a heading, "Docket No. XX 99999", \
the all-pleadings sentence, a bare number in running text. Nothing points at a document.
- record - the text cites a party's FILING and the docket number is only its address. \
Example shape: "Applicant Reply 2, Jan. 1, 2020, XX 99999".

The mention to classify is the number between << >>. Answer with the JSON {{"role": ...}} \
and nothing else.

<<<
{snippet}
>>>"""

SNIPPET = 400  # characters either side of the hit


def ask(host: str, model: str, prompt: str, timeout: float) -> str:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": SCHEMA,
            "think": False,
            "options": {"temperature": 0, "num_ctx": 4096},
        }
    ).encode()
    req = urllib.request.Request(
        f"{host}/api/generate", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        answer = json.load(resp)
    try:
        role = json.loads(answer.get("response") or "{}").get("role")
    except json.JSONDecodeError:
        role = None
    # An unreadable answer is recorded as one, never folded into `citation`: scoring an
    # inference failure as the majority class hides it inside the figure being measured
    # (code review, 2026-08-30). `unreadable` matches no truth row, so it costs precision
    # rather than quietly earning recall.
    return role if role in ("citation", "caption", "record") else "unreadable"


def mock(snippet: str) -> str:
    """The keyword-window heuristic, for plumbing tests and as the floor to beat."""
    return "citation" if DOC_WORDS.search(snippet) else "caption"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="mock")
    ap.add_argument("--backend", choices=("ollama", "mock"), default="ollama")
    ap.add_argument("--text-dir", required=True, type=Path)
    ap.add_argument("--registry", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()
    held = registry(args.registry)
    own = own_dockets(args.registry)
    label = "mock" if args.backend == "mock" else args.model.replace(":", "-").replace("/", "-")
    out_dir = args.out / f"roles-{label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(args.text_dir.glob("*.txt")):
        did = f.stem.rsplit("-", 1)[-1]
        target = out_dir / f"{did}.json"
        if target.exists():
            print(f"{did}: done already")
            continue
        parts = PAGE_RE.split(f.read_text(encoding="utf-8", errors="replace"))
        record = {
            "decision_id": did,
            "model": f"roles:{label}",
            "prompt_version": PROMPT_VERSION,
            "pages": [],
        }
        started = time.monotonic()
        for i in range(1, len(parts), 2):
            page_no, body = int(parts[i]), parts[i + 1]
            findings, seen = [], set()
            for m in DOCKET.finditer(body):
                key = key_of(m)
                if key not in held or key in seen:
                    continue
                seen.add(key)
                before = body[max(0, m.start() - SNIPPET) : m.start()]
                after = body[m.end() : m.end() + SNIPPET]
                snippet = f"{before}<<{m.group(0)}>>{after}"
                if args.backend == "mock":
                    ctx = body[max(0, m.start() - WINDOW) : m.end() + WINDOW]
                    role = mock(ctx)
                else:
                    role = ask(args.host, args.model, PROMPT.format(snippet=snippet), args.timeout)
                # a `citation` to the decision's own proceeding stays a citation here;
                # the store's projection rule (ADR 0017 decision 5) is downstream, and
                # the sheet's own-docket document citations are genuine edges
                kind = "citation" if role in ("citation", "record") else "caption"
                tk = {
                    "citation": "stb",
                    "record": "record",
                    "caption": "self",
                    "unreadable": "unreadable",
                }[role]
                start = body.rfind("\n", 0, m.start()) + 1
                end = body.find("\n", m.end())
                findings.append(
                    {
                        "kind": kind,
                        "quoted": body[start : end if end > 0 else len(body)].strip(),
                        "target": printed(m),
                        "target_kind": tk,
                        "note": f"regex hit; role={role}; own={key in own.get(did, set())}",
                    }
                )
            record["pages"].append({"page": page_no, "findings": findings})
        record["seconds"] = round(time.monotonic() - started, 1)
        target.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        n = sum(len(p["findings"]) for p in record["pages"])
        print(f"{did}: {n} hits classified in {record['seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
