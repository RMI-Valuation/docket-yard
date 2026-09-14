"""Draw the long-form check and build its page (docs/research/long-form-check/README.md).

Finder 2026-09-13 reads `Finance Docket No. N` and `Ex Parte No. N`. Its card is measured on
the sixty decisions, which print one long-form citation, so a hundred long-form citations are
judged one at a time as the gate before the branch merges (the operator, 2026-09-13).

RUNS THE SHIPPED WALK over a store's text layer, with the finder and resolver this checkout
holds, so what is judged is what would load. Read-only.

    python tools/rmi-ai-machine/long_form_check_sheet.py [--store data/rehearse-family.sqlite]

The draw is the README's, fixed before anything was drawn: long-form citations only (the
finding's `target` matches `keys.LONG_DOCKET` and its `kind` is `citation`); 40 from decisions
served 1996–2005, 35 from 2006–2019, 15 from 2020 on, then 10 more from the unresolved of any
era; at most one citation per document, so a long volume cannot fill a stratum; seed 20260913.

Writes `docs/research/long-form-check/sample.json` (what was drawn and why) and
`data/long-form-check.html` (the page the operator judges on: the key, the line it was quoted
from, the page text around it, and the Board's own page one click away). Verdicts stay in the
browser; Copy findings hands them back as `document_sha256 TAB page TAB key TAB verdict TAB note`.
"""

# ruff: noqa: E501 — an HTML document lives in this file; its CSS and markup keep their own
# line lengths, and reflowing them to the code width would only make them harder to read.

import html
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from docketyard.citator import find, keys, resolve, walk  # noqa: E402

SEED = 20260913
STRATA = (("1996-2005", 40), ("2006-2019", 35), ("2020+", 15))
UNRESOLVED_EXTRA = 10
SITE = "https://docketyard.org"
SAMPLE = ROOT / "docs" / "research" / "long-form-check" / "sample.json"
PAGE = ROOT / "data" / "long-form-check.html"
YEAR = re.compile(r"\b(19|20)\d{2}\b")
AROUND = 400  # characters of page text either side of the first occurrence


def eras(con) -> dict[str, str]:
    """document -> the era of the earliest service date among the decisions carrying it."""
    years: dict[str, list[int]] = {}
    for sha, served in con.execute(
        "SELECT a.document_sha256, r.service_date FROM decision_attachment a"
        " JOIN decision_record r ON r.decision_pk = a.decision_pk"
        " WHERE a.document_sha256 IS NOT NULL"
    ):
        if served and (m := YEAR.search(served)):
            years.setdefault(sha, []).append(int(m.group(0)))
    out = {}
    for sha, ys in years.items():
        y = min(ys)
        out[sha] = "1996-2005" if y < 2006 else "2006-2019" if y < 2020 else "2020+"
    return out


def candidates(con) -> list[dict]:
    held, works, era_of = keys.registry(con), keys.works(con), eras(con)
    out = []
    for doc in walk.documents(con, channel="text-layer"):
        sha = doc["document_sha256"]
        for f in doc["findings"]:
            if f["kind"] != "citation" or not keys.LONG_DOCKET.match(f["target"]):
                continue
            # the finding's own key, and the family its anchor reads (ADR 0018 addendum of
            # 2026-09-14): the printed target alone misses the own-fused rule
            key = f.get("key") or keys.normalise(f["target"])
            if key is None:  # a long form always keys; a None here is a grammar bug, not a row
                raise SystemExit(f"{sha} p{f['page']}: {f['target']!r} matched but keys as nothing")
            r = resolve.resolve(key, held, works, f["quoted"], f["target"], walk.own_of(con, sha))
            text_id = (doc.get("text_ids") or {}).get(str(f["page"]))
            text = con.execute(
                "SELECT text FROM document_text WHERE text_id = ?", (text_id,)
            ).fetchone()
            start = (f.get("spans") or [[0, 0, ""]])[0][0]
            page_text = text[0] if text else ""
            lo, hi = max(0, start - AROUND), min(len(page_text), start + AROUND)
            out.append(
                {
                    "document_sha256": sha,
                    "page": f["page"],
                    "key": key,
                    "target": f["target"],
                    "quoted": f["quoted"],
                    "era": era_of.get(sha, "unknown"),
                    "outcome": r.outcome,
                    "cited_docket_id": r.docket_id,
                    "cited_decision_id": r.decision_id,
                    "board_pdf": f"{SITE}/document/{sha}.pdf#page={f['page']}",
                    "excerpt": page_text[lo:hi],
                    "excerpt_offset": lo,
                    "spans": f.get("spans") or [],
                }
            )
    out.sort(key=lambda c: (c["document_sha256"], c["page"], c["key"]))
    return out


