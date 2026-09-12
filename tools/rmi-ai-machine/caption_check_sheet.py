"""Forty of the review queue's items where both models say the record is wrong.

Two model families, run over all 1,476 `citation_exposed` items, independently agree that 981
of them are not citations at all but the deciding decision's own caption — a bare docket
number naming no document (`docs/extraction-benchmark.md`). 649 of those are the citing
decision's own docket and 964 have no served date anywhere near them.

**That agreement is not two independent witnesses.** Both models were given the same prompt,
and that prompt tells them a bare number naming no document is a proceeding. The agreement
may be the prompt talking to itself. What is not model-dependent is the passage on the page
and the code path that classified it, and a person reading forty passages settles it.

THE QUESTION IS BINARY, so the page is its own and not the work sheet's: that card asks which
document a citation names, and here the point is whether there is a citation at all.

    python tools/rmi-ai-machine/caption_check_sheet.py \
        --runs data/benchmark/runs-queue/queue-gemma4-e4b@mac \
               data/benchmark/runs-queue/queue-qwen3-14b@mac \
        --store data/rehearse-wrap2.sqlite --size 40
"""

import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import review_queue_panel as rp  # noqa: E402

from docketyard.citator import resolve, review, walk  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SEED = 20260912  # named, so the same forty come back and the measurement can be checked

PAGE = """<title>Caption or citation?</title>
<style>
:root{--paper:#faf8f5;--card:#fff;--ink:#1b1a17;--muted:#6d675f;--rule:#e0dad1;
--accent:#24427a;--yes:#2f6b3f;--no:#a3391f;--hold:#7d5f10;--mark:#fdf0b8}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--paper:#16161a;--card:#1e1e23;
--ink:#eceae6;--muted:#a7a099;--rule:#33323a;--accent:#93b2e8;--yes:#7fc08d;--no:#e88f74;
--hold:#d8b45c;--mark:#4a3f14}}
body{margin:0;background:var(--paper);color:var(--ink);
font:16px/1.5 "Source Sans 3",system-ui,sans-serif}
.wrap{max-width:52em;margin:0 auto;padding-block:2em;padding-left:16px;padding-right:16px}
h1{font-size:1.3rem;margin:0 0 .2em}
.sub{color:var(--muted);margin:0 0 1.5em;font-size:.95rem}
.card{background:var(--card);border:1px solid var(--rule);border-radius:8px;padding:1.3em;
margin-bottom:1em}
.key{font:600 1.15rem "IBM Plex Mono",ui-monospace,monospace;color:var(--accent)}
.meta{color:var(--muted);font-size:.9rem;margin:.4em 0 1em}
.line{background:var(--paper);border-left:3px solid var(--rule);padding:.7em .9em;
font:.95rem/1.6 "IBM Plex Mono",ui-monospace,monospace;white-space:pre-wrap;
overflow-wrap:anywhere;margin:.8em 0}
mark{background:var(--mark);color:inherit}
.says{font-size:.9rem;color:var(--muted);margin:.6em 0 1em}
.btns{display:flex;gap:.5em;flex-wrap:wrap}
button{font:inherit;padding:.5em 1em;border-radius:6px;border:1px solid var(--rule);
background:var(--card);color:var(--ink);cursor:pointer}
button.on[data-v=caption]{background:var(--yes);color:#fff;border-color:var(--yes)}
button.on[data-v=citation]{background:var(--no);color:#fff;border-color:var(--no)}
button.on[data-v=unclear]{background:var(--hold);color:#fff;border-color:var(--hold)}
kbd{font-size:.75em;opacity:.7;margin-left:.4em}
.tally{position:sticky;bottom:0;background:var(--card);border-top:1px solid var(--rule);
padding:1em;margin-top:1.5em}
textarea{width:100%;height:7em;font:.85rem "IBM Plex Mono",ui-monospace,monospace;
background:var(--paper);color:var(--ink);border:1px solid var(--rule);border-radius:6px;
padding:.6em;box-sizing:border-box}
</style>
<div class=wrap>
<h1>Caption or citation?</h1>
<p class=sub>The record classified each of these as a <strong>citation</strong> and put it in
the review queue. Two models say each is just the deciding decision's own caption. Read the
passage and say which is right. <kbd>y</kbd> caption &middot; <kbd>n</kbd> real citation
&middot; <kbd>u</kbd> unclear.</p>
<div id=rows></div>
<div class=tally>
<div id=t></div>
<textarea id=out readonly></textarea>
</div>
</div>
<script>
const ROWS = /*DATA*/[];
let V = {};
try { V = JSON.parse(localStorage.getItem("dy-caption-verdicts") || "{}"); } catch(e) { V = {}; }
const esc = s => (s||"").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",
  '"':"&quot;"}[c]));
function draw(){
  document.getElementById("rows").innerHTML = ROWS.map((r,i) => {
    const v = V[r.id] || "";
    const line = esc(r.passage).replace(new RegExp(esc(r.printed)
      .replace(/[.*+?^${}()|[\\]\\\\]/g,"\\\\$&"),"g"), m => "<mark>"+m+"</mark>");
    return `<div class=card>
      <div><span class=key>${esc(r.printed)}</span></div>
      <div class=meta>in decision ${esc(r.citing)}${r.own
          ? " &mdash; <strong>that decision's own docket</strong>" : ""}
        &middot; page ${r.page}${r.served
          ? " &middot; date read: " + esc(r.served)
          : " &middot; no served date found"}</div>
      <div class=line>${line}</div>
      <div class=says>both models say: not a citation, just the proceeding named</div>
      <div class=btns>
        <button data-i="${i}" data-v="caption" class="${v==="caption"?"on":""}"
          >Caption<kbd>y</kbd></button>
        <button data-i="${i}" data-v="citation" class="${v==="citation"?"on":""}"
          >Real citation<kbd>n</kbd></button>
        <button data-i="${i}" data-v="unclear" class="${v==="unclear"?"on":""}"
          >Unclear<kbd>u</kbd></button>
      </div></div>`;
  }).join("");
  document.querySelectorAll("#rows button").forEach(b =>
    b.addEventListener("click", () => mark(+b.dataset.i, b.dataset.v)));
  tally();
}
function mark(i, v){
  const r = ROWS[i];
  V[r.id] = V[r.id] === v ? undefined : v;
  if(!V[r.id]) delete V[r.id];
  try { localStorage.setItem("dy-caption-verdicts", JSON.stringify(V)); } catch(e){}
  draw();
}
function tally(){
  const n = Object.keys(V).length;
  const c = Object.values(V).filter(x => x === "caption").length;
  const t = Object.values(V).filter(x => x === "citation").length;
  document.getElementById("t").textContent =
    `${n} of ${ROWS.length} judged — ${c} caption, ${t} real citation, ${n-c-t} unclear`;
  document.getElementById("out").value = ROWS.filter(r => V[r.id])
    .map(r => [r.citing, r.key, r.page, V[r.id]].join("\\t")).join("\\n");
}
document.addEventListener("keydown", e => {
  const k = {y:"caption", n:"citation", u:"unclear"}[e.key];
  if(!k) return;
  const first = ROWS.findIndex(r => !V[r.id]);
  if(first >= 0) mark(first, k);
});
draw();
</script>
"""


