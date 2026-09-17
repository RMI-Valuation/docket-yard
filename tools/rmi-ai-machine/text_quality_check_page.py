"""Build the text-layer quality check queue (docs/research/text-quality).

One page per sampled page: the scan beside the text layer the site actually shows for it,
the drafted judgements, and the chips to agree with or overrule them. Verdicts and notes
stay in the reader's browser; "Copy corrections" hands them back in one block.

THREE AXES, BECAUSE THE FIRST RUBRIC CONFLATED TWO OF THEM (the operator, 2026-09-17). A
page's KIND (prose, table, map, drawing, form) is not a verdict on its text; a table whose
values all came through with its grid destroyed is `table` + `clean` + `ordered`, and the
first pass had no way to say that — its `nontext` label meant "not prose AND faithfully
carried", which files a broken grid as a success and a garbled map as a text failure. The
benchmark already scores those separately (`ocr_score.py`: CER for the words, cell recall
for the grid; qwen3-vl:32b reads the tabular tier at 5.6% CER with 0% cell recall), so the
labels now match that convention.

A page the first pass called `nontext` therefore carries NO drafted quality: the old label
cannot be translated into the new one without inventing a judgement nobody made.

THE SCORE IS NOT ON THE PAGE, deliberately. The sample was drawn by score band and the
draft labels were made blind to it; showing it here would anchor the check against the very
signal the check exists to test. The band is joined back from `sample.json` afterwards.

Takes the sample and the drafted labels from `docs/research/text-quality/`, and the page
renders and stored readings from the session scratchpad — one `<label_id>.jpg` at 150 DPI and
one `<label_id>.txt` (the reading as `document_text_display` shows it) per page. A draft row is
`{quality, kind, structure, note, conflict}`; `conflict` is set when two blind passes disagreed.

    python tools/rmi-ai-machine/text_quality_check_page.py         sample.json drafts.json <txt-dir> <img-dir> out.html "rail subtitle"
"""

# ruff: noqa: E501 — an HTML document lives in this file; its CSS and markup keep their own
# line lengths, and reflowing them to the code width would only make them harder to read.

import json
import sys
from base64 import b64encode
from pathlib import Path

QUALITY = [
    ("clean", "1", "the page's words, errors rare"),
    ("noisy", "2", "readable, wrong several times a paragraph"),
    ("garbage", "3", "most of it not legibly reproduced"),
    ("partial", "4", "accurate, but most of the page missing"),
    ("mismatch", "5", "text belongs to another page"),
]
KIND = [
    ("prose", "Q", "running text"),
    ("table", "W", "a grid whose columns carry meaning"),
    ("map", "E", "a map or plan with place labels"),
    ("drawing", "R", "engineering, CAD or figure"),
    ("form", "T", "printed form, cover sheet, stamps"),
    ("mixed", "Y", "two of these share the page"),
]
STRUCTURE = [
    ("grid", "Z", "rows and columns survive"),
    ("ordered", "X", "values in reading order, grid gone"),
    ("scrambled", "C", "values out of order, rows unfollowable"),
    ("absent", "V", "the values are not in the text"),
]
# the first pass's label that mixed kind with quality; it drafts a kind, never a quality
OLD_NONTEXT = "nontext"


def page_items(sample: dict, drafts: dict, txt: Path, img: Path) -> list[dict]:
    """The rows the page renders. `drafts[id]` carries `quality`, `kind`, `structure` and a
    `note`; a `conflict` string is shown when two independent passes disagreed, because a
    page two readers read differently is the one worth a person's minute."""
    # THE SHEET IS A SUBSET OF ITS SAMPLE, and says which. The top-up's check holds the 7
    # pages two blind passes read differently plus a random 24 they agreed on, out of 102
    # labelled; a draft row is what puts a page on the sheet.
    items = []
    for lid in sorted(drafts, key=lambda k: int(k[1:])):
        if lid not in sample:
            raise KeyError(f"{lid} has a draft but is not in the sample")
        p, d = sample[lid], drafts[lid]
        q = d.get("quality")
        items.append(
            {
                "id": lid,
                "sha": p["sha"],
                "pg": p["page"],
                "yr": p["year"],
                "rec": p["kinds"],
                "dq": None if q == OLD_NONTEXT else q,
                "dk": d["kind"],
                "ds": d.get("structure") if d.get("structure") not in (None, "n/a") else None,
                "kn": d.get("note", ""),
                "cf": d.get("conflict", ""),
                "t": (txt / f"{lid}.txt").read_text(encoding="utf-8"),
                # THE SCAN TRAVELS IN THE PAGE. A published artifact's supporting files are
                # fetched per image, and one self-contained file is also what the earlier
                # check sheets hand over; 150 DPI grey JPEG keeps 64 pages inside the limit.
                "img": "data:image/jpeg;base64,"
                + b64encode((img / f"{lid}.jpg").read_bytes()).decode(),
            }
        )
    return items


