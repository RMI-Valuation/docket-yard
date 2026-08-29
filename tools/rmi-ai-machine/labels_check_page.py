"""Build the extraction-labels check queue (docs/research/benchmark).

The unit of review is a decision, not a row: its text on one side with every labelled
passage highlighted in place, its labels on the other. Highlighting is the point — for OCR
the check is whether what is written is right, but a label set is also judged on what is
**missing**, and an unhighlighted citation in the running text is the only way to see one.

Four recurring judgement calls (a decision's own caption docket, a repeated short-form
reference, a citation to a court, and "effective on its service date" as a deadline)
account for about 130 of the 977 rows, so the queue asks those once, up front, rather than
row by row.

    python tools/rmi-ai-machine/labels_check_page.py

Reads docs/research/benchmark/labels.csv and the per-decision text in data/benchmark/text.
"""

# ruff: noqa: E501 — an HTML document lives in this file; its CSS and markup keep their own
# line lengths, and reflowing them to the code width would only make them harder to read.

import csv
import html
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path("e:/DevProjects/docket-yard")
OUT = Path(
    "C:/Users/CAMERO~1/AppData/Local/Temp/claude/e--DevProjects-docket-yard/"
    "96fc75d7-5d5a-4c59-a069-310fcbb7766b/scratchpad/labels-check.html"
)

CONVENTIONS = [
    {
        "id": "self",
        "q": "Is a decision's own caption docket a citation?",
        "detail": "The drafter labelled the docket numbers in a decision's own caption "
        "(noted <em>self</em>). They are the proceeding the decision is in, not a reference "
        "to another one.",
        "count": "about 35 rows noted <em>self</em>",
    },
    {
        "id": "shortform",
        "q": "Is a repeated short-form reference its own citation?",
        "detail": "Where a decision cites a docket in full and then refers to it again in "
        "short form, the drafter labelled each occurrence (noted <em>short form</em>). The "
        "alternative is to label the first full citation only.",
        "count": "54 rows noted <em>short form</em>",
    },
    {
        "id": "court",
        "q": "Are citations to court decisions in scope?",
        "detail": "The drafter labelled references to court opinions (noted <em>court</em>). "
        "The citator is an STB and ICC citator; a court citation may belong to a later "
        "capability, or may be worth capturing now as negative treatment.",
        "count": "about 62 rows noted <em>court</em>",
    },
    {
        "id": "effective",
        "q": "Is “effective on its service date” a deadline?",
        "detail": "The drafter labelled ordering-paragraph sentences that make a decision "
        "effective on the day it is served as deadlines with a blank target, since no date "
        "is quoted. The alternative is that a deadline needs a date on the page.",
        "count": "45 deadline rows carry no target",
    },
]


PAGE_MARK = re.compile(r"(?m)^===== page \d+ =====$")


def stripped(text: str) -> tuple[str, list[int]]:
    """The text with every space removed, and a map back to the original offsets.

    Locating a quoted passage cannot depend on spacing at all: the PDF wraps lines
    wherever it likes, so extraction turns a wrap inside a caption into a space — the text
    holds "Inc.— Discontinuance" where the label, read off the page, quotes
    "Inc.—Discontinuance" (diagnosed 2026-08-29). Dropping whitespace on both sides
    locates the passage whatever the wrap did to it.
    """
    skip = set()
    for m in PAGE_MARK.finditer(text):  # our own page markers must not break a quote
        skip.update(range(m.start(), m.end()))
    out, idx = [], []
    for i, ch in enumerate(text):
        if not ch.isspace() and i not in skip:
            out.append(ch)
            idx.append(i)
    return "".join(out), idx


