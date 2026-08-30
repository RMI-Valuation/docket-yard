"""Party types, tier 1: draw the stratified sample the operator checks.

docs/party-types.md § Evidence: no figure is published and no label ships before a
~300-party sample, drafted by the machine tiers, is checked by the operator. This draws
it — seeded, stratified over the draft rule types with the unmatched tail oversampled —
and writes the sheet the check queue renders and the scorer will read.

    python tools/party_types_sample.py --store data/prod-copy.sqlite \\
        --out docs/research/party-types

Output: `sample.json` (what was drawn and why), `labels.csv` (one row per party: the
draft type, its method and evidence; the operator's check corrects the `type` column).
The draft rules are `rule:party-type/2026-08-30`; their measured cautions
(`3M Transportation Department` is not a government) are the reason this sheet exists.
"""

import argparse
import csv
import json
import random
import re
import sqlite3
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    con = sqlite3.connect(args.store)
    rows = con.execute(
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
    buckets: dict[str, list[tuple[int, str]]] = {}
    for pid, raw in rows:
        buckets.setdefault(draft(raw), []).append((pid, raw))
    rng = random.Random(SEED)
    sample = []
    for t, n in DRAW.items():
        pool = buckets.get(t, [])
        take = pool if len(pool) <= n else rng.sample(pool, n)
        sample += [(t, pid, raw) for pid, raw in take]

    args.out.mkdir(parents=True, exist_ok=True)
    dockets = {}
    for _t, pid, _raw in sample:
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
        dockets[pid] = "; ".join(r[0] for r in ds)

    with (args.out / "labels.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(
            ["party_id", "as_filed", "draft_type", "type", "method", "evidence", "dockets", "note"]
        )
        for t, pid, raw in sorted(sample, key=lambda x: (x[0], x[2])):
            evidence = "held reporting mark" if pid in marks and t == "railroad" else "name"
            # `type` starts equal to the draft; the operator's check corrects it
            w.writerow([pid, raw, t, t, RULE_VERSION, evidence, dockets[pid], ""])

    (args.out / "sample.json").write_text(
        json.dumps(
            {
                "drawn": "2026-08-30",
                "seed": SEED,
                "store": str(args.store),
                "strata": {t: min(n, len(buckets.get(t, []))) for t, n in DRAW.items()},
                "population": {t: len(v) for t, v in sorted(buckets.items())},
                "why": "party-types.md tier 1: the operator-checked ground truth every "
                "machine tier is measured against before anything publishes; unmatched "
                "oversampled because it is where the rules say nothing",
                "rule_version": RULE_VERSION,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(sample)} parties -> {args.out / 'labels.csv'}")
    for t in DRAW:
        print(f"  {t:13s} {sum(1 for x in sample if x[0] == t):3d} of {len(buckets.get(t, []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
