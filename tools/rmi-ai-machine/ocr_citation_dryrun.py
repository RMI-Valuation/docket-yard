"""Dry-run the citation pipeline over the OCR citation benchmark, and write the `ocr` card.

`citation_dryrun.py` does this for the sixty born-digital decisions on the text layer. This is
the same chain for `docs/research/ocr-citation-benchmark/`: 98 decision documents drawn in four
strata, each read on its LABELLED pages only (548), from the OCR text production holds for them,
scored against the operator's checked labels. ADR 0017 D3 keeps the `ocr` channel unmeasured
until a card for it is declared, and `citator load` refuses an OCR batch until then.

    python tools/rmi-ai-machine/ocr_citation_dryrun.py --registry data/rehearse-long-forms.sqlite \
        [--store data/ocr-citation-dryrun.sqlite] \
        [--findings data/ocr-citation/findings-2026-09-13b] [--scores-out data/card-ocr.json]

THE TRUTH, as the operator decided it (the benchmark's README § Decided):
  * a drafted `citation`/`stb` row whose target is a docket and which the check called ok;
  * whose own QUOTE prints that docket's number, in any form — `FD 36500`, `Finance Docket No.
    36500`, or a bare `Docket 42125` the finder does not read. A prior decision named by date on
    a page whose caption prints the docket is a supplied target and stays out;
  * counted per (document, docket), the grain the sixty's sets used per decision.
An `unsure` or unjudged row that would be truth, a caption the check called wrong, and a missed
line printing a docket number are REFUSED rather than guessed: each is a question for the
operator, and a guess here is a Claude-flavoured target inside a published precision.

THE RUN is the SHIPPED finder through `find.findings_document`, the function `walk.documents`
calls on production, on channel `ocr` with production's family (`walk.own_by_document`).
`--findings` checks it against production's own findings on the same pages, and that production
walked every labelled page on `ocr`; it refuses to score when either differs, and `--scores-out`
is refused without it: a card must measure the finder that will load, on the text it will read.

THE TWO CHAINS, as in `citation_dryrun.py`: the scorer's sets (its own normaliser, registry and
family — `benchmark_score`, `projection_score`) against the shipped `scorecard.declare`, `load`
and `project.projected` on a scratch copy of the registry. The card is written only when they
agree, less the two differences that script names: rule-2 repairs and the exposure gate.

TWO GRAINS. The card counts (document, docket) pairs, because the sample is of documents. The
projection folds to the citing WORK (ADR 0018 D9) and judges family per work, so the chains are
compared per (work, docket); a document carried by several decisions is projected, or shown, when
it projects for any of them.
"""

import csv
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import benchmark_score as bs  # noqa: E402
import citation_dryrun as dry  # noqa: E402
import projection_score as ps  # noqa: E402

from docketyard.citator import (  # noqa: E402
    find,
    keys,
    load,
    methods,
    project,
    resolve,
    scorecard,
    walk,
)
from docketyard.store import db  # noqa: E402

SCORE_FILE = "tools/rmi-ai-machine/ocr_citation_dryrun.py"
BENCH = ROOT / "docs/research/ocr-citation-benchmark"
DATA = ROOT / "data/ocr-citation"
CHANNEL = methods.CHANNEL_OCR
# The operator's check, in the order it is read: a later file's verdict on a row replaces an
# earlier one's, and the resolutions are his answers to part 1's unsure rows.
VERDICTS = ("check-1.tsv", "check-2.tsv", "check-1-resolutions.tsv")
# A missed line is free text, so whether it prints a docket is read with the finder's grammar
# plus the bare form the operator counted; a hit is refused, never scored.
BARE_DOCKET = re.compile(r"\bDocket\s+(?:No\.?\s*)?\d{3,6}\b", re.I)


def drafted() -> dict[tuple[str, int, int], dict]:
    """(document, page, row) -> the drafted row. Rows are numbered per page in file order,
    COUNTING a "nothing to label" row, which is how `ocr_citation_check_page.py` numbered the
    verdicts the operator returned (its `p.rows` index); only labelled rows are kept."""
    out: dict[tuple[str, int, int], dict] = {}
    for path in sorted((DATA / "drafts").glob("batch-*.csv")):
        per: Counter = Counter()
        for row in csv.DictReader(path.open(encoding="utf-8")):
            at = (row["document_sha256"], int(row["page"]))
            if row["kind"]:  # an empty kind is "nothing to label": numbered, not kept
                out[(*at, per[at])] = row
            per[at] += 1
    return out


