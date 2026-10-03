#!/usr/bin/env python3
"""Build the BLIND kind sheet for the flagged pages (docs/research/text-quality).

    python3 kinds_check_sheet.py kinds-flagged-sample.json <img-dir> <text.json> out.html

ONE QUESTION, and it is the sample's own: of the pages the prose screen ORDERS, what kind is
each page? The kind vocabulary is the one the earlier passes used (`text_quality_check_page.py`),
so these labels sit beside `labels-checked.json` and `topup-labels-checked.json` without
translation. Quality and structure are NOT asked: the screen being measured here sorts pages by
what they ARE, and a sheet that asks three questions gets three tired answers.

BLIND BY CONSTRUCTION, NOT BY FLAG. `kinds-flagged-sample.json` carries each page's `good`
score, the screen's own `screen_prose` verdict and the layout features the screen reads — it
must, or the draw is not reproducible and the scoring afterwards is impossible. None of the
three may reach the reader: this sheet measures whether the screen is right, and a reader who
can see the screen's answer is no longer measuring it. `SHOWN` below is the whitelist of sample
fields that reach the page, applied once at the entry point, so a later edit of the template
cannot leak the screen by naming a key. The scoring pass joins the verdicts back to the sample
afterwards, by `label_id`.

Model labels are a screen, never a measurement (the operator, twice over: the 64-page pass
drafted kinder than his check, the top-up's two blind passes harsher). NOTHING IS DRAFTED HERE
— there is no "agree" button, because there is nothing to agree with. Every kind on this sheet
is the operator's own, typed against the page.

The images are the renders from the fleet box (150 DPI grey JPEG, the whole page, never
cropped, as `ocr_page_images.py` argues); `text.json` is `{label_id: {"text": ...}}` as
`document_text_display` shows the page — the display rule itself, read from the store, never a
second copy of it.
"""

# ruff: noqa: E501 — an HTML document lives in this file; its CSS and markup keep their own
# line lengths, and reflowing them to the code width would only make them harder to read.

import json
import sys
from base64 import b64encode
from pathlib import Path

KIND = [
    ("prose", "Q", "running text"),
    ("table", "W", "a grid whose columns carry meaning"),
    ("map", "E", "a map or plan with place labels"),
    ("drawing", "R", "engineering, CAD or figure"),
    ("form", "T", "printed form, cover sheet, stamps"),
    ("mixed", "Y", "two of these share the page"),
]
# The ONLY sample fields a reader may see. `good`, `screen_prose` and `layout` are the screen
# under test and are deliberately absent; `kinds` is the RECORD's own type (filing, decision),
# not a verdict about the page, and every earlier sheet here showed it.
SHOWN = ("label_id", "sha", "page", "year", "kinds")


def page_items(pages: list[dict], img: Path, texts: dict) -> list[dict]:
    """One row per sampled page, carrying `SHOWN` and nothing else."""
    items = []
    for p in sorted(pages, key=lambda r: int(r["label_id"][1:])):
        lid = p["label_id"]
        got = texts.get(lid)
        if got is None:
            raise KeyError(f"{lid} is in the sample and has no text")
        text = got if isinstance(got, str) else got.get("text")
        if text is None:
            raise KeyError(f"{lid} has a text row carrying no text: {got!r}")
        shot = img / f"{lid}.jpg"
        if not shot.exists():
            raise FileNotFoundError(f"{lid} is in the sample and has no render at {shot}")
        items.append(
            {
                "id": lid,
                "sha": p["sha"],
                "pg": p["page"],
                "yr": p["year"],
                "rec": p["kinds"],
                "t": text,
                # THE SCAN TRAVELS IN THE PAGE, as it does in every other sheet here: one
                # self-contained file is what the operator is handed, and a per-image fetch is
                # what a published artifact would otherwise do.
                "img": "data:image/jpeg;base64," + b64encode(shot.read_bytes()).decode(),
            }
        )
    return items


