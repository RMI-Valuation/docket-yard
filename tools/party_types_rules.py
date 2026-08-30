"""Party types, tier 2: the name rules, and their score against the checked sheet.

Rules v2, written 2026-08-30 from the confusion table of v1's operator check
(`docs/research/party-types/README.md`), not from imagination. What the check taught:

- v1's `honorable` prefix never fired — the pattern was case-sensitive and the Board
  prints `Honorable Andy Harris`. 28 of the 75 unmatched were elected officials.
- `Nth District of X` was drafted `government`; the operator judged elected-official.
- Eight `railroad` drafts were **joined pairs** (`Sierra Railroad Company And Sierra
  Northern Railway`) that the leading-`And` rule cannot see. The join test must be
  two-sided — both halves carrying an entity suffix — or `Delaware And Hudson Railway
  Company`, one railroad, would be torn in half.
- `association` lost 7 to `labor-union` and `government` lost 4 each to `port` and to
  `association`: the vocabulary the operator added has real name signals.
- `company` lost 6 to `railroad`, mostly names carrying a bare `Rail` (`AJAK Rail, LLC`).

Order is the design: the first matching rule wins, and the order below is what the
measurement rewarded — artefacts and people before organisations, the narrow signals
(union, port, rail) before the broad ones (association, government, company).

    python tools/party_types_rules.py --sheet docs/research/party-types/labels.csv
"""

import argparse
import collections
import csv
import re
from pathlib import Path

VERSION = "rule:party-type/2026-08-30b"

# an entity's tail: what makes a fragment look like a whole organisation
_SUFFIX = (
    r"(?:inc|llc|l\.l\.c|corp|corporation|compan(?:y|ies)|ltd|limited|railway"
    r"|railroad|association|authority|lp)"
)
JOINED = re.compile(rf"\b{_SUFFIX}\b[.,]?\s*(?:and|&)\s+.+\b{_SUFFIX}\b", re.I)
# `Inc.Luzerne`, `CompanyMeridian`: a suffix glued to the next name. Case-SENSITIVE on
# purpose — the capital is the whole signal.
RUNON = re.compile(r"\b(?:Inc|Llc|LLC|Corp|Company|Railway|Railroad)\.?[A-Z]")

ORGISH = re.compile(
    r"\b(?:action|organization|organisation|connections|systems|services|works|farm"
    r"|trust|fund|solutions|logistics|transport|holdings|ventures|resources|partners"
    r"|society|network|project|alliance|center|centre)\b",
    re.I,
)