def verdicts() -> tuple[dict[tuple[str, int, int], str], list[tuple[str, int, str]]]:
    """The verdict on each row, and every missed line as (document, page, text)."""
    judged: dict[tuple[str, int, int], str] = {}
    missed: list[tuple[str, int, str]] = []
    for name in VERDICTS:
        for line in (BENCH / name).read_text(encoding="utf-8").splitlines()[1:]:
            f = line.split("\t")
            if len(f) < 4:
                continue
            if f[2] == "missed":
                missed.append((f[0], int(f[1]), f[4] if len(f) > 4 else ""))
            else:
                judged[(f[0], int(f[1]), int(f[2]))] = f[3]
    return judged, missed


def prints_number(quoted: str, key: str) -> bool:
    """Whether the row's own quote prints the docket's number. Read as the NUMBER and not with
    the finder's grammar: the truth is what the page says, and a form the finder cannot read
    is exactly what a card must be able to count against it."""
    return re.search(rf"(?<!\d){key.split()[1]}(?!\d)", quoted) is not None


def truth(rows: dict, judged: dict, missed: list) -> dict[str, set[str]]:
    T: dict[str, set[str]] = defaultdict(set)
    questions: list[str] = []
    for at, r in rows.items():
        verdict = judged.get(at)
        where = f"{at[0][:12]} p{at[1]} row {at[2]}"
        if r["kind"] == "caption" and verdict == "wrong":
            questions.append(f"{where}: a caption called wrong, so possibly a citation missed")
        if r["kind"] != "citation" or r["target_kind"] != "stb":
            continue
        key = bs.norm_target(r["target"])
        if not bs.DOCKET_KEY.match(key) or not prints_number(r["quoted"], key):
            continue
        if verdict == "wrong":
            continue
        if verdict != "ok":
            questions.append(f"{where}: {verdict or 'unjudged'}, {r['quoted'][:70]!r}")
            continue
        T[at[0]].add(key)
    for sha, page, text in missed:
        if keys.docket_search(text) or BARE_DOCKET.search(text):
            questions.append(f"{sha[:12]} p{page}: a missed line prints a docket, {text[:70]!r}")
    if questions:
        raise SystemExit("the truth has questions for the operator:\n  " + "\n  ".join(questions))
    return T


def sample() -> tuple[list[str], dict[str, set[int]]]:
    docs = [
        d for batch in json.loads((DATA / "batches.json").read_text()) for d in batch["documents"]
    ]
    return [d["document_sha256"] for d in docs], {
        d["document_sha256"]: set(d["labelled_pages"]) for d in docs
    }


def run_the_finder(shas: list[str], labelled: dict, own: dict) -> tuple[list[dict], int]:
    """The shipped finder over each document's labelled pages, in the interchange `load` takes.
    `text_ref` is 'benchmark': these pages come from an export, so no span may point into them."""
    text = json.loads((DATA / "ocr-text.json").read_text(encoding="utf-8"))["pages"]
    docs, blank = [], 0
    for sha in shas:
        if sha not in own:
            raise SystemExit(
                f"{sha[:12]}: no docket in the registry, so every caption reads as a citation"
            )
        pages = [(p, text[sha][str(p)]["text"] or "") for p in sorted(labelled[sha])]
        if not any(body.strip() for _, body in pages):
            blank += 1  # `walk.documents` skips a reading of nothing, and so does this
            continue
        docs.append(
            find.findings_document(
                pages,
                document_sha256=sha,
                own=own[sha],
                text_ref="benchmark",
                reading_channel=CHANNEL,
            )
        )
    return docs, blank


def differs_from_production(docs: list[dict], findings: Path, labelled: dict) -> list[str]:
    out = []
    for doc in docs:
        sha = doc["document_sha256"]
        prod = json.loads((findings / f"{sha}.json").read_text(encoding="utf-8"))

        def shape(fs, pages):
            return Counter(
                (f["page"], f["kind"], f["target"], f["quoted"]) for f in fs if f["page"] in pages
            )

        same = shape(prod["findings"], labelled[sha]) == shape(doc["findings"], labelled[sha]) and (
            prod["method_version"],
            prod["reading_channel"],
        ) == (doc["method_version"], doc["reading_channel"])
        # and every labelled page must be one production READ on this channel: a page it files
        # under the text layer finds nothing on either side and would agree trivially, while its
        # truth counted as an OCR miss (ingest specialist, 2026-09-13, F2)
        walked = {int(p) for p in prod.get("pages_walked") or ()}
        if not same or not labelled[sha] <= walked:
            out.append(sha[:12])
    return out


def carriers(con: sqlite3.Connection, shas: set[str]) -> dict[str, set]:
    """document -> the decisions carrying it: the works an edge from it folds to."""
    out: dict[str, set] = defaultdict(set)
    for sha, did in con.execute(
        "SELECT DISTINCT da.document_sha256, dr.stb_decision_id FROM decision_attachment da"
        " JOIN decision_record dr ON dr.decision_pk = da.decision_pk"
        " WHERE da.document_sha256 IS NOT NULL"
    ):
        if sha in shas:
            out[sha].add(did)
    return out


