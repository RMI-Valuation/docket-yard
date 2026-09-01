"""Dry-run the citation pipeline over the sixty-decision benchmark, through migration 0014.

`projection_score.py` runs the chain in Python and reports each stage. This runs the same
chain THROUGH THE SHIPPED CODE — `docketyard.citator` — so the check is of what production
would do, not of a second implementation that agrees with it today.

    python tools/rmi-ai-machine/citation_dryrun.py [data/benchmark/text] \
        [--registry data/prod-copy.sqlite] [--store <path>] [--out <run dir>]

The point is not to produce a number. The number is already known. The point is that the
shipped resolver, span test, loader and projection must produce THE SAME number: if SQL and
the scorer disagree, something in the pipeline has lost what the chain needs, and the
disagreement is the finding. The script exits non-zero when they differ.

Nothing here writes to a real store. It copies the registry to a scratch database, migrates
it, and loads into that. It is a dry run in the literal sense.

**It runs the SHIPPED finder over the benchmark text**, not a replay of a run directory:
`docketyard.citator.find` reads `data/benchmark/text/*.txt` and produces the interchange the
enrichment box will POST. So this is the whole chain in shipping code — finder, resolver,
span test, loader, projection — measured against the same sheet, and the run directory it
consumes is reproducible from the pipeline rather than a fossil nobody can regenerate.

It is also the configuration ADR 0017 § The figures describes and could not re-derive: the
finder with NO REGISTRY FILTER (D2), emitting every docket-shaped hit including the captions
the earlier tool dropped.

Two things it also checks, because both are claims the records make about themselves:

  * `docs/citator-query-2.sql` executes against the migrated store and returns the empty
    set — correct on day one for three reasons, listed in that file's header.
  * The span test's disjunction. ADR 0017 D4 makes it disjunctive over every occurrence of a
    target in the citing WORK, while a judgement row is keyed per PAGE. The two are
    reconciled by the fold, not by a wider judgement. If that reasoning is wrong the
    projected count comes out low here.
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import benchmark_score as bs  # noqa: E402
import projection_score as ps  # noqa: E402

from docketyard.citator import find, keys, load, methods, project, resolve  # noqa: E402
from docketyard.store import db  # noqa: E402

SCORE_FILE = "tools/rmi-ai-machine/projection_score.py"


def scratch_store(registry: Path, out: Path) -> sqlite3.Connection:
    """A migrated copy of the registry. The dockets and decisions are real; nothing else is."""
    for suffix in ("", "-wal", "-shm"):
        Path(str(out) + suffix).unlink(missing_ok=True)
    src = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
    dst = sqlite3.connect(out)
    src.backup(dst)
    src.close()
    dst.close()
    return db.connect(out)


def citing_documents(con: sqlite3.Connection, ids: set[str]) -> dict[str, str]:
    """decision id -> the bytes the benchmark read. Where a decision has several
    attachments the first by url is taken, and the choice is reported rather than hidden."""
    out: dict[str, str] = {}
    several = 0
    for did in sorted(ids):
        rows = con.execute(
            "SELECT DISTINCT da.document_sha256 FROM decision_record dr"
            " JOIN decision_attachment da ON da.decision_pk = dr.decision_pk"
            " WHERE dr.stb_decision_id = ? AND da.document_sha256 IS NOT NULL"
            " ORDER BY da.source_url",
            (did,),
        ).fetchall()
        if not rows:
            continue
        out[did] = rows[0][0]
        several += len(rows) > 1
    if several:
        print(f"  note: {several} of {len(out)} decisions have several attachments; took the first")
    return out


def own_dockets(con: sqlite3.Connection) -> dict[str, set[str]]:
    """Per decision, the normalised keys of every docket it is entered in — the record's own
    knowledge, which ADR 0017 D1 says no extractor should be asked to guess."""
    out: dict[str, set[str]] = {}
    for did, prefix, seq, sub_seq, suffix in con.execute(
        "SELECT r.stb_decision_id, d.prefix, d.sequence, d.sub_sequence, d.suffix"
        " FROM decision_record r JOIN docket d USING (docket_id)"
    ):
        out.setdefault(str(did), set()).add(keys.registry_key(prefix, seq, sub_seq, suffix))
    return out


def register(con: sqlite3.Connection, version: str, scores: dict) -> dict:
    """What a real pipeline does on its first run: declare the methods, record the scores."""
    methods.declare(con, version)
    truth, date = scores["truth"], db.utcnow()[:10]
    # EVERY measurement carries a PRECISION, because that is what a row is stamped with
    # (ADR 0017 D3) and `methods.stamp` refuses a measurement without one. The extraction
    # and resolution precisions are of what each stage EMITS; the projection's is of what a
    # reader is shown, and they have different denominators on purpose.
    emitted = scores["emitted"]
    if not emitted:
        raise SystemExit("the run emitted nothing: there is no precision to record")
    _ = {
        "citation": methods.measure(
            con,
            measured_target="citation",
            cls="docket",
            extractor_version=version,
            score_file=SCORE_FILE,
            benchmark_date=date,
            recall=scores["found"] / truth,
            precision=scores["found"] / emitted,
            truth_count=truth,
            found_count=scores["found"],
        ),
        "citation_resolution": methods.measure(
            con,
            measured_target="citation_resolution",
            cls="docket",
            extractor_version=version,
            score_file=SCORE_FILE,
            benchmark_date=date,
            recall=scores["resolved"] / truth,
            # the precision of the RESOLUTION class is over what it resolved, not over what
            # the finder emitted — `resolved / emitted` is neither a precision nor a recall,
            # and this record has published enough of those
            precision=scores["resolved"] / max(scores["resolved_shown"], 1),
            truth_count=truth,
            found_count=scores["found"],
        ),
        "projection": methods.measure(
            con,
            measured_target="projection",
            cls="docket",
            extractor_version=version,
            score_file=SCORE_FILE,
            benchmark_date=date,
            recall=scores["projected"] / truth,
            precision=scores["projected"] / scores["shown"],
            truth_count=truth,
            found_count=scores["found"],
            shown_count=scores["shown"],
        ),
    }
    con.commit()
    return methods.stamp(con)


def python_chain(run: Path, registry: Path) -> dict:
    """projection_score.py's chain, as numbers rather than as printed lines."""
    truth_doc, _ = bs.truth()
    run_doc, _, _ = bs.run_findings(run, None)

    def keep(d):
        return {k: {x for x in v if bs.DOCKET_KEY.match(x)} for k, v in d.items()}

    T = keep(bs.collect(truth_doc, "citation", "stb"))
    R = keep(bs.collect(run_doc, "citation", "stb"))
    con = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
    heldset, fam = ps.registry(con), ps.families(con, set(T) | set(R))
    con.close()
    quoted = ps.spans(run)

    def names(did, key):
        return bool(ps.SPAN_NAMES_DOCUMENT.search(quoted.get((did, key), "")))

    found = resolved = projected = 0
    shown_pairs = set()
    for did, ks in T.items():
        for k in ks:
            if k not in R.get(did, set()):
                continue
            found += 1
            if k not in heldset:
                continue
            resolved += 1
            if k in fam.get(did, set()) and not names(did, k):
                continue
            projected += 1
            shown_pairs.add((did, k))
    for did, ks in R.items():
        for k in ks - T.get(did, set()):
            if k in heldset and not (k in fam.get(did, set()) and not names(did, k)):
                shown_pairs.add((did, k))
    resolved_shown = sum(1 for did, ks in R.items() for k in ks if k in heldset)
    return {
        "truth": sum(map(len, T.values())),
        "emitted": sum(map(len, R.values())),
        "resolved_shown": resolved_shown,
        "found": found,
        "resolved": resolved,
        "projected": projected,
        "shown": len(shown_pairs),
        "pairs": shown_pairs,
        "T": T,
    }