RULES: list[tuple[str, re.Pattern]] = [
    # 1. not one party at all — the split is the defect, typing waits for the re-split
    ("span-artefact", re.compile(r"^and\s|^d/b/a\s|;", re.I)),
    ("span-artefact", JOINED),
    ("span-artefact", re.compile(rf"\b(?:inc|llc|corp|company)\.?(?=[A-Z])|{_SUFFIX}-[A-Z]")),
    # 2. people, before any organisation word in the name can claim them
    (
        "elected-official",
        re.compile(
            r"^honorable\b|\b\d+(?:st|nd|rd|th)\s+district\b"
            r"|^(?:rep|sen|senator|representative|congress(?:man|woman))\b",
            re.I,
        ),
    ),
    ("law-firm", re.compile(r"\b(?:llp|pllc|p\.c\.|law offices?|attorneys? at law)\b", re.I)),
    # 3. the narrow organisation signals, before the broad ones
    (
        "labor-union",
        re.compile(
            r"\b(?:brotherhood|teamsters|seafarers|smart-?td"
            r"|(?:international|transportation|communications) union"
            r"|general committee of adjustment|legislative board"
            r"|labor organization)\b",
            re.I,
        ),
    ),
    ("port", re.compile(r"\bport authority\b|\bport of\b|\bport\b\s*$|\bports\b", re.I)),
    (
        "association",
        re.compile(
            r"\b(?:association|assn|coalition|league|institute|alliance|chamber|committee"
            r"|brotherhood|federation|conference|society|friends of|greenway"
            r"|communities for|council|(?:economic|industrial) development corporation)\b",
            re.I,
        ),
    ),
    (
        "railroad",
        re.compile(
            r"\b(?:railroad|railway|rail road|railnet|railmet|rail link"
            r"|r\.?r\.?|\brr\b)\b|\brail\b(?!\s*(?:conference|labor))",
            re.I,
        ),
    ),
    ("utility", re.compile(r"\b(?:electric|power|energy|utilit(?:y|ies)|gas co)\b", re.I)),
    # 4. the broad ones. association before government: a chamber of commerce and an
    #    economic development corporation are associations, and the operator judged them so
    (
        "government",
        re.compile(
            r"\b(?:united states|u\.?s\.? dep|department|dept"
            r"|federal|administration|commission|authority|state of|city of"
            r"|cities of|county|town of|village of|amtrak|board of|legislature"
            r"|assembly|university|college|park district|task force"
            r"|wheat board|municipal)\b",
            re.I,
        ),
    ),
    (
        "company",
        re.compile(
            r"\b(?:inc|llc|l\.l\.c|corp|corporation|company|co|ltd|limited|lp"
            r"|l\.p\.|holdings|group|partners|enterprises|industries"
            r"|cooperative)\b\.?",
            re.I,
        ),
    ),
    # 5. what is left that looks like a person's name
    (
        "individual",
        re.compile(
            r"^(?:mr|mrs|ms|dr)\.?\s"  # a title
            r"|^(?:[A-Z]\.?\s*){1,3}\(?[A-Z][\w'’-]*\)?\s+[A-Z][\w'’-]+$"  # J.R. (Bo) Thompson
            r"|^[A-Z][\w'’-]+(?:\s+&\s+[A-Z][\w'’-]+)?"  # Elmer & Delores Hurling
            r"(?:\s+[A-Z][\w'’.-]*){1,3}$",  # two to four capitalised words
        ),
    ),
]


def draft(name: str) -> str:
    """The first matching rule wins; `individual` additionally requires that the name
    carry no organisation word, or `Farm Action` and `Wild Connections` read as people."""
    for t, rx in RULES:
        if rx.search(name):
            if t == "individual" and ORGISH.search(name):
                continue
            return t
    return "unmatched"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", type=Path, default=Path("docs/research/party-types/labels.csv"))
    ap.add_argument("--show", default="", help="print the misses for one judged type")
    args = ap.parse_args()
    rows = list(csv.DictReader(args.sheet.open(encoding="utf-8")))
    per = collections.defaultdict(lambda: [0, 0])  # judged type -> [found, total]
    emitted = collections.Counter()
    right = collections.Counter()
    conf = collections.Counter()
    for r in rows:
        judged, got = r["type"], draft(r["as_filed"])
        per[judged][1] += 1
        emitted[got] += 1
        if got == judged:
            per[judged][0] += 1
            right[got] += 1
        else:
            conf[(got, judged)] += 1
            if args.show and judged == args.show:
                print(f"    missed as {got:15s} {r['as_filed'][:60]}")
    total = sum(v[0] for v in per.values())
    print(f"{args.sheet.name}: {len(rows)} judged parties, rules {VERSION}\n")
    print(f"{'judged type':16s} {'recall':>14s}   {'precision (of what it emitted)':>34s}")
    for t, (found, tot) in sorted(per.items(), key=lambda x: -x[1][1]):
        em = emitted.get(t, 0)
        pre = f"{right[t] / em:6.1%} of {em:3d}" if em else "        —"
        print(f"  {t:14s} {found:3d}/{tot:3d} {found / tot:6.1%}   {pre}")
    print(f"\n  overall agreement {total}/{len(rows)} = {total / len(rows):.1%}")
    print("\n  top confusions (rule said -> operator judged):")
    for (got, judged), n in conf.most_common(10):
        print(f"    {got:15s} -> {judged:16s} x{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
