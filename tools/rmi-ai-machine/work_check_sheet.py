"""Draft the work-level column of the sixty-decision sheet, for the operator to check.

    python tools/rmi-ai-machine/citation_dryrun.py data/benchmark/text \
        --registry <a production copy> --store data/work-dryrun.sqlite \
        --out data/benchmark/runs-regex/work
    python tools/rmi-ai-machine/work_check_sheet.py --store data/work-dryrun.sqlite \
        --run data/benchmark/runs-regex/work

`docs/research/benchmark/labels.csv` is checked ground truth for WHICH PROCEEDING a citation
names. It says nothing about which DOCUMENT, and `('citation_resolution', 'work')` cannot be
scored until it does (`project.cited_by` refuses the work grain for exactly that reason). The
operator's decision of 2026-09-10 (`docs/runbook.md` § Blocker 4): the column is drafted from
the sheet the record already has rather than from a new sample, and declared before the
citator's first load, so one load stamps both classes.

WHAT THIS DRAFTS AND WHAT IT DOES NOT. It runs nothing of its own: it reads the resolutions
`citation_dryrun.py` wrote through the shipped loader, and reports, per (citing work, target),
the document the shipped resolver reached and the evidence it reached it from. **Nothing here
is truth until the operator judges it** — the flow this project uses for every sheet (the
party-type sample, 2026-08-30; the citation sheet itself). The draft exists so the judging is
a yes/no against the record rather than a lookup the operator performs by hand.

BOTH HALVES OF THE MEASUREMENT NEED A ROW, so a pair the resolver left at docket level is
drafted too, with the reason it stopped — and the reason is separated into the rule's and the
record's, because they answer different questions. "The page names no date I can anchor" is a
limit of `resolve.SERVED` and its window; "the day holds two decisions in that docket" is ADR
0018 D4 declining to arbitrate; "the record holds no decision served that day" is a gap in the
record, not a miss by the rule. A recall figure that mixed the three would blame the resolver
for the archive.
"""

import argparse
import csv
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import benchmark_score as bs  # noqa: E402

from docketyard.citator import keys, resolve  # noqa: E402

SHEET = Path("docs/research/benchmark/labels.csv")
# The work column, checked by the operator 2026-09-10 — `SHEET`'s sibling and the same kind of
# thing: ground truth, kept in the repository, because a judging sitting is not reproducible
# from the pipeline and everything in `data/` is.
WORK_LABELS = Path("docs/research/benchmark/work-labels.csv")
TEMPLATE = Path(__file__).resolve().parent / "work_check_page.html"
# What the page needs of a row. Named rather than "everything", so a column added here for the
# CSV does not silently double the page's weight.
PAGE_FIELDS = (
    "citing_decision",
    "citing_url",
    "citing_docket",
    "target_key",
    "target_caption",
    "served_date_read",
    "drafted_decision",
    "drafted_service_date",
    "drafted_type",
    "drafted_body",
    "drafted_docket",
    "drafted_url",
    "why_no_document",
    "pages",
    "anchored_segment",
    "quoted_line",
)

# What a drafted row can say about why no document was reached. The rule's limits and the
# record's gaps are named apart on purpose: only the first is a miss the resolver could close.
NO_DATE = "the segment anchored to this target names no single served date"
AMBIGUOUS_DAY = "the record holds several decisions in that docket that day (ADR 0018 D4)"
NO_DECISION = "the record holds no decision in that docket served that day"
UNREGISTERED = "the decision is not in decision_work, so a resolution could not point at it"
UNRESOLVED = "the target did not resolve to a docket, so no document was looked for"


def sheet_rows() -> dict[tuple[str, str], list[dict]]:
    """(citing decision, normalised target) -> the sheet's own labelled rows for it.

    Keyed through `bs.norm_target` because that is the form `citation_resolution.target_key`
    carries, and a test pins the two normalisers together.
    """
    out: dict[tuple[str, str], list[dict]] = {}
    with SHEET.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["kind"] != "citation" or row["target_kind"] != "stb":
                continue
            key = bs.norm_target(row["target"])
            if not bs.DOCKET_KEY.match(key or ""):
                continue
            out.setdefault((row["decision_id"], key), []).append(row)
    return out


