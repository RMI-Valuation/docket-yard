"""The operator's check of the exposed-class sample, as one self-contained page.

ADR 0017 sends an EXPOSED citation — a bare docket number of four digits or fewer whose
last-digit-stripped reading is also a held docket — to a person, because a footnote marker
fused onto the number (`AB 124` + footnote `2` read as `AB 1242`) resolves confidently to the
wrong proceeding. Measured 2026-09-11 on the 2026-09-04 rehearsal load: 1,360 of its 1,946
exposed keys cite the docket their own document is filed in. This page puts a random 50 of
those in front of the operator (`docs/research/benchmark/exposed-sample/`), one card each:
the docket the extractor resolved, the passage with the printed form marked, the page's text
and the scan one click away, and three answers — the docket it names, a fused footnote, or
cannot tell. Judgements stay in the browser (localStorage, under `--key`); **Copy findings**
hands back one TSV block the session writes to `labels.csv`.

    python tools/exposed_check_page.py --sample docs/research/benchmark/exposed-sample/sample.json \\
        --out data/exposed-check.html
"""

# ruff: noqa: E501 — an HTML/JS template reads worse wrapped (party_types_check_page precedent)
import argparse
import html
import json
from pathlib import Path

SITE = "https://docketyard.org"


def stripped(target_key: str) -> tuple[str, str] | None:
    """`AB 1242` -> (`AB 124`, `2`): the shorter docket and the digit a fused footnote would
    be. None where the key is not a bare prefix and number."""
    parts = target_key.split()
    if len(parts) != 2 or not parts[1].isdigit() or len(parts[1]) < 2:
        return None
    return f"{parts[0]} {parts[1][:-1]}", parts[1][-1]


def marked(passage: str, printed: str) -> str:
    """The passage, escaped, with the first occurrence of the printed form marked."""
    at = passage.find(printed) if printed else -1
    if at < 0:
        return html.escape(passage)
    end = at + len(printed)
    return (
        html.escape(passage[:at])
        + "<mark>"
        + html.escape(passage[at:end])
        + "</mark>"
        + html.escape(passage[end:])
    )


