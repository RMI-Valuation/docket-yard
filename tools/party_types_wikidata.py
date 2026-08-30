"""Party types, tier 3 draft: Wikidata evidence for the sampled organisations.

Reads the sample sheet, links every non-individual, non-span row against Wikidata
(suffix-normalised search, then `instance of`), and writes `wikidata.csv` beside it —
evidence for the check queue and later a measured tier (`link:wikidata`). Individuals
are never looked up (docs/party-types.md: a wrong link about a person is a data defect
and a privacy harm). Polite: identified UA, ~1.5 s spacing, backoff on 429.

    python tools/party_types_wikidata.py --dir docs/research/party-types
"""

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {
    "User-Agent": "DocketYard-research/0.1 (https://docketyard.org; operator contactable via site)"
}
# Never looked up. `type` is the operator's judgement where the sheet has one and the
# draft otherwise: keying on the draft alone let 13 judged individuals through, and five
# wrong person links reached a public repository (code review, 2026-08-30).
SKIP = {"individual", "elected-official", "span-artefact"}
# The second line of defence, which needs no judgement at all: Wikidata itself says the
# match is a human, so the match is discarded whatever the sheet called the party. A wrong
# link about a person is a data defect and a privacy harm (docs/party-types.md).
HUMAN = "Q5"
# instance-of values seen in the record's world, mapped to the draft vocabulary;
# anything unmapped stays raw for the check queue to read
P31_MAP = {
    "Q249556": "railroad",  # railway company
    "Q740752": "railroad",  # Class I railroad
    "Q1141470": "railroad",  # shortline railroad
    "Q35657": "government",  # U.S. state
    "Q3624078": "government",  # sovereign state
    "Q515": "government",  # city
    "Q1093829": "government",  # city of the United States
    "Q28564": "government",  # county seat? (left mapped loosely; queue reads raw too)
    "Q327333": "government",  # government agency
    "Q2178147": "association",  # trade association
    "Q48204": "association",  # voluntary association
    "Q79913": "association",  # non-governmental organization
    "Q4830453": "company",
    "Q6881511": "company",
    "Q891723": "company",  # public company
    "Q5": "individual",
}


def api(params: dict) -> dict:
    for attempt in range(5):
        req = urllib.request.Request(
            "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(params), headers=UA
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(6 * (attempt + 1))
                continue
            raise
    return {}


def norm(name: str) -> str:
    n = re.sub(
        r"[,.]? (Company|Corporation|Incorporated|Inc\.?|LLC|L\.L\.C\.?|Co\.?|Ltd\.?)\s*$",
        "",
        name,
        flags=re.I,
    )
    return re.sub(r"\s+", " ", n).strip()


def link(name: str) -> tuple:
    for q in dict.fromkeys([norm(name), name]):
        d = api(
            {
                "action": "wbsearchentities",
                "search": q,
                "language": "en",
                "format": "json",
                "type": "item",
                "limit": 1,
            }
        )
        hits = d.get("search") or []
        if not hits:
            continue
        qid = hits[0]["id"]
        d2 = api(
            {
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims|descriptions|labels",
                "languages": "en",
                "format": "json",
            }
        )
        ent = d2.get("entities", {}).get(qid, {})
        claims = ent.get("claims", {})
        p31 = [
            cl["mainsnak"]["datavalue"]["value"]["id"]
            for cl in claims.get("P31", [])
            if cl["mainsnak"].get("datavalue")
        ]
        mark = [
            cl["mainsnak"]["datavalue"]["value"]
            for cl in claims.get("P5768", [])
            if cl["mainsnak"].get("datavalue")
        ]
        label = (ent.get("labels", {}).get("en") or {}).get("value", "")
        desc = (ent.get("descriptions", {}).get("en") or {}).get("value", "")
        if HUMAN in p31:
            return "", "", "", "", "", ""  # a person: never stored, never published
        mapped = next((P31_MAP[x] for x in p31 if x in P31_MAP), "")
        return qid, label, desc, "|".join(p31), "|".join(mark), mapped
    return "", "", "", "", "", ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    args = ap.parse_args()
    rows = list(csv.DictReader((args.dir / "labels.csv").open(encoding="utf-8")))
    out_path = args.dir / "wikidata.csv"
    done = set()
    if out_path.exists():
        done = {r["party_id"] for r in csv.DictReader(out_path.open(encoding="utf-8"))}
    mode = "a" if done else "w"
    with out_path.open(mode, encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        if not done:
            w.writerow(
                [
                    "party_id",
                    "as_filed",
                    "qid",
                    "wd_label",
                    "wd_description",
                    "p31",
                    "mark",
                    "mapped_type",
                ]
            )
        looked = 0
        for r in rows:
            judged = (r.get("type") or r["draft_type"]).strip()
            if judged in SKIP or r["draft_type"] in SKIP or r["party_id"] in done:
                continue
            qid, label, desc, p31, mark, mapped = link(r["as_filed"])
            w.writerow([r["party_id"], r["as_filed"], qid, label, desc, p31, mark, mapped])
            f.flush()
            looked += 1
            time.sleep(1.5)
        print(f"{looked} looked up -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
