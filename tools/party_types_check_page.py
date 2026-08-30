"""The operator's check queue for the party-type sample, as one self-contained page.

Reads `labels.csv` (and `wikidata.csv` if present) from docs/research/party-types and
renders one card per party: the name as filed, the dockets it filed in, the draft type
and its evidence, and a row of type buttons. Judgements stay in the browser
(localStorage); **Copy findings** hands back one block — party_id, chosen type, note —
that the session applies to the sheet. The pattern is the labels queue's
(`rmi-ai-machine/labels_check_page.py`), smaller.

    python tools/party_types_check_page.py --dir docs/research/party-types \\
        --out data/party-types-check.html
"""

# ruff: noqa: E501 — an HTML/JS template reads worse wrapped (labels_check_page precedent)
import argparse
import csv
import html
from pathlib import Path

TYPES = [
    "railroad",
    "company",
    "government",
    "association",
    "individual",
    "law-firm",
    "elected-official",
    "span-artefact",
    "unknown",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    rows = list(csv.DictReader((args.dir / "labels.csv").open(encoding="utf-8")))
    wd = {}
    if (args.dir / "wikidata.csv").exists():
        wd = {
            r["party_id"]: r
            for r in csv.DictReader((args.dir / "wikidata.csv").open(encoding="utf-8"))
            if r.get("qid")
        }
    cards = []
    for r in rows:
        pid = r["party_id"]
        w = wd.get(pid)
        wd_line = ""
        if w:
            wd_line = (
                f"<p class='ev'>Wikidata: <a href='https://www.wikidata.org/wiki/{html.escape(w['qid'])}'"
                f" target='_blank' rel='noopener'>{html.escape(w['qid'])}</a>"
                f" — {html.escape(w['wd_label'])}"
                f"{' · ' + html.escape(w['wd_description']) if w['wd_description'] else ''}"
                f"{' · says <b>' + html.escape(w['mapped_type']) + '</b>' if w['mapped_type'] else ''}"
                f"{' · mark ' + html.escape(w['mark']) if w['mark'] else ''}</p>"
            )
        btns = "".join(
            f"<button data-pid='{pid}' data-type='{t}'"
            f"{' class=draft' if t == r['draft_type'] else ''}>{t}</button>"
            for t in TYPES
        )
        cards.append(
            f"<div class='card' id='p{pid}' data-pid='{pid}' data-draft='{html.escape(r['draft_type'])}'>"
            f"<h2>{html.escape(r['as_filed'])}</h2>"
            f"<p class='ev'>drafted <b>{html.escape(r['draft_type'])}</b>"
            f" ({html.escape(r['evidence'])}) · files in {html.escape(r['dockets'] or '—')}"
            f" · <a href='https://docketyard.org/p/{pid}' target='_blank' rel='noopener'>/p/{pid}</a></p>"
            f"{wd_line}<div class='btns'>{btns}</div>"
            f"<input class='note' data-pid='{pid}' placeholder='note (optional)'>"
            "</div>"
        )
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Party types — the operator's check</title>
<style>
body {{ font: 15px/1.5 system-ui, sans-serif; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; color: #222 }}
.card {{ border-bottom: 1px solid #ddd; padding: .8rem 0 }}
.card h2 {{ font-size: 1.05rem; margin: 0 0 .2rem }}
.ev {{ color: #555; font-size: .85rem; margin: .1rem 0 }}
.btns button {{ margin: .15rem .3rem .15rem 0; padding: .25rem .6rem; border: 1px solid #bbb;
  background: #fff; border-radius: 4px; cursor: pointer }}
.btns button.draft {{ border-color: #46a; border-width: 2px }}
.btns button.picked {{ background: #2a7; color: #fff; border-color: #2a7 }}
.note {{ width: 100%; margin-top: .3rem; border: 1px solid #ddd; padding: .25rem }}
#bar {{ position: sticky; top: 0; background: #fff; padding: .6rem 0; border-bottom: 2px solid #222 }}
#copy {{ padding: .4rem .8rem }}
</style></head><body>
<div id="bar"><b>Party types — check {len(cards)} parties.</b>
<span id="prog"></span>
<button id="copy">Copy findings</button>
<label><input type="checkbox" id="only-undone"> show unjudged only</label>
<p class="ev">A boxed button is the machine's draft; click the correct type (clicking the draft
confirms it). Judgements stay in this browser until copied.</p></div>
{"".join(cards)}
<script>
const KEY = "party-types-check-2026-08-30";
let state = {{}};
try {{ state = JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (e) {{}}
function save() {{ try {{ localStorage.setItem(KEY, JSON.stringify(state)); }} catch (e) {{}} }}
function paint() {{
  let done = 0;
  document.querySelectorAll(".card").forEach(c => {{
    const pid = c.dataset.pid, st = state[pid] || {{}};
    c.querySelectorAll("button[data-type]").forEach(b =>
      b.classList.toggle("picked", st.type === b.dataset.type));
    if (st.type) done++;
    c.style.display = (document.getElementById("only-undone").checked && st.type) ? "none" : "";
    const n = c.querySelector(".note"); if (st.note !== undefined && n.value !== st.note) n.value = st.note;
  }});
  document.getElementById("prog").textContent = ` ${{done}} / ${{document.querySelectorAll(".card").length}} judged. `;
}}
document.addEventListener("click", e => {{
  const b = e.target.closest("button[data-type]");
  if (b) {{ const pid = b.dataset.pid; state[pid] = state[pid] || {{}};
    state[pid].type = (state[pid].type === b.dataset.type) ? undefined : b.dataset.type;
    save(); paint(); }}
}});
document.addEventListener("input", e => {{
  if (e.target.classList.contains("note")) {{ const pid = e.target.dataset.pid;
    state[pid] = state[pid] || {{}}; state[pid].note = e.target.value; save(); }}
  if (e.target.id === "only-undone") paint();
}});
document.getElementById("copy").addEventListener("click", () => {{
  const out = [];
  document.querySelectorAll(".card").forEach(c => {{
    const pid = c.dataset.pid, st = state[pid] || {{}};
    if (st.type) out.push([pid, st.type, (st.note || "").replaceAll("\\t", " ")].join("\\t"));
  }});
  navigator.clipboard.writeText("party_id\\ttype\\tnote\\n" + out.join("\\n"));
}});
paint();
</script></body></html>"""
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8", newline="\n")
    print(f"{len(cards)} cards -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
