"""Score what a READER sees, not what the finder emits.

`benchmark_regex.py` measures extraction and `benchmark_score.py` scores it. Neither applies
the projection rules, so both answer "did the finder see it" and neither answers "does the
edge reach a page". ADR 0017 published 95.1% recall for the projected class on that basis;
it was measured before the gate that suppresses edges, and it was wrong. This runs the whole
chain and reports each stage, so a figure can never again be quoted for a stage it did not
measure.

    python tools/rmi-ai-machine/projection_score.py <run-dir> [--registry data/prod-copy.sqlite]

The chain, in the order ADR 0017 and 0018 specify:

  1. EXTRACTION   the finder emits every docket-shaped hit (no registry filter - 0017 D2)
  2. RESOLUTION   rule 1 matches the normalised key against the registry; a miss is stored
                  `unresolved` and never projects, but IS a real edge and goes to review
  3. PROJECTION   an own-family mention is suppressed at docket level unless its quoted span
                  names a document (0017 D4). The span test is SPAN_NAMES_DOCUMENT below and
                  is the classifier the published precision figure was measured with.

Family closure is `web/cite.py`'s - self, sub-dockets, parent - unioned over every docket the
citing decision is entered in (0017 D4).
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import benchmark_score as bs  # noqa: E402

N = bs.norm_target

# The span test of ADR 0017 decision 4: does the quoted passage name a DOCUMENT rather than
# just a proceeding? `served\s+\w+\.?\s+\d` carries an optional period because the Board
# abbreviates the month - "(STB served Mar. 12, 2021)". Without it the test missed two real
# document-naming spans in the sixty decisions and suppressed two true edges (measured
# 2026-09-01); this is the shipping definition and the one every published figure uses.
SPAN_NAMES_DOCUMENT = re.compile(
    r"Decision No\.|slip op|served\s+\w+\.?\s+\d|\bDecision\s+\d{4,6}\b", re.I
)


def printed(prefix: str, seq: int, sub: int | None, suffix: str | None) -> str:
    """A `docket` row in the key a citation normalises to.

    BUILT FROM THE COLUMNS, never round-tripped through the normaliser. It was
    `N(f"{prefix} {seq} ({suffix})")` until 2026-09-01, and `norm_target` is not idempotent:
    it reads `AB 1296X` as `AB 1296 (X)` but reads `AB 1296 (X)` as `AB 1296`, because its
    parenthetical pattern requires the words "Sub-No.". So every suffixed docket entered
    this registry WITHOUT its suffix - 2,711 of them hold a suffix and no sub-docket - and
    a finding keyed `AB 1296 (X)` could never resolve. Those targets scored as registry
    unresolvables, which is why the projected figure was measured low.

    `docketyard.citator.keys.registry_key` is the same function on the shipped side, and
    this stays a copy on purpose: a scorer that imports the code it scores cannot catch the
    code being wrong. They are pinned equal by a test instead.
    """
    key = f"{prefix.upper()} {int(seq)}"
    # `if sub` and not `if sub is not None`: a sub-number of zero is no sub-number, which is
    # `ingest.dockets.parse_docket_id`'s rule and so the record's. No `docket` row holds a
    # zero today, so this changes nothing the store can produce — it keeps this copy spelling
    # the rule the same way `keys.registry_key` does (2026-09-04).
    inner = f"{int(sub) if sub else ''}{(suffix or '').upper()}"
    return f"{key} ({inner})" if inner else key


def registry(con: sqlite3.Connection) -> set[str]:
    return {
        printed(*row)
        for row in con.execute("SELECT prefix, sequence, sub_sequence, suffix FROM docket")
    }


def families(con: sqlite3.Connection, ids: set[str]) -> dict[str, set[str]]:
    """Per citing decision: every docket in its family, over every docket it is entered in."""
    out: dict[str, set[str]] = {}
    for did in ids:
        keys: set[str] = set()
        for docket_id, p, s, sub, suf, parent in con.execute(
            "SELECT d.docket_id, d.prefix, d.sequence, d.sub_sequence, d.suffix,"
            " d.parent_docket_id FROM decision_record r"
            " JOIN docket d ON d.docket_id = r.docket_id WHERE r.stb_decision_id = ?",
            (did,),
        ):
            keys.add(printed(p, s, sub, suf))
            for q in con.execute(
                "SELECT prefix, sequence, sub_sequence, suffix FROM docket"
                " WHERE docket_id = ? OR parent_docket_id = ? OR docket_id = ?",
                (docket_id, docket_id, parent or docket_id),
            ):
                keys.add(printed(*q))
        out[did] = keys
    return out


def spans(run: Path) -> dict[tuple[str, str], str]:
    """Every quoted passage per (decision, target), joined - a target may be cited twice."""
    out: dict[tuple[str, str], list[str]] = {}
    for f in sorted(run.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        for page in doc.get("pages", []):
            for fi in page.get("findings", []):
                if fi.get("kind") == "citation" and fi.get("target_kind") == "stb":
                    out.setdefault((doc["decision_id"], N(fi["target"])), []).append(
                        fi.get("quoted", "")
                    )
    return {k: " | ".join(v) for k, v in out.items()}


def main(run: Path, db: Path) -> None:
    truth_doc, _ = bs.truth()
    run_doc, _, _ = bs.run_findings(run, None)

    def keep(d: dict) -> dict:
        return {k: {x for x in v if bs.DOCKET_KEY.match(x)} for k, v in d.items()}

    T = keep(bs.collect(truth_doc, "citation", "stb"))
    R = keep(bs.collect(run_doc, "citation", "stb"))

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    held = registry(con)
    fam = families(con, set(T) | set(R))
    quoted = spans(run)
    con.close()

    def names_document(did: str, key: str) -> bool:
        return bool(SPAN_NAMES_DOCUMENT.search(quoted.get((did, key), "")))

    truth = sum(map(len, T.values()))
    emitted = sum(map(len, R.values()))
    found = unresolved = suppressed = projected = 0
    for did, keys in T.items():
        for k in keys:
            if k not in R.get(did, set()):
                continue
            found += 1
            if k not in held:
                unresolved += 1  # a real edge; review queue, not a page
            elif k in fam.get(did, set()) and not names_document(did, k):
                suppressed += 1  # decision 4, working as intended
            else:
                projected += 1

    extras_suppressed = extras_projected = 0
    for did, keys in R.items():
        for k in keys - T.get(did, set()):
            if k in fam.get(did, set()) and not names_document(did, k):
                extras_suppressed += 1
            else:
                extras_projected += 1

    # What a reader is shown = projected true edges + the extras that survived the gate.
    # The unresolved and the suppressed reach no page and belong on NEITHER side of this
    # ratio; subtracting them from `emitted` instead counts them as shown-and-wrong, which
    # is how a first draft of this scorer read 93.5% for a class measured at 98%.
    shown = projected + extras_projected
    print(f"truth {truth} occurrences   emitted {emitted}\n")
    print("RECALL, by stage - each is true of a different thing:")
    print(f"  extraction  the finder saw it              {found:3d}  {100 * found / truth:5.1f}%")
    print(
        f"  resolution  and the registry resolved it   {found - unresolved:3d} "
        f" {100 * (found - unresolved) / truth:5.1f}%   "
        f"({unresolved} real edges to the review queue)"
    )
    print(
        f"  PROJECTED   and a reader sees it           {projected:3d} "
        f" {100 * projected / truth:5.1f}%   "
        f"({suppressed} own-family self-references suppressed by design)"
    )
    print("\nPRECISION of what projects:")
    print(
        f"  {projected} true of {shown} shown = {100 * projected / shown:.1f}%"
        f"   ({extras_projected} projected extras, {extras_suppressed} extras absorbed)"
    )
    print(
        "\nQuote the PROJECTED line for anything a reader is shown. The extraction line is"
        "\nthe finder's, and quoting it for the projected class is the error ADR 0017 made."
    )


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    db = (
        Path(sys.argv[sys.argv.index("--registry") + 1])
        if "--registry" in sys.argv
        else Path("data/prod-copy.sqlite")
    )
    main(Path(args[0]), db)