def draw(pool: list[dict], seed: int = SEED, excluded: frozenset[str] = frozenset()) -> list[dict]:
    rng = random.Random(seed)
    # A DOCUMENT AN EARLIER SAMPLE DREW IS NEVER DRAWN AGAIN: a rule chosen after seeing those
    # verdicts is gated only on documents nobody has judged (the operator, 2026-09-13)
    used: set[str] = set(excluded)
    drawn: list[dict] = []

    def take(rows: list[dict], n: int, stratum: str) -> None:
        rows = rows[:]
        rng.shuffle(rows)
        got = 0
        for c in rows:
            if got == n:
                break
            if c["document_sha256"] in used:
                continue
            used.add(c["document_sha256"])
            drawn.append({"stratum": stratum, **c})
            got += 1

    for era, n in STRATA:
        take([c for c in pool if c["era"] == era], n, era)
    take([c for c in pool if c["outcome"] == "unresolved"], UNRESOLVED_EXTRA, "unresolved")
    return drawn


def marked(item: dict) -> str:
    """The excerpt, escaped, with every occurrence of this finding highlighted."""
    text, off = item["excerpt"], item["excerpt_offset"]
    out, at = [], 0
    for s, e, _raw in sorted(item["spans"]):
        s, e = s - off, e - off
        if s < at or e > len(text) or s < 0:
            continue
        out.append(html.escape(text[at:s]))
        out.append(f"<mark>{html.escape(text[s:e])}</mark>")
        at = e
    out.append(html.escape(text[at:]))
    return "".join(out)


def main(store: Path, seed: int = SEED, exclude: Path | None = None, name: str = "sample") -> int:
    excluded: frozenset[str] = frozenset()
    if exclude is not None:
        excluded = frozenset(
            d["document_sha256"] for d in json.loads(exclude.read_text(encoding="utf-8"))["drawn"]
        )
    sample_path = SAMPLE.with_name(f"{name}.json")
    page_path = PAGE if name == "sample" else PAGE.with_name(f"long-form-check-{name}.html")
    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    pool = candidates(con)
    con.close()
    drawn = draw(pool, seed, excluded)
    population = {}
    for c in pool:
        k = f"{c['era']} {c['outcome']}"
        population[k] = population.get(k, 0) + 1
    record = {
        "seed": seed,
        "excluded_documents_from": exclude.as_posix() if exclude is not None else None,
        "excluded_documents": len(excluded),
        "store": store.as_posix(),
        "finder_version": find.FINDER_VERSION,
        "key_version": keys.KEY_VERSION,
        "population": dict(sorted(population.items())),
        "strata": {**dict(STRATA), "unresolved": UNRESOLVED_EXTRA},
        "drawn": [{k: v for k, v in d.items() if k not in ("excerpt", "spans")} for d in drawn],
    }
    sample_path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")
    items = [
        {
            "k": f"{d['document_sha256']}/{d['page']}/{d['key']}",
            "sha": d["document_sha256"],
            "page": d["page"],
            "key": d["key"],
            "stratum": d["stratum"],
            "outcome": d["outcome"],
            "quoted": d["quoted"],
            "pdf": d["board_pdf"],
            "excerpt": marked(d),
        }
        for d in drawn
    ]
    data = json.dumps(items, separators=(",", ":")).replace("</", "<\\/")
    html_out = HTML.replace("__DATA__", data)
    if name != "sample":
        # its own name in the gallery, and its own verdicts: two checks must never share a store
        html_out = html_out.replace(
            "<title>Long-Form Docket Check</title>",
            f"<title>Long-Form Docket Check ({name})</title>",
        ).replace('"dy-long-form-check-v1"', f'"dy-long-form-check-{name}"')
    page_path.write_text(html_out, encoding="utf-8", newline="\n")
    print(f"{len(pool)} long-form citations; drew {len(drawn)} -> {sample_path}, {page_path}")
    print("by stratum:", {s: sum(1 for d in drawn if d["stratum"] == s) for s in record["strata"]})
    return 0


