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
import urllib.error
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
                    "kind": {"type": "string", "enum": ["citation", "deadline", "caption"]},
                    "quoted": {"type": "string"},
                    "target": {"type": "string"},
                    "target_kind": {
                        "type": "string",
                        "enum": [
                            "stb",
                            "court",
                            "record",
                            "self",
                            "date",
                            "period",
                            "reference",
                            "indefinite",
                        ],
                    },
                    "note": {"type": "string"},
                },
                "required": ["kind", "quoted", "target", "target_kind", "note"],
            },
        }
    },
    "required": ["findings"],
}
PROMPT = """You are labelling one page of a Surface Transportation Board decision for a benchmark.
Find every CITATION, DEADLINE and CAPTION reference on this page and return them as JSON.
"quoted" is always the text exactly as printed on the page. Never compute anything.

CITATION - a reference to a decision or docket other than this decision's own. Set
"target" to what a citator would resolve, and "target_kind" to one of:
  stb    - a Board or ICC DECISION: "Docket No. FD 36500", "EP 711 (Sub-No. 1)",
           "1 S.T.B. 233 (1996)", "360 I.C.C. 91 (1979)", "Decision No. 1, FD 36732 et al.,
           slip op. at 6", "NPRM, EP 787, slip op. at 4", a prior decision given by date
           alone ("By decision served March 12, 2024, the Board vacated the NITU"), or a
           short form ("Decision No. 44, 1 S.T.B. at 562", "Id. at 5"). This holds even
           when the decision cited sits in THIS decision's own docket - a prior decision is
           a different document, and citing it is a real reference. Target is the docket as
           printed, or the document as printed where it is given by date alone
           ("decision served March 12, 2024").
  court  - a court case: "Grainbelt Corp. v. STB, 109 F.3d 794 (D.C. Cir. 1997)". Target is
           the reporter cite ("109 F.3d 794"), or, where none is printed, the court's own
           docket number ("No. 25-7442").
  record - a FILING in this proceeding, cited by party and date: "IANR Reply 2, Aug. 14,
           2024, FD 36798". Set target to the docket as printed: it addresses the filing,
           which is what a citator resolves. What makes this `record` rather than `stb` is
           that the thing cited is a party's filing, not a decision of the Board.
Statutes and CFR sections are NOT citations.

CAPTION - the decision's own proceeding named as ITSELF, naming no document: the caption,
a section heading, a table header, a bare "Docket No. X", or the "All pleadings, referring
to Docket No. X, should be filed" paragraph. Set kind "caption", target_kind "self", and
target to the docket as printed. These are not citations - the decision belongs to that
docket, it does not cite it - but list them, because telling the two apart is the task.

The test is whether the text names a DOCUMENT or only the PROCEEDING. "Docket No. EP 787"
is a caption; "NPRM, EP 787, slip op. at 4" is a citation, because it points at a specific
decision. Words like "slip op.", "Decision No.", "served", "NPRM" or "order" mean a
document is being cited, whatever docket it sits in.

DEADLINE - a date or period THIS decision sets for someone to act by. A date recited as
history is not one. "quoted" is the whole sentence that sets it; "target_kind" is:
  date       - a date is printed: target is that date exactly as printed ("October 15, 2024").
  period     - only a period is printed ("within 30 days", "15 days after the draft EA is
               available"): leave target empty; the quoted sentence is the whole answer.
  reference  - the date is another known date, not printed here ("effective on its service
               date"): set target to that reference, e.g. "service date".
  indefinite - no end is fixed ("until further order of the Board", deadlines tolled by a
               lapse in appropriations): leave target empty.

Rules: copy text exactly as printed, including em dashes and abbreviations. List each
distinct reference once; repeating the same target later on the page is neither required
nor penalised. If the page has none of the three, return {{"findings": []}}.

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


class Fatal(RuntimeError):
    """A condition no page will recover from: no credit, a bad key, a rejected model."""


def ask_claude(model: str, prompt: str, timeout: float, cfg: dict) -> tuple[dict, float]:
    """The same prompt through the Anthropic API, so that one extractor can be pointed at
    the publisher's text layer and at an OCR of the same pages and the difference charged
    to OCR rather than to the extractor.

    The schema is forced through a tool call, which is this API's equivalent of Ollama's
    `format`. Asking for JSON in prose does not work: a first attempt did that and 429 of
    443 pages came back in a shape the reader did not recognise -- `type` for `kind`, or no
    `findings` wrapper at all -- which reads as an engine that found nothing rather than as
    a malformed answer. Key handling follows ocr_run.py: never on a command line, never
    printed."""
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [
                {
                    "name": "record_findings",
                    "description": "Record every citation, caption and deadline on the page.",
                    "input_schema": SCHEMA,
                }
            ],
            "tool_choice": {"type": "tool", "name": "record_findings"},
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": cfg["_key"],
        },
    )
    t = time.monotonic()
    wait = 2.0
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                answer = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < 4:
                e.close()
                time.sleep(wait)
                wait *= 2
                continue
            detail = e.read(300).decode("utf-8", "replace")
            if e.code in (400, 401, 403):
                raise Fatal(f"HTTP {e.code}: {detail}") from None
            raise RuntimeError(f"HTTP {e.code}: {detail}") from None
        except (urllib.error.URLError, OSError):
            if attempt < 4:
                time.sleep(wait)
                wait *= 2
                continue
            raise RuntimeError("transport failed after retries") from None
    else:
        raise RuntimeError("retries exhausted")
    stop = answer.get("stop_reason")
    if stop not in (None, "end_turn", "tool_use"):
        raise RuntimeError(f"stop_reason {stop}")
    usage = answer.get("usage", {})
    cfg["_in"] = cfg.get("_in", 0) + usage.get("input_tokens", 0)
    cfg["_out"] = cfg.get("_out", 0) + usage.get("output_tokens", 0)
    for block in answer.get("content", []):
        if block.get("type") == "tool_use":
            return _findings(block.get("input")), time.monotonic() - t
    raise RuntimeError("no tool_use block in the answer")


def _findings(payload) -> dict:
    """A tool input is not always the shape its schema declares: on a small share of pages
    `findings` comes back as the JSON *text* rather than the array. Left alone it reads as
    a page with hundreds of findings, one per character."""
    if not isinstance(payload, dict):
        return {"findings": []}
    got = payload.get("findings")
    if isinstance(got, str):
        try:
            parsed = json.loads(got)
        except json.JSONDecodeError:
            return {"findings": []}
        got = parsed.get("findings") if isinstance(parsed, dict) else parsed
    if not isinstance(got, list):
        return {"findings": []}
    return {"findings": [x for x in got if isinstance(x, dict)]}


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
    ap.add_argument(
        "--backend",
        choices=("ollama", "claude"),
        default="ollama",
        help="claude reads the key from ANTHROPIC_API_KEY or ~/.anthropic-key",
    )
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--only", nargs="*", help="decision ids to run (default: every file)")
    args = ap.parse_args()
    cfg: dict = {}
    if args.backend == "claude":
        import importlib.util  # noqa: PLC0415 — only the claude path needs the key loader

        spec = importlib.util.spec_from_file_location(
            "ocr_run", Path(__file__).parent / "ocr_run.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load ocr_run.py for its key handling")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cfg["_key"] = mod._api_key()  # fails now, not on page 1 of 443
    # `hf.co/org/repo:Q8_0` (a Hugging Face GGUF) must not become nested directories
    out_dir = Path(args.out) / args.model.replace(":", "-").replace("/", "-")
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
            "prompt_version": "2026-08-29",
            "pages": [],
        }
        started = time.monotonic()
        for page, body in pages_of(text):
            prompt = PROMPT.format(page=page, decision_id=decision_id, text=body[:24000])
            try:
                if args.backend == "claude":
                    parsed, elapsed = ask_claude(args.model, prompt, args.timeout, cfg)
                else:
                    parsed, elapsed = ask(args.host, args.model, prompt, args.timeout)
                record["pages"].append({"page": page, "seconds": round(elapsed, 1), **parsed})
            except Fatal as e:
                # nothing later will succeed either; keep what was answered and say why
                target.write_text(
                    json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
                )
                print(f"{decision_id}: stopped at page {page} — {e}")
                return 1
            except Exception as e:  # noqa: BLE001 — one page must not cost the run
                record["pages"].append({"page": page, "error": f"{type(e).__name__}: {e}"})
        record["seconds"] = round(time.monotonic() - started, 1)
        n = sum(len(p.get("findings", [])) for p in record["pages"])
        target.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{decision_id}: {len(record['pages'])} pages, {n} findings, {record['seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