def passages(run: Path) -> dict[tuple[str, int, str], list[str]]:
    """(citing decision, page, target key) -> the lines the finder quoted there.

    THE PAGE IS IN THE KEY BECAUSE THE RESOLVER'S GRAIN IS THE PAGE. `load` resolves each
    (page, target) from the quotes on that page alone, so a draft that joined a document's
    pages would hand a target a served date printed on some other page — and would then
    report the resolver as having missed a document it was never shown. Reproduced while
    drafting this: 14 pairs looked like unexplained misses until the page came back into
    the key, and every one was a date on a different page.
    """
    out: dict[tuple[str, int, str], list[str]] = {}
    for path in sorted(run.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        did = doc["decision_id"]
        for page in doc.get("pages", []):
            for f in page.get("findings", []):
                if f.get("kind") != "citation":
                    continue
                key = keys.normalise(f.get("target", ""))
                if key:
                    out.setdefault((did, int(page["page"]), key), []).append(f.get("quoted", ""))
    return out


def decisions(con: sqlite3.Connection) -> dict[str, dict]:
    """Every decision the draft may name, with what identifies it to a reader."""
    out: dict[str, dict] = {}
    for did, service_date, dtype, body, docket_id, raw in con.execute(
        "SELECT r.stb_decision_id, r.service_date, r.decision_type, r.deciding_body,"
        "       r.docket_id, d.raw_docket"
        " FROM decision_record r JOIN docket d USING (docket_id)"
    ):
        out[str(did)] = {
            "decision_id": str(did),
            "service_date": service_date,
            "decision_type": dtype,
            "deciding_body": body,
            "docket_id": docket_id,
            "raw_docket": raw,
        }
    return out


def pdf_urls(con: sqlite3.Connection) -> dict[str, str]:
    """decision id -> the Board's own file, which is what the operator judges against."""
    out: dict[str, str] = {}
    for did, url in con.execute(
        "SELECT r.stb_decision_id, MIN(da.source_url) FROM decision_record r"
        " JOIN decision_attachment da ON da.decision_pk = r.decision_pk"
        " WHERE da.source_url IS NOT NULL GROUP BY r.stb_decision_id"
    ):
        out[str(did)] = url
    return out


def captions(con: sqlite3.Connection) -> dict[str, str]:
    """docket key -> the Board's caption, trimmed. A parent docket's caption is every
    sub-docket's concatenated, which identifies nothing; the first clause is what names it."""
    out: dict[str, str] = {}
    for title, caption in con.execute(
        "SELECT title, caption FROM search_doc WHERE kind = 'docket' AND caption <> ''"
    ):
        first = (caption or "").split("�")[0].strip()
        out[str(title)] = first[:150]
    return out


def served_day(con: sqlite3.Connection, docket_id: int, day: str) -> list[str]:
    """Every decision in that docket served that day — the count is what `keys.works` folds
    on, so the draft can say WHICH of D4's two ways out a docket-level answer took."""
    return [
        str(r[0])
        for r in con.execute(
            "SELECT DISTINCT stb_decision_id FROM decision_record"
            " WHERE docket_id = ? AND service_date = ?",
            (docket_id, day),
        )
    ]


def build(store: Path, run: Path) -> list[dict]:
    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    sheet, quotes = sheet_rows(), passages(run)
    decs, urls, caps = decisions(con), pdf_urls(con), captions(con)
    registered = {r[0] for r in con.execute("SELECT stb_decision_id FROM decision_work")}

    # ONE DRAFTED ROW IS ONE CLAIM, and a claim is (citing work, target, document): a citing
    # document may cite two decisions of one proceeding on two pages, and `CITED_BY_WORK` keys
    # on `cited_decision_id`, so those are two edges a reader sees and two judgements to make.
    # A pair that reached no document is one row however many pages it sat on — there is one
    # thing to say about it.
    claims: dict[tuple[str, str, str], dict] = {}
    for citing, page, key, docket_id, decision_id in con.execute(
        "SELECT COALESCE(dr.stb_decision_id, r.citing_document), r.page, r.target_key,"
        "       r.cited_docket_id, r.cited_decision_id"
        " FROM citation_resolution r"
        " LEFT JOIN decision_attachment da ON da.document_sha256 = r.citing_document"
        " LEFT JOIN decision_record dr ON dr.decision_pk = da.decision_pk"
        " WHERE r.superseded_by IS NULL"
    ):
        at = claims.setdefault(
            (str(citing), key, decision_id or ""),
            {"docket_id": docket_id, "decision_id": decision_id, "pages": []},
        )
        at["pages"].append((int(page), key))

    # a pair the sheet labels that the loader never resolved at all (no bytes, no finding):
    # it still owes a row if its quote names a date, or the recall denominator is the
    # pipeline's own reach rather than the sheet's
    for pair in sheet:
        if not any(c[0] == pair[0] and c[1] == pair[1] for c in claims):
            claims[(pair[0], pair[1], "")] = {"docket_id": None, "decision_id": None, "pages": []}

    rows = []
    for (citing, key, _), got in sorted(claims.items()):
        sheet_rows_here = sheet.get((citing, key), [])
        printed = next((r["target"] for r in sheet_rows_here if r["target"]), key)
        pages = sorted({p for p, _ in got["pages"]})
        segments, lines, day = [], [], None
        for page in pages:
            passage = " | ".join(q for q in quotes.get((citing, page, key), []) if q)
            segment = resolve._anchored(passage, printed) if passage else ""
            if segment:
                segments.append(segment)
            if passage:
                lines.append(passage)
            day = day or resolve.served_date(segment)
        answer = got["decision_id"]

        # a pair with no drafted answer and no served date anywhere near it is not a work
        # question at all, and putting it in front of the operator would be 300 rows of noise
        sheet_day = next(
            (d for d in (resolve.served_date(r["quoted"]) for r in sheet_rows_here) if d), None
        )
        if answer is None and day is None and sheet_day is None:
            continue

        why = ""
        if answer is None:
            docket_id = got["docket_id"]
            if docket_id is None:
                why = UNRESOLVED
            elif day is None:
                why = NO_DATE
            else:
                same = served_day(con, docket_id, day)
                if not same:
                    why = NO_DECISION
                elif len(same) > 1:
                    why = AMBIGUOUS_DAY
                elif same[0] not in registered:
                    why = UNREGISTERED
                else:  # pragma: no cover — `works` and this query would have to disagree
                    why = "no document, and the reasons above do not explain it"
        target = decs.get(answer or "", {})
        cite_row = (sheet_rows_here or [{}])[0]
        rows.append(
            {
                "citing_decision": citing,
                "citing_url": urls.get(citing, cite_row.get("board_url", "")),
                "citing_docket": cite_row.get("docket", ""),
                "target_key": key,
                "target_caption": caps.get(key, ""),
                "in_sheet": "yes" if (citing, key) in sheet else "no",
                "served_date_read": day or sheet_day or "",
                "drafted_decision": answer or "",
                "drafted_service_date": target.get("service_date", ""),
                "drafted_type": target.get("decision_type", ""),
                "drafted_body": target.get("deciding_body", ""),
                "drafted_docket": target.get("raw_docket", ""),
                "drafted_url": urls.get(answer or "", ""),
                "why_no_document": why,
                "pages": ",".join(str(p) for p in pages),
                "anchored_segment": " | ".join(segments)[:400],
                # THE WHOLE LINE, not only the window: a served date anchored to the WRONG
                # target is the failure this measurement exists to catch (three such bugs were
                # fixed on 2026-09-10 alone), and it is invisible unless the neighbours the
                # window excluded are on the page beside it.
                "quoted_line": " | ".join(lines)[:900],
                "sheet_quote": cite_row.get("quoted", ""),
                "verdict": "",  # the operator's column: right | wrong | (the id it should be)
            }
        )
    con.close()
    # THE DRAFTED CLAIMS COME FIRST, because they are the half a card needs: precision is
    # what a row is stamped with (ADR 0017 D3), and it is measured over what the rule
    # ANSWERED. The docket-level stops that follow are the recall half — worth having and
    # not worth blocking a measurement on, so the queue says which is which rather than
    # presenting 211 rows as one undifferentiated pile.
    rows.sort(key=lambda r: (not r["drafted_decision"], r["citing_decision"], r["target_key"]))
    return rows


def render(rows: list[dict], out: Path) -> Path:
    """The check queue, from the template beside this file.

    It is a page and not a printout because 211 judgements is a sitting, not a glance: it
    keeps its place, saves as it goes, and hands back the verdicts as the sheet wants them.
    The template is in the repository so the queue is reproducible from the tool rather than
    being a file somebody has to still have.
    """
    page = TEMPLATE.read_text(encoding="utf-8")
    data = json.dumps([{k: r[k] for k in PAGE_FIELDS} for r in rows], ensure_ascii=False)
    if "/*DATA*/[]" not in page:  # pragma: no cover — the template is ours
        raise SystemExit(f"{TEMPLATE} has no /*DATA*/[] placeholder to fill")
    out.write_text(page.replace("/*DATA*/[]", data), encoding="utf-8")
    return out


def score(rows: list[dict], verdicts: Path) -> dict:
    """The operator's judgements as the card's work block — counts, never a precision.

    `scorecard.declare` computes the precision from these, so nobody re-types one; the
    conventions the counting rests on are stated here because they decide what the figure
    means:

    * A claim judged `unclear` is in NEITHER the numerator nor the denominator, and is
      counted apart. Folding it in as a wrong would charge the rule for the judge's
      uncertainty, and as a right would be worse.
    * `should-be:<id>` on a drafted claim is a WRONG that also names the truth, so the sheet
      gains an answer and the precision loses one. On a docket-level stop it is a MISS: the
      citation named a document and the rule did not reach it.
    * A RECALL IS EMITTED ONLY WHEN THE SHEET DETERMINES ONE. A bare `wrong` says the rule
      named the wrong document without saying whether the citation names any, so a truth
      count computed over a sheet holding one is a lower bound — and a recall from a lower
      bound is an upper bound published as a measurement. So the block carries `truth` only
      when every row is judged and none is a bare `wrong`; otherwise `class_measurement`
      takes a NULL recall, which is what nullable means here.
    """
    said: dict[tuple[str, str, str], str] = {}
    # The CHECKED sheet is CSV with a header, like every other sheet under `docs/research`;
    # what the check queue copies out is tab separated. Both are read, because the second is
    # what the operator's hands produce and the first is what the repository keeps.
    if verdicts.suffix == ".csv":
        with verdicts.open(encoding="utf-8", newline="") as f:
            parsed = list(csv.reader(f))[1:]
    else:
        parsed = [r.split("\t") for r in verdicts.read_text(encoding="utf-8").splitlines()]
    for n, parts in enumerate(parsed, 1):
        if not any(p.strip() for p in parts):
            continue
        if len(parts) != 4:
            raise SystemExit(f"{verdicts}:{n}: expected four fields, got {parts}")
        said[(parts[0], parts[1], parts[2])] = parts[3].strip()
    known = {(r["citing_decision"], r["target_key"], r["drafted_decision"]): r for r in rows}
    # A VERDICTS FILE FROM ANOTHER DRAFT IS REFUSED. The draft is regenerated from whatever
    # registry the dry run used, and a claim that no longer exists cannot be scored — nor may
    # its verdict be quietly dropped into a denominator it does not belong to.
    if orphans := [k for k in said if k not in known]:
        raise SystemExit(
            f"{verdicts}: {len(orphans)} judgements name claims this draft does not hold,"
            f" e.g. {orphans[:3]}. Re-draft, or judge against the draft these came from."
        )

    # EVERY VERDICT IS ONE OF THESE. An unrecognised word was silently dropped from both the
    # numerator and the denominator, which is how a typo becomes a precision (code review,
    # 2026-09-10) — the queue writes these strings and nothing else should reach here.
    known_verdicts = {"right", "wrong", "unclear", "right-to-stop"}
    if odd := {
        v for v in said.values() if v not in known_verdicts and not v.startswith("should-be:")
    }:
        raise SystemExit(f"{verdicts}: verdicts this tool does not know: {sorted(odd)}")

    right = judged = unclear = missed = bare_wrong = 0
    for k, row in known.items():
        v = said.get(k, "")
        if row["drafted_decision"]:
            if v == "unclear":
                unclear += 1
            elif v == "right":
                right += 1
                judged += 1
            elif v == "wrong" or v.startswith("should-be:"):
                judged += 1
                bare_wrong += v == "wrong"
        elif v.startswith("should-be:"):
            missed += 1
        elif v == "unclear":
            unclear += 1
    if not judged:
        raise SystemExit(f"{verdicts}: no drafted claim was judged; there is no precision")
    # AN UNCLEAR IS A ROW WHOSE TRUTH IS UNKNOWN, so it bars a truth count exactly as a bare
    # `wrong` does: it is in neither `judged` nor `missed`, and `right + (judged - right) +
    # missed` would then count fewer true documents than the sheet holds — a lower bound, and
    # a recall from a lower bound is an upper bound published as a measurement (code review).
    complete = len(said) == len(known) and not unclear
    block = {
        "right": right,
        "judged": judged,
        "score_file": verdicts.as_posix(),
        "benchmark_date": date.today().isoformat(),
    }
    if complete and not bare_wrong:
        block["truth"] = right + (judged - right) + missed
    return block | {
        "_unclear": unclear,
        "_missed": missed,
        "_bare_wrong": bare_wrong,
        "_unjudged": len(known) - len(said),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", type=Path, default=Path("data/work-dryrun.sqlite"))
    ap.add_argument("--run", type=Path, default=Path("data/benchmark/runs-regex/work"))
    ap.add_argument("--csv", type=Path, default=Path("data/work-check.csv"))
    ap.add_argument("--json", type=Path, default=Path("data/work-check.json"))
    ap.add_argument("--html", type=Path, default=Path("data/work-check.html"))
    ap.add_argument(
        "--verdicts",
        type=Path,
        nargs="?",
        const=WORK_LABELS,
        help="the operator's judgements. With this the tool SCORES instead of drafting and"
        f" writes the card's work block. Bare, it reads the checked sheet at {WORK_LABELS};"
        " with a path, a tab-separated file as the check queue copies one out.",
    )
    ap.add_argument("--block", type=Path, default=Path("data/work-block.json"))
    args = ap.parse_args()

    rows = build(args.store, args.run)
    if args.verdicts:
        block = score(rows, args.verdicts)
        aside = {k[1:]: block.pop(k) for k in list(block) if k.startswith("_")}
        args.block.write_text(json.dumps(block, indent=1), encoding="utf-8")
        print(f"{block['right']} of {block['judged']} judged claims name the right document")
        print(f"  precision {100 * block['right'] / block['judged']:.1f}% -> {args.block}")
        if "truth" in block:
            print(f"  recall {100 * block['right'] / block['truth']:.1f}% of {block['truth']} true")
        else:
            print(
                f"  NO RECALL: {aside['bare_wrong']} bare `wrong`, {aside['unclear']} unclear,"
                f" {aside['unjudged']} unjudged — a truth count over those is a lower bound,"
                " and a recall from a lower bound is an upper bound published as a measurement"
            )
        print(f"  set aside: {aside['unclear']} unclear; the stops name {aside['missed']} missed")
        print("Fold it into the card with citation_dryrun.py --work, then `citator declare`.")
        return 0

    # AN EMPTY DRAFT IS A FINDING, not a file. It means the run directory held no findings or
    # the store no resolutions — and writing a headerless CSV and a queue with nothing in it
    # would report that as a completed draft (code review, 2026-09-10).
    if not rows:
        raise SystemExit(
            f"no claims to judge: {args.run} and {args.store} between them produced no"
            " resolution carrying a served date. Re-run citation_dryrun.py first."
        )
    with args.csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    args.json.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    render(rows, args.html)

    drafted = [r for r in rows if r["drafted_decision"]]
    print(f"{len(rows)} rows to judge -> {args.csv}, {args.json}, {args.html}")
    print(f"  {len(drafted)} carry a drafted document; {len(rows) - len(drafted)} stop at docket")
    reasons: dict[str, int] = {}
    for r in rows:
        if r["why_no_document"]:
            reasons[r["why_no_document"]] = reasons.get(r["why_no_document"], 0) + 1
    for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"    {n:4d}  {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
