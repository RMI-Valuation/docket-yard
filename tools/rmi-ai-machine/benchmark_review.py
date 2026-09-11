"""Step 2 of the local-reviewer measurement (`docs/extraction-benchmark.md` § Local models as
reviewers): a model is asked THE REVIEW QUESTION about every docket-shaped hit the shipped finder
makes in the sixty checked decisions, and is handed what the record holds.

Step 1 scored the stored role runs, which asked "document, proceeding or filing?" with no record
behind it. The labelling guide's own test turns on a fact that model was never told: which
proceeding the citing decision is entered in. This run tells it, and gives it the candidates the
resolver would weigh:

  * the decision's own dockets (ADR 0017 D1 — the record knows them, and the guide's caption
    is the decision's OWN docket named as itself);
  * whether the registry holds the number, and the shorter number when a footnote marker could
    have lengthened it (the exposure test and rule 2, `resolve.resolve`);
  * every decision in that docket served on the date the passage prints for this target
    (`resolve.served_date` over `resolve._anchored`), ALL of them — `keys.works` drops a day
    holding several, and a reviewer is shown those too.

The output is a run in benchmark_run.py's shape, so the caption split is scored as every other
engine is. Each finding also carries the model's `decision`, which `--score` checks against the
work sheet (`docs/research/benchmark/work-labels.csv`), and the finder's own `kind`, so the
own-docket rule is scored beside the models on the same hits. Nothing here writes to a store.

    # the Mac mini's Ollama through a tunnel (ssh -N -L 11435:localhost:11434 rmi-mac), then:
    python tools/rmi-ai-machine/benchmark_review.py --model qwen3:14b \\
        --store data/<a production copy>.sqlite --host http://127.0.0.1:11435
    python tools/rmi-ai-machine/benchmark_review.py --score data/benchmark/runs-review/review-*
"""

import argparse
import csv
import http.client
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import benchmark_score as bs  # noqa: E402
from citation_dryrun import own_dockets  # noqa: E402

from docketyard.citator import find, keys, resolve  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "docs/research/benchmark/work-labels.csv"
PROMPT_VERSION = "review/2026-09-11"
SNIPPET = 400  # characters either side of the mention, as benchmark_roles.py
NAMES = ("document", "proceeding", "filing")
SCHEMA = {
    "type": "object",
    "properties": {
        "names": {"type": "string", "enum": list(NAMES)},
        "docket": {"type": "string"},
        "decision": {"type": "string"},
    },
    "required": ["names", "docket", "decision"],
}
# The examples are placeholders the registry can never hold: a small model copies worked
# examples onto pages where they do not exist (13 of qwen3:14b's extras, 2026-08-30).
PROMPT = """You are checking ONE docket-number mention in a Surface Transportation Board \
decision, as a reviewer would.

The decision you are reading is entered in these dockets: {own}.
The mention is the number between << >> in the text below, printed as "{printed}".

Answer three things:

1. names: what the text around the mention points at.
   - "document": a specific decision or order. Words like "slip op.", "Decision No.", \
"served", "NPRM", or a case name with a pin cite. A prior decision in one of this decision's \
own dockets is still a document.
   - "proceeding": only the proceeding itself. A heading, "Docket No. XX 99999", the \
all-pleadings sentence, or a bare number that names no document. One of this decision's own \
dockets named as itself is the proceeding.
   - "filing": a party's filing, where the docket number is only its address.
2. docket: which docket the page means. One of: {dockets}.
3. decision: if it names a document, which one. One of: {decisions}. Answer "none" if it \
names no document, or if none of these is it.

Answer with the JSON {{"names": ..., "docket": ..., "decision": ...}} and nothing else.

<<<
{snippet}
>>>"""


def ask(host: str, model: str, prompt: str, timeout: float) -> dict | None:
    """The model's answer, or None when it is not one: an unreadable answer is recorded as
    such and never folded into a class (benchmark_roles.py, code review 2026-08-30)."""
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
        out = json.loads(answer.get("response") or "{}")
    except json.JSONDecodeError:
        return None
    return out if isinstance(out, dict) and out.get("names") in NAMES else None


def locate(page: str, key: str) -> tuple[int, int] | None:
    """Where the first mention of `key` sits on the page, as the finder reads it."""
    for m in keys.DOCKET.finditer(page):
        if keys.normalise(find.printed(page, m)) == key:
            return m.start(), find._target_end(page, m)
    return None


