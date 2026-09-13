"""Build the OCR citation benchmark's check pages (docs/research/ocr-citation-benchmark/).

The unit of review is a PAGE: the scan, whole, beside the drafted labels for it, each marked
right, wrong or unsure, with a box for what the draft missed. Below them sits the machine
reading the finder read, with every target it emitted highlighted where it read it, so the
checker can see both what the draft says the page holds and what the finder made of the OCR.
The draft is judged against the SCAN, never against the reading: the reading is what is being
measured.

    uv run --no-project --with pillow python tools/rmi-ai-machine/ocr_citation_check_page.py

Reads, all under `data/ocr-citation/` except the sample: `batches.json`, `drafts/batch-NN.csv`
(the drafting brief's columns), `pages/*.png`, `ocr-text.json` (the live OCR row of every
labelled page, exported from production), `findings/<sha>.json` (the shipped finder's
output), and `docs/research/ocr-citation-benchmark/sample.json`.

A DRAFT THAT DOES NOT COVER THE SAMPLE IS REFUSED, not rendered around: a labelled page with no
row, or a row on a page that was not labelled, means the draft and the sample disagree about
what was read, and a check page built over that would hide it.

The scans are embedded as 1-bit PNGs thresholded per page (Otsu, `ocr_page_images.py`), which
is how the OCR ground truth's queue carried its pages. All 548 come to 22 MB as base64, over a
published page's 16 MB, so the batches are split into two pages: 1-5 and 6-10.
"""

# ruff: noqa: E501 — an HTML document lives in this file; its CSS and markup keep their own
# line lengths, and reflowing them to the code width would only make them harder to read.

import base64
import csv
import html
import io
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ocr_page_images  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "data" / "ocr-citation"
SAMPLE = ROOT / "docs" / "research" / "ocr-citation-benchmark" / "sample.json"
SITE = "https://docketyard.org"
PARTS = ((1, (1, 2, 3, 4, 5)), (2, (6, 7, 8, 9, 10)))


def one_bit(path: Path) -> str:
    im = Image.open(path).convert("L")
    t = ocr_page_images.otsu(im.histogram())
    bw = im.point(lambda v: 255 if v > t else 0).convert("1")
    buf = io.BytesIO()
    bw.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def marked(text: str, findings: list[dict]) -> str:
    """The reading, escaped, with every span the finder emitted wrapped by its kind. Spans are
    `[start, end, raw]` in this text's own coordinates (ADR 0026 D4); an overlap keeps the first."""
    spans = sorted(
        (s[0], s[1], f.get("kind") or "", f.get("target") or "")
        for f in findings
        for s in f.get("spans") or []
        if 0 <= s[0] < s[1] <= len(text)
    )
    out, at = [], 0
    for start, end, kind, target in spans:
        if start < at:
            continue
        out.append(html.escape(text[at:start]))
        cls = "cit" if kind == "citation" else "cap"
        out.append(
            f'<mark class="{cls}" title="{html.escape(kind)}: {html.escape(target)}">'
            f"{html.escape(text[start:end])}</mark>"
        )
        at = end
    out.append(html.escape(text[at:]))
    return "".join(out)


def load_drafts(batches: list[dict]) -> dict[tuple[str, int], list[dict]]:
    expected = {
        (d["document_sha256"], p)
        for b in batches
        for d in b["documents"]
        for p in d["labelled_pages"]
    }
    rows: dict[tuple[str, int], list[dict]] = {}
    stray = []
    for b in batches:
        path = WORK / "drafts" / f"batch-{b['batch']:02d}.csv"
        if not path.is_file():
            raise SystemExit(f"no draft for batch {b['batch']}: {path}")
        with path.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                at = (r["document_sha256"].strip(), int(r["page"]))
                if at not in expected:
                    stray.append(at)
                    continue
                rows.setdefault(at, []).append(r)
    missing = sorted(expected - rows.keys())
    if stray or missing:
        raise SystemExit(
            f"the draft does not cover the sample: {len(missing)} labelled pages have no row"
            f" {[(s[:12], p) for s, p in missing[:10]]}; {len(stray)} rows sit on pages not"
            f" labelled {[(s[:12], p) for s, p in stray[:10]]}"
        )
    return rows


