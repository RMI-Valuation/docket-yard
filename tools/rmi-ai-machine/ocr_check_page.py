"""Build the OCR ground-truth check queue (docs/research/ocr-benchmark).

One self-contained page: every sampled scan beside its drafted transcription, the scan
whole and at full resolution with zoom, pan and a view-only turn, and the Board's own file
one click away at its permanent address. Verdicts, notes, tier corrections and the turn are
kept in the reader's browser; "Copy corrections" hands them back in one block.

Needs `data/ocr/pageimg.json` from `ocr_page_images.py` and the drafts in
`docs/research/ocr-benchmark/ground-truth`. This is a stand-in for the `/review` queue
ADR 0016 accepts, and a paper prototype of it: the real one shows the document at
`/document/<sha>.pdf` and records each check as a provenance row.
"""

# ruff: noqa: E501 — an HTML document lives in this file; its CSS and markup keep their own
# line lengths, and reflowing them to the code width would only make them harder to read.

import json
from pathlib import Path

ROOT = Path("e:/DevProjects/docket-yard")
OUT = Path(
    "C:/Users/CAMERO~1/AppData/Local/Temp/claude/e--DevProjects-docket-yard/"
    "96fc75d7-5d5a-4c59-a069-310fcbb7766b/scratchpad/ocr-check.html"
)

sample = json.loads((ROOT / "data/ocr/sample.json").read_text(encoding="utf-8"))
pageimg = json.loads((ROOT / "data/ocr/pageimg.json").read_text(encoding="utf-8"))
draft = ROOT / "docs/research/ocr-benchmark/ground-truth"

order = {"clean": 0, "degraded": 1, "tabular": 2, "graphic": 3, "blank": 4}
items = []
for p in sorted(
    (p for p in sample["pages"] if p["selected"]), key=lambda p: (order[p["tier"]], p["png"])
):
    text = (draft / p["png"].replace(".png", ".txt")).read_text(encoding="utf-8")
    items.append(
        {
            "f": p["png"].replace(".png", ".txt"),
            "sha": p["sha256"],
            "pg": p["page"] + 1,
            "of": p["pages"],
            "d": p["raw_docket"],
            "k": p["kind"],
            "r": p["record_id"],
            "dt": p["date"],
            "ty": p["type"] or "",
            "t": p["tier"],
            "x": text,
            "img": pageimg[p["png"]],
        }
    )