def card(n: int, s: dict) -> str:
    key = f"{s['citing_document']}/{s['page']}/{s['target_key']}"
    short = stripped(s["target_key"])
    fused = (
        f"fused — {html.escape(short[0])} + footnote {html.escape(short[1])}"
        if short
        else "fused — a footnote on a shorter number"
    )
    base = f"{SITE}/{s['record_kind']}/{html.escape(str(s['record_id']))}"
    buttons = "".join(
        f"<button data-k='{html.escape(key)}' data-v='{v}'>{label}</button>"
        for v, label in (
            ("right", f"right — {html.escape(s['target_key'])}"),
            ("fused", fused),
            ("unsure", "can't tell"),
        )
    )
    return (
        f"<div class='card' data-k='{html.escape(key)}' data-n='{n}'>"
        f"<h2>{n}. {html.escape(s['target_key'])}"
        f" <span class='ev'>printed “{html.escape(s['cited_raw'] or '')}”</span></h2>"
        f"<p class='passage'>{marked(s['quoted_passage'] or '', s['cited_raw'] or '')}</p>"
        f"<p class='ev'>{html.escape(s['record_kind'])} {html.escape(str(s['record_id']))},"
        f" page {s['page']}, filed in {html.escape(s['record_docket'] or '—')}"
        f" · <a href='{base}/text#p{s['page']}' target='_blank' rel='noopener'>the page's text</a>"
        f" · <a href='{base}#file' target='_blank' rel='noopener'>the scan</a></p>"
        f"<div class='btns'>{buttons}</div>"
        f"<input class='note' data-k='{html.escape(key)}' placeholder='note (optional)'>"
        "</div>"
    )


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Exposed Citation Check</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;700&display=swap">
<style>
:root { --bg: #FAFAF7; --ink: #22261F; --muted: #6A7069; --line: #DEDFD7;
  --accent: #2E6E4E; --accent-ink: #FDFDFB; --mark: #F3E3A0; --field: #FFFFFF; --focus: #38609C; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #17191B; --ink: #E7E5DE; --muted: #9BA19A; --line: #34383B;
  --accent: #4E9E76; --accent-ink: #10130F; --mark: #5B4E1E; --field: #1F2224; --focus: #7FA3D8; } }
:root[data-theme="dark"] { --bg: #17191B; --ink: #E7E5DE; --muted: #9BA19A; --line: #34383B;
  --accent: #4E9E76; --accent-ink: #10130F; --mark: #5B4E1E; --field: #1F2224; --focus: #7FA3D8; }
body { font: 15px/1.5 "Public Sans", system-ui, sans-serif; max-width: 52rem; margin: 0 auto;
  padding: 0 1rem 4rem; color: var(--ink); background: var(--bg) }
[hidden] { display: none !important }
.card { border-bottom: 1px solid var(--line); padding: .8rem 0 }
.card h2 { font-size: 1.05rem; font-weight: 600; margin: 0 0 .2rem }
.passage { font-family: ui-serif, Georgia, serif; margin: .2rem 0; overflow-wrap: anywhere }
mark { background: var(--mark); color: inherit; padding: 0 .1rem }
.ev { color: var(--muted); font-size: .85rem; font-weight: 400; margin: .1rem 0 }
.ev a { color: inherit }
.btns { display: flex; flex-wrap: wrap; gap: .3rem; margin-top: .3rem }
.btns button { padding: .25rem .6rem; border: 1px solid var(--line); color: var(--ink);
  background: var(--field); border-radius: 4px; cursor: pointer; font: inherit }
.btns button.picked { background: var(--accent); color: var(--accent-ink); border-color: var(--accent) }
.btns button:focus-visible, #copy:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px }
.note { width: 100%; margin-top: .35rem; border: 1px solid var(--line); padding: .3rem;
  background: var(--field); color: var(--ink); font: inherit; border-radius: 4px; box-sizing: border-box }
#bar { position: sticky; top: 0; background: var(--bg); padding: .8rem 0 .4rem; border-bottom: 2px solid var(--ink) }
#prog { font-variant-numeric: tabular-nums }
#copy { padding: .4rem .8rem; font: inherit; border: 1px solid var(--ink); background: var(--field);
  color: var(--ink); border-radius: 4px; cursor: pointer }
</style></head><body>
<div id="bar"><b>Exposed citations — check __COUNT__.</b>
<span id="prog"></span>
<button id="copy">Copy findings</button>
<label><input type="checkbox" id="only-undone"> show unjudged only</label>
<p class="ev">Each card is a citation the extractor read as the docket shown, in a decision filed in
that same docket. The question is only this: is the number the docket it names, or a shorter
docket number with a footnote marker run onto its end? The marked text is what was printed.
Where the passage cannot settle it, the page's text and the scan are one click away; “can't
tell” is an answer, not a failure. Judgements stay in this browser until copied.</p></div>
__CARDS__
<script>
const KEY = __KEY__;
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
function paint() {
  let done = 0;
  document.querySelectorAll(".card").forEach(c => {
    const k = c.dataset.k, st = state[k] || {};
    c.querySelectorAll("button[data-v]").forEach(b => b.classList.toggle("picked", st.v === b.dataset.v));
    if (st.v) done++;
    c.hidden = document.getElementById("only-undone").checked && !!st.v;
    const n = c.querySelector(".note"); if (st.note !== undefined && n.value !== st.note) n.value = st.note;
  });
  document.getElementById("prog").textContent = ` ${done} / ${document.querySelectorAll(".card").length} judged. `;
}
document.addEventListener("click", e => {
  const b = e.target.closest("button[data-v]");
  if (b) { const k = b.dataset.k; state[k] = state[k] || {};
    state[k].v = (state[k].v === b.dataset.v) ? undefined : b.dataset.v; save(); paint(); }
});
document.addEventListener("input", e => {
  if (e.target.classList.contains("note")) { const k = e.target.dataset.k;
    state[k] = state[k] || {}; state[k].note = e.target.value; save(); }
  if (e.target.id === "only-undone") paint();
});
document.getElementById("copy").addEventListener("click", () => {
  const out = [];
  document.querySelectorAll(".card").forEach(c => {
    const k = c.dataset.k, st = state[k] || {};
    if (st.v) { const [doc, page, ...t] = k.split("/");
      out.push([c.dataset.n, doc, page, t.join("/"), st.v, (st.note || "").replaceAll("\\t", " ")].join("\\t")); }
  });
  navigator.clipboard.writeText("n\\tciting_document\\tpage\\ttarget_key\\tverdict\\tnote\\n" + out.join("\\n"));
});
paint();
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--key", default="exposed-check-2026-09-11", help="localStorage key")
    args = ap.parse_args()
    sample = json.loads(args.sample.read_text(encoding="utf-8"))["sample"]
    cards = "".join(card(n, s) for n, s in enumerate(sample, 1))
    doc = (
        PAGE.replace("__COUNT__", str(len(sample)))
        .replace("__KEY__", json.dumps(args.key))
        .replace("__CARDS__", cards)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8", newline="\n")
    print(f"{len(sample)} cards -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
