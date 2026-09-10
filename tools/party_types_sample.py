"""Party types, tier 1: draw the stratified sample the operator checks.

docs/party-types.md § Evidence: no figure is published and no label ships before a
~300-party sample, drafted by the machine tiers, is checked by the operator. This draws
it — seeded, stratified over the draft rule types with the unmatched tail oversampled —
and writes the sheet the check queue renders and the scorer will read.

The first sheet (2026-08-30, rules v1, from a store copy):

    python tools/party_types_sample.py --store data/prod-copy.sqlite \\
        --out docs/research/party-types

The held-out sheet (decided 2026-09-10): rules v2, stratified over what v2 EMITS, disjoint
from the first, from the live population (`party_types_export.py`), and with the judged
column left BLANK so a row the operator has not judged can never score as agreement:

    python tools/party_types_sample.py --population data/party-pop.json --rules v2 \\
        --exclude docs/research/party-types/labels.csv --seed 20260910 --blank \\
        --draw '{"government": 40, ...}' --out docs/research/party-types/held-out

Output: `sample.json` (what was drawn and why), `labels.csv` (one row per party: the
draft type, its method and evidence; the operator's check fills or corrects `type`).
The v1 rules are `rule:party-type/2026-08-30`; their measured cautions
(`3M Transportation Department` is not a government) are the reason the first sheet exists.
"""

import argparse
import csv
import json
import random
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

RULE_VERSION = "rule:party-type/2026-08-30"
SEED = 20260830
DRAW = {
    "railroad": 40,
    "company": 40,
    "government": 40,
    "association": 40,
    "individual": 40,
    "law-firm": 15,
    "span-artefact": 10,
    "unmatched": 75,
}

# Order matters: first match wins. The known misfires stay in on purpose — the sheet
# exists to measure them, not to hide them.
RULES = [
    ("span-artefact", re.compile(r"^and\s", re.I)),
    ("law-firm", re.compile(r"\b(llp|pllc|law offices?|attorneys? at law)\b", re.I)),
    (
        "railroad",
        re.compile(r"\b(railroad|railway|rail road|ry\.?|r\.?r\.?\b|rr\b)\b", re.I),
    ),
    (
        "government",
        re.compile(
            r"\b(united states|department|federal|administration|commission|authority"
            r"|state of|city of|county|town of|village of|port of|amtrak|board of"
            r"|\d+(st|nd|rd|th) district)\b",
            re.I,
        ),
    ),
    (
        "association",
        re.compile(
            r"\b(association|assn|coalition|league|council|institute|alliance|chamber"
            r"|committee|union(?!\s+pacific)|brotherhood|federation|conference)\b",
            re.I,
        ),
    ),
    (
        "company",
        re.compile(
            r"\b(inc\.?|llc|l\.l\.c|corp\.?|corporation|company|co\.$|ltd|lp$|l\.p\."
            r"|holdings|group|partners|enterprises|industries|cooperative)\b",
            re.I,
        ),
    ),
    (
        "individual",
        re.compile(
            r"^(mr|mrs|ms|dr|honorable)\.?\s|^[A-Z][a-z]+ ([A-Z]\.? )?[A-Z][a-z]+(-[A-Z][a-z]+)?$"
        ),
    ),
]


def draft(name: str) -> str:
    for t, rx in RULES:
        if rx.search(name):
            return t
    return "unmatched"


def _rules(which: str):
    """(draft function, method version). v2 lives in its own module with its scorer."""
    if which == "v1":
        return draft, RULE_VERSION
    sys.path.insert(0, str(Path(__file__).parent))
    import party_types_rules as v2

    return v2.draft, v2.VERSION


