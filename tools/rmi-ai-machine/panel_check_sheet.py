"""A slice of what the panel would clear, drawn for the operator to judge.

`review_queue_panel.py --panel --clears` says how many of the 1,476 exposed keys two models
settle between them. **A rate is not a precision.** ADR 0017 D3 stamps a row with a MEASURED
figure, and the only way to measure this one is to judge a sample of the keys the panel would
have published without a person. This draws that sample and builds the page it is judged on.

WHAT THE READER IS ASKED IS THE EXPOSED QUEUE'S OWN QUESTION. The key is held because a fused
footnote marker could explain it: the page printed `AB 878` and the record holds both `AB 878`
and `AB 87`. So the card names the docket the panel CHOSE, and says when that is the shorter
one, because agreeing on the document while disagreeing about which proceeding it sits in is
the failure this queue exists to catch.

THE PAGE IS THE WORK SHEET'S. `work_check_page.html` already keeps its place, saves as it
goes and hands back TSV; a second template would be a second thing to maintain and a second
set of keys for the operator to learn. The fields are mapped onto it rather than restated.

    python tools/rmi-ai-machine/review_queue_panel.py --panel \
        data/benchmark/runs-queue/queue-gemma4-e4b@mac \
        data/benchmark/runs-queue/queue-qwen3-14b@mac --clears data/panel-clears.json
    python tools/rmi-ai-machine/panel_check_sheet.py --clears data/panel-clears.json \
        --store data/rehearse-wrap2.sqlite --out data/panel-check.html
"""

import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from work_check_sheet import (  # noqa: E402 — one page, one set of keys
    PAGE_FIELDS,
    TEMPLATE,
    captions,
    decisions,
    links,
    pdf_urls,
)

from docketyard.citator import resolve, review  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
# The sample is drawn with a NAMED seed so the same slice comes back. A sample nobody can
# redraw is a sample whose measurement cannot be checked (the party-type sheet, 2026-09-10).
SEED = 20260911


def carriers(con) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for sha, did in con.execute(
        "SELECT a.document_sha256, r.stb_decision_id FROM decision_attachment a"
        " JOIN decision_record r ON r.decision_pk = a.decision_pk"
    ):
        out.setdefault(sha, []).append(str(did))
    return {sha: sorted(set(v)) for sha, v in out.items()}


def build(clears: Path, store: Path, size: int) -> list[dict]:
    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    payload = json.loads(clears.read_text(encoding="utf-8"))
    would = payload["would_clear"]
    # The queue row carries the passage and what the page printed; the panel's file carries
    # only its answer. They are joined on the queue's own four columns (`review._KEY_COLS`).
    items = {
        (i["citing_document"], i["page"], i["target_kind"], i["target_key"]): i
        for i in review.pending(con, payload.get("queue", "citation_exposed"), limit=None)
    }
    known, urls, caps, who = decisions(con), pdf_urls(con), captions(con), carriers(con)

    rows = []
    for c in would:
        k = (c["citing_document"], c["page"], c["target_kind"], c["target_key"])
        item = items.get(k)
        if item is None:
            continue  # the queue moved under the run; it is not a row to judge
        named = known.get(str(c["decision"]))
        if named is None:
            # the panel named an id the record does not hold. Not a row for this sheet: it is
            # a stray, and a stray never clears (`review_queue_panel.panel`).
            continue
        chose, printed = c["docket"], item["cited_raw"]
        shorter = chose != c["target_key"]
        caption = caps.get(chose, "")
        note = (
            f"the page printed “{printed}”; read here as {chose}, the last digit a footnote marker"
            if shorter
            else f"printed “{printed}”"
        )
        citing = who.get(c["citing_document"], [])
        segment = resolve._anchored(item["quoted_passage"], printed) or ""
        rows.append(
            {
                "citing_decision": ", ".join(citing) or "?",
                "citing_url": urls.get(citing[0], "") if citing else "",
                "citing_docket": "",
                "target_key": chose,
                "target_caption": f"{caption} — {note}" if caption else note,
                "served_date_read": resolve.served_date(segment) or "",
                "drafted_decision": str(c["decision"]),
                "drafted_service_date": named["service_date"],
                "drafted_type": named["decision_type"] or "decision",
                "drafted_body": named["deciding_body"] or "",
                "drafted_docket": ", ".join(sorted(set(named["dockets"].values()))),
                "drafted_url": urls.get(str(c["decision"]), ""),
                "why_no_document": "",
                "pages": str(c["page"]),
                "anchored_segment": segment,
                "quoted_line": item["quoted_passage"],
            }
        )
    con.close()
    rows.sort(key=lambda r: (r["citing_decision"], r["target_key"]))
    if size and len(rows) > size:
        rows = sorted(
            random.Random(SEED).sample(rows, size),
            key=lambda r: (r["citing_decision"], r["target_key"]),
        )
    return rows


def render(rows: list[dict], out: Path) -> Path:
    page = TEMPLATE.read_text(encoding="utf-8")
    data = json.dumps([{k: r[k] for k in PAGE_FIELDS} | links(r) for r in rows], ensure_ascii=False)
    if "/*DATA*/[]" not in page:  # pragma: no cover — the template is ours
        raise SystemExit(f"{TEMPLATE} has no /*DATA*/[] placeholder to fill")
    out.write_text(page.replace("/*DATA*/[]", data), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clears", type=Path, required=True, help="the panel's --clears file")
    ap.add_argument("--store", type=Path, required=True, help="the store the panel ran against")
    ap.add_argument("--out", type=Path, default=ROOT / "data/panel-check.html")
    ap.add_argument("--size", type=int, default=150, help="0 for every cleared key")
    args = ap.parse_args()
    rows = build(args.clears, args.store, args.size)
    if not rows:
        raise SystemExit("no cleared key could be drawn: check the --clears file and the store")
    render(rows, args.out)
    shorter = sum(1 for r in rows if "footnote marker" in r["target_caption"])
    print(f"{len(rows)} keys to judge -> {args.out}")
    print(f"  {shorter} of them read the printed number as the SHORTER docket")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
