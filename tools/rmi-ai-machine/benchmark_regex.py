"""The regex-first candidate: no model. Find every docket number in a decision's text with
a pattern, keep the ones the registry holds, and classify each by the citator gate's own
test — does the surrounding text name a DOCUMENT (`slip op.`, `Decision No.`, `served`,
`NPRM`, `order`, a case name with `v.`) or only the PROCEEDING (`Docket No. EP 787`)?

Output is a run in benchmark_run.py's shape, so benchmark_score.py scores it beside the
models. Measured 2026-08-30 as the floor a paid extractor must clear on the docket-shaped
class, and as the front half of the design where a small local model only classifies
regex hits rather than extracting (docs/extraction-benchmark.md § Step 3 follow-up).

    python tools/rmi-ai-machine/benchmark_regex.py --text-dir data/benchmark/text \\
        --registry data/prod-copy.sqlite --out data/benchmark/runs-regex
"""

import argparse
import json
import re
import sqlite3
from pathlib import Path

PAGE_RE = re.compile(r"^===== page (\d+) =====$", re.M)
# `FD 36873`, `FD-36873`, `EP 542 (Sub-No. 32)`, `EP 711 (Sub-\nNo. 2)` and the older
# `NOR DOCKET NO. 42183` (prefix, then the words, then the number — decision 52616's caption).
# The PREFIX is case-sensitive and `SO` is why: "it is so 100 percent" would otherwise key as
# the docket `SO 100`, the same trap the scorer's own regex was fixed for on 2026-08-30. The
# Board prints its prefixes upper-case; the rest of the pattern stays case-insensitive.
DOCKET = re.compile(
    r"\b(AB|FD|EP|NOR|MCF|WCC|FSB|NOM|PCA|WB|MCC|ISM|SDM|SO|DOP|STA)"
    r"(?:[\s\-–—]*(?:[Nn]o\.?\s*)?|\s+[Dd]ocket\s+[Nn]o\.?\s*)(\d{1,5})([A-Z])?"
    r"(?:\s*\((?:[Ss]ub-?\s*[Nn]o\.?\s*)?(\d+)\s*([A-Z])?\))?",
)
# words that mean a document rather than a proceeding, within a window round the number
DOC_WORDS = re.compile(
    r"slip op|Decision No|served|NPRM|\border\b|\bv\.\s|Notice of Interim|\bS\.T\.B\.|I\.C\.C\.",
    re.I,
)
WINDOW = 160


def registry(db: Path) -> set:
    con = sqlite3.connect(db)
    keys = set()
    for p, s, sub, suf in con.execute("select prefix, sequence, sub_sequence, suffix from docket"):
        k = f"{p.upper()} {int(s)}"
        if sub is not None:
            k += f" ({int(sub)}{(suf or '').upper()})"
        elif suf:
            k += f" ({suf.upper()})"
        keys.add(k)
    return keys


def key_of(m: re.Match) -> str:
    """The registry key: `EP 542 (32)`, `AB 1296 (X)`, `AB 55 (814X)`."""
    k = f"{m.group(1).upper()} {int(m.group(2))}"
    if m.group(4):
        k += f" ({int(m.group(4))}{(m.group(5) or '').upper()})"
    elif m.group(3):
        k += f" ({m.group(3).upper()})"
    return k


def printed(m: re.Match) -> str:
    """The target as the Board prints it, `EP 542 (Sub-No. 32)` or `AB 1296X` — the form
    the sheet and the model runs use, and what the scorer's normaliser recognises."""
    k = f"{m.group(1).upper()} {int(m.group(2))}{(m.group(3) or '').upper()}"
    if m.group(4):
        k += f" (Sub-No. {int(m.group(4))}{(m.group(5) or '').upper()})"
    return k


def own_dockets(db: Path) -> dict:
    """{stb_decision_id: set of docket keys the decision is entered in}, from the Board's
    own table — the decision's proceeding, which a caption names and a citation does not."""
    con = sqlite3.connect(db)
    out: dict = {}
    q = (
        "select r.stb_decision_id, d.prefix, d.sequence, d.sub_sequence, d.suffix "
        "from decision_record r join docket d using (docket_id)"
    )
    for did, p, s, sub, suf in con.execute(q):
        k = f"{p.upper()} {int(s)}"
        if sub is not None:
            k += f" ({int(sub)}{(suf or '').upper()})"
        elif suf:
            k += f" ({suf.upper()})"
        out.setdefault(str(did), set()).add(k)
    return out


def findings(page_text: str, held: set, rule: str, own: set) -> list[dict]:
    """Two classifiers. `window`: a document word near the number means a citation, else a
    caption. `own`: a caption only when the number is the decision's own proceeding AND no
    document word is near; any other held docket is a citation — the record already knows
    which proceeding a decision sits in, so that is the one thing regex need not decide."""
    out, seen = [], set()
    for m in DOCKET.finditer(page_text):
        key = key_of(m)
        if key not in held or key in seen:
            continue
        seen.add(key)
        ctx = page_text[max(0, m.start() - WINDOW) : m.end() + WINDOW]
        doc_word = bool(DOC_WORDS.search(ctx))
        names_document = doc_word if rule == "window" else (doc_word or key not in own)
        # the quoted text is the sentence-ish span round the match, for the on-page check
        start = page_text.rfind("\n", 0, m.start()) + 1
        end = page_text.find("\n", m.end())
        quoted = page_text[start : end if end > 0 else len(page_text)].strip()
        out.append(
            {
                "kind": "citation" if names_document else "caption",
                "quoted": quoted,
                "target": printed(m),
                "target_kind": "stb" if names_document else "self",
                "note": "regex+registry; document word in window"
                if names_document
                else "regex+registry; no document word in window",
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-dir", required=True, type=Path)
    ap.add_argument("--registry", required=True, type=Path, help="a store copy with `docket`")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--rule", choices=("window", "own"), default="own")
    args = ap.parse_args()
    held = registry(args.registry)
    own = own_dockets(args.registry)
    out_dir = args.out / f"regex-{args.rule}"
    out_dir.mkdir(parents=True, exist_ok=True)
    orphans = []
    for f in sorted(args.text_dir.glob("*.txt")):
        did = f.stem.rsplit("-", 1)[-1]
        if did not in own:
            # without the decision's own dockets the `own` rule calls every caption a
            # citation — degrade loudly, not silently (code review, 2026-08-30)
            orphans.append(did)
        parts = PAGE_RE.split(f.read_text(encoding="utf-8", errors="replace"))
        pages = [
            {
                "page": int(parts[i]),
                "seconds": 0.0,
                "findings": findings(parts[i + 1], held, args.rule, own.get(did, set())),
            }
            for i in range(1, len(parts), 2)
        ]
        record = {
            "decision_id": did,
            "model": f"regex-{args.rule}",
            "prompt_version": "2026-08-30",
            "pages": pages,
        }
        (out_dir / f"{did}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    print(f"{len(list(out_dir.glob('*.json')))} decisions -> {out_dir}")
    if orphans and args.rule == "own":
        print(
            f"WARNING: {len(orphans)} decisions have no decision_record in the registry "
            f"copy ({', '.join(orphans[:8])}{'…' if len(orphans) > 8 else ''}); the own "
            "rule treated their every hit as a citation"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