def _from_store(path: Path):
    con = sqlite3.connect(path)
    names = con.execute(
        "SELECT party_id, raw_name FROM party_name"
        " WHERE superseded_by IS NULL AND name_kind = 'as_filed' ORDER BY party_id"
    ).fetchall()
    marks = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT party_id FROM party_name"
            " WHERE superseded_by IS NULL AND name_kind = 'mark'"
        )
    }

    def dockets_of(pid):
        ds = con.execute(
            """
            SELECT DISTINCT d.prefix || ' ' || d.sequence
              FROM filing_party_link l
              JOIN filing_party_span s ON s.span_id = l.span_id
                   AND s.superseded_by IS NULL AND s.role = 'filed_for'
              JOIN filing f ON f.filing_pk = s.filing_pk AND f.filed_for_raw = s.raw_text
              JOIN docket d ON d.docket_id = f.docket_id
             WHERE l.party_id = ? AND l.superseded_by IS NULL LIMIT 4
            """,
            (pid,),
        ).fetchall()
        return "; ".join(r[0] for r in ds)

    return names, marks, dockets_of, str(path)


def _from_export(path: Path):
    pop = json.loads(path.read_text(encoding="utf-8"))
    names = [(int(p), n) for p, n in pop["names"]]
    marks = set(pop["marks"])
    return (
        names,
        marks,
        lambda pid: "; ".join(pop["dockets"].get(str(pid), [])),
        f"live store, schema {pop['schema']}, exported {pop['exported_at']}",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--store", type=Path, help="a store copy")
    src.add_argument("--population", type=Path, help="party_types_export.py's JSON")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--rules", choices=("v1", "v2"), default="v1")
    ap.add_argument("--exclude", type=Path, help="a labels.csv whose parties are not drawn")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--draw", help="per-stratum counts as JSON; default the first sheet's")
    ap.add_argument("--blank", action="store_true", help="leave `type` for the operator")
    ap.add_argument(
        "--why",
        default="party-types.md tier 1: the operator-checked ground truth every machine tier"
        " is measured against before anything publishes; unmatched oversampled because it is"
        " where the rules say nothing",
    )
    args = ap.parse_args()

    rule, version = _rules(args.rules)
    plan = json.loads(args.draw) if args.draw else DRAW
    names, marks, dockets_of, source = (
        _from_store(args.store) if args.store else _from_export(args.population)
    )
    excluded: set[int] = set()
    if args.exclude:
        with args.exclude.open(encoding="utf-8") as f:
            excluded = {int(r["party_id"]) for r in csv.DictReader(f)}
    buckets: dict[str, list[tuple[int, str]]] = {}
    for pid, raw in names:
        if pid not in excluded:
            buckets.setdefault(rule(raw), []).append((pid, raw))
    unplanned = sorted(set(buckets) - set(plan))
    if unplanned:  # a stratum the rules emit and the plan forgot is a silent hole
        raise SystemExit(f"the draw names no count for {unplanned}")
    rng = random.Random(args.seed)
    sample = []
    for t, n in plan.items():
        pool = buckets.get(t, [])
        take = pool if len(pool) <= n else rng.sample(pool, n)
        sample += [(t, pid, raw) for pid, raw in take]

    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "labels.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(
            ["party_id", "as_filed", "draft_type", "type", "method", "evidence", "dockets", "note"]
        )
        for t, pid, raw in sorted(sample, key=lambda x: (x[0], x[2])):
            evidence = "held reporting mark" if pid in marks and t == "railroad" else "name"
            # `type` starts equal to the draft on the first sheet, where the operator's check
            # corrects it; blank on a held-out sheet, where only a judgement may fill it
            judged = "" if args.blank else t
            w.writerow([pid, raw, t, judged, version, evidence, dockets_of(pid), ""])

    (args.out / "sample.json").write_text(
        json.dumps(
            {
                "drawn": datetime.now(UTC).date().isoformat(),
                "seed": args.seed,
                "store": source,
                "excluded": {"sheet": args.exclude.as_posix(), "parties": len(excluded)}
                if args.exclude
                else None,
                "strata": {t: min(n, len(buckets.get(t, []))) for t, n in plan.items()},
                "population": {t: len(v) for t, v in sorted(buckets.items())},
                "why": args.why,
                "rule_version": version,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",  # LF everywhere (.gitattributes); Windows would otherwise write CRLF
    )
    print(f"{len(sample)} parties -> {args.out / 'labels.csv'}")
    for t in plan:
        print(f"  {t:17s} {sum(1 for x in sample if x[0] == t):3d} of {len(buckets.get(t, []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