def main() -> int:
    batches = json.loads((WORK / "batches.json").read_text(encoding="utf-8"))
    sample = {
        d["document_sha256"]: d for d in json.loads(SAMPLE.read_text(encoding="utf-8"))["drawn"]
    }
    reading = json.loads((WORK / "ocr-text.json").read_text(encoding="utf-8"))["pages"]
    drafts = load_drafts(batches)
    by_batch = {b["batch"]: b for b in batches}
    for part, numbers in PARTS:
        items = []
        for n in numbers:
            for doc in by_batch[n]["documents"]:
                sha = doc["document_sha256"]
                found = json.loads((WORK / "findings" / f"{sha}.json").read_text(encoding="utf-8"))
                dockets = sorted({x["docket"] for x in sample[sha]["decisions"]})
                for page in doc["labelled_pages"]:
                    row = reading[sha][str(page)]
                    on_page = [f for f in found.get("findings") or [] if int(f["page"]) == page]
                    items.append(
                        {
                            "k": f"{sha[:12]}_p{page}",
                            "sha": sha,
                            "pg": page,
                            "batch": n,
                            "stratum": sample[sha]["stratum"],
                            "dockets": dockets,
                            "pdf": f"{SITE}/document/{sha}.pdf#page={page}",
                            "img": one_bit(WORK / "pages" / f"{sha[:12]}_p{page}.png"),
                            "engine": row["engine"],
                            "rows": [
                                {
                                    c: (r.get(c) or "")
                                    for c in ("kind", "target_kind", "quoted", "target", "note")
                                }
                                for r in drafts[(sha, page)]
                            ],
                            "finder": [
                                {"kind": f.get("kind"), "target": f.get("target")} for f in on_page
                            ],
                            "ocr": marked(row["text"], on_page),
                        }
                    )
        out = WORK / f"check-{part}.html"
        data = json.dumps(items, separators=(",", ":")).replace("</", "<\\/")
        out.write_text(
            HTML.replace("__PART__", str(part)).replace("__DATA__", data),
            encoding="utf-8",
            newline="\n",
        )
        print(f"wrote {out} {round(out.stat().st_size / 1e6, 1)} MB, {len(items)} pages")
    return 0