DATA = json.dumps(items, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028")

HTML = """<title>Ground Truth Queue</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&family=Source+Sans+3:wght@400;600;700&display=swap">
<style>
  :root {
    --paper: #f6f5f2; --panel: #fffefb; --ink: #1a1c20; --soft: #5c5f68; --faint: #8a8d96;
    --rule: #dcd9d3; --rule-firm: #c3bfb6; --accent: #3a3f7d; --accent-soft: #ececf6;
    --alert: #9d3a30; --alert-soft: #f7ebe8; --ok: #2f6b46;
    --clean: #5b6b7a; --degraded: #8a6a1f; --tabular: #2c6b66; --graphic: #6b4478; --blank: #7a7a7a;
    --shadow: 0 1px 2px rgba(26,28,32,.06), 0 8px 24px -16px rgba(26,28,32,.28);
  }
  :root:not([data-theme="light"]) { color-scheme: light dark; }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --paper: #15161a; --panel: #1c1e23; --ink: #e9e7e2; --soft: #a7abb5; --faint: #7c8089;
      --rule: #2e3037; --rule-firm: #3d4048; --accent: #9aa1e4; --accent-soft: #23263a;
      --alert: #e0897b; --alert-soft: #33231f; --ok: #7fbf9a;
      --clean: #9fb0c0; --degraded: #d3ab5a; --tabular: #6fb5ad; --graphic: #b291c4; --blank: #9a9a9a;
      --shadow: 0 1px 2px rgba(0,0,0,.5), 0 10px 30px -18px rgba(0,0,0,.8);
    }
  }
  :root[data-theme="dark"] {
    --paper: #15161a; --panel: #1c1e23; --ink: #e9e7e2; --soft: #a7abb5; --faint: #7c8089;
    --rule: #2e3037; --rule-firm: #3d4048; --accent: #9aa1e4; --accent-soft: #23263a;
    --alert: #e0897b; --alert-soft: #33231f; --ok: #7fbf9a;
    --clean: #9fb0c0; --degraded: #d3ab5a; --tabular: #6fb5ad; --graphic: #b291c4; --blank: #9a9a9a;
    --shadow: 0 1px 2px rgba(0,0,0,.5), 0 10px 30px -18px rgba(0,0,0,.8);
  }

  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--paper); color: var(--ink);
    font: 400 16px/1.55 "Source Sans 3", ui-sans-serif, system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .shell { display: grid; grid-template-columns: 268px minmax(0, 1fr); min-height: 100vh; }

  /* ---- rail ---- */
  .rail {
    border-right: 1px solid var(--rule); background: var(--panel);
    display: flex; flex-direction: column; height: 100vh; position: sticky; top: 0;
  }
  .rail-head { padding: 18px 18px 12px; border-bottom: 1px solid var(--rule); }
  .wordmark {
    font-family: Newsreader, Georgia, serif; font-size: 20px; font-weight: 600;
    letter-spacing: -.01em; margin: 0 0 2px;
  }
  .rail-head p { margin: 0; font-size: 12.5px; color: var(--faint); }
  .meter { height: 4px; background: var(--rule); border-radius: 2px; margin-top: 12px; overflow: hidden; }
  .meter span { display: block; height: 100%; background: var(--accent); width: 0; transition: width .25s ease; }
  .meter-note { display: flex; justify-content: space-between; font-size: 12px; color: var(--soft); margin-top: 6px; font-variant-numeric: tabular-nums; }

  .filters { display: flex; flex-wrap: wrap; gap: 4px; padding: 10px 14px; border-bottom: 1px solid var(--rule); }
  .filters button {
    font: inherit; font-size: 11.5px; letter-spacing: .04em; text-transform: uppercase;
    background: none; border: 1px solid var(--rule-firm); color: var(--soft);
    padding: 3px 8px; border-radius: 3px; cursor: pointer;
  }
  .filters button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--panel); }
  .filters button:focus-visible, .act:focus-visible, .verdict button:focus-visible,
  .list button:focus-visible, textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  .list { overflow-y: auto; flex: 1; padding: 6px 0 24px; }
  .list button {
    width: 100%; display: grid; grid-template-columns: 10px 1fr auto; gap: 9px; align-items: center;
    background: none; border: 0; border-left: 3px solid transparent; text-align: left;
    padding: 7px 14px 7px 11px; font: inherit; font-size: 13.5px; color: var(--ink); cursor: pointer;
  }
  .list button:hover { background: var(--accent-soft); }
  .list button[aria-current="true"] { border-left-color: var(--accent); background: var(--accent-soft); font-weight: 600; }
  .dot { width: 8px; height: 8px; border-radius: 50%; border: 1.5px solid var(--rule-firm); }
  .dot.ok { background: var(--ok); border-color: var(--ok); }
  .dot.fix { background: var(--alert); border-color: var(--alert); }
  .list .n { color: var(--faint); font-size: 12px; font-variant-numeric: tabular-nums; }
  .list .who { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  /* ---- main ---- */
  main { padding: 26px 34px 80px; max-width: 1500px; }
  .intro { border-bottom: 1px solid var(--rule); padding-bottom: 18px; margin-bottom: 22px; }
  .intro h1 { font-family: Newsreader, Georgia, serif; font-size: 30px; font-weight: 600; margin: 0 0 6px; letter-spacing: -.015em; text-wrap: balance; }
  .intro p { margin: 0; color: var(--soft); max-width: 78ch; font-size: 15px; }
  .intro strong { color: var(--ink); }
  .rules { display: grid; grid-template-columns: repeat(auto-fit, minmax(310px, 1fr)); gap: 10px 28px; margin-top: 16px; }
  .rules .lede {
    font-size: 11.5px; letter-spacing: .08em; text-transform: uppercase; font-weight: 700;
    margin: 0 0 6px; color: var(--accent);
  }
  .rules div:last-child .lede { color: var(--faint); }
  .rules ul { margin: 0; padding-left: 18px; color: var(--soft); font-size: 14px; }
  .rules li { margin-bottom: 4px; }
  .rules .m { font-family: ui-monospace, Consolas, monospace; font-size: 12.5px; color: var(--ink); }

  .head { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }
  .head h2 { font-family: Newsreader, Georgia, serif; font-size: 23px; font-weight: 600; margin: 0; letter-spacing: -.01em; }
  .chip {
    font-size: 11px; letter-spacing: .07em; text-transform: uppercase; font-weight: 700;
    padding: 2px 7px; border-radius: 3px; color: var(--panel);
  }
  .chip.clean { background: var(--clean); } .chip.degraded { background: var(--degraded); }
  .chip.tabular { background: var(--tabular); } .chip.graphic { background: var(--graphic); }
  .chip.blank { background: var(--blank); }
  .sub { color: var(--soft); font-size: 14px; margin: 0 0 16px; font-variant-numeric: tabular-nums; }
  .sub .sep { color: var(--rule-firm); padding: 0 5px; }

  .pair { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 22px; align-items: start; }
  .scan { position: sticky; top: 20px; display: flex; flex-direction: column; gap: 10px; }
  .zoombar { display: flex; align-items: center; gap: 5px; }
  .zoombar button {
    font: inherit; font-size: 13px; line-height: 1; padding: 5px 10px; border-radius: 3px;
    border: 1px solid var(--rule-firm); background: var(--panel); color: var(--soft); cursor: pointer;
  }
  .zoombar button:hover { color: var(--ink); }
  .zoombar button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .zoombar button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--panel); }
  .zoombar .pct { font-size: 12.5px; color: var(--faint); font-variant-numeric: tabular-nums; min-width: 3.4em; }
  .viewport {
    position: relative; overflow: hidden; height: 560px;
    border: 1px solid var(--rule-firm); background: #fff; box-shadow: var(--shadow);
    cursor: grab; touch-action: none;
  }
  .viewport.dragging { cursor: grabbing; }
  .viewport img {
    position: absolute; top: 0; left: 0; transform-origin: 0 0;
    user-select: none;
  }
  .pair.widepage { grid-template-columns: 1fr; }
  .pair.widepage .scan { position: static; }
  .pair.widepage .viewport { height: 680px; }
  .act {
    display: inline-flex; align-items: center; justify-content: center; gap: 7px;
    background: var(--accent); color: var(--panel); border: 0; border-radius: 4px;
    padding: 10px 14px; font: inherit; font-weight: 600; font-size: 14.5px;
    text-decoration: none; cursor: pointer;
  }
  .act:hover { filter: brightness(1.08); }
  .act.ghost { background: none; color: var(--accent); border: 1px solid var(--rule-firm); }
  .hint { font-size: 12.5px; color: var(--faint); margin: 0; }

  .transcript { border: 1px solid var(--rule); background: var(--panel); border-radius: 4px; box-shadow: var(--shadow); }
  .transcript header {
    display: flex; justify-content: space-between; align-items: center; gap: 10px;
    padding: 8px 12px; border-bottom: 1px solid var(--rule);
    font: 12.5px/1 ui-monospace, "SF Mono", Consolas, monospace; color: var(--faint);
  }
  .transcript pre {
    margin: 0; padding: 16px 18px; white-space: pre-wrap; overflow-x: auto;
    font: 13.5px/1.5 ui-monospace, "SF Mono", Consolas, "Liberation Mono", monospace;
    max-height: 62vh; overflow-y: auto; tab-size: 8;
  }
  mark { background: var(--alert-soft); color: var(--alert); padding: 0 2px; border-radius: 2px; font-weight: 600; }

  .verdict { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 10px; }
  .verdict button {
    font: inherit; font-size: 14px; padding: 7px 13px; border-radius: 4px; cursor: pointer;
    border: 1px solid var(--rule-firm); background: var(--panel); color: var(--ink);
  }
  .verdict button[aria-pressed="true"][data-v="ok"] { background: var(--ok); border-color: var(--ok); color: var(--panel); }
  .verdict button[aria-pressed="true"][data-v="fix"] { background: var(--alert); border-color: var(--alert); color: var(--panel); }
  .verdict .key { color: var(--faint); font-size: 12px; margin-left: 5px; }
  .retier { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin: 0 0 10px; }
  .retier-label { font-size: 11.5px; letter-spacing: .07em; text-transform: uppercase; color: var(--faint); font-weight: 700; margin-right: 2px; }
  .retier button {
    font: inherit; font-size: 12.5px; padding: 3px 9px; border-radius: 3px; cursor: pointer;
    border: 1px solid var(--rule-firm); background: var(--panel); color: var(--soft);
  }
  .retier button[aria-pressed="true"] { color: var(--panel); border-color: transparent; font-weight: 600; }
  .retier button[aria-pressed="true"][data-t="clean"] { background: var(--clean); }
  .retier button[aria-pressed="true"][data-t="degraded"] { background: var(--degraded); }
  .retier button[aria-pressed="true"][data-t="tabular"] { background: var(--tabular); }
  .retier button[aria-pressed="true"][data-t="graphic"] { background: var(--graphic); }
  .retier button[aria-pressed="true"][data-t="blank"] { background: var(--blank); }
  .retier button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .retier-note { font-size: 12.5px; color: var(--alert); }
  .chip.moved { box-shadow: inset 0 0 0 2px var(--alert); }
  .verdict button[aria-pressed="true"] .key { color: inherit; opacity: .75; }
  textarea {
    width: 100%; min-height: 92px; resize: vertical; padding: 11px 13px; border-radius: 4px;
    border: 1px solid var(--rule-firm); background: var(--panel); color: var(--ink);
    font: 14.5px/1.5 "Source Sans 3", system-ui, sans-serif;
  }
  .foot { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 14px; }
  .status { font-size: 13px; color: var(--soft); }

  kbd {
    font: 11.5px ui-monospace, Consolas, monospace; border: 1px solid var(--rule-firm);
    border-bottom-width: 2px; border-radius: 3px; padding: 1px 5px; color: var(--soft);
  }
  @media (max-width: 900px) {
    .shell { grid-template-columns: 1fr; }
    .rail { position: static; height: auto; max-height: 46vh; }
    main { padding: 20px 18px 60px; }
    .pair { grid-template-columns: 1fr; }
    .scan { position: static; }
  }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="shell">
  <nav class="rail" aria-label="Pages to check">
    <div class="rail-head">
      <p class="wordmark">Ground truth</p>
      <p>OCR benchmark &middot; 90 scanned pages</p>
      <div class="meter"><span id="bar"></span></div>
      <div class="meter-note"><span id="done">0 checked</span><span id="flagged">0 to fix</span></div>
    </div>
    <div class="filters" id="filters">
      <button data-f="all" aria-pressed="true">All 90</button>
      <button data-f="clean" aria-pressed="false">Clean 35</button>
      <button data-f="degraded" aria-pressed="false">Degraded 37</button>
      <button data-f="tabular" aria-pressed="false">Tables 7</button>
      <button data-f="graphic" aria-pressed="false">Graphic 10</button>
      <button data-f="blank" aria-pressed="false">Blank 1</button>
      <button data-f="todo" aria-pressed="false">Unchecked</button>
    </div>
    <div class="list" id="list"></div>
  </nav>

  <main>
    <div class="intro">
      <h1>Check what the drafter read</h1>
      <p>Ninety pages the Board scanned without a text layer, transcribed by a model. Each is
      ground truth only once you have compared it with the page. Open the Board&rsquo;s own file
      beside the transcript &mdash; it opens at the right page &mdash; and mark the page
      <strong>reads correctly</strong> or <strong>needs a fix</strong>. Your marks and notes stay in
      this browser; <strong>Copy corrections</strong> hands them back in one block.</p>
      <div class="rules">
        <div>
          <p class="lede">Worth a fix</p>
          <ul>
            <li>A <strong>docket number or date</strong> read wrongly, or invented where the page has none &mdash; both are scored on their own.</li>
            <li>Words misread, missing, or asserted that are not on the page.</li>
            <li><strong>Reading order</strong> scrambled: a two-column page read straight across, a stamp spliced mid-sentence.</li>
            <li>A <strong>table</strong> whose rows merged, or whose cells are not tab-separated.</li>
            <li>Prose invented on a <strong>graphic</strong> or <strong>blank</strong> page.</li>
            <li>A fragment of a <strong>facing page</strong> caught in the scan that is not wrapped in <span class="m">[adjacent page]</span> &hellip; <span class="m">[end adjacent page]</span>, or a cut line the drafter <strong>completed</strong> instead of ending in <span class="m">[cut]</span>. Completing a cut line is the worst error here.</li>
            <li>The <strong>tier</strong> itself, when it is wrong &mdash; use the Tier row, not the note. The tier decides which scoring rule applies and was assigned from thumbnails, so it is the assertion most likely to be wrong; leave the verdict for the transcription.</li>
            <li>On a <strong>map</strong>: a milepost, county, carrier mark or place name misread &mdash; or a callout broken up (<span class="m">BEGIN ABANDONMENT</span>, <span class="m">MP 54.3 TO MP 48.1</span> stay whole).</li>
          </ul>
        </div>
        <div>
          <p class="lede">Not worth a mark</p>
          <ul>
            <li><strong>Where the lines break</strong> in running prose. Ground truth and every engine pass through one normaliser first &mdash; whitespace collapsed, line-end hyphens joined &mdash; so an engine that keeps the printed lines and one that reflows score alike.</li>
            <li>An end-of-line hyphen (<span class="m">irresponsi-</span> / <span class="m">ble</span>). Joined on both sides before scoring.</li>
            <li>The bracket labels themselves: <span class="m">[stamp: &hellip;]</span> unwraps to its content, <span class="m">[illegible]</span> is excluded from the count.</li>
            <li>Text inside <span class="m">[adjacent page]</span>. It is the facing page, cut off at the edge &mdash; excluded from the score, since reading it or skipping it are both sensible.</li>
            <li>The <strong>order of labels on a map</strong>. Scattered labels have no reading order, so a graphic page is scored as a set &mdash; which labels were recovered, which invented &mdash; not as a sequence. A map is transcribed, never described: the mileposts, counties and carriers are the payload.</li>
          </ul>
        </div>
      </div>
    </div>

    <div class="head">
      <h2 id="title">&nbsp;</h2>
      <span class="chip" id="tier"></span>
    </div>
    <p class="sub" id="sub"></p>

    <div class="pair">
      <div class="scan">
        <div class="zoombar">
          <button id="zout" title="Zoom out (-)" aria-label="Zoom out">&minus;</button>
          <button id="zfit" title="The whole page (0)">Page</button>
          <button id="zink" title="Fill the frame with the type, margins off-screen (i)">Ink</button>
          <button id="zin" title="Zoom in (+)" aria-label="Zoom in">+</button>
          <span class="pct" id="zpct">100%</span>
          <button id="rccw" title="Turn anticlockwise (Shift+R)" aria-label="Turn anticlockwise">&#8634;</button>
          <button id="rcw" title="Turn clockwise (r)" aria-label="Turn clockwise">&#8635;</button>
          <button id="wide" title="Give the page the full width (w)" aria-pressed="false">Wide</button>
        </div>
        <div class="viewport" id="vp"><img id="scan" alt="" draggable="false"></div>
        <a class="act" id="open" href="#" target="_blank" rel="noopener">Open the Board&rsquo;s file at this page</a>
        <p class="hint">The whole page as the Board&rsquo;s PDF has it. Scroll to zoom, drag to pan;
        the figure is the true scale, so 100% is one screen pixel per scan pixel.
        <kbd>r</kbd> turns it (for reading only) &middot; <kbd>i</kbd> fills the frame with the type &middot;
        <kbd>0</kbd> whole page &middot;
        <kbd>z</kbd> toggle &middot; <kbd>w</kbd> full width &middot; <kbd>o</kbd> opens
        <span id="addr"></span>, the Board&rsquo;s own file.</p>
      </div>

      <div>
        <div class="transcript">
          <header><span id="fname"></span><span id="stats"></span></header>
          <pre id="text"></pre>
        </div>

        <div class="verdict">
          <button data-v="ok" aria-pressed="false">Reads correctly <span class="key">1</span></button>
          <button data-v="fix" aria-pressed="false">Needs a fix <span class="key">2</span></button>
          <button class="act ghost" id="prev">&larr; Previous</button>
          <button class="act ghost" id="next">Next &rarr;</button>
        </div>
        <div class="retier">
          <span class="retier-label">Tier</span>
          <span id="tierbtns"></span>
          <span class="retier-note" id="tiernote"></span>
        </div>
        <textarea id="note" placeholder="What is wrong, and what should it say? Quote the line. (Optional for a page that reads correctly.)"></textarea>
        <div class="foot">
          <button class="act" id="copy">Copy corrections</button>
          <span class="status" id="status">Nothing marked yet.</span>
        </div>
        <p class="hint" style="margin-top:14px">
          <kbd>j</kbd> <kbd>k</kbd> or arrows move &middot; <kbd>1</kbd> reads correctly &middot;
          <kbd>2</kbd> needs a fix &middot; <kbd>z</kbd> zoom &middot; <kbd>r</kbd> turn &middot;
          <kbd>i</kbd> fill with type &middot;
          <kbd>w</kbd> widen &middot;
          <kbd>o</kbd> the Board&rsquo;s file &middot; typing in the note box ignores shortcuts.
        </p>
      </div>
    </div>
  </main>
</div>

<script id="pages" type="application/json">__DATA__</script>
<script>
(function () {
  "use strict";
  var PAGES = JSON.parse(document.getElementById("pages").textContent);
  var KEY = "dy-ocr-check-v1";
  var state = {};
  try { state = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { state = {}; }
  var filter = "all", at = 0, view = PAGES.map(function (_, i) { return i; });

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* private window */ }
  }
  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function markup(text) {
    // the bracket conventions are what a checker scans for: make them visible
    return esc(text).replace(/\\[(illegible[^\\]]*|stamp:[^\\]]*|handwritten[^\\]]*|signature|seal[^\\]]*|graphic page|blank page|rotated page|cut|adjacent page|end adjacent page)\\]/g,
      function (m) { return "<mark>" + m + "</mark>"; });
  }

  function matches(i) {
    var p = PAGES[i], s = state[p.f];
    if (filter === "all") return true;
    if (filter === "todo") return !s || !s.v;
    return ((s && s.t) || p.t) === filter;
  }
  function rebuild() {
    view = PAGES.map(function (_, i) { return i; }).filter(matches);
    var list = el("list");
    list.textContent = "";
    view.forEach(function (i, n) {
      var p = PAGES[i], s = state[p.f] || {};
      var b = document.createElement("button");
      b.type = "button";
      b.innerHTML = '<span class="dot ' + (s.v || "") + '"></span>' +
        '<span class="who">' + esc(p.d.replace(/_/g, " ")) + '</span>' +
        '<span class="n">' + (n + 1) + "</span>";
      b.setAttribute("aria-current", i === at ? "true" : "false");
      b.addEventListener("click", function () { at = i; render(); });
      list.appendChild(b);
    });
    var done = 0, fix = 0;
    PAGES.forEach(function (p) {
      var s = state[p.f];
      if (s && s.v) { done++; if (s.v === "fix") fix++; }
    });
    el("bar").style.width = (done / PAGES.length * 100) + "%";
    el("done").textContent = done + " of 90 checked";
    el("flagged").textContent = fix + " to fix";
    el("status").textContent = done === 0 ? "Nothing marked yet."
      : done + " marked, " + fix + " needing a fix.";
  }

  function render() {
    var p = PAGES[at], s = state[p.f] || {};
    var pos = view.indexOf(at);
    el("title").textContent = p.d.replace(/_/g, " ");
    var tier = s.t || p.t;
    el("tier").textContent = tier;
    el("tier").className = "chip " + tier + (s.t ? " moved" : "");
    [].forEach.call(document.querySelectorAll(".retier button"), function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.t === tier));
    });
    el("tiernote").textContent = s.t ? "drawn as " + p.t : "";
    el("sub").innerHTML = (pos >= 0 ? "Page " + (pos + 1) + " of " + view.length : "Not in this filter") +
      '<span class="sep">|</span>' + esc(p.k) + " " + esc(p.r) +
      '<span class="sep">|</span>' + esc(p.dt) +
      (p.ty ? '<span class="sep">|</span>' + esc(p.ty) : "") +
      '<span class="sep">|</span>sheet page ' + p.pg + " of " + p.of;
    el("scan").src = "data:" + p.img.m + ";base64," + p.img.d;
    el("scan").alt = "Scanned page " + p.pg + " of " + p.d.replace(/_/g, " ");
    natural = { w: p.img.w, h: p.img.h };
    ink = p.img.c || null;
    rot = s.r || 0;
    sizeViewport();
    whenSized(fit);
    var url = "https://docketyard.org/document/" + p.sha + ".pdf#page=" + p.pg;
    el("open").href = url;
    el("addr").textContent = "/document/" + p.sha.slice(0, 10) + "\\u2026.pdf";
    el("fname").textContent = p.f;
    var lines = p.x.split("\\n").length, ill = (p.x.match(/\\[illegible/g) || []).length;
    el("stats").textContent = lines + " lines \\u00b7 " + p.x.length + " characters" +
      (ill ? " \\u00b7 " + ill + " illegible" : "");
    el("text").innerHTML = markup(p.x);
    el("note").value = s.n || "";
    [].forEach.call(document.querySelectorAll(".verdict button[data-v]"), function (b) {
      b.setAttribute("aria-pressed", String(s.v === b.dataset.v));
    });
    rebuild();
    var cur = el("list").querySelector('[aria-current="true"]');
    if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: "nearest" });
  }

  function move(d) {
    var pos = view.indexOf(at);
    if (pos < 0) { at = view[0]; }
    else { at = view[Math.max(0, Math.min(view.length - 1, pos + d))]; }
    if (at === undefined) at = 0;
    render();
  }
  function verdict(v) {
    var p = PAGES[at];
    var s = state[p.f] || (state[p.f] = {});
    s.v = s.v === v ? "" : v;
    s.n = el("note").value.trim();
    save();
    render();
  }

  [].forEach.call(document.querySelectorAll(".verdict button[data-v]"), function (b) {
    b.addEventListener("click", function () { verdict(b.dataset.v); });
  });
  ["clean", "degraded", "tabular", "graphic", "blank"].forEach(function (name) {
    var b = document.createElement("button");
    b.type = "button"; b.dataset.t = name; b.textContent = name;
    b.setAttribute("aria-pressed", "false");
    b.addEventListener("click", function () {
      var pg = PAGES[at];
      var s = state[pg.f] || (state[pg.f] = {});
      s.t = name === pg.t ? "" : name;   // choosing the drawn tier again clears the correction
      save(); render();
    });
    el("tierbtns").appendChild(b);
  });

  el("next").addEventListener("click", function () { move(1); });
  el("prev").addEventListener("click", function () { move(-1); });
  el("note").addEventListener("input", function () {
    var p = PAGES[at];
    var s = state[p.f] || (state[p.f] = {});
    s.n = el("note").value;
    save();
  });
  [].forEach.call(document.querySelectorAll("#filters button"), function (b) {
    b.addEventListener("click", function () {
      filter = b.dataset.f;
      [].forEach.call(document.querySelectorAll("#filters button"), function (o) {
        o.setAttribute("aria-pressed", String(o === b));
      });
      rebuild();
      if (view.length && view.indexOf(at) < 0) { at = view[0]; render(); }
    });
  });

  el("copy").addEventListener("click", function () {
    var out = ["OCR ground-truth check \\u2014 corrections", ""];
    var fix = 0, ok = 0, tiers = [];
    PAGES.forEach(function (pg) {
      var st = state[pg.f];
      if (st && st.t && st.t !== pg.t) tiers.push("  " + pg.f + "  " + pg.t + " -> " + st.t);
    });
    if (tiers.length) { out.push("Tier corrections (" + tiers.length + "):"); out = out.concat(tiers, [""]); }
    PAGES.forEach(function (p) {
      var s = state[p.f];
      if (!s || (!s.v && !(s.n || "").trim())) return;
      if (s.v === "ok" && !(s.n || "").trim()) { ok++; return; }
      if (s.v === "fix") fix++;
      out.push(p.f + "  [" + (s.v || "no verdict") + "]  " + p.d.replace(/_/g, " ") +
        " p." + p.pg);
      if ((s.n || "").trim()) out.push("    " + s.n.trim().replace(/\\n/g, "\\n    "));
      out.push("");
    });
    out.push(ok + " page" + (ok === 1 ? "" : "s") + " read correctly with no note; " +
      fix + " needing a fix; " + tiers.length + " re-tiered.");
    var text = out.join("\\n");
    var done = function () {
      el("status").textContent = "Corrections copied \\u2014 paste them back to Claude.";
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { window.prompt("Copy:", text); });
    } else { window.prompt("Copy:", text); }
  });

  // ---- zoom and pan: the page stays beside the transcript, so a line can be compared
  var vp = el("vp"), img = el("scan");
  var natural = { w: 1275, h: 1650 }, ink = null, rot = 0;
  var scale = 1, tx = 0, ty = 0, fitScale = 1, pending = true;

  // the page is turned for reading only — the image and the transcription are untouched.
  // With transform-origin at 0 0 a rotation swings the page out of view, so each quarter
  // turn is followed by the offset that brings its corner back to the top left.
  function dispW() { return rot % 180 ? natural.h : natural.w; }
  function dispH() { return rot % 180 ? natural.w : natural.h; }
  function dispInk() {
    if (!ink) { return null; }
    var x = ink[0], y = ink[1], w = ink[2], h = ink[3], W = natural.w, H = natural.h;
    if (rot === 90) { return [H - (y + h), x, h, w]; }
    if (rot === 180) { return [W - (x + w), H - (y + h), w, h]; }
    if (rot === 270) { return [y, W - (x + w), h, w]; }
    return [x, y, w, h];
  }

  function apply() {
    var ox = tx, oy = ty;
    if (rot === 90) { ox += natural.h * scale; }
    else if (rot === 180) { ox += natural.w * scale; oy += natural.h * scale; }
    else if (rot === 270) { oy += natural.w * scale; }
    img.style.transform =
      "translate(" + ox + "px," + oy + "px) rotate(" + rot + "deg) scale(" + scale + ")";
    el("zpct").textContent = Math.round(scale * 100) + "%";
  }
  function clamp() {
    var w = dispW() * scale, h = dispH() * scale;
    var vw = vp.clientWidth, vh = vp.clientHeight;
    tx = w <= vw ? (vw - w) / 2 : Math.min(0, Math.max(vw - w, tx));
    ty = h <= vh ? 0 : Math.min(0, Math.max(vh - h, ty));
  }
  function whenSized(cb, tries) {
    // the first measurement inside the artifact frame can land mid-layout; a viewport a
    // tenth of its final width fitted the page to a tenth of its size (2026-08-29)
    tries = tries || 0;
    if ((vp.clientWidth > 120 && vp.clientHeight > 120) || tries > 40) { cb(); return; }
    requestAnimationFrame(function () { whenSized(cb, tries + 1); });
  }
  function sizeViewport() {
    // measured, not `vh`: the frame's viewport units cannot be trusted here
    var wide = document.querySelector(".pair").classList.contains("widepage");
    var room = (window.innerHeight || 800) - (wide ? 150 : 190);
    vp.style.height = Math.max(340, Math.min(wide ? 1100 : 920, room)) + "px";
  }
  function measured() { return vp.clientWidth > 60 && vp.clientHeight > 60; }
  function fit() {
    if (!measured()) { pending = true; return; }
    pending = false;
    fitScale = Math.min(vp.clientWidth / dispW(), vp.clientHeight / dispH());
    scale = fitScale; tx = 0; ty = 0; clamp(); apply();
  }
  function refit() {
    // the box changed size: keep the reader where they were, at the same magnification
    if (!measured()) return;
    if (pending) { fit(); return; }
    var ratio = fitScale > 0 ? scale / fitScale : 1;
    fitScale = Math.min(vp.clientWidth / dispW(), vp.clientHeight / dispH());
    if (ratio > 1.02) { scale = fitScale * ratio; } else { scale = fitScale; tx = 0; ty = 0; }
    clamp(); apply();
  }
  function zoomTo(next, cx, cy) {
    next = Math.max(fitScale, Math.min(fitScale * 8, next));
    if (cx === undefined) { cx = vp.clientWidth / 2; cy = vp.clientHeight / 2; }
    tx = cx - (cx - tx) * (next / scale);
    ty = cy - (cy - ty) * (next / scale);
    scale = next; clamp(); apply();
  }
  function toInk() {
    var box = dispInk();
    if (!box || !measured()) { fit(); return; }
    var s = Math.min(vp.clientWidth / box[2], vp.clientHeight / box[3]);
    scale = Math.max(fitScale, Math.min(fitScale * 8, s));
    tx = -box[0] * scale + (vp.clientWidth - box[2] * scale) / 2;
    ty = -box[1] * scale + (vp.clientHeight - box[3] * scale) / 2;
    clamp(); apply();
  }
  function turn(by) {
    var ratio = fitScale > 0 ? scale / fitScale : 1;
    rot = (rot + by + 360) % 360;
    var pg = PAGES[at];
    var s = state[pg.f] || (state[pg.f] = {});
    if (rot) { s.r = rot; } else { delete s.r; }
    save();
    fit();
    if (ratio > 1.02) { zoomTo(fitScale * ratio); }
  }
  el("rcw").addEventListener("click", function () { turn(90); });
  el("rccw").addEventListener("click", function () { turn(-90); });
  el("zink").addEventListener("click", toInk);
  el("zin").addEventListener("click", function () { zoomTo(scale * 1.5); });
  el("zout").addEventListener("click", function () { zoomTo(scale / 1.5); });
  el("zfit").addEventListener("click", fit);
  el("wide").addEventListener("click", function () {
    var pair = document.querySelector(".pair");
    var on = !pair.classList.contains("widepage");
    pair.classList.toggle("widepage", on);
    el("wide").setAttribute("aria-pressed", String(on));
    setTimeout(function () { sizeViewport(); fit(); }, 0);
  });
  vp.addEventListener("wheel", function (e) {
    e.preventDefault();
    var r = vp.getBoundingClientRect();
    zoomTo(scale * (e.deltaY < 0 ? 1.18 : 1 / 1.18), e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });
  vp.addEventListener("dblclick", function (e) {
    var r = vp.getBoundingClientRect();
    if (scale > fitScale * 1.02) fit();
    else zoomTo(1, e.clientX - r.left, e.clientY - r.top);
  });
  (function drag() {
    var down = false, sx = 0, sy = 0, ox = 0, oy = 0;
    vp.addEventListener("pointerdown", function (e) {
      down = true; sx = e.clientX; sy = e.clientY; ox = tx; oy = ty;
      vp.classList.add("dragging"); vp.setPointerCapture(e.pointerId);
    });
    vp.addEventListener("pointermove", function (e) {
      if (!down) return;
      tx = ox + (e.clientX - sx); ty = oy + (e.clientY - sy); clamp(); apply();
    });
    ["pointerup", "pointercancel"].forEach(function (ev) {
      vp.addEventListener(ev, function () { down = false; vp.classList.remove("dragging"); });
    });
  })();
  img.addEventListener("load", function () { if (pending) { fit(); } });
  window.addEventListener("resize", function () { sizeViewport(); refit(); });
  if (window.ResizeObserver) { new ResizeObserver(refit).observe(vp); }
  requestAnimationFrame(function () { sizeViewport(); if (pending) { fit(); } });

  document.addEventListener("keydown", function (e) {
    var t = e.target.tagName;
    if (t === "TEXTAREA" || t === "INPUT" || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "1") { verdict("ok"); }
    else if (e.key === "2") { verdict("fix"); }
    else if (e.key === "o") { window.open(el("open").href, "_blank", "noopener"); }
    else if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomTo(scale * 1.5); }
    else if (e.key === "-" || e.key === "_") { e.preventDefault(); zoomTo(scale / 1.5); }
    else if (e.key === "0") { fit(); }
    else if (e.key === "z") { if (scale > fitScale * 1.02) { fit(); } else { zoomTo(1); } }
    else if (e.key === "w") { el("wide").click(); }
    else if (e.key === "i") { toInk(); }
    else if (e.key === "r") { turn(90); }
    else if (e.key === "R") { turn(-90); }
  });

  render();
})();
</script>
"""

OUT.write_text(HTML.replace("__DATA__", DATA), encoding="utf-8", newline="\n")
print("wrote", OUT, round(OUT.stat().st_size / 1e6, 2), "MB;", len(items), "pages")