def build(items: list[dict], title: str, intro: str) -> str:
    data = (
        json.dumps(items, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028")
    )

    def axis(rows):
        return json.dumps([{"k": k, "key": key, "d": d} for k, key, d in rows])

    return (
        HTML.replace("__DATA__", data)
        .replace("__TITLE__", title)
        .replace("__INTRO__", intro)
        .replace("__QUALITY__", axis(QUALITY))
        .replace("__KIND__", axis(KIND))
        .replace("__STRUCTURE__", axis(STRUCTURE))
    )


HTML = """<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&family=Source+Sans+3:wght@400;600;700&display=swap">
<style>
  :root {
    --paper: #f6f5f2; --panel: #fffefb; --ink: #1a1c20; --soft: #5c5f68; --faint: #8a8d96;
    --rule: #dcd9d3; --rule-firm: #c3bfb6; --accent: #3a3f7d; --accent-soft: #ececf6;
    --alert: #9d3a30; --ok: #2f6b46; --scan: #e8e6e1;
    --shadow: 0 1px 2px rgba(26,28,32,.06), 0 8px 24px -16px rgba(26,28,32,.28);
  }
  :root:not([data-theme="light"]) { color-scheme: light dark; }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --paper: #15161a; --panel: #1c1e23; --ink: #e9e7e2; --soft: #a7abb5; --faint: #7c8089;
      --rule: #2e3037; --rule-firm: #3d4048; --accent: #9aa1e4; --accent-soft: #23263a;
      --alert: #e0897b; --ok: #7fbf9a; --scan: #0f1013;
      --shadow: 0 1px 2px rgba(0,0,0,.5), 0 10px 30px -18px rgba(0,0,0,.8);
    }
  }
  :root[data-theme="dark"] {
    --paper: #15161a; --panel: #1c1e23; --ink: #e9e7e2; --soft: #a7abb5; --faint: #7c8089;
    --rule: #2e3037; --rule-firm: #3d4048; --accent: #9aa1e4; --accent-soft: #23263a;
    --alert: #e0897b; --ok: #7fbf9a; --scan: #0f1013;
    --shadow: 0 1px 2px rgba(0,0,0,.5), 0 10px 30px -18px rgba(0,0,0,.8);
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--paper); color: var(--ink); font: 400 16px/1.55 "Source Sans 3", ui-sans-serif, system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
  .shell { display: grid; grid-template-columns: 250px minmax(0, 1fr); min-height: 100vh; }
  .rail { border-right: 1px solid var(--rule); background: var(--panel); display: flex; flex-direction: column; height: 100vh; position: sticky; top: env(safe-area-inset-top, 0px); }
  .rail-head { padding: 16px 16px 12px; border-bottom: 1px solid var(--rule); }
  .wordmark { font-family: Newsreader, Georgia, serif; font-size: 19px; font-weight: 600; margin: 0 0 2px; }
  .rail-head p { margin: 0; font-size: 12.5px; color: var(--faint); }
  .meter { height: 4px; background: var(--rule); border-radius: 2px; margin-top: 12px; overflow: hidden; }
  .meter span { display: block; height: 100%; background: var(--accent); width: 0; transition: width .25s ease; }
  .meter-note { display: flex; justify-content: space-between; font-size: 12px; color: var(--soft); margin-top: 6px; font-variant-numeric: tabular-nums; }
  .filters { display: flex; flex-wrap: wrap; gap: 4px; padding: 10px 14px; border-bottom: 1px solid var(--rule); }
  .filters button { font: inherit; font-size: 11.5px; letter-spacing: .04em; text-transform: uppercase; background: none; border: 1px solid var(--rule-firm); color: var(--soft); padding: 3px 8px; border-radius: 3px; cursor: pointer; }
  .filters button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--panel); }
  .list { overflow-y: auto; flex: 1; padding: 6px 0 24px; }
  .list button { width: 100%; display: grid; grid-template-columns: 8px 1fr auto; gap: 9px; align-items: center; background: none; border: 0; border-bottom: 1px solid var(--rule); padding: 9px 14px; text-align: left; font: inherit; font-size: 13.5px; color: var(--ink); cursor: pointer; }
  .list button[aria-current="true"] { background: var(--accent-soft); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--rule-firm); }
  .dot.done { background: var(--ok); }
  .dot.changed { background: var(--alert); }
  .list .who { font-size: 11.5px; color: var(--faint); text-transform: uppercase; letter-spacing: .03em; }
  main { padding: 20px 20px 64px; min-width: 0; }
  .head { display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: baseline; border-bottom: 1px solid var(--rule); padding-bottom: 12px; }
  .head h1 { font-family: Newsreader, Georgia, serif; font-size: 25px; margin: 0; font-weight: 600; }
  .meta { font-size: 13px; color: var(--soft); font-variant-numeric: tabular-nums; }
  .meta a { color: var(--accent); }
  .pair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18px; margin-top: 16px; align-items: start; }
  .col h2, .axis h2 { font-size: 11.5px; letter-spacing: .07em; text-transform: uppercase; color: var(--faint); margin: 0 0 8px; font-weight: 700; }
  .col h2 span { text-transform: none; letter-spacing: 0; }
  .scan { background: var(--scan); border: 1px solid var(--rule); border-radius: 3px; padding: 8px; box-shadow: var(--shadow); }
  .scan img { display: block; width: 100%; max-width: 100%; cursor: zoom-in; }
  .scan.zoom { overflow: auto; }
  .scan.zoom img { width: auto; max-width: none; cursor: zoom-out; }
  pre.text { margin: 0; background: var(--panel); border: 1px solid var(--rule); border-radius: 3px; padding: 12px 14px; font: 400 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 78vh; overflow: auto; box-shadow: var(--shadow); }
  .verdict { margin-top: 20px; border-top: 1px solid var(--rule); padding-top: 14px; display: grid; gap: 16px; }
  .axis { display: grid; gap: 7px; }
  .axis .why { margin: 0; font-size: 13px; color: var(--soft); }
  .axis .why b { color: var(--ink); }
  .axis[data-off="true"] { opacity: .45; }
  .chips { display: flex; flex-wrap: wrap; gap: 7px; }
  .chips button { font: inherit; font-size: 14px; background: var(--panel); border: 1px solid var(--rule-firm); color: var(--ink); padding: 6px 11px; border-radius: 3px; cursor: pointer; display: flex; gap: 7px; align-items: baseline; }
  .chips button small { color: var(--faint); font-size: 12px; }
  .chips button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--panel); }
  .chips button[aria-pressed="true"] small { color: var(--accent-soft); }
  .chips kbd, .note kbd { font: inherit; font-size: 11px; color: var(--faint); border: 1px solid var(--rule); border-radius: 2px; padding: 0 4px; }
  textarea { width: 100%; min-height: 60px; font: inherit; font-size: 14px; background: var(--panel); color: var(--ink); border: 1px solid var(--rule-firm); border-radius: 3px; padding: 9px 11px; resize: vertical; }
  .acts { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  .act { font: inherit; font-size: 14px; background: var(--panel); border: 1px solid var(--rule-firm); color: var(--ink); padding: 7px 14px; border-radius: 3px; cursor: pointer; }
  .act.primary { background: var(--accent); border-color: var(--accent); color: var(--panel); }
  .said { font-size: 13px; color: var(--ok); }
  .note { font-size: 13px; color: var(--soft); max-width: 70ch; margin: 0; }
  button:focus-visible, textarea:focus-visible, .list button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  @media (max-width: 860px) {
    .shell { grid-template-columns: 1fr; }
    .rail { position: static; height: auto; max-height: 45vh; border-right: 0; border-bottom: 1px solid var(--rule); }
    .pair { grid-template-columns: 1fr; }
    main { padding: 16px 16px 48px; }
    pre.text { max-height: 50vh; }
  }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="shell">
  <nav class="rail">
    <div class="rail-head">
      <p class="wordmark">Text layer check</p>
      <p>__INTRO__</p>
      <div class="meter"><span id="bar"></span></div>
      <div class="meter-note"><span id="count">0 of 64</span><span id="changed"></span></div>
    </div>
    <div class="filters">
      <button data-filter="all" aria-pressed="true">All</button>
      <button data-filter="todo" aria-pressed="false">To do</button>
      <button data-filter="changed" aria-pressed="false">Changed</button>
    </div>
    <div class="list" id="list"></div>
  </nav>
  <main>
    <div class="head">
      <h1 id="title">L01</h1>
      <span class="meta" id="meta"></span>
      <span class="meta"><a id="board" href="#" target="_blank" rel="noopener">the Board's file</a></span>
    </div>
    <p class="note" id="intro">Does the text reproduce what is printed on the page? Judge it against the scan, not against what the document ought to say. Three separate questions: what the page <em>is</em>, how well its words came through, and — for a table — whether the grid survived. The signal's score is deliberately not shown.</p>
    <div class="pair">
      <div class="col">
        <h2>The scan <span>— click to zoom</span></h2>
        <div class="scan" id="scanbox"><img id="scan" alt="the scanned page" /></div>
      </div>
      <div class="col">
        <h2>What the site shows as this page's text</h2>
        <pre class="text" id="text"></pre>
      </div>
    </div>
    <div class="verdict">
      <p class="note" id="conflict" hidden></p>
      <div class="axis" id="axis-kind">
        <h2>What the page is</h2>
        <div class="chips" id="chips-kind"></div>
        <p class="why" id="why-kind"></p>
      </div>
      <div class="axis" id="axis-quality">
        <h2>How well its words came through</h2>
        <div class="chips" id="chips-quality"></div>
        <p class="why" id="why-quality"></p>
      </div>
      <div class="axis" id="axis-structure">
        <h2>The table's structure</h2>
        <div class="chips" id="chips-structure"></div>
        <p class="why" id="why-structure"></p>
      </div>
      <textarea id="note" placeholder="A note, if a judgement needs one (optional)"></textarea>
      <div class="acts">
        <button class="act" id="prev">← Previous</button>
        <button class="act" id="next">Next →</button>
        <button class="act" id="agree">Agree with all three</button>
        <button class="act primary" id="copy">Copy corrections</button>
        <span class="said" id="said"></span>
      </div>
      <p class="note">Keys: <kbd>1</kbd>–<kbd>5</kbd> words, <kbd>Q</kbd>–<kbd>Y</kbd> page, <kbd>Z</kbd>–<kbd>V</kbd> table structure, <kbd>Enter</kbd> agrees with every drafted answer, <kbd>J</kbd>/<kbd>K</kbd> move. A page counts as done once what it <em>is</em> and how its words came through are both set. Your answers stay in this browser until you copy them.</p>
    </div>
  </main>
</div>

<script>
  const ITEMS = __DATA__;
  const AXES = { quality: __QUALITY__, kind: __KIND__, structure: __STRUCTURE__ };
  const DRAFT = { quality: "dq", kind: "dk", structure: "ds" };
  const KEY = "dy-text-quality-check-v2";
  let state = {};
  try { state = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { state = {}; }
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };
  let at = 0, filter = "all";

  const listEl = document.getElementById("list");
  const noteEl = document.getElementById("note");
  const saidEl = document.getElementById("said");

  Object.keys(AXES).forEach(axis => {
    const box = document.getElementById("chips-" + axis);
    AXES[axis].forEach(opt => {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.value = opt.k;
      b.innerHTML = '<kbd>' + opt.key + '</kbd><span>' + opt.k + '</span><small>' + opt.d + '</small>';
      b.addEventListener("click", () => pick(axis, opt.k));
      box.appendChild(b);
    });
  });

  const answered = it => {
    const s = state[it.id];
    return !!(s && s.kind && s.quality);
  };
  // a row may hold a note and no verdict; `answered` is what the meter and the filters count
  const differs = it => {
    const s = state[it.id];
    if (!s) return false;
    return (s.quality && s.quality !== it.dq) || (s.kind && s.kind !== it.dk) ||
           (s.structure && s.structure !== it.ds);
  };

  function visible() {
    return ITEMS.filter(it => {
      if (filter === "todo") return !answered(it);
      if (filter === "changed") return differs(it);
      return true;
    });
  }

  function drawList() {
    listEl.textContent = "";
    visible().forEach(it => {
      const b = document.createElement("button");
      b.type = "button";
      const cls = !answered(it) ? "" : (differs(it) ? " changed" : " done");
      const s = state[it.id] || {};
      const shown = (s.kind || it.dk) + " · " + (s.quality || it.dq || "—");
      b.innerHTML = '<span class="dot' + cls + '"></span><span>' + it.id + ' · ' + (it.yr || "undated") + '</span><span class="who">' + shown + '</span>';
      b.setAttribute("aria-current", ITEMS[at] && ITEMS[at].id === it.id ? "true" : "false");
      b.addEventListener("click", () => { at = ITEMS.indexOf(it); draw(); });
      listEl.appendChild(b);
    });
    const done = ITEMS.filter(answered).length;
    const changed = ITEMS.filter(differs).length;
    document.getElementById("bar").style.width = (100 * done / ITEMS.length) + "%";
    document.getElementById("count").textContent = done + " of " + ITEMS.length;
    document.getElementById("changed").textContent = changed ? changed + " changed" : "";
  }

  function draw() {
    const it = ITEMS[at], s = state[it.id] || {};
    document.getElementById("title").textContent = it.id;
    document.getElementById("meta").textContent = "page " + it.pg + " · " + (it.yr || "undated") + " · " + it.rec;
    document.getElementById("board").href = "https://docketyard.org/document/" + it.sha + ".pdf#page=" + it.pg;
    const img = document.getElementById("scan");
    img.src = it.img;
    img.alt = "page " + it.pg + " as scanned";
    document.getElementById("scanbox").classList.remove("zoom");
    document.getElementById("text").textContent = it.t;
    const cf = document.getElementById("conflict");
    cf.hidden = !it.cf;
    if (it.cf) cf.innerHTML = '<b>Two readers disagreed here:</b> ' + it.cf;

    Object.keys(AXES).forEach(axis => {
      const chosen = s[axis], drafted = it[DRAFT[axis]];
      [...document.getElementById("chips-" + axis).children].forEach(b =>
        b.setAttribute("aria-pressed", chosen === b.dataset.value ? "true" : "false"));
      const why = document.getElementById("why-" + axis);
      if (axis === "structure") {
        const isTable = (chosen || s.kind || it.dk) === "table" || (s.kind || it.dk) === "mixed";
        document.getElementById("axis-structure").dataset.off = isTable ? "false" : "true";
        why.innerHTML = isTable
          ? (drafted ? 'Drafted: <b>' + drafted + '</b>. The test is whether a cell\\u2019s column still tells you what the cell is.'
                     : 'Nothing drafted. The test is whether a cell\\u2019s column still tells you what the cell is.')
          : 'Only for a table; leave it unset.';
        return;
      }
      if (axis === "quality" && !drafted) {
        why.innerHTML = 'Nothing drafted: the first pass called this page <b>nontext</b>, a label that mixed what the page is with how well it read. Yours is the first judgement of its words.';
        return;
      }
      why.innerHTML = 'Drafted: <b>' + drafted + '</b>' + (axis === "kind" && it.kn ? ' \\u2014 ' + it.kn : '') + '. Agree, or overrule it.';
    });

    noteEl.value = s.note || "";
    saidEl.textContent = "";
    drawList();
  }

  function pick(axis, value) {
    const it = ITEMS[at];
    const s = state[it.id] || (state[it.id] = { note: noteEl.value.trim() });
    s[axis] = s[axis] === value ? undefined : value;
    save();
    draw();
  }

  function agreeAll() {
    const it = ITEMS[at];
    const s = state[it.id] || (state[it.id] = { note: noteEl.value.trim() });
    if (it.dq) s.quality = it.dq;
    s.kind = it.dk;
    if (it.ds) s.structure = it.ds;
    save();
    draw();
    if (at < ITEMS.length - 1) { at++; draw(); }
  }

  // A NOTE IS KEPT EVEN WITH NO VERDICT YET. `state[id]` used to be created only by a chip,
  // so a note typed on an untouched page was dropped on the way out (review, 2026-09-17).
  function keepNote(it) {
    const v = noteEl.value.trim();
    if (!v && !state[it.id]) return;
    (state[it.id] || (state[it.id] = {})).note = v;
    save();
  }

  function move(d) {
    const it = ITEMS[at];
    keepNote(it);
    at = Math.max(0, Math.min(ITEMS.length - 1, at + d));
    draw();
  }

  document.getElementById("prev").addEventListener("click", () => move(-1));
  document.getElementById("next").addEventListener("click", () => move(1));
  document.getElementById("agree").addEventListener("click", agreeAll);
  document.getElementById("scanbox").addEventListener("click", e => {
    if (e.target.tagName === "IMG") e.currentTarget.classList.toggle("zoom");
  });
  noteEl.addEventListener("blur", () => keepNote(ITEMS[at]));
  [...document.querySelectorAll(".filters button")].forEach(b => {
    b.addEventListener("click", () => {
      filter = b.dataset.filter;
      [...document.querySelectorAll(".filters button")].forEach(o => o.setAttribute("aria-pressed", String(o === b)));
      drawList();
    });
  });

  document.getElementById("copy").addEventListener("click", () => {
    const rows = ITEMS.filter(it => state[it.id]).map(it => {
      const s = state[it.id];
      return {
        id: it.id, kind: s.kind || null, quality: s.quality || null, structure: s.structure || null,
        drafted: { kind: it.dk, quality: it.dq, structure: it.ds },
        note: s.note || ""
      };
    });
    const text = "text-layer labels, checked " + new Date().toISOString().slice(0, 10) + "\\n" + JSON.stringify(rows, null, 1);
    const done = () => { saidEl.textContent = "Copied " + rows.length + " pages."; };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, () => window.prompt("Copy:", text));
    } else { window.prompt("Copy:", text); }
  });

  document.addEventListener("keydown", e => {
    if (e.target.tagName === "TEXTAREA" || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "Enter") { agreeAll(); e.preventDefault(); return; }
    for (const axis of Object.keys(AXES)) {
      const hit = AXES[axis].find(o => o.key.toLowerCase() === e.key.toLowerCase());
      if (hit) { pick(axis, hit.k); e.preventDefault(); return; }
    }
    if (e.key === "j" || e.key === "ArrowDown" || e.key === "ArrowRight") { move(1); e.preventDefault(); }
    if (e.key === "k" || e.key === "ArrowUp" || e.key === "ArrowLeft") { move(-1); e.preventDefault(); }
  });

  draw();
</script>
"""


if __name__ == "__main__":
    # sample.json  drafts.json  txt-dir  img-dir  out.html  "rail subtitle"
    # a sample file is a list of pages, or an object carrying them under `pages` beside the
    # population counts the estimate needs (the top-up's shape)
    raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    sample = {p["label_id"]: p for p in (raw["pages"] if isinstance(raw, dict) else raw)}
    drafts = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    items = page_items(sample, drafts, Path(sys.argv[3]), Path(sys.argv[4]))
    out = Path(sys.argv[5])
    out.write_text(build(items, "Text Layer Check", sys.argv[6]), encoding="utf-8")
    print(f"{out} ({out.stat().st_size / 1024:.0f} KB) {len(items)} of {len(sample)} sampled pages")