def mark_up(text: str, rows: list[dict]) -> tuple[str, list[bool]]:
    """The decision's text as HTML, with each row's quoted passage highlighted where it is
    found. Returns the HTML and, per row, whether its passage was located at all — a quote
    that is nowhere in the text is itself a finding."""
    flat, idx = stripped(text)
    spans, found, cursor = [], [], 0
    for n, r in enumerate(rows):
        q = stripped(r["quoted"])[0]
        if not q:
            found.append(False)
            continue
        at = flat.find(q, cursor)
        if at < 0:
            at = flat.find(q)  # an out-of-order quote still counts as located
        if at < 0:
            found.append(False)
            continue
        found.append(True)
        cursor = at + len(q)
        spans.append((idx[at], idx[at + len(q) - 1] + 1, n, r["kind"]))
    spans.sort()
    parts, pos = [], 0
    for start, end, n, kind in spans:
        if start < pos:  # overlapping labels: the first one keeps the passage
            continue
        parts.append(html.escape(text[pos:start]))
        parts.append(f'<mark class="{kind}" data-row="{n}">{html.escape(text[start:end])}</mark>')
        pos = end
    parts.append(html.escape(text[pos:]))
    body = "".join(parts)
    return re.sub(
        r"(?m)^(===== page \d+ =====)$", r'<span class="pagebreak">\1</span>', body
    ), found


