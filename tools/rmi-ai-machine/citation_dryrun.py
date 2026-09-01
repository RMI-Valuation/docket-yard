"""Dry-run the citation pipeline over the sixty-decision benchmark, through migration 0014.

`projection_score.py` runs the chain in Python and reports each stage. This runs the same
chain THROUGH THE SCHEMA — every finding becomes a `citation`, a `citation_reading`, a
`citation_resolution` and a `span_names_document` judgement, the methods register themselves
in `assertion_method`, the figures land in `class_measurement`, and the projection is then
computed in SQL rather than in Python.

    python tools/rmi-ai-machine/citation_dryrun.py data/benchmark/runs-regex/regex-own \
        [--registry data/prod-copy.sqlite] [--store <path>]

The point is not to produce a number. The number is already known. The point is that ADR
0018's shape must produce THE SAME number: if SQL and the scorer disagree, the schema has
lost something the chain needs, and the disagreement is the finding. The script exits
non-zero when they differ.

Nothing here writes to a real store. It copies the registry to a scratch database, migrates
it, and loads into that. It is a dry run in the literal sense.

Two things it also checks, because both are claims the records make about themselves:

  * `docs/citator-query-2.sql` executes against the migrated store, and returns the empty set
    (ADR 0017 D7: every edge in the first slice is `cites`; that query filters on a negative
    polarity, so an empty result is the correct answer on day one).
  * The span test's disjunction. ADR 0017 D4 makes the test disjunctive over every occurrence
    of a target in the citing WORK, while a judgement row is keyed per PAGE. The two are
    reconciled by the fold, not by a wider judgement: a page whose span names no document is
    filtered out, another page's row for the same target survives, and the DISTINCT over the
    work collapses them. If that reasoning is wrong the projected count comes out low here.
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import benchmark_score as bs  # noqa: E402
import projection_score as ps  # noqa: E402

from docketyard.store import db  # noqa: E402

N = bs.norm_target

CHANNEL = "text-layer"
RANK = "v1"
EXTRACTOR = "regex-docket-cite"
RESOLVER = "registry-match"
RESOLVER_VERSION = "rule-1"
SPAN_METHOD = "span-names-document"
SPAN_VERSION = "2026-09-01"
# ADR 0018 D8: this names three things at once - the span test's version, the family
# closure's version, and rank_version - because the projection is that product.
PROJECTION_RULE = f"span={SPAN_VERSION};closure=cite.py@2026-09-01;rank={RANK}"

# The stamped numbers, each from the stage it measures and no other (ADR 0017 § The figures,
# by stage). They are written here rather than inline so that a row cannot quietly acquire a
# figure from a neighbouring stage — the error ADR 0017 made four times.
EXTRACTION_CONFIDENCE = 0.978  # the finder saw it
RESOLUTION_CONFIDENCE = 0.933  # and the registry resolved it
PROJECTION_PRECISION = 0.980  # and of what a reader is shown, this much is true

# The projection that SHIPS: "what cites this". It is docs/citator-query-2.sql with the
# treatment join and the negative-polarity filter removed - which is exactly what ADR 0017 D7
# says day one is, and why query 2 itself returns nothing until the treatment pass runs.
# Every other term is the same, deliberately: if these two ever disagree on the resolution,
# family or span terms, one of them is wrong.
PROJECTION = """
WITH rank_res AS (
  SELECT method, method_version, reading_channel, role, precedence_rank
  FROM assertion_method
  WHERE target_table = 'citation_resolution' AND rank_version = :rank_version
),
res_cand AS (                            -- the predicate goes on the CANDIDATE SET
  SELECT r.*, rr.role, rr.precedence_rank
  FROM citation_resolution r
  JOIN rank_res rr ON rr.method          = r.method
                  AND rr.method_version  = r.method_version
                  AND rr.reading_channel = r.reading_channel
  WHERE r.superseded_by IS NULL
    AND r.confidence_state IN ('measured', 'human')
),
suppressed AS (                          -- a veto names the reading it checked
  SELECT DISTINCT citing_document, page, target_kind, target_key, reading_channel
  FROM res_cand WHERE role = 'suppress' AND outcome = 'vetoed'
),
resolved AS (
  SELECT * FROM (
    SELECT rc.*, ROW_NUMBER() OVER (
             PARTITION BY rc.citing_document, rc.page, rc.target_kind, rc.target_key
             ORDER BY rc.precedence_rank) AS rn
    FROM res_cand rc
    WHERE rc.role = 'resolve' AND rc.outcome IN ('resolved', 'repaired')
      -- the veto filters the CANDIDATE SET, like every other term (0018 D7)
      AND NOT EXISTS (SELECT 1 FROM suppressed s
                       WHERE s.citing_document = rc.citing_document
                         AND s.page            = rc.page
                         AND s.target_kind     = rc.target_kind
                         AND s.target_key      = rc.target_key
                         AND s.reading_channel = rc.reading_channel)
  ) ranked
  WHERE ranked.rn = 1
),
citing_work AS (
  SELECT r.citing_document,
         COALESCE(dr.stb_decision_id, r.citing_document) AS citing_work_id
  FROM (SELECT DISTINCT citing_document FROM resolved) r
  LEFT JOIN decision_attachment da ON da.document_sha256 = r.citing_document
  LEFT JOIN decision_record     dr ON dr.decision_pk     = da.decision_pk
),
span AS (
  SELECT * FROM (
    SELECT j.citing_document, j.page, j.target_kind, j.target_key, j.value,
           ROW_NUMBER() OVER (
             PARTITION BY j.citing_document, j.page, j.target_kind, j.target_key
             ORDER BY am.precedence_rank) AS rn
    FROM citation_judgement j
    JOIN assertion_method am ON am.target_table    = 'citation_judgement'
                            AND am.method          = j.method
                            AND am.method_version  = j.method_version
                            AND am.reading_channel = j.reading_channel
                            AND am.rank_version    = :rank_version
    WHERE j.judgement = 'span_names_document' AND j.superseded_by IS NULL
      AND j.confidence_state IN ('measured', 'human')
  ) WHERE rn = 1
),
family AS (
  SELECT dr.stb_decision_id, dr.docket_id FROM decision_record dr
  UNION
  SELECT dr.stb_decision_id, ch.docket_id
    FROM decision_record dr JOIN docket ch ON ch.parent_docket_id = dr.docket_id
  UNION
  SELECT dr.stb_decision_id, pa.docket_id
    FROM decision_record dr JOIN docket me ON me.docket_id = dr.docket_id
                            JOIN docket pa ON pa.docket_id = me.parent_docket_id
)
SELECT DISTINCT cw.citing_work_id, rd.target_key
FROM resolved rd
-- ADR 0018 D2: the parent must be joined AND live, or a retraction changes nothing
JOIN citation c         ON (c.citing_document, c.page, c.target_kind, c.target_key)
                         = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
                       AND c.superseded_by IS NULL
                       AND c.confidence_state IN ('measured', 'human')