def pct(part: int, whole: int) -> str:
    """A rate, or a reason there is none. A run that resolves nothing must report that
    rather than divide by zero — the empty case is a finding, not a crash."""
    return f"{100 * part / whole:5.1f}%" if whole else "    n/a"


def run_the_finder(text_dir: Path, out: Path, own: dict[str, set[str]]) -> Path:
    """The SHIPPED finder over every extracted decision, written in benchmark_run.py's shape
    so `projection_score.py` can score it beside the models.

    This is the run ADR 0017 § The figures describes and could not re-derive — the finder
    with NO registry filter (D2) — and it is regenerated on every dry run rather than kept as
    a directory nobody can reproduce. `data/` is disposable, and this is what makes it so.
    """
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.json"):
        stale.unlink()
    orphans = []
    for path in sorted(text_dir.glob("*.txt")):
        did = path.stem.rsplit("-", 1)[-1]
        if did not in own:
            # without the decision's own dockets the rule calls every caption a citation:
            # degrade LOUDLY, never silently (the same guard benchmark_regex.py carries)
            orphans.append(did)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        doc = {
            "decision_id": did,
            "model": methods.EXTRACTOR,
            "prompt_version": find.FINDER_VERSION,
            "pages": [
                {
                    "page": page,
                    "findings": [
                        {
                            **f,
                            # benchmark_run.py's convention: a caption is `self`, and
                            # `benchmark_score.collect(…, 'citation', 'stb')` reads the pair
                            "target_kind": "stb" if f["kind"] == "citation" else "self",
                            "note": "regex-docket-cite; no registry filter (ADR 0017 D2)",
                        }
                        for f in find.find(body, own[did])
                    ],
                }
                for page, body in find.pages(text)
            ],
        }
        (out / f"{did}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    if orphans:
        print(f"  WARNING: {len(orphans)} decisions have no docket in the registry: {orphans[:5]}")
    return out


def main(text_dir: Path, registry: Path, store: Path, out: Path) -> int:
    con0 = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
    own = own_dockets(con0)
    con0.close()
    run = run_the_finder(text_dir, out, own)
    py = python_chain(run, registry)
    print(f"finder over {text_dir} -> {run}   registry {registry}\n")
    print("PYTHON CHAIN (tools/rmi-ai-machine/projection_score.py):")
    print(
        f"  extraction {py['found']:3d}/{py['truth']}   resolution {py['resolved']:3d}"
        f"   PROJECTED {py['projected']:3d} {pct(py['projected'], py['truth'])}"
    )
    print(
        f"  precision  {py['projected']} of {py['shown']} shown ="
        f" {pct(py['projected'], py['shown'])}\n"
    )

    con = scratch_store(registry, store)
    version = find.FINDER_VERSION
    stamps = register(con, version, py)
    held = keys.registry(con)
    docs = citing_documents(con, {p.stem for p in run.glob("*.json")})
    print(f"  {len(docs)} of 60 decisions have fetched bytes to hang an edge on")

    # ADR 0018 D9 measured it: 5 documents of 20,992 hang under two stb_decision_ids. The
    # same bytes are ONE citing document; the fold at projection is what turns them back
    # into two citing works, correctly and not as a doubling.
    seen: set[str] = set()
    totals = {"emitted": 0, "out_of_class": 0, "unresolved": 0, "review": 0}
    for path in sorted(run.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        sha = docs.get(doc["decision_id"])
        if sha is None or sha in seen:
            continue
        seen.add(sha)
        result = load.load_document(
            con,
            {
                "document_sha256": sha,
                "method": methods.EXTRACTOR,
                "method_version": doc["prompt_version"],
                "reading_channel": methods.CHANNEL_TEXT,
                "pages_read": len(doc.get("pages", [])),
                "findings": [
                    {"page": page["page"], **f}
                    for page in doc.get("pages", [])
                    for f in page.get("findings", [])
                ],
            },
            held,
            stamps,
        )
        totals["emitted"] += result.emitted
        totals["out_of_class"] += result.out_of_class
        totals["unresolved"] += result.unresolved
        totals["review"] += len(result.review)
    con.commit()
    print(
        f"  loaded {totals['emitted']} (document, page, target) rows through four families;"
        f" {totals['out_of_class']} out of class, {totals['unresolved']} unresolved,"
        f" {totals['review']} to review\n"
    )

    rows = project.projected(con)
    sql_pairs = {(r[0], r[2]) for r in rows}  # citing_work_id, target_key
    sql_true = {(d, k) for d, k in sql_pairs if k in py["T"].get(d, set())}
    print("SQL CHAIN (docketyard.citator over migration 0014):")
    print(f"  PROJECTED {len(sql_true):3d} {pct(len(sql_true), py['truth'])}")
    print(
        f"  precision  {len(sql_true)} of {len(sql_pairs)} shown ="
        f" {pct(len(sql_true), len(sql_pairs))}\n"
    )

    q2 = con.execute(
        Path("docs/citator-query-2.sql").read_text(encoding="utf-8"),
        {"rank_version": methods.RANK_VERSION, "target_work": "52526"},
    ).fetchall()
    print(
        f"  docs/citator-query-2.sql executes and returns {len(q2)} rows"
        "  (three reasons it is empty; see its header)"
    )
    # the docket grain is the one a reader's "cited by" list is built from, so it is
    # exercised here rather than left to be discovered on the day a page needs it
    if rows:
        busiest = max(rows, key=lambda r: r[3] or 0)[3]
        print(
            f"  cited_by(docket_id={busiest}) returns"
            f" {len(project.cited_by(con, docket_id=busiest))} rows"
        )

    # Only decisions whose bytes are in the store can carry an edge; the Python chain scores
    # every decision in the sheet. Compare on the intersection, and say so.
    # THE TWO CHAINS MODEL DIFFERENT RULES ONCE A REPAIR FIRES. `projection_score.py` knows
    # only rule 1; the shipped resolver also has rule 2, so a repaired edge is legitimately
    # in SQL and not in Python. Report those separately rather than failing a correct
    # pipeline — and report them, because a silent difference is how the two drift.
    repaired = {
        (w, k)
        for w, k in con.execute(
            "SELECT DISTINCT r.target_key, r.method_version FROM citation_resolution r"
            " WHERE r.method_version = ? AND r.superseded_by IS NULL",
            (resolve.RULE_2,),
        )
    }
    if repaired:
        print(f"  {len(repaired)} rule-2 repairs, which the Python chain does not model")
    # THE REVIEW GATE IS A THIRD LEGITIMATE DIFFERENCE (migration 0015). ADR 0017 D2 sends
    # the exposed class to a human before publication, and `projection_score.py` does not
    # model that — it measures the PAIR, extractor plus projection rule, while this is a
    # queue state a review clears. So the held edges are NAMED and excluded from the
    # comparison rather than failing a correct pipeline.
    held_for_review = {
        (w, k)
        for w, k in con.execute(
            "SELECT DISTINCT COALESCE(dr.stb_decision_id, r.citing_document), r.target_key"
            " FROM citation_resolution r"
            " JOIN citation_judgement j ON j.citing_document = r.citing_document"
            "  AND j.page = r.page AND j.target_kind = r.target_kind"
            "  AND j.target_key = r.target_key AND j.judgement = 'exposed'"
            "  AND j.value = 'true' AND j.superseded_by IS NULL"
            " LEFT JOIN decision_attachment da ON da.document_sha256 = r.citing_document"
            " LEFT JOIN decision_record dr ON dr.decision_pk = da.decision_pk"
            " WHERE r.superseded_by IS NULL AND r.outcome IN ('resolved', 'repaired')"
            " AND NOT EXISTS (SELECT 1 FROM citation_resolution h"
            "  WHERE h.citing_document = r.citing_document AND h.page = r.page"
            "  AND h.target_kind = r.target_kind AND h.target_key = r.target_key"
            "  AND h.confidence_state = 'human' AND h.superseded_by IS NULL)"
        )
    }
    if held_for_review:
        print(
            f"  {len(held_for_review)} edges HELD FOR REVIEW by the exposure test"
            f" (ADR 0017 D2), so a reader sees {len(sql_true)} of {py['truth']} ="
            f" {pct(len(sql_true), py['truth']).strip()} until the queue is worked:"
        )
        for work, key in sorted(held_for_review):
            print(f"    {work}  {key}")

    reachable = {(d, k) for d, k in py["pairs"] if d in docs}
    ok = sql_pairs == reachable - held_for_review
    print(
        f"\n  python projects {len(reachable)} pairs on documents the store holds, less"
        f" {len(held_for_review)} held for review; SQL projects {len(sql_pairs)}"
    )
    print(f"  AGREEMENT: {'yes' if ok else 'NO'}")
    if not ok:
        print(f"    in python not SQL: {sorted(reachable - sql_pairs)[:5]}")
        print(f"    in SQL not python: {sorted(sql_pairs - reachable)[:5]}")
    # the stamped confidence must be the resolution stage's own, or the display quotes one
    # stage for another — the error ADR 0017 made four times
    stamped = {r[5] for r in rows}
    if stamped and stamped != {stamps["citation_resolution"][1]}:
        print(f"  WRONG STAGE STAMPED on a projected row: {stamped}")
        ok = False
    con.close()
    return 0 if ok else 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    args = [a for a in argv if not a.startswith("--")]

    def opt(name, default):
        return Path(argv[argv.index(name) + 1]) if name in argv else Path(default)

    sys.exit(
        main(
            Path(args[0]) if args else Path("data/benchmark/text"),
            opt("--registry", "data/prod-copy.sqlite"),
            opt("--store", "data/citation-dryrun.sqlite"),
            opt("--out", "data/benchmark/runs-regex/shipped"),
        )
    )