def main() -> None:
    rows = list(
        csv.DictReader((ROOT / "docs/research/benchmark/labels.csv").open(encoding="utf-8"))
    )
    by_decision: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_decision[r["decision_id"]].append(r)

    text_dir = ROOT / "data/benchmark/text"
    files = {f.name.split("-")[-1].removesuffix(".txt"): f for f in text_dir.glob("*.txt")}

    order = {"heavy": 0, "routine": 1, "short": 2}
    items = []
    for did, rs in sorted(by_decision.items(), key=lambda kv: (order[kv[1][0]["stratum"]], kv[0])):
        f = files.get(did)
        text = f.read_text(encoding="utf-8", errors="replace") if f else ""
        rs.sort(key=lambda r: (int(r["page"] or 0), rows.index(r)))
        marked, found = mark_up(text, rs)
        head = rs[0]
        items.append(
            {
                "id": did,
                "s": head["stratum"],
                "d": head["docket"],
                "dt": head["date"],
                "url": head["board_url"],
                "t": marked,
                "rows": [
                    {
                        "k": r["kind"],
                        "p": r["page"],
                        "q": r["quoted"],
                        "tg": r["target"],
                        "n": r["note"],
                        "f": found[i] if i < len(found) else False,
                    }
                    for i, r in enumerate(rs)
                ],
            }
        )

    data = (
        json.dumps(items, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028")
    )
    conv = json.dumps(CONVENTIONS, ensure_ascii=False).replace("<", "\\u003c")
    total = len(rows)
    missing = sum(1 for it in items for r in it["rows"] if not r["f"])
    html_out = (
        TEMPLATE.replace("__DATA__", data)
        .replace("__CONV__", conv)
        .replace("__TOTAL__", str(total))
    )
    OUT.write_text(html_out, encoding="utf-8", newline="\n")
    print(f"wrote {OUT} {OUT.stat().st_size / 1e6:.2f} MB")
    print(
        f"{len(items)} decisions, {total} labels, {missing} whose quoted passage is not in the text"
    )


TEMPLATE = """<title>Label Ledger</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600&family=Source+Sans+3:wght@400;600;700&display=swap">
<style>
  :root {
    --paper: #f6f5f2; --panel: #fffefb; --ink: #1a1c20; --soft: #5c5f68; --faint: #8a8d96;
    --rule: #dcd9d3; --rule-firm: #c3bfb6; --accent: #3a3f7d; --accent-soft: #ececf6;
    --alert: #9d3a30; --alert-soft: #f7ebe8; --ok: #2f6b46;
    --cite: #2c5f8a; --cite-soft: #dcebf6; --dead: #8a5a1f; --dead-soft: #f8eeda;
    --heavy: #6b4478; --routine: #2c6b66; --short: #5b6b7a;
    --shadow: 0 1px 2px rgba(26,28,32,.06), 0 8px 24px -16px rgba(26,28,32,.28);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --paper: #15161a; --panel: #1c1e23; --ink: #e9e7e2; --soft: #a7abb5; --faint: #7c8089;
      --rule: #2e3037; --rule-firm: #3d4048; --accent: #9aa1e4; --accent-soft: #23263a;
      --alert: #e0897b; --alert-soft: #33231f; --ok: #7fbf9a;
      --cite: #8ec3ea; --cite-soft: #1d3040; --dead: #e0b877; --dead-soft: #35291a;
      --heavy: #b291c4; --routine: #6fb5ad; --short: #9fb0c0;
      --shadow: 0 1px 2px rgba(0,0,0,.5), 0 10px 30px -18px rgba(0,0,0,.8);
    }
  }
  :root[data-theme="dark"] {
    --paper: #15161a; --panel: #1c1e23; --ink: #e9e7e2; --soft: #a7abb5; --faint: #7c8089;
    --rule: #2e3037; --rule-firm: #3d4048; --accent: #9aa1e4; --accent-soft: #23263a;
    --alert: #e0897b; --alert-soft: #33231f; --ok: #7fbf9a;
    --cite: #8ec3ea; --cite-soft: #1d3040; --dead: #e0b877; --dead-soft: #35291a;
    --heavy: #b291c4; --routine: #6fb5ad; --short: #9fb0c0;
    --shadow: 0 1px 2px rgba(0,0,0,.5), 0 10px 30px -18px rgba(0,0,0,.8);
  }

  * { box-sizing: border-box; }
  body { margin: 0; background: var(--paper); color: var(--ink); font: 400 16px/1.55 "Source Sans 3", system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
  .shell { display: grid; grid-template-columns: 250px minmax(0, 1fr); min-height: 100vh; }

  .rail { border-right: 1px solid var(--rule); background: var(--panel); display: flex; flex-direction: column; height: 100vh; position: sticky; top: 0; }
  .rail-head { padding: 16px 16px 12px; border-bottom: 1px solid var(--rule); }
  .wordmark { font-family: Newsreader, Georgia, serif; font-size: 20px; font-weight: 600; margin: 0 0 2px; }
  .rail-head p { margin: 0; font-size: 12.5px; color: var(--faint); }
  .meter { height: 4px; background: var(--rule); border-radius: 2px; margin-top: 12px; overflow: hidden; }
  .meter span { display: block; height: 100%; background: var(--accent); width: 0; }
  .meter-note { display: flex; justify-content: space-between; font-size: 12px; color: var(--soft); margin-top: 6px; font-variant-numeric: tabular-nums; }
  .filters { display: flex; flex-wrap: wrap; gap: 4px; padding: 9px 13px; border-bottom: 1px solid var(--rule); }
  .filters button { font: inherit; font-size: 11.5px; letter-spacing: .04em; text-transform: uppercase; background: none; border: 1px solid var(--rule-firm); color: var(--soft); padding: 3px 8px; border-radius: 3px; cursor: pointer; }
  .filters button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--panel); }
  .list { overflow-y: auto; flex: 1; padding: 6px 0 24px; }
  .list button { width: 100%; display: grid; grid-template-columns: 9px 1fr auto; gap: 9px; align-items: center; background: none; border: 0; border-left: 3px solid transparent; text-align: left; padding: 7px 13px 7px 10px; font: inherit; font-size: 13.5px; color: var(--ink); cursor: pointer; }
  .list button:hover { background: var(--accent-soft); }
  .list button[aria-current="true"] { border-left-color: var(--accent); background: var(--accent-soft); font-weight: 600; }
  .dot { width: 8px; height: 8px; border-radius: 50%; border: 1.5px solid var(--rule-firm); }
  .dot.done { background: var(--ok); border-color: var(--ok); }
  .dot.part { background: var(--dead); border-color: var(--dead); }
  .list .n { color: var(--faint); font-size: 12px; font-variant-numeric: tabular-nums; }
  .list .who { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  main { padding: 24px 30px 80px; max-width: 1600px; }
  .intro { border-bottom: 1px solid var(--rule); padding-bottom: 16px; margin-bottom: 18px; }
  .intro h1 { font-family: Newsreader, Georgia, serif; font-size: 29px; font-weight: 600; margin: 0 0 6px; letter-spacing: -.015em; }
  .intro p { margin: 0; color: var(--soft); max-width: 82ch; font-size: 15px; }
  .intro strong { color: var(--ink); }

  .conv { margin: 16px 0 0; border: 1px solid var(--rule-firm); border-radius: 5px; background: var(--panel); box-shadow: var(--shadow); }
  .conv > summary { cursor: pointer; padding: 12px 16px; font-weight: 600; font-size: 15px; list-style: none; display: flex; justify-content: space-between; gap: 12px; }
  .conv > summary::-webkit-details-marker { display: none; }
  .conv > summary .hintline { font-weight: 400; color: var(--faint); font-size: 13px; }
  .conv .body { padding: 0 16px 14px; display: grid; gap: 14px; }
  .cq { border-top: 1px solid var(--rule); padding-top: 12px; }
  .cq h3 { margin: 0 0 4px; font-size: 15px; font-weight: 600; }
  .cq p { margin: 0 0 8px; font-size: 14px; color: var(--soft); max-width: 80ch; }
  .cq .count { color: var(--faint); font-size: 12.5px; }
  .cq .opts { display: flex; gap: 6px; flex-wrap: wrap; }
  .cq button { font: inherit; font-size: 13.5px; padding: 5px 11px; border-radius: 4px; border: 1px solid var(--rule-firm); background: var(--panel); color: var(--ink); cursor: pointer; }
  .cq button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--panel); font-weight: 600; }

  .head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin: 18px 0 2px; }
  .head h2 { font-family: Newsreader, Georgia, serif; font-size: 23px; font-weight: 600; margin: 0; }
  .chip { font-size: 11px; letter-spacing: .07em; text-transform: uppercase; font-weight: 700; padding: 2px 7px; border-radius: 3px; color: var(--panel); }
  .chip.heavy { background: var(--heavy); } .chip.routine { background: var(--routine); } .chip.short { background: var(--short); }
  .sub { color: var(--soft); font-size: 14px; margin: 0 0 14px; font-variant-numeric: tabular-nums; }
  .sub .sep { color: var(--rule-firm); padding: 0 5px; }

  .pair { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 20px; align-items: start; }
  .doc { border: 1px solid var(--rule); background: var(--panel); border-radius: 4px; box-shadow: var(--shadow); position: sticky; top: 16px; }
  .doc header { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; border-bottom: 1px solid var(--rule); font-size: 12.5px; color: var(--faint); }
  .doc pre { margin: 0; padding: 14px 16px; white-space: pre-wrap; font: 13px/1.55 ui-monospace, "SF Mono", Consolas, monospace; max-height: 74vh; overflow-y: auto; }
  mark { padding: 0 1px; border-radius: 2px; cursor: pointer; }
  mark.citation { background: var(--cite-soft); box-shadow: inset 0 -2px 0 var(--cite); }
  mark.deadline { background: var(--dead-soft); box-shadow: inset 0 -2px 0 var(--dead); }
  mark.on { outline: 2px solid var(--accent); }
  .pagebreak { color: var(--faint); }

  .rows { display: flex; flex-direction: column; gap: 8px; }
  .row { border: 1px solid var(--rule); border-radius: 4px; background: var(--panel); padding: 10px 12px; box-shadow: var(--shadow); }
  .row.on { border-color: var(--accent); }
  .row .top { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; font-size: 12px; color: var(--faint); }
  .kind { font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; font-weight: 700; padding: 1px 6px; border-radius: 3px; }
  .kind.citation { background: var(--cite-soft); color: var(--cite); }
  .kind.deadline { background: var(--dead-soft); color: var(--dead); }
  .quoted { font: 13px/1.5 ui-monospace, Consolas, monospace; margin: 0 0 5px; }
  .target { font-size: 14px; margin: 0 0 4px; }
  .target b { font-weight: 600; }
  .note { font-size: 13px; color: var(--soft); margin: 0 0 8px; }
  .lost { font-size: 12.5px; color: var(--alert); margin: 0 0 8px; }
  .verd { display: flex; gap: 6px; }
  .verd button { font: inherit; font-size: 13px; padding: 4px 10px; border-radius: 3px; border: 1px solid var(--rule-firm); background: var(--panel); color: var(--soft); cursor: pointer; }
  .verd button[aria-pressed="true"][data-v="ok"] { background: var(--ok); border-color: var(--ok); color: var(--panel); }
  .verd button[aria-pressed="true"][data-v="no"] { background: var(--alert); border-color: var(--alert); color: var(--panel); }

  .act { display: inline-flex; align-items: center; gap: 6px; background: var(--accent); color: var(--panel); border: 0; border-radius: 4px; padding: 9px 14px; font: inherit; font-weight: 600; font-size: 14.5px; text-decoration: none; cursor: pointer; }
  .act.ghost { background: none; color: var(--accent); border: 1px solid var(--rule-firm); }
  .sweep { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 14px 0 10px; }
  textarea { width: 100%; min-height: 76px; resize: vertical; padding: 10px 12px; border-radius: 4px; border: 1px solid var(--rule-firm); background: var(--panel); color: var(--ink); font: 14.5px/1.5 "Source Sans 3", system-ui, sans-serif; }
  .status { font-size: 13px; color: var(--soft); }
  .hint { font-size: 12.5px; color: var(--faint); }
  kbd { font: 11.5px ui-monospace, Consolas, monospace; border: 1px solid var(--rule-firm); border-bottom-width: 2px; border-radius: 3px; padding: 1px 5px; color: var(--soft); }
  button:focus-visible, a:focus-visible, textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  @media (max-width: 1100px) { .pair { grid-template-columns: 1fr; } .doc { position: static; } }
  @media (max-width: 900px) { .shell { grid-template-columns: 1fr; } .rail { position: static; height: auto; max-height: 40vh; } main { padding: 18px 16px 60px; } }
</style>

<div class="shell">
  <nav class="rail" aria-label="Decisions">
    <div class="rail-head">
      <p class="wordmark">Label ledger</p>
      <p>Extraction benchmark &middot; 60 decisions</p>
      <div class="meter"><span id="bar"></span></div>
      <div class="meter-note"><span id="done">0 of __TOTAL__ labels</span><span id="flagged">0 wrong</span></div>
    </div>
    <div class="filters" id="filters">
      <button data-f="all" aria-pressed="true">All</button>
      <button data-f="heavy" aria-pressed="false">Heavy</button>
      <button data-f="routine" aria-pressed="false">Routine</button>
      <button data-f="short" aria-pressed="false">Short</button>
      <button data-f="todo" aria-pressed="false">Unchecked</button>
      <button data-f="lost" aria-pressed="false">Not found</button>
    </div>
    <div class="list" id="list"></div>
  </nav>

  <main>
    <div class="intro">
      <h1>Check what the drafter labelled</h1>
      <p>977 citations and deadlines drawn from 60 decisions by a model, against the decisions&rsquo;
      own text. Each is ground truth only once you have judged it. The text is on the left with every
      labelled passage <mark class="citation">highlighted</mark> in place &mdash; which is the point:
      a label set is judged on <strong>what is missing</strong> as well as what is wrong, and an
      unhighlighted citation in the running text is the only way to see one. Mark a label
      <strong>right</strong> or <strong>wrong</strong>, or sweep a whole decision. Everything stays in
      this browser; <strong>Copy findings</strong> hands it back in one block.</p>
      <details class="conv" id="conv" open>
        <summary>Four questions worth answering first <span class="hintline">they settle about 130 rows between them</span></summary>
        <div class="body" id="convbody"></div>
      </details>
    </div>

    <div class="head">
      <h2 id="title">&nbsp;</h2>
      <span class="chip" id="stratum"></span>
    </div>
    <p class="sub" id="sub"></p>

    <div class="pair">
      <div class="doc">
        <header><span id="docname"></span><a id="open" href="#" target="_blank" rel="noopener">the Board&rsquo;s PDF</a></header>
        <pre id="text"></pre>
      </div>
      <div>
        <div class="sweep">
          <button class="act" id="allok">All right on this decision <kbd>a</kbd></button>
          <button class="act ghost" id="prev">&larr;</button>
          <button class="act ghost" id="next">&rarr;</button>
        </div>
        <textarea id="miss" placeholder="Anything the drafter missed on this decision — a citation or a deadline in the text that carries no highlight. Quote it."></textarea>
        <div class="sweep">
          <button class="act" id="copy">Copy findings</button>
          <span class="status" id="status">Nothing marked yet.</span>
        </div>
        <div class="rows" id="rows"></div>
        <p class="hint" style="margin-top:12px"><kbd>j</kbd> <kbd>k</kbd> move between decisions &middot; <kbd>a</kbd> sweeps this one &middot; clicking a highlight scrolls to its label, and back.</p>
      </div>
    </div>
  </main>
</div>

<script id="data" type="application/json">__DATA__</script>
<script id="conventions" type="application/json">__CONV__</script>
<script>
(function () {
  "use strict";
  var DEC = JSON.parse(document.getElementById("data").textContent);
  var CONV = JSON.parse(document.getElementById("conventions").textContent);
  var TOTAL = DEC.reduce(function (n, d) { return n + d.rows.length; }, 0);
  var KEY = "dy-labels-check-v1";
  var state = {};
  try { state = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { state = {}; }
  if (!state.rows) { state.rows = {}; }
  if (!state.miss) { state.miss = {}; }
  if (!state.conv) { state.conv = {}; }
  var filter = "all", at = 0, view = DEC.map(function (_, i) { return i; });

  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
  function el(id) { return document.getElementById(id); }
  function key(d, n) { return d.id + ":" + n; }

  function counts() {
    var done = 0, wrong = 0;
    DEC.forEach(function (d) {
      d.rows.forEach(function (_, n) {
        var v = state.rows[key(d, n)];
        if (v) { done++; if (v === "no") { wrong++; } }
      });
    });
    return { done: done, wrong: wrong };
  }
  function decDone(d) {
    var n = 0;
    d.rows.forEach(function (_, i) { if (state.rows[key(d, i)]) { n++; } });
    return n;
  }

  function matches(i) {
    var d = DEC[i];
    if (filter === "all") { return true; }
    if (filter === "todo") { return decDone(d) < d.rows.length; }
    if (filter === "lost") { return d.rows.some(function (r) { return !r.f; }); }
    return d.s === filter;
  }
  function rail() {
    view = DEC.map(function (_, i) { return i; }).filter(matches);
    var list = el("list");
    list.textContent = "";
    view.forEach(function (i) {
      var d = DEC[i], n = decDone(d);
      var b = document.createElement("button");
      b.type = "button";
      b.innerHTML = '<span class="dot ' + (n === d.rows.length ? "done" : n ? "part" : "") + '"></span>' +
        '<span class="who">' + d.d.replace(/_/g, " ") + "</span>" +
        '<span class="n">' + n + "/" + d.rows.length + "</span>";
      b.setAttribute("aria-current", i === at ? "true" : "false");
      b.addEventListener("click", function () { at = i; render(); });
      list.appendChild(b);
    });
    var c = counts();
    el("bar").style.width = (c.done / TOTAL * 100) + "%";
    el("done").textContent = c.done + " of " + TOTAL + " labels";
    el("flagged").textContent = c.wrong + " wrong";
    el("status").textContent = c.done === 0 ? "Nothing marked yet." : c.done + " judged, " + c.wrong + " wrong.";
  }

  function paintRow(card, d, n) {
    var v = state.rows[key(d, n)] || "";
    [].forEach.call(card.querySelectorAll(".verd button"), function (b) {
      b.setAttribute("aria-pressed", String(v === b.dataset.v));
    });
  }

  function render() {
    var d = DEC[at], pos = view.indexOf(at);
    el("title").textContent = d.d.replace(/_/g, " ");
    el("stratum").textContent = d.s;
    el("stratum").className = "chip " + d.s;
    el("sub").innerHTML = (pos >= 0 ? "Decision " + (pos + 1) + " of " + view.length : "Not in this filter") +
      '<span class="sep">|</span>decision ' + d.id +
      '<span class="sep">|</span>' + d.dt +
      '<span class="sep">|</span>' + d.rows.length + " label" + (d.rows.length === 1 ? "" : "s");
    el("docname").textContent = "decision " + d.id + " — text layer";
    el("open").href = d.url;
    el("text").innerHTML = d.t;
    el("miss").value = state.miss[d.id] || "";

    var host = el("rows");
    host.textContent = "";
    d.rows.forEach(function (r, n) {
      var card = document.createElement("div");
      card.className = "row";
      card.id = "row" + n;
      card.innerHTML =
        '<div class="top"><span class="kind ' + r.k + '">' + r.k + "</span><span>page " + r.p + "</span></div>" +
        '<p class="quoted">&ldquo;' + esc(r.q) + "&rdquo;</p>" +
        (r.tg ? '<p class="target"><b>' + esc(r.tg) + "</b></p>" : '<p class="target"><span style="color:var(--faint)">no target</span></p>') +
        (r.n ? '<p class="note">' + esc(r.n) + "</p>" : "") +
        (r.f ? "" : '<p class="lost">This passage was not found in the decision&rsquo;s text.</p>') +
        '<div class="verd"><button data-v="ok">Right</button><button data-v="no">Wrong</button></div>';
      [].forEach.call(card.querySelectorAll(".verd button"), function (b) {
        b.addEventListener("click", function () {
          var k = key(d, n);
          state.rows[k] = state.rows[k] === b.dataset.v ? "" : b.dataset.v;
          if (!state.rows[k]) { delete state.rows[k]; }
          save(); paintRow(card, d, n); rail();
        });
      });
      card.addEventListener("mouseenter", function () {
        var m = el("text").querySelector('mark[data-row="' + n + '"]');
        if (m) { m.classList.add("on"); }
      });
      card.addEventListener("mouseleave", function () {
        var m = el("text").querySelector('mark[data-row="' + n + '"]');
        if (m) { m.classList.remove("on"); }
      });
      host.appendChild(card);
      paintRow(card, d, n);
    });
    [].forEach.call(el("text").querySelectorAll("mark"), function (m) {
      m.addEventListener("click", function () {
        var card = el("row" + m.dataset.row);
        if (card) { card.scrollIntoView({ block: "center", behavior: "smooth" }); card.classList.add("on"); setTimeout(function () { card.classList.remove("on"); }, 1200); }
      });
    });
    rail();
    var cur = el("list").querySelector('[aria-current="true"]');
    if (cur && cur.scrollIntoView) { cur.scrollIntoView({ block: "nearest" }); }
  }

  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function move(step) {
    var pos = view.indexOf(at);
    at = pos < 0 ? view[0] : view[Math.max(0, Math.min(view.length - 1, pos + step))];
    if (at === undefined) { at = 0; }
    render();
  }

  el("next").addEventListener("click", function () { move(1); });
  el("prev").addEventListener("click", function () { move(-1); });
  el("allok").addEventListener("click", function () {
    var d = DEC[at];
    d.rows.forEach(function (_, n) { if (!state.rows[key(d, n)]) { state.rows[key(d, n)] = "ok"; } });
    save(); render();
  });
  el("miss").addEventListener("input", function () {
    state.miss[DEC[at].id] = el("miss").value;
    if (!el("miss").value.trim()) { delete state.miss[DEC[at].id]; }
    save();
  });
  [].forEach.call(document.querySelectorAll("#filters button"), function (b) {
    b.addEventListener("click", function () {
      filter = b.dataset.f;
      [].forEach.call(document.querySelectorAll("#filters button"), function (o) { o.setAttribute("aria-pressed", String(o === b)); });
      rail();
      if (view.length && view.indexOf(at) < 0) { at = view[0]; render(); }
    });
  });

  (function conventions() {
    var host = el("convbody");
    CONV.forEach(function (c) {
      var box = document.createElement("div");
      box.className = "cq";
      box.innerHTML = "<h3>" + c.q + '</h3><p>' + c.detail + ' <span class="count">(' + c.count + ")</span></p>" +
        '<div class="opts"><button data-a="yes">Yes, keep them</button><button data-a="no">No, drop them</button><button data-a="later">Decide later</button></div>';
      [].forEach.call(box.querySelectorAll("button"), function (b) {
        b.addEventListener("click", function () {
          state.conv[c.id] = state.conv[c.id] === b.dataset.a ? "" : b.dataset.a;
          save(); paintConv();
        });
      });
      host.appendChild(box);
      box.dataset.id = c.id;
    });
    paintConv();
  })();
  function paintConv() {
    [].forEach.call(el("convbody").children, function (box) {
      [].forEach.call(box.querySelectorAll("button"), function (b) {
        b.setAttribute("aria-pressed", String(state.conv[box.dataset.id] === b.dataset.a));
      });
    });
  }

  el("copy").addEventListener("click", function () {
    var out = ["Extraction labels — findings", ""];
    var answered = CONV.filter(function (c) { return state.conv[c.id]; });
    if (answered.length) {
      out.push("Conventions:");
      answered.forEach(function (c) { out.push("  " + c.id + ": " + state.conv[c.id] + "  (" + c.q + ")"); });
      out.push("");
    }
    var wrong = 0;
    DEC.forEach(function (d) {
      var bad = [];
      d.rows.forEach(function (r, n) {
        if (state.rows[key(d, n)] === "no") { bad.push('    [' + r.k + ' p.' + r.p + '] "' + r.q + '" -> ' + (r.tg || "(no target)")); }
      });
      var miss = (state.miss[d.id] || "").trim();
      if (!bad.length && !miss) { return; }
      wrong += bad.length;
      out.push(d.id + "  " + d.d.replace(/_/g, " ") + "  " + d.dt);
      if (bad.length) { out.push("  wrong:"); out = out.concat(bad); }
      if (miss) { out.push("  missed: " + miss.replace(/\\n/g, "\\n          ")); }
      out.push("");
    });
    var c = counts();
    out.push(c.done + " of " + TOTAL + " labels judged; " + wrong + " marked wrong.");
    var text = out.join("\\n");
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { el("status").textContent = "Findings copied — paste them back to Claude."; },
        function () { window.prompt("Copy:", text); });
    } else { window.prompt("Copy:", text); }
  });

  document.addEventListener("keydown", function (e) {
    var t = e.target.tagName;
    if (t === "TEXTAREA" || t === "INPUT" || e.metaKey || e.ctrlKey || e.altKey) { return; }
    if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "a") { el("allok").click(); }
  });

  render();
})();
</script>
"""


if __name__ == "__main__":
    main()