JOIN citing_work cw     ON cw.citing_document = rd.citing_document
JOIN citation_reading rg ON (rg.citing_document, rg.page, rg.target_kind, rg.target_key)
                          = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
                        AND rg.reading_channel = rd.reading_channel
                        AND rg.superseded_by IS NULL
LEFT JOIN span sp ON (sp.citing_document, sp.page, sp.target_kind, sp.target_key)
                   = (rd.citing_document, rd.page, rd.target_kind, rd.target_key)
-- inside the family, an edge projects ONLY on a live span judgement saying true;
-- absent judgement = suppress, which is the stated default
WHERE NOT (EXISTS (SELECT 1 FROM family f
                    WHERE f.stb_decision_id = cw.citing_work_id
                      AND f.docket_id       = rd.cited_docket_id)
           AND COALESCE(sp.value, 'false') <> 'true')
"""


def scratch_store(registry: Path, out: Path) -> sqlite3.Connection:
    """A migrated copy of the registry. The dockets and decisions are real; nothing else is."""
    if out.exists():
        for suffix in ("", "-wal", "-shm"):
            Path(str(out) + suffix).unlink(missing_ok=True)
    src = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
    dst = sqlite3.connect(out)
    src.backup(dst)
    src.close()
    dst.close()
    return db.connect(out)


def docket_ids(con: sqlite3.Connection) -> dict[str, int]:
    """The registry as the resolver sees it: normalised printed form -> docket_id."""
    return {
        ps.printed(p, s, sub, suf): did
        for did, p, s, sub, suf in con.execute(
            "SELECT docket_id, prefix, sequence, sub_sequence, suffix FROM docket"
        )
    }


def citing_documents(con: sqlite3.Connection, ids: set[str]) -> dict[str, str]:
    """decision id -> the bytes the benchmark read. One attachment per decision in this set;
    where a decision has several, the first by url is taken and the choice is reported."""
    out: dict[str, str] = {}
    extra = 0
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
        extra += len(rows) > 1
    if extra:
        print(f"  note: {extra} of {len(out)} decisions have several attachments; took the first")
    return out


def register(con: sqlite3.Connection, version: str, stamp: str, scores: dict[str, int]) -> None:
    """The methods declare themselves, and the figures land in the one home for a score.

    No row is seeded by the migration on purpose (ADR 0018 D1: ownership is fixed at insert
    time from the owning method's own declaration), so this is what a real pipeline does on
    its first run.
    """
    truth, found, resolved, projected, shown = (
        scores["truth"],
        scores["found"],
        scores["resolved"],
        scores["projected"],
        scores["shown"],
    )
    m = {}
    for key, target, cls, recall, precision, rule in (
        ("extraction", "citation", "docket", found / truth, None, None),
        ("resolution", "citation_resolution", "docket", resolved / truth, None, None),
        (
            "projection",
            "projection",
            "docket",
            projected / truth,
            projected / shown,
            PROJECTION_RULE,
        ),
    ):
        cur = con.execute(
            "INSERT INTO class_measurement (measured_target, class, extraction_method,"
            " extraction_method_version, resolution_method, resolution_method_version,"
            " reading_channel, projection_rule_version, benchmark_date, score_file,"
            " truth_count, found_count, shown_count, recall, precision, measured_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                target,
                cls,
                EXTRACTOR,
                version,
                None if key == "extraction" else RESOLVER,
                None if key == "extraction" else RESOLVER_VERSION,
                CHANNEL,
                rule,
                stamp[:10],
                "tools/rmi-ai-machine/projection_score.py",
                truth,
                found,
                shown if key == "projection" else None,
                recall,
                precision,
                stamp,
            ),
        )
        m[key] = cur.lastrowid
    # The span test carries the projection measurement, because that IS what it was measured
    # with: ADR 0017 D4's 98.0% is a property of the pair, extractor plus this rule.
    m["span"] = m["projection"]

    # `role` only where the projection reads one: the resolution family has a suppress
    # term, judgement and treatment rank and nothing else.
    for target_table, method, mversion, channel, role, rank, kind, form in (
        ("citation", EXTRACTOR, version, None, None, None, "stb", "docket"),
        ("citation_resolution", RESOLVER, RESOLVER_VERSION, CHANNEL, "resolve", 1, None, None),
        ("citation_judgement", SPAN_METHOD, SPAN_VERSION, CHANNEL, None, 1, None, None),
    ):
        con.execute(
            "INSERT INTO assertion_method (target_table, method, method_version,"
            " reading_channel, role, precedence_rank, target_kind, target_form, rank_version,"
            " declared_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (target_table, method, mversion, channel, role, rank, kind, form, RANK, stamp),
        )
    con.commit()
    globals()["MEASUREMENT"] = m


def load(
    con: sqlite3.Connection,
    run: Path,
    docs: dict[str, str],
    held: dict[str, int],
    version: str,
    stamp: str,
) -> int:
    """Every docket-shaped finding, through all four families. Returns the edge count."""
    m = globals()["MEASUREMENT"]
    loaded = 0
    # ADR 0018 D9 measured it: 5 documents of 20,992 hang under two stb_decision_ids. The
    # same bytes are ONE citing document, so the second decision's findings are the rows the
    # first already wrote, and loading them again would collide on the citation key. The
    # fold to the work is what turns one document back into two citing works, later.
    seen: set[str] = set()
    for path in sorted(run.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        did = doc["decision_id"]
        sha = docs.get(did)
        if sha is None or sha in seen:
            continue
        seen.add(sha)
        # a target may be printed several times on one page; the key holds one row, so the
        # quotes are joined exactly the way projection_score.py joins them
        per_page: dict[tuple[int, str], list[str]] = {}
        raw: dict[tuple[int, str], str] = {}
        for page in doc.get("pages", []):
            for fi in page.get("findings", []):
                if fi.get("kind") != "citation" or fi.get("target_kind") != "stb":
                    continue
                key = N(fi["target"])
                if not bs.DOCKET_KEY.match(key):
                    continue
                per_page.setdefault((page["page"], key), []).append(fi.get("quoted", ""))
                raw.setdefault((page["page"], key), fi["target"])

        pages_read = len(doc.get("pages", []))
        for (page, key), quotes in per_page.items():
            passage = " | ".join(quotes)
            # the key first: it is a registry row, not an assertion, so the extraction
            # assertion below can supersede without the identity moving
            con.execute(
                "INSERT INTO citation_key (citing_document, page, target_kind, target_key,"
                " key_version, first_seen_at) VALUES (?, ?, 'stb', ?, ?, ?)",
                (sha, page, key, "norm_target@2026-08-30", stamp),
            )
            con.execute(
                "INSERT INTO citation (citing_document, page, target_kind, target_key,"
                " asserted_from_document, method, method_version, asserted_at,"
                " confidence, confidence_state, measured_target, score_row_id)"
                " VALUES (?, ?, 'stb', ?, ?, ?, ?, ?, ?, 'measured', 'citation', ?)",
                (
                    sha,
                    page,
                    key,
                    sha,
                    EXTRACTOR,
                    version,
                    stamp,
                    EXTRACTION_CONFIDENCE,
                    m["extraction"],
                ),
            )
            con.execute(
                "INSERT INTO citation_reading (citing_document, page, target_kind, target_key,"
                " reading_channel, cited_raw, quoted_passage, source_location,"
                " asserted_from_document, method, method_version, asserted_at, confidence,"
                " confidence_state, measured_target, score_row_id)"
                " VALUES (?, ?, 'stb', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'measured', 'citation',"
                " ?)",
                (
                    sha,
                    page,
                    key,
                    CHANNEL,
                    raw[(page, key)],
                    passage,
                    json.dumps({"page": page}),
                    sha,
                    EXTRACTOR,
                    version,
                    stamp,
                    EXTRACTION_CONFIDENCE,
                    m["extraction"],
                ),
            )
            # ADR 0017 D2: the registry check is the FIRST RULE OF RESOLUTION, not a filter
            # inside the finder. A miss is stored unresolved and never projected - it is a
            # real edge and it goes to the review queue.
            docket_id = held.get(key)
            con.execute(
                "INSERT INTO citation_resolution (citing_document, page, target_kind,"
                " target_key, method, method_version, reading_channel, outcome,"
                " cited_docket_id, cited_decision_id, asserted_from_document, asserted_at,"
                " confidence, confidence_state, measured_target, score_row_id)"
                " VALUES (?, ?, 'stb', ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, 'measured',"
                " 'citation_resolution', ?)",
                (
                    sha,
                    page,
                    key,
                    RESOLVER,
                    RESOLVER_VERSION,
                    CHANNEL,
                    "resolved" if docket_id else "unresolved",
                    docket_id,
                    sha,
                    stamp,
                    RESOLUTION_CONFIDENCE,
                    m["resolution"],
                ),
            )
            # The span judgement is a STORED ASSERTION, never a predicate computed inside a
            # view (ADR 0017 D4), because it decides what every published edge IS.
            names = bool(ps.SPAN_NAMES_DOCUMENT.search(passage))
            con.execute(
                "INSERT INTO citation_judgement (citing_document, page, target_kind,"
                " target_key, judgement, value_domain, value, method, method_version,"
                " reading_channel, asserted_from_document, asserted_at, confidence,"
                " confidence_state, measured_target, score_row_id)"
                " VALUES (?, ?, 'stb', ?, 'span_names_document', 'boolean', ?, ?, ?, ?, ?,"
                " ?, ?, 'measured', 'projection', ?)",
                (
                    sha,
                    page,
                    key,
                    "true" if names else "false",
                    SPAN_METHOD,
                    SPAN_VERSION,
                    CHANNEL,
                    sha,
                    stamp,
                    PROJECTION_PRECISION,
                    m["span"],
                ),
            )
            loaded += 1
        # ADR 0018 D10: absence is not a measurement. The pass is recorded whether or not it
        # found anything, and out-of-class findings are COUNTED, never silently dropped.
        out_of_class = sum(
            1
            for page in doc.get("pages", [])
            for fi in page.get("findings", [])
            if fi.get("kind") == "citation"
            and fi.get("target_kind") == "stb"
            and not bs.DOCKET_KEY.match(N(fi["target"]))
        )
        con.execute(
            "INSERT INTO extraction_run (document_sha256, method, method_version,"
            " reading_channel, outcome, pages_read, targets_emitted, targets_out_of_class,"
            " ran_at) VALUES (?, ?, ?, ?, 'read', ?, ?, ?, ?)",
            (sha, EXTRACTOR, version, CHANNEL, pages_read, len(per_page), out_of_class, stamp),
        )
    con.commit()
    return loaded


def python_chain(run: Path, registry: Path) -> dict:
    """projection_score.py's chain, as numbers rather than as printed lines."""
    truth_doc, _ = bs.truth()
    run_doc, _, _ = bs.run_findings(run, None)

    def keep(d):
        return {k: {x for x in v if bs.DOCKET_KEY.match(x)} for k, v in d.items()}

    T, R = (
        keep(bs.collect(truth_doc, "citation", "stb")),
        keep(bs.collect(run_doc, "citation", "stb")),
    )
    con = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
    heldset, fam = ps.registry(con), ps.families(con, set(T) | set(R))
    con.close()
    quoted = ps.spans(run)

    def names(did, key):
        return bool(ps.SPAN_NAMES_DOCUMENT.search(quoted.get((did, key), "")))

    found = resolved = projected = 0
    shown_pairs = set()
    for did, keys in T.items():
        for k in keys:
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
    for did, keys in R.items():
        for k in keys - T.get(did, set()):
            if k in heldset and not (k in fam.get(did, set()) and not names(did, k)):
                shown_pairs.add((did, k))
    return {
        "truth": sum(map(len, T.values())),
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


def main(run: Path, registry: Path, store: Path) -> int:
    stamp = db.utcnow()
    py = python_chain(run, registry)
    print(f"run {run}  registry {registry}\n")
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
    version = json.loads(next(run.glob("*.json")).read_text(encoding="utf-8"))["prompt_version"]
    register(con, version, stamp, py)
    held = docket_ids(con)
    docs = citing_documents(con, {p.stem for p in run.glob("*.json")})
    print(f"  {len(docs)} of 60 decisions have fetched bytes to hang an edge on")
    rows = load(con, run, docs, held, version, stamp)
    print(f"  loaded {rows} (document, page, target) rows through four families\n")

    sql_pairs = {(w, k) for w, k in con.execute(PROJECTION, {"rank_version": RANK}).fetchall()}
    sql_true = {(d, k) for d, k in sql_pairs if k in py["T"].get(d, set())}
    print("SQL CHAIN (migration 0014, the projection computed in the store):")
    print(f"  PROJECTED {len(sql_true):3d} {pct(len(sql_true), py['truth'])}")
    print(
        f"  precision  {len(sql_true)} of {len(sql_pairs)} shown ="
        f" {pct(len(sql_true), len(sql_pairs))}\n"
    )

    q2 = con.execute(
        Path("docs/citator-query-2.sql").read_text(encoding="utf-8"),
        {"rank_version": RANK, "target_work": "52526"},
    ).fetchall()
    # Empty for THREE independent reasons, and crediting only the first overstates what this
    # check proves: no treatment row exists (ADR 0017 D7), no assertion_method row ranks
    # citation_treatment, and the query keys on cited_decision_id — the work grain, which
    # ADR 0018 D9 measures as the rare one (decision_number is populated for 0 of 23,713
    # rows). What it does prove is that the shape parses, plans and joins.
    print(
        f"  docs/citator-query-2.sql executes and returns {len(q2)} rows"
        "  (three reasons it is empty; see its header)"
    )

    # Only decisions whose bytes are in the store can carry an edge; the Python chain scores
    # every decision in the sheet. Compare on the intersection, and say so.
    reachable = {(d, k) for d, k in py["pairs"] if d in docs}
    ok = sql_pairs == reachable
    missing, extra = sorted(reachable - sql_pairs)[:5], sorted(sql_pairs - reachable)[:5]
    print(
        f"\n  python projects {len(reachable)} pairs on documents the store holds;"
        f" SQL projects {len(sql_pairs)}"
    )
    print(f"  AGREEMENT: {'yes' if ok else 'NO'}")
    if not ok:
        print(f"    in python not SQL: {missing}")
        print(f"    in SQL not python: {extra}")
    con.close()
    return 0 if ok else 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)

    def opt(name, default):
        return Path(argv[argv.index(name) + 1]) if name in argv else Path(default)

    sys.exit(
        main(
            Path(args[0]),
            opt("--registry", "data/prod-copy.sqlite"),
            opt("--store", "data/citation-dryrun.sqlite"),
        )
    )