def docket_options(key: str, held: dict[str, int]) -> list[tuple[str, str]]:
    """The number as printed, and the shorter one where `resolve.resolve` would weigh it: the
    exposure test (four digits or fewer, both held) and rule 2 (five digits, only the shorter
    held)."""
    opts = [(key, "in the record" if key in held else "NOT in the record")]
    bare = keys.BARE_KEY.match(key)
    digits = len(bare.group(1)) if bare else 0
    stripped = resolve._stripped(key)
    if (
        stripped
        and stripped in held
        and ((key in held and digits <= 4) or (digits == 5 and key not in held))
    ):
        opts.append((stripped, "in the record; the last digit printed may be a footnote marker"))
    return opts


def decisions_on(con, docket_id: int, served: str) -> list[tuple[str, str]]:
    return con.execute(
        "SELECT DISTINCT stb_decision_id, COALESCE(decision_type, 'decision') FROM decision_record"
        " WHERE docket_id = ? AND service_date = ? ORDER BY stb_decision_id",
        (docket_id, served),
    ).fetchall()


def errored(path: Path) -> int:
    """How many of a finished decision's mentions never reached the model. A run resumed over
    one of these bakes the gap in for good: the mentions are scored as answered-and-wrong, and
    the model's recall is read as a fact when it is a floor (code review 2026-09-11)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    return sum(1 for pg in doc["pages"] for f in pg["findings"] if f.get("error"))


def review(args) -> int:
    con = sqlite3.connect(f"file:{args.store}?mode=ro", uri=True)
    held, own = keys.registry(con), own_dockets(con)
    label = args.model.replace(":", "-").replace("/", "-")
    # THE HOST IS PART OF THE RUN (the operator's decision, 2026-09-11): the same weights at
    # temperature 0 may answer differently on Metal, CUDA and CPU, and that is what the
    # cross-machine run measures, so two hosts must never share a directory
    if args.tag:
        label += f"@{args.tag}"
    with urllib.request.urlopen(f"{args.host}/api/version", timeout=30) as resp:
        engine = f"ollama {json.load(resp).get('version')}"
    out_dir = args.out / f"review-{label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(args.text_dir.glob("*.txt"))[: args.limit or None]
    for path in files:
        did = path.stem.rsplit("-", 1)[-1]
        target = out_dir / f"{did}.json"
        if target.exists() and not errored(target):
            continue
        if did not in own:
            # without its own dockets the question cannot be asked fairly; loudly, not silently
            print(f"{did}: no docket in the registry, skipped")
            continue
        started, record = (
            time.monotonic(),
            {
                "decision_id": did,
                "model": f"review:{label}",
                "prompt_version": PROMPT_VERSION,
                "host": args.tag or None,
                "engine": engine,
                "pages": [],
            },
        )
        for page_no, body in find.pages(path.read_text(encoding="utf-8", errors="replace")):
            findings = []
            for f in find.find(body, own[did]):
                key = keys.normalise(f["target"])
                where = locate(body, key) if key else None
                if key is None or where is None:
                    continue
                s, e = where
                snippet = f"{body[max(0, s - SNIPPET) : s]}<<{body[s:e]}>>{body[e : e + SNIPPET]}"
                dockets = docket_options(key, held)
                served = resolve.served_date(resolve._anchored(f["quoted"], f["target"]))
                offered = [
                    (dec, f"{kind} in {k}, served {served}")
                    for k, _ in dockets
                    if served and k in held
                    for dec, kind in decisions_on(con, held[k], served)
                ]
                prompt = PROMPT.format(
                    own=", ".join(sorted(own[did])),
                    printed=f["target"],
                    dockets="; ".join(f'"{k}" ({why})' for k, why in dockets),
                    decisions="; ".join([f'"{d}" ({why})' for d, why in offered] + ['"none"']),
                    snippet=snippet,
                )
                try:
                    answer, error = ask(args.host, args.model, prompt, args.timeout), None
                except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
                    # URLError and TimeoutError alone let RemoteDisconnected and a truncated
                    # body abort the whole run, which the documented ssh -L tunnel makes a
                    # live risk (code review 2026-09-11)
                    answer, error = None, f"{type(exc).__name__}: {exc}"
                names = answer["names"] if answer else "unreadable"
                chosen = answer.get("docket") if answer else None
                findings.append(
                    {
                        # benchmark_run.py's shape, so benchmark_score reads the caption split
                        "kind": "caption" if names == "proceeding" else "citation",
                        "target_kind": {
                            "document": "stb",
                            "filing": "record",
                            "proceeding": "self",
                        }.get(names, "unreadable"),
                        "target": chosen if chosen in {k for k, _ in dockets} else key,
                        "quoted": f["quoted"],
                        "decision": answer.get("decision") if answer else None,
                        "finder_kind": f["kind"],
                        "key": key,
                        "offered": {"dockets": dockets, "decisions": offered},
                        "answer": answer,
                        **({"error": error} if error else {}),
                    }
                )
            record["pages"].append({"page": page_no, "findings": findings})
        record["seconds"] = round(time.monotonic() - started, 1)
        target.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        n = sum(len(p["findings"]) for p in record["pages"])
        print(f"{did}: {n} mentions reviewed in {record['seconds']}s", flush=True)
    return 0


def work_truth() -> tuple[dict, set, int]:
    """(citing decision, key) -> EVERY document a reviewer said the citation names on some
    page; the pairs where stopping at the docket was right; and the count of verdicts naming
    no id, skipped and never guessed at.

    THE TRUTH IS A SET: a decision may cite two documents of one docket on two pages, and the
    sheet holds a row for each. The first draft of this kept one per pair and let the second
    overwrite the first, scoring a model wrong for naming a document the sheet says is right.
    """
    docs, stops, skipped = {}, set(), []
    for row in csv.DictReader(WORK.open(encoding="utf-8")):
        pair, v = (row["citing_decision"], row["target_key"]), row["verdict"]
        if v == "right":
            docs.setdefault(pair, set()).add(row["drafted_decision"])
        elif v == "right-to-stop":
            stops.add(pair)
        elif m := re.match(r"should-be:References (\d+)", v):
            docs.setdefault(pair, set()).add(m.group(1))
        else:
            # named, never counted: both of these DO name an id, in prose the pattern above
            # cannot read, so the pair silently leaves the truth set (code review 2026-09-11)
            skipped.append(f"{pair[0]} {pair[1]}: {v}")
    return docs, stops, skipped


def run_sets(run: Path) -> dict:
    """A run's docket-shaped pairs by class, its document choices, the finder's own, WHICH
    DECISIONS IT COVERS and how many mentions never reached the model. The last two are not
    decoration: a run that answered one decision of sixty scores as 0% recall, and a run with
    a hole in it scores as a fact what is only a floor (code review 2026-09-11)."""
    cite, cap, rule, choice = set(), set(), set(), {}
    seen, errors = set(), 0
    for f_path in sorted(run.glob("*.json")):
        doc = json.loads(f_path.read_text(encoding="utf-8"))
        did = doc["decision_id"]
        seen.add(did)
        errors += sum(1 for pg in doc["pages"] for f in pg["findings"] if f.get("error"))
        for page in doc["pages"]:
            for f in page["findings"]:
                k = bs.norm_target(f["target"])
                if not bs.DOCKET_KEY.match(k):
                    continue
                if f["kind"] == "citation" and f["target_kind"] == "stb":
                    cite.add((did, k))
                    if f.get("decision") not in (None, "none"):
                        choice.setdefault((did, k), set()).add(f["decision"])
                    else:
                        choice.setdefault((did, k), set())
                elif f["kind"] == "caption":
                    cap.add((did, k))
                if f["finder_kind"] == "citation":
                    rule.add((did, bs.norm_target(f["key"])))
    return {
        "cite": cite,
        "cap": cap,
        "rule": rule,
        "choice": choice,
        "decisions": seen,
        "errors": errors,
    }


def score(runs: list[Path]) -> int:
    runs = list(dict.fromkeys(r.resolve() for r in runs))
    by_name: dict[str, Path] = {}
    for run in runs:
        if run.name in by_name:
            print(f"two runs are both named {run.name}: {by_name[run.name]} and {run}")
            print("a run is one model on one machine (--tag); rename or score them apart")
            return 2
        by_name[run.name] = run
    sets = {run.name: run_sets(run) for run in runs}

    # EVERY RUN IS SCORED OVER THE SAME DECISIONS. Before this, the finder's baseline was read
    # off whichever run was listed first, and the agreement intersected runs of different
    # length: one 1-decision run turned the baseline from 257 pairs into 31 and emptied the
    # unanimity table, with nothing said (code review 2026-09-11).
    shared = set.intersection(*(s["decisions"] for s in sets.values()))
    covers = {n: len(s["decisions"]) for n, s in sets.items()}
    if len(set(covers.values())) > 1 or any(
        len(s["decisions"]) > len(shared) for s in sets.values()
    ):
        print("the runs do not cover the same decisions, so all are scored over the shared set:")
        for name, n in sorted(covers.items(), key=lambda kv: kv[1]):
            print(f"  {name:42s} {n:3d} decisions")
        print(f"  shared: {len(shared)}\n")
    if not shared:
        print("no decision is covered by every run; nothing can be compared")
        return 2
    for s in sets.values():
        for field in ("cite", "cap", "rule"):
            s[field] = {(d, k) for d, k in s[field] if d in shared}
        s["choice"] = {p: v for p, v in s["choice"].items() if p[0] in shared}

    t, _ = bs.truth()
    truth = {
        (d, k)
        for d, ks in bs.collect(t, "citation", "stb").items()
        for k in ks
        if bs.DOCKET_KEY.match(k) and d in shared
    }
    docs, stops, skipped = work_truth()
    docs = {p: v for p, v in docs.items() if p[0] in shared}
    stops = {p for p in stops if p[0] in shared}

    def line(name: str, pairs: set) -> None:
        real = len(pairs & truth)
        pre = f"{real / len(pairs):6.1%}" if pairs else "   n/a"
        print(
            f"  {name:28s} says citation {len(pairs):4d}  real {real:4d}  precision {pre}"
            f"  recall {real / len(truth):6.1%}"
        )

    print(f"truth: {len(truth)} docket-shaped citation targets over {len(shared)} decisions")
    line("own-docket rule (finder)", next(iter(sets.values()))["rule"])
    for name, s in sets.items():
        line(name, s["cite"])
        if s["errors"]:
            # a floor, not a measurement: these mentions were never put to the model
            print(f"  {'':28s} ^ {s['errors']} mentions never reached the model; recall is a floor")
    if len(sets) > 1:
        agree_cite = set.intersection(*(s["cite"] for s in sets.values()))
        agree_cap = set.intersection(*(s["cap"] for s in sets.values()))
        every = set.union(*(s["cite"] | s["cap"] for s in sets.values()))
        split = every - agree_cite - agree_cap
        print(f"\nall {len(sets)} agree:")
        for name, pairs in (("citation", agree_cite), ("caption", agree_cap), ("split", split)):
            real = len(pairs & truth)
            print(
                f"  {name:9s} pairs {len(pairs):4d}  real citations {real:4d}"
                f"  not {len(pairs) - real:4d}"
            )
    # Scored as SETS of (pair, document), as citations are: over the sheet's pairs, a named
    # document is right when the sheet holds it for that pair, and a document named where the
    # sheet says stopping was right is a wrong one.
    pairs = set(docs) | stops
    true = {(p, d) for p, ds in docs.items() for d in ds}
    print(
        f"\nthe document named, against the work sheet ({len(true)} documents over {len(pairs)}"
        f" pairs, {len(stops)} where stopping was right):"
    )
    for name, s in sets.items():
        named = {(p, d) for p in pairs for d in s["choice"].get(p, set())}
        hit = len(named & true)
        pre = f"{hit / len(named):6.1%}" if named else "   n/a"
        print(
            f"  {name:28s} names {len(named):4d}  right {hit:4d}  precision {pre}"
            f"  recall {hit / len(true):6.1%}"
        )
    if skipped:
        print(f"\n{len(skipped)} verdicts the sheet's pattern cannot read, so their pairs are")
        print("not in the truth above. Each DOES name an id, in prose:")
        for row in skipped:
            print(f"  {row}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--store", type=Path, help="a copy of production: the registry and decisions")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--text-dir", type=Path, default=ROOT / "data/benchmark/text")
    ap.add_argument("--out", type=Path, default=ROOT / "data/benchmark/runs-review")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--limit", type=int, default=0, help="decisions, for a smoke test")
    ap.add_argument("--tag", default="", help="the host, so two machines never share a run")
    ap.add_argument("--score", type=Path, nargs="+")
    args = ap.parse_args()
    if args.score:
        return score(args.score)
    if not (args.model and args.store):
        ap.error("--model and --store are needed to run; --score to score")
    return review(args)


if __name__ == "__main__":
    raise SystemExit(main())