def build(items: list[dict], intro: str) -> str:
    data = (
        json.dumps(items, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028")
    )
    kinds = json.dumps([{"k": k, "key": key, "d": d} for k, key, d in KIND])
    return HTML.replace("__DATA__", data).replace("__INTRO__", intro).replace("__KIND__", kinds)


HTML = """<title>Flagged Page Kinds</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&family=Source+Sans+3:wght@400;600;700&display=swap">
<style>
  :root {
    --paper: #f6f5f2; --panel: #fffefb; --ink: #1a1c20; --soft: #5c5f68; --faint: #8a8d96;
    --rule: #dcd9d3; --rule-firm: #c3bfb6; --accent: #3a3f7d; --accent-soft: #ececf6;
    --ok: #2f6b46; --scan: #e8e6e1;
    --shadow: 0 1px 2px rgba(26,28,32,.06), 0 8px 24px -16px rgba(26,28,32,.28);
  }
  :root:not([data-theme="light"]) { color-scheme: light dark; }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --paper: #15161a; --panel: #1c1e23; --ink: #e9e7e2; --soft: #a7abb5; --faint: #7c8089;
      --rule: #2e3037; --rule-firm: #3d4048; --accent: #9aa1e4; --accent-soft: #23263a;
      --ok: #7fbf9a; --scan: #0f1013;
      --shadow: 0 1px 2px rgba(0,0,0,.5), 0 10px 30px -18px rgba(0,0,0,.8);
    }
  }
  :root[data-theme="dark"] {
    --paper: #15161a; --panel: #1c1e23; --ink: #e9e7e2; --soft: #a7abb5; --faint: #7c8089;
    --rule: #2e3037; --rule-firm: #3d4048; --accent: #9aa1e4; --accent-soft: #23263a;
    --ok: #7fbf9a; --scan: #0f1013;
    --shadow: 0 1px 2px rgba(0,0,0,.5), 0 10px 30px -18px rgba(0,0,0,.8);
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--paper); color: var(--ink); font: 400 16px/1.55 "Source Sans 3", ui-sans-serif, system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
  .shell { display: grid; grid-template-columns: 250px minmax(0, 1fr); min-height: 100vh; }
  .rail { border-right: 1px solid var(--rule); background: var(--panel); display: flex; flex-direction: column; height: 100vh; position: sticky; top: env(safe-area-inset-top, 0px); }
  .rail-head { padding: 16px 16px 12px; border-bottom: 1px solid var(--rule); }
  .wordmark { font-family: Newsreader, Georgia, serif; font-size: 19px; font-weight: 600; margin: 0 0 2px; color: var(--ink); }
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
      <p class="wordmark">Flagged page kinds</p>
      <p>__INTRO__</p>
      <div class="meter"><span id="bar"></span></div>
      <div class="meter-note"><span id="count">0</span><span id="left"></span></div>
    </div>
    <div class="filters">
      <button data-filter="all" aria-pressed="true">All</button>
      <button data-filter="todo" aria-pressed="false">To do</button>
      <button data-filter="done" aria-pressed="false">Done</button>
    </div>
    <div class="list" id="list"></div>
  </nav>
  <main>
    <div class="head">
      <h1 id="title">K01</h1>
      <span class="meta" id="meta"></span>
      <span class="meta"><a id="board" href="#" target="_blank" rel="noopener">the Board's file</a></span>
    </div>
    <p class="note" id="intro">One question: <b>what is this page?</b> Judge it from the scan — the text beside it is what the site shows for the page, there so you can see what was made of it, not so you can grade it. Nothing is drafted and no score is shown: these labels are the measurement, and what the screen said about each page is joined back afterwards.</p>
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
      <div class="axis">
        <h2>What the page is</h2>
        <div class="chips" id="chips-kind"></div>
        <p class="note">A page is <b>mixed</b> when two of these genuinely share it — a table under a page of argument, a map with a paragraph beside it — not when a heading sits above prose.</p>
      </div>
      <textarea id="note" placeholder="A note, if the kind needs one (optional)"></textarea>
      <div class="acts">
        <button class="act" id="prev">&larr; Previous</button>
        <button class="act" id="next">Next &rarr;</button>
        <button class="act primary" id="copy">Copy kinds</button>
        <span class="said" id="said"></span>
      </div>
      <p class="note">Keys: <kbd>Q</kbd>&ndash;<kbd>Y</kbd> pick a kind and move on, <kbd>J</kbd>/<kbd>K</kbd> move without answering. Your answers stay in this browser until you copy them.</p>
    </div>
  </main>
</div>

<script>
  const ITEMS = __DATA__;
  const KINDS = __KIND__;
  // the browser slot these verdicts live in until they are copied out; named SLOT rather
  // than KEY because the secret scanner reads `const KEY = "..."` as a credential
  const SLOT = "dy-kinds-flagged-v1";
  let state = {};
  try { state = JSON.parse(localStorage.getItem(SLOT) || "{}") || {}; } catch (e) { state = {}; }
  const save = () => { try { localStorage.setItem(SLOT, JSON.stringify(state)); } catch (e) {} };
  let at = 0, filter = "all";

  const listEl = document.getElementById("list");
  const noteEl = document.getElementById("note");
  const saidEl = document.getElementById("said");

  const box = document.getElementById("chips-kind");
  KINDS.forEach(opt => {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.value = opt.k;
    b.innerHTML = '<kbd>' + opt.key + '</kbd><span>' + opt.k + '</span><small>' + opt.d + '</small>';
    b.addEventListener("click", () => pick(opt.k));
    box.appendChild(b);
  });

  const answered = it => !!(state[it.id] && state[it.id].kind);

  const shows = it => filter === "todo" ? !answered(it) : filter === "done" ? answered(it) : true;
  const visible = () => ITEMS.filter(shows);

  // A BUTTON KEEPS FOCUS AFTER A CLICK, and both of this sheet's keyboard failures come from
  // that. Space or Enter on a chip the reader has just clicked re-activates it NATIVELY — the
  // keydown guard below suppresses this file's handler, not the browser's — so with the
  // auto-advance in `pick` a press meant to scroll the scan records a kind on the page AFTER
  // the one the reader judged. The same focus makes that guard swallow Q-Y and J/K for the
  // rest of the session, killing the flow the sheet advertises. Dropping focus fixes both.
  const unfocus = () => {
    const el = document.activeElement;
    if (el && el.tagName === "BUTTON") el.blur();
  };

  // TRAVERSAL FOLLOWS THE FILTER. With "To do" on, stepping through ITEMS walks the reader
  // back into pages the rail no longer lists and `aria-current` highlights nothing; and after
  // an answer the page just judged leaves the list, so the step is taken from where the reader
  // WAS, not from where the list now starts.
  function nextShown(from, d) {
    for (let i = from + d; i >= 0 && i < ITEMS.length; i += d) if (shows(ITEMS[i])) return i;
    return -1;
  }

  function drawList() {
    listEl.textContent = "";
    visible().forEach(it => {
      const b = document.createElement("button");
      b.type = "button";
      const s = state[it.id] || {};
      b.innerHTML = '<span class="dot' + (answered(it) ? " done" : "") + '"></span><span>' + it.id + ' &middot; ' + (it.yr || "undated") + '</span><span class="who">' + (s.kind || "&mdash;") + '</span>';
      b.setAttribute("aria-current", ITEMS[at] && ITEMS[at].id === it.id ? "true" : "false");
      b.addEventListener("click", () => { at = ITEMS.indexOf(it); draw(); });
      listEl.appendChild(b);
    });
    const done = ITEMS.filter(answered).length;
    document.getElementById("bar").style.width = (100 * done / ITEMS.length) + "%";
    document.getElementById("count").textContent = done + " of " + ITEMS.length;
    document.getElementById("left").textContent = done === ITEMS.length ? "all done" : "";
  }

  function draw() {
    const it = ITEMS[at], s = state[it.id] || {};
    document.getElementById("title").textContent = it.id;
    document.getElementById("meta").textContent = "page " + it.pg + " \\u00b7 " + (it.yr || "undated") + " \\u00b7 " + it.rec;
    document.getElementById("board").href = "https://docketyard.org/document/" + it.sha + ".pdf#page=" + it.pg;
    const img = document.getElementById("scan");
    img.src = it.img;
    img.alt = "page " + it.pg + " as scanned";
    document.getElementById("scanbox").classList.remove("zoom");
    document.getElementById("text").textContent = it.t;
    [...box.children].forEach(b => b.setAttribute("aria-pressed", s.kind === b.dataset.value ? "true" : "false"));
    noteEl.value = s.note || "";
    saidEl.textContent = "";
    drawList();
  }

  // PICKING A KIND MOVES ON, because this sheet asks one question and forty pages is forty
  // extra clicks otherwise. A wrong letter is corrected by stepping back and typing the right
  // one; typing the SAME letter again clears the answer and stays put, so a page can be left
  // unanswered on purpose rather than only re-answered.
  function pick(value) {
    unfocus();
    const it = ITEMS[at];
    keepNote(it);
    const s = state[it.id] || (state[it.id] = {});
    const again = s.kind === value;
    s.kind = again ? undefined : value;
    save();
    if (!again) {
      const i = nextShown(at, 1);
      if (i !== -1) at = i;
    }
    draw();
  }

  // A NOTE IS KEPT EVEN WITH NO KIND YET: a note typed on an untouched page was dropped on the
  // way out of the sheet this one is modelled on, until a review caught it (2026-09-17).
  function keepNote(it) {
    const v = noteEl.value.trim();
    if (!v && !state[it.id]) return;
    (state[it.id] || (state[it.id] = {})).note = v;
    save();
  }

  function move(d) {
    unfocus();
    keepNote(ITEMS[at]);
    const i = nextShown(at, d);
    if (i !== -1) at = i;
    draw();
  }

  document.getElementById("prev").addEventListener("click", () => move(-1));
  document.getElementById("next").addEventListener("click", () => move(1));
  document.getElementById("scanbox").addEventListener("click", e => {
    if (e.target.tagName === "IMG") e.currentTarget.classList.toggle("zoom");
  });
  noteEl.addEventListener("blur", () => keepNote(ITEMS[at]));
  [...document.querySelectorAll(".filters button")].forEach(b => {
    b.addEventListener("click", () => {
      filter = b.dataset.filter;
      [...document.querySelectorAll(".filters button")].forEach(o => o.setAttribute("aria-pressed", String(o === b)));
      unfocus();
      // the page open behind the rail may not survive the new filter; land on one that does
      if (!shows(ITEMS[at])) {
        const i = nextShown(at, 1), j = i !== -1 ? i : nextShown(at, -1);
        if (j !== -1) at = j;
      }
      draw();
    });
  });

  document.getElementById("copy").addEventListener("click", () => {
    unfocus();
    keepNote(ITEMS[at]);
    const rows = {};
    ITEMS.filter(it => state[it.id] && (state[it.id].kind || state[it.id].note)).forEach(it => {
      rows[it.id] = { kind: state[it.id].kind || null, note: state[it.id].note || "" };
    });
    const n = Object.keys(rows).length;
    const text = "flagged-page kinds, checked " + new Date().toISOString().slice(0, 10) + "\\n" + JSON.stringify(rows, null, 1);
    const done = () => { saidEl.textContent = "Copied " + n + " pages."; };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, () => window.prompt("Copy:", text));
    } else { window.prompt("Copy:", text); }
  });

  document.addEventListener("keydown", e => {
    // A KEY MUST NOT ACT FOR A BUTTON THE READER IS ON: Enter on a focused chip already clicks
    // it, and a second handler would record a kind the reader did not choose (code review,
    // 2026-09-17, on the sheet this one is modelled on).
    const tag = e.target.tagName;
    if (tag === "TEXTAREA" || tag === "BUTTON" || e.metaKey || e.ctrlKey || e.altKey) return;
    const hit = KINDS.find(o => o.key.toLowerCase() === e.key.toLowerCase());
    if (hit) { pick(hit.k); e.preventDefault(); return; }
    if (e.key === "j" || e.key === "ArrowDown" || e.key === "ArrowRight") { move(1); e.preventDefault(); }
    if (e.key === "k" || e.key === "ArrowUp" || e.key === "ArrowLeft") { move(-1); e.preventDefault(); }
  });

  draw();
</script>
"""


if __name__ == "__main__":
    # kinds-flagged-sample.json  <img-dir>  text.json  out.html
    raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    pages = raw["pages"] if isinstance(raw, dict) else raw
    kept = [{k: p[k] for k in SHOWN} for p in pages]  # the whitelist, applied once
    texts = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    items = page_items(kept, Path(sys.argv[2]), texts)
    out = Path(sys.argv[4])
    out.write_text(
        build(items, f"{len(items)} pages the prose screen ordered. One question each."),
        encoding="utf-8",
    )
    print(f"{out} ({out.stat().st_size / 1024 / 1024:.1f} MB) {len(items)} pages")