def build(runs: list[Path], store: Path, size: int) -> list[dict]:
    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    own = walk.own_by_document(con)
    loaded = [rp.load_run(r) for r in runs]
    shared = set.intersection(*(set(x) for x in loaded))
    carriers = rp.carriers(con)
    items = {
        (i["citing_document"], i["page"], i["target_kind"], i["target_key"]): i
        for i in review.pending(con, "citation_exposed", limit=None)
    }
    rows = []
    for k in sorted(shared):
        kinds = {(x[k]["answer"] or {}).get("names") for x in loaded}
        if kinds != {"proceeding"}:
            continue
        item = items.get(k)
        if item is None:
            continue
        printed = item["cited_raw"]
        stripped = resolve._stripped(k[3])
        mine = own.get(k[0], set())
        rows.append(
            {
                "id": "/".join(str(x) for x in k),
                "citing": ", ".join(carriers.get(k[0], [])) or "?",
                "key": k[3],
                "page": k[1],
                "printed": printed,
                "passage": item["quoted_passage"] or "",
                "own": k[3] in mine or bool(stripped and stripped in mine),
                "served": resolve.served_date(resolve._anchored(item["quoted_passage"], printed))
                or "",
            }
        )
    con.close()
    if size and len(rows) > size:
        rows = random.Random(SEED).sample(rows, size)
    rows.sort(key=lambda r: (r["citing"], r["key"]))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, nargs="+", required=True)
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "data/caption-check.html")
    ap.add_argument("--size", type=int, default=40)
    args = ap.parse_args()
    rows = build(args.runs, args.store, args.size)
    if not rows:
        raise SystemExit("no agreed-proceeding item could be drawn")
    data = json.dumps(rows, ensure_ascii=False)
    args.out.write_text(PAGE.replace("/*DATA*/[]", data), encoding="utf-8")
    own = sum(1 for r in rows if r["own"])
    nodate = sum(1 for r in rows if not r["served"])
    print(f"{len(rows)} to judge -> {args.out}")
    print(f"  {own} are the citing decision's own docket; {nodate} have no served date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