def python_chain(docs: list[dict], T: dict, registry: Path) -> dict:
    """The scorer's sets: `citation_dryrun.python_chain` at the document grain."""
    R: dict[str, set[str]] = defaultdict(set)
    quoted: dict[tuple[str, str], list[str]] = defaultdict(list)
    for doc in docs:
        for f in doc["findings"]:
            # the finding's key, which the own-fused rule can set apart from its printed target
            key = f.get("key") or bs.norm_target(f["target"])
            if f["kind"] == "citation" and bs.DOCKET_KEY.match(key):
                R[doc["document_sha256"]].add(key)
                quoted[(doc["document_sha256"], key)].append(f["quoted"])
    con = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
    held = ps.registry(con)
    works = carriers(con, {d["document_sha256"] for d in docs})
    fam = ps.families(con, {w for ws in works.values() for w in ws})
    con.close()

    def shown_for(sha: str, key: str) -> set:
        if key not in held:
            return set()
        names = bool(ps.SPAN_NAMES_DOCUMENT.search(" | ".join(quoted[(sha, key)])))
        return {w for w in works.get(sha, ()) if names or key not in fam.get(w, set())}

    pairs, shown = set(), set()
    for sha, ks in R.items():
        for key in ks:
            for_works = shown_for(sha, key)
            pairs |= {(w, key) for w in for_works}
            if for_works:
                shown.add((sha, key))
    found = [(sha, k) for sha, ks in T.items() for k in ks if k in R.get(sha, set())]
    resolved = [p for p in found if p[1] in held]
    return {
        "truth": sum(map(len, T.values())),
        "emitted": sum(map(len, R.values())),
        "resolved_shown": sum(1 for ks in R.values() for k in ks if k in held),
        "found": len(found),
        "resolved": len(resolved),
        "projected": sum(1 for p in resolved if p in shown),
        "shown": len(shown),
        "pairs": pairs,
        "works": works,
        "R": R,
        "held": held,
    }


HELD_FOR_REVIEW = """
SELECT DISTINCT r.citing_document, r.target_key
  FROM citation_resolution r
  JOIN citation_judgement j ON j.citing_document = r.citing_document AND j.page = r.page
   AND j.target_kind = r.target_kind AND j.target_key = r.target_key
   AND j.judgement = 'exposed' AND j.value = 'true' AND j.superseded_by IS NULL
 WHERE r.superseded_by IS NULL AND r.outcome IN ('resolved', 'repaired') AND r.reading_channel = ?
   AND NOT EXISTS (SELECT 1 FROM citation_resolution h
                    WHERE h.citing_document = r.citing_document AND h.page = r.page
                      AND h.target_kind = r.target_kind AND h.target_key = r.target_key
                      AND h.confidence_state = 'human' AND h.superseded_by IS NULL)
"""