HTML = """<title>Long-Form Docket Check</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Source+Sans+3:wght@400;600&display=swap">
<style>
:root{--paper:#faf8f5;--card:#fff;--ink:#1b1a17;--muted:#6d675f;--rule:#e0dad1;--accent:#24427a;
--yes:#2f6b3f;--no:#a3391f;--hold:#7d5f10;--mark:#fdf0b8}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--paper:#16161a;--card:#1e1e23;--ink:#eceae6;
--muted:#a7a099;--rule:#33323a;--accent:#93b2e8;--yes:#7fc08d;--no:#e88f74;--hold:#d8b45c;--mark:#4a3f14}}
:root[data-theme=dark]{--paper:#16161a;--card:#1e1e23;--ink:#eceae6;--muted:#a7a099;--rule:#33323a;
--accent:#93b2e8;--yes:#7fc08d;--no:#e88f74;--hold:#d8b45c;--mark:#4a3f14}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 "Source Sans 3",system-ui,sans-serif}
.wrap{max-width:54em;margin:0 auto;padding-block:1.5em;padding-left:16px;padding-right:16px}
h1{font-size:1.25rem;margin:0 0 .3em}.muted{color:var(--muted)}
.bar{position:sticky;top:0;background:var(--paper);padding:.5em 0;border-bottom:1px solid var(--rule);display:flex;gap:1em;flex-wrap:wrap;align-items:center;z-index:1}
.card{background:var(--card);border:1px solid var(--rule);border-radius:8px;padding:1em 1.2em;margin:1em 0}
.key{font:600 1.1rem "IBM Plex Mono",ui-monospace,monospace;color:var(--accent)}
.line{font:.92rem/1.55 "IBM Plex Mono",ui-monospace,monospace;background:var(--paper);border-left:3px solid var(--rule);padding:.5em .8em;margin:.6em 0;white-space:pre-wrap;overflow-wrap:anywhere}
mark{background:var(--mark);color:inherit}
button{font:inherit;padding:.35em .9em;border-radius:6px;border:1px solid var(--rule);background:var(--card);color:var(--ink);cursor:pointer}
button.on[data-v=right]{background:var(--yes);color:#fff;border-color:var(--yes)}
button.on[data-v=wrong]{background:var(--no);color:#fff;border-color:var(--no)}
button.on[data-v=unclear]{background:var(--hold);color:#fff;border-color:var(--hold)}
button.on[data-v=caption]{background:var(--accent);color:var(--card);border-color:var(--accent)}
input{font:inherit;width:100%;box-sizing:border-box;margin-top:.5em;border:1px solid var(--rule);border-radius:6px;padding:.35em .5em;background:var(--paper);color:var(--ink)}
a{color:var(--accent)}
</style>
<div class="wrap">
<h1>Long-form citations — the gate for finder 2026-09-13</h1>
<p class="muted"><b>right</b>: the key names the proceeding the page prints, and it is a citation. A document cited in the own docket (<i>Decision No. 5</i>, <i>served …</i>) is a citation. The quoted line is only the line the number sat on, so a case name cut short is still right. <b>wrong</b>: the key is not the proceeding printed. <b>caption</b>: the document's own proceeding named as itself (its caption, a heading, a bare docket number). <b>unclear</b>: the page does not settle it. Check against the Board's page where the text is unclear.</p>
<div class="bar"><span id="prog"></span><button id="copy">Copy findings</button><span id="copied" class="muted"></span></div>
<div id="cards"></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  var ITEMS = JSON.parse(document.getElementById("data").textContent);
  var KEY = "dy-long-form-check-v1", state = {};
  try { state = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { state = {}; }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"}[c]; }); }
  function progress() {
    var n = ITEMS.filter(function (it) { return state[it.k] && state[it.k].v; }).length;
    document.getElementById("prog").textContent = n + " of " + ITEMS.length + " judged";
  }
  var box = document.getElementById("cards");
  box.innerHTML = ITEMS.map(function (it, i) {
    var s = state[it.k] || {};
    return '<div class="card" data-k="' + esc(it.k) + '"><div><span class="key">' + esc(it.key) + '</span> <span class="muted">#' + (i + 1) + " · " + esc(it.stratum) + " · " + esc(it.outcome) + " · page " + it.page + '</span></div>' +
      '<div class="line">' + esc(it.quoted) + '</div>' +
      '<div class="line">' + it.excerpt + '</div>' +
      '<div><a target="_blank" rel="noopener" href="' + esc(it.pdf) + '">The Board\\'s page</a></div>' +
      '<div style="margin-top:.6em;display:flex;gap:.4em;flex-wrap:wrap">' +
      ["right", "wrong", "caption", "unclear"].map(function (v) { return '<button data-v="' + v + '" class="' + (s.v === v ? "on" : "") + '">' + v + "</button>"; }).join("") + "</div>" +
      '<input placeholder="Note (what is wrong, or why unclear)" value="' + esc(s.note || "") + '"></div>';
  }).join("");
  Array.prototype.forEach.call(box.querySelectorAll(".card"), function (card) {
    var k = card.getAttribute("data-k");
    card.querySelectorAll("button").forEach(function (b) {
      b.onclick = function () {
        var s = state[k] || (state[k] = {}), v = b.getAttribute("data-v");
        s.v = s.v === v ? "" : v; save();
        card.querySelectorAll("button").forEach(function (x) { x.classList.toggle("on", x.getAttribute("data-v") === s.v); });
        progress();
      };
    });
    card.querySelector("input").oninput = function (e) { (state[k] || (state[k] = {})).note = e.target.value; save(); };
  });
  document.getElementById("copy").onclick = function () {
    var out = ITEMS.filter(function (it) { return state[it.k] && (state[it.k].v || state[it.k].note); }).map(function (it) {
      var s = state[it.k];
      return [it.sha, it.page, it.key, s.v || "", (s.note || "").replace(/[\\t\\n]/g, " ")].join("\\t");
    });
    var text = out.join("\\n");
    function done() { document.getElementById("copied").textContent = out.length + " lines copied"; }
    if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(text).then(done, function () { window.prompt("Copy:", text); }); }
    else { window.prompt("Copy:", text); }
  };
  progress();
})();
</script>
"""

if __name__ == "__main__":
    argv = sys.argv[1:]
    store = (
        Path(argv[argv.index("--store") + 1])
        if "--store" in argv
        else ROOT / "data/rehearse-family.sqlite"
    )
    seed = int(argv[argv.index("--seed") + 1]) if "--seed" in argv else SEED
    exclude = Path(argv[argv.index("--exclude") + 1]) if "--exclude" in argv else None
    name = argv[argv.index("--name") + 1] if "--name" in argv else "sample"
    raise SystemExit(main(store, seed, exclude, name))