HTML = """<title>OCR citations — check __PART__</title>
<style>
:root{--paper:#faf8f5;--card:#fff;--ink:#1b1a17;--muted:#6d675f;--rule:#e0dad1;--accent:#24427a;
--yes:#2f6b3f;--no:#a3391f;--hold:#7d5f10;--cit:#fdf0b8;--cap:#dde7f7}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--paper:#16161a;--card:#1e1e23;--ink:#eceae6;
--muted:#a7a099;--rule:#33323a;--accent:#93b2e8;--yes:#7fc08d;--no:#e88f74;--hold:#d8b45c;--cit:#4a3f14;--cap:#23324d}}
:root[data-theme=dark]{--paper:#16161a;--card:#1e1e23;--ink:#eceae6;--muted:#a7a099;--rule:#33323a;
--accent:#93b2e8;--yes:#7fc08d;--no:#e88f74;--hold:#d8b45c;--cit:#4a3f14;--cap:#23324d}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 "Source Sans 3",system-ui,sans-serif}
.wrap{padding-block:12px;padding-left:16px;padding-right:16px}
header{display:flex;flex-wrap:wrap;gap:.6em 1.2em;align-items:baseline;margin-bottom:10px}
h1{font-size:1.1rem;margin:0}.muted{color:var(--muted)}
.pair{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:14px}
@media (max-width:900px){.pair{grid-template-columns:minmax(0,1fr)}}
.vp{position:relative;overflow:hidden;background:#fff;border:1px solid var(--rule);border-radius:6px;height:78vh;touch-action:none;cursor:grab}
.vp img{position:absolute;left:0;top:0;transform-origin:0 0;image-rendering:auto;user-select:none;-webkit-user-drag:none}
.tools{display:flex;gap:.4em;flex-wrap:wrap;margin:6px 0}
button{font:inherit;padding:.3em .7em;border-radius:6px;border:1px solid var(--rule);background:var(--card);color:var(--ink);cursor:pointer}
button:focus-visible{outline:2px solid var(--accent)}
.card{background:var(--card);border:1px solid var(--rule);border-radius:8px;padding:10px 12px;margin-bottom:8px}
.q{font:600 .95rem "IBM Plex Mono",ui-monospace,monospace;overflow-wrap:anywhere}
.t{font:.9rem "IBM Plex Mono",ui-monospace,monospace;color:var(--accent)}
.note{font-size:.88rem;color:var(--muted)}
.v button.on[data-v=ok]{background:var(--yes);color:#fff;border-color:var(--yes)}
.v button.on[data-v=wrong]{background:var(--no);color:#fff;border-color:var(--no)}
.v button.on[data-v=unsure]{background:var(--hold);color:#fff;border-color:var(--hold)}
textarea,input{font:inherit;width:100%;box-sizing:border-box;border:1px solid var(--rule);border-radius:6px;background:var(--paper);color:var(--ink);padding:.35em .5em}
.ocr{white-space:pre-wrap;overflow-wrap:anywhere;font:.82rem/1.5 "IBM Plex Mono",ui-monospace,monospace;max-height:40vh;overflow:auto;background:var(--paper);border:1px solid var(--rule);border-radius:6px;padding:8px}
mark.cit{background:var(--cit);color:inherit}mark.cap{background:var(--cap);color:inherit}
a{color:var(--accent)}.done{color:var(--yes);font-weight:600}
</style>
<div class="wrap">
<header>
  <h1>OCR citations — check __PART__ of 2</h1>
  <span id="pos" class="muted"></span><span id="prog" class="muted"></span>
  <span class="muted">Judge each draft row against the <b>scan</b>. <kbd>j</kbd>/<kbd>k</kbd> next/previous page, <kbd>a</kbd> all rows right.</span>
</header>
<div class="tools">
  <button id="prev">&larr; Previous</button><button id="next">Next &rarr;</button>
  <button id="nextopen">Next unchecked</button>
  <button id="copy">Copy findings</button><span id="copied" class="muted"></span>
</div>
<div class="pair">
  <div>
    <div class="tools"><button id="zin">+</button><button id="zout">&minus;</button><button id="zfit">Fit</button><button id="z1">1:1</button>
      <a id="open" target="_blank" rel="noopener">The Board's file, this page</a></div>
    <div class="vp" id="vp"><img id="img" alt="the scanned page"></div>
  </div>
  <div>
    <div class="card"><div id="meta"></div></div>
    <div id="rows"></div>
    <div class="card"><label for="missed"><b>Missed on this page</b> <span class="muted">— one per line: kind, target, as printed</span></label>
      <textarea id="missed" rows="3"></textarea></div>
    <div class="card"><b>What the finder read</b> <span class="muted">— the OCR reading; <mark class="cit">citation</mark> <mark class="cap">caption</mark> as the finder called them</span>
      <div id="engine" class="muted"></div><div class="ocr" id="ocr"></div></div>
  </div>
</div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  var PAGES = JSON.parse(document.getElementById("data").textContent);
  var KEY = "dy-ocr-citation-check-v1-__PART__";
  var state = {};
  try { state = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { state = {}; }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"}[c]; }); }
  var at = 0, img = el("img"), vp = el("vp"), scale = 1, fitScale = 1, tx = 0, ty = 0;

  function st(p) { return state[p.k] || (state[p.k] = {rows: {}, missed: ""}); }
  function judged(p) {
    // a page whose only rows are "nothing to label" has nothing to judge, visited or not
    var s = state[p.k] || {rows: {}};
    return p.rows.every(function (r, i) { return r.kind === "" || (s.rows[i] && s.rows[i].v); });
  }
  function progress() {
    var n = PAGES.filter(judged).length;
    el("prog").textContent = n + " of " + PAGES.length + " pages judged";
  }
  function apply() { img.style.transform = "translate(" + tx + "px," + ty + "px) scale(" + scale + ")"; }
  function clamp() {
    var w = img.naturalWidth * scale, h = img.naturalHeight * scale, vw = vp.clientWidth, vh = vp.clientHeight;
    tx = w <= vw ? (vw - w) / 2 : Math.min(0, Math.max(vw - w, tx));
    ty = h <= vh ? 0 : Math.min(0, Math.max(vh - h, ty));
  }
  function fit() {
    if (!img.naturalWidth || vp.clientWidth < 60) return;
    fitScale = Math.min(vp.clientWidth / img.naturalWidth, vp.clientHeight / img.naturalHeight);
    scale = fitScale; tx = 0; ty = 0; clamp(); apply();
  }
  function zoomTo(next, cx, cy) {
    next = Math.max(fitScale, Math.min(fitScale * 10, next));
    if (cx === undefined) { cx = vp.clientWidth / 2; cy = vp.clientHeight / 2; }
    tx = cx - (cx - tx) * (next / scale); ty = cy - (cy - ty) * (next / scale);
    scale = next; clamp(); apply();
  }
  img.addEventListener("load", fit);
  window.addEventListener("resize", fit);
  vp.addEventListener("wheel", function (e) {
    e.preventDefault(); var r = vp.getBoundingClientRect();
    zoomTo(scale * (e.deltaY < 0 ? 1.18 : 1 / 1.18), e.clientX - r.left, e.clientY - r.top);
  }, {passive: false});
  vp.addEventListener("dblclick", function (e) {
    var r = vp.getBoundingClientRect();
    if (scale > fitScale * 1.02) fit(); else zoomTo(1, e.clientX - r.left, e.clientY - r.top);
  });
  (function () {
    var down = false, sx = 0, sy = 0, ox = 0, oy = 0;
    vp.addEventListener("pointerdown", function (e) { down = true; sx = e.clientX; sy = e.clientY; ox = tx; oy = ty; vp.setPointerCapture(e.pointerId); });
    vp.addEventListener("pointermove", function (e) { if (!down) return; tx = ox + e.clientX - sx; ty = oy + e.clientY - sy; clamp(); apply(); });
    ["pointerup", "pointercancel"].forEach(function (ev) { vp.addEventListener(ev, function () { down = false; }); });
  })();
  el("zin").onclick = function () { zoomTo(scale * 1.5); };
  el("zout").onclick = function () { zoomTo(scale / 1.5); };
  el("zfit").onclick = fit;
  el("z1").onclick = function () { zoomTo(1); };

  function render() {
    var p = PAGES[at], s = st(p);
    el("pos").textContent = "Page " + (at + 1) + " of " + PAGES.length + " (batch " + p.batch + ")";
    if (img.getAttribute("src") !== p.img) { img.src = p.img; }
    el("open").href = p.pdf;
    el("meta").innerHTML = "<b>" + esc(p.k) + "</b> &middot; page " + p.pg + " &middot; " + esc(p.stratum) +
      "<div class=muted>Own proceeding: " + esc(p.dockets.join(", ")) + " (and its parent and sub-dockets)</div>" +
      (judged(p) ? "<div class=done>judged</div>" : "");
    el("rows").innerHTML = p.rows.map(function (r, i) {
      if (r.kind === "") return '<div class=card><span class=muted>Draft: nothing to label on this page.</span> ' +
        "<div class=note>" + esc(r.note) + "</div><div class=muted>If that is wrong, write what it missed below.</div></div>";
      var v = (s.rows[i] || {}).v || "", fix = (s.rows[i] || {}).fix || "";
      return '<div class=card data-i="' + i + '"><div>' + esc(r.kind) + " &middot; " + esc(r.target_kind) + "</div>" +
        '<div class=q>' + esc(r.quoted) + '</div><div class=t>&rarr; ' + esc(r.target) + "</div>" +
        (r.note ? "<div class=note>" + esc(r.note) + "</div>" : "") +
        '<div class="tools v"><button data-v=ok class="' + (v === "ok" ? "on" : "") + '">Right</button>' +
        '<button data-v=wrong class="' + (v === "wrong" ? "on" : "") + '">Wrong</button>' +
        '<button data-v=unsure class="' + (v === "unsure" ? "on" : "") + '">Unsure</button></div>' +
        '<input placeholder="What it should say (wrong or unsure)" value="' + esc(fix) + '"></div>';
    }).join("");
    Array.prototype.forEach.call(el("rows").querySelectorAll(".card[data-i]"), function (card) {
      var i = card.getAttribute("data-i");
      card.querySelectorAll("button").forEach(function (b) {
        b.onclick = function () { var rs = s.rows[i] || (s.rows[i] = {}); rs.v = rs.v === b.getAttribute("data-v") ? "" : b.getAttribute("data-v"); save(); render(); };
      });
      card.querySelector("input").oninput = function (e) { var rs = s.rows[i] || (s.rows[i] = {}); rs.fix = e.target.value; save(); };
    });
    el("missed").value = s.missed || "";
    el("engine").textContent = "Read by " + p.engine + "; the finder emitted " + p.finder.length + " on this page.";
    el("ocr").innerHTML = p.ocr || "<span class=muted>(the reading is empty)</span>";
    progress();
    // NO fit here: a verdict re-renders the page, and refitting would throw away the zoom the
    // checker used to read the citation (code review, 2026-09-13). Only a page change refits.
  }
  el("missed").oninput = function (e) { st(PAGES[at]).missed = e.target.value; save(); };
  function move(by) { at = Math.max(0, Math.min(PAGES.length - 1, at + by)); render(); requestAnimationFrame(fit); window.scrollTo(0, 0); }
  el("prev").onclick = function () { move(-1); };
  el("next").onclick = function () { move(1); };
  el("nextopen").onclick = function () {
    for (var j = 1; j <= PAGES.length; j++) { var k = (at + j) % PAGES.length; if (!judged(PAGES[k])) { at = k; render(); requestAnimationFrame(fit); return; } }
  };
  document.addEventListener("keydown", function (e) {
    var t = e.target.tagName; if (t === "TEXTAREA" || t === "INPUT" || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "j") move(1); else if (e.key === "k") move(-1);
    else if (e.key === "a") { var p = PAGES[at], s = st(p); p.rows.forEach(function (r, i) { if (r.kind !== "") { (s.rows[i] || (s.rows[i] = {})).v = "ok"; } }); save(); render(); }
  });
  el("copy").onclick = function () {
    var out = ["part\\t__PART__"];
    PAGES.forEach(function (p) {
      var s = state[p.k]; if (!s) return;
      p.rows.forEach(function (r, i) {
        var rs = s.rows[i]; if (!rs || !(rs.v || rs.fix)) return;
        out.push([p.sha, p.pg, i, rs.v || "", (rs.fix || "").replace(/[\\t\\n]/g, " ")].join("\\t"));
      });
      if ((s.missed || "").trim()) {
        s.missed.split("\\n").forEach(function (line) { if (line.trim()) out.push([p.sha, p.pg, "missed", "", line.replace(/\\t/g, " ")].join("\\t")); });
      }
    });
    var text = out.join("\\n");
    function done() { el("copied").textContent = (out.length - 1) + " lines copied"; }
    if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(text).then(done, function () { window.prompt("Copy:", text); }); }
    else { window.prompt("Copy:", text); }
  };
  render();
})();
</script>
"""

if __name__ == "__main__":
    raise SystemExit(main())