def main(registry: Path, store: Path, findings: Path | None, card_out: Path | None) -> int:
    shas, labelled = sample()
    T = truth(drafted(), *verdicts())
    con0 = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
    own = walk.own_by_document(con0)
    con0.close()
    docs, blank = run_the_finder(shas, labelled, own)
    print(f"finder {find.FINDER_VERSION} on {CHANNEL}: {len(docs)} documents read, {blank} blank")
    if findings is not None:
        differ = differs_from_production(docs, findings, labelled)
        print(f"  against production's findings in {findings}: {len(docs) - len(differ)} identical")
        if differ:
            print(f"  NOT SCORED: {len(differ)} documents differ, {differ[:5]}")
            return 1

    py = python_chain(docs, T, registry)
    print("\nPYTHON CHAIN (the scorer's sets, per document):")
    for stage, num, denom in (
        ("citation", "found", "emitted"),
        ("citation_resolution", "resolved", "resolved_shown"),
        ("projection", "projected", "shown"),
    ):
        print(
            f"  {stage:20} recall {py[num]:3d}/{py['truth']} {dry.pct(py[num], py['truth'])}"
            f"   precision {py[num]:3d}/{py[denom]} {dry.pct(py[num], py[denom])}"
        )
    missed = sorted(
        (sha[:12], k) for sha, ks in T.items() for k in ks if k not in py["R"].get(sha, set())
    )
    extra = sorted(
        (sha[:12], k, k in py["held"])
        for sha, ks in py["R"].items()
        for k in ks
        if k not in T.get(sha, set())
    )
    print(f"  truth not found ({len(missed)}): {missed}")
    print(f"  emitted, not truth ({len(extra)}; (document, key, held)): {extra}")

    con = dry.scratch_store(registry, store)
    card = scorecard.build(
        py,
        extractor_version=find.FINDER_VERSION,
        score_file=SCORE_FILE,
        benchmark_date=db.utcnow()[:10],
        reading_channel=CHANNEL,
    )
    stamps = scorecard.declare(con, card)  # the verb `citator declare --scores` runs
    held, works_by_day = keys.registry(con), keys.works(con)
    totals: Counter = Counter()
    for doc in docs:
        try:
            result = load.load_document(con, doc, held, works_by_day, stamps)
        except load.WrongChannel as e:
            # the one-channel-per-page guard, on a registry whose copy already holds another
            # channel's readings of a sampled page: a card measured around a refused document
            # would not be the load production runs, so none is written
            print(f"  NOT SCORED: the loader refused a sampled document: {e}")
            con.close()
            return 1
        for name in ("emitted", "out_of_class", "resolved", "repaired", "unresolved", "exposed"):
            totals[name] += getattr(result, name)
    con.commit()
    print(f"\n  declared rank {methods.RANK_VERSION} and loaded: {dict(totals)}")

    works = py["works"]
    sample_works = {w for ws in works.values() for w in ws}
    rows = [r for r in project.projected(con) if r[10] == CHANNEL and r[0] in sample_works]
    sql_pairs = {(r[0], r[2]) for r in rows}

    def fold(pairs) -> set:
        return {(w, k) for sha, k in pairs for w in works.get(sha, ())}

    repaired = fold(
        con.execute(
            "SELECT DISTINCT citing_document, target_key FROM citation_resolution"
            " WHERE method_version = ? AND reading_channel = ? AND superseded_by IS NULL",
            (resolve.RULE_2, CHANNEL),
        )
    )
    held_for_review = fold(con.execute(HELD_FOR_REVIEW, (CHANNEL,)))
    expected = py["pairs"] - held_for_review
    # A PROJECTED RULE-2 REPAIR IS REFUSED, NOT EXEMPTED (Codex review on PR #29, 2026-09-13).
    # The projection admits `repaired` beside `resolved` and no gate holds it for review, so a
    # repaired edge publishes stamped with this card's precision — which the scorer's sets cannot
    # score, because the raw key is not in the registry. `citation_dryrun.py` only prints them;
    # here a card is written only for a sample whose projection holds none.
    projected_repairs = sql_pairs & repaired
    ok = not projected_repairs and sql_pairs == expected
    if projected_repairs:
        print(f"  NOT SCORED: {len(projected_repairs)} rule-2 repairs project and are unscored:")
        print(f"    {sorted(projected_repairs, key=str)[:8]}")
    print("SQL CHAIN (declare, load, project.projected, per work):")
    print(
        f"  python shows {len(py['pairs'])} (work, docket) pairs, {len(held_for_review)} held for"
        f" review; SQL projects {len(sql_pairs)}, {len(sql_pairs & repaired)} of them rule-2"
        " repairs"
    )
    for citing_work, key in sorted(held_for_review, key=str):
        print(f"    held for review: {citing_work}  {key}")
    print(f"  AGREEMENT: {'yes' if ok else 'NO'}")
    if not ok:
        print(f"    in python not SQL: {sorted(expected - sql_pairs, key=str)[:8]}")
        print(f"    in SQL not python: {sorted(sql_pairs - repaired - expected, key=str)[:8]}")
    figures = {
        methods.DOCKET_CLASS: stamps["citation_resolution"][1],
        methods.WORK_CLASS: (stamps.get(methods.WORK_KEY) or (None, None))[1],
    }
    wrong = {(r[14], r[5]) for r in rows if r[5] != figures.get(r[14])}
    if wrong:
        print(f"  WRONG CLASS STAMPED on a projected row (class, confidence): {sorted(wrong)}")
        ok = False
    con.close()
    # WRITTEN LAST, AND ONLY WHEN THE RUN AGREED WITH ITSELF (`citation_dryrun.py`'s rule).
    if card_out is not None:
        if not ok:
            print(f"  NO SCORE CARD: this run disagreed with itself, so {card_out} is not written")
        else:
            scorecard.write(card_out, card)
            scorecard.read(card_out)
            print(f"  score card -> {card_out} ({card['truth_count']} truth targets, {CHANNEL})")
    return 0 if ok else 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    OPTIONS = ("--registry", "--store", "--findings", "--scores-out")
    for option in OPTIONS:
        if option in argv and argv.index(option) + 1 >= len(argv):
            raise SystemExit(f"usage: {option} needs a value")
    if "--scores-out" in argv and "--findings" not in argv:
        raise SystemExit(
            "--scores-out needs --findings: a card is written only for the finder production ran,"
            " checked against its own findings page by page"
        )

    def opt(name: str) -> Path | None:
        return Path(argv[argv.index(name) + 1]) if name in argv else None

    sys.exit(
        main(
            opt("--registry") or Path("data/prod-copy.sqlite"),
            opt("--store") or Path("data/ocr-citation-dryrun.sqlite"),
            opt("--findings"),
            opt("--scores-out"),
        )
    )
