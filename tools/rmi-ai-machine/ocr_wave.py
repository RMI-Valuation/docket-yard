#!/usr/bin/env python3
"""The OCR wave over the image-only record, on RMI-AI-MACHINE (docs/ocr-plan.md).

Writes READING DOCUMENTS in the shape `docketyard text load` reads (`docketyard/text/load.py`,
the module docstring): one file per document per pass under `<root>/<xx>/<sha>.json`, the
engine's own output kept whole, every page carrying the class it was routed as (ADR 0021 D4),
and a `second` reading naming the primary its agreement was measured against (D8). The
instance loads each root in the order below; nothing here touches the store.

THE PASSES, in the operator's order of 2026-09-02 (prose before pictures; tables not in
this wave) and 2026-09-04 (200 DPI for the degraded tier; the provisional split):

    route      PP-DocLayoutV3 over every page at 150 DPI: the regions, and the class.
    ppocr      PP-OCRv6 medium at 150 DPI over every page, cached; a PRIMARY reading
               document for the clean and unrouted pages  ->  ocr/ppocr-primary
    dots       dots.mocr at 200 DPI over the degraded pages, through the vLLM server;
               PRIMARY                                    ->  ocr/dots
    second     PP-OCRv6's cached reading of the degraded pages as the SECOND reading,
               with its distance from the dots primary    ->  ocr/ppocr-second
    graphic    PP-OCRv6's cached reading of the graphic pages as PRIMARY, last
                                                          ->  ocr/ppocr-graphic
    status     what has been done, per root and per class

`route` and `ppocr` run together (`run-paddle`), because both need the 150 DPI render and the
GPU, and the GPU is theirs until `dots` starts: vLLM takes 95% of the card. `second` and
`graphic` read the cache and run anywhere.

THE ROUTER, AND WHAT IS PROVISIONAL IN IT. The rule is the one `ocr_router_probe.py` fixed
before its first run — no content region: unrouted (the blank call is unsafe, so the page goes
to the default reader and never to a skip); any `table`: tabular; figure area at least half
the content: graphic; else text — plus ONE split the probe declined to make and the operator
took on 2026-09-04: a text page with more than REGION_CUT regions is degraded, else clean.
The cut is the midpoint of the two measured medians (8.5 clean, 18.0 degraded; AUC 0.843 on
90 pages the sample cannot confirm). Every row records the router as
`pp-doclayoutv3+regions` at `provisional-1`, so the label is honest and a confirmed rule can
supersede it by re-reading, which is what ADR 0021 D4 asks.

WHAT A PAGE CLASS MEANS FOR THE READERS:

    clean      PP-OCRv6 primary; read once, no band (the plan's +23% buys the band where the
               errors are)
    degraded   dots.mocr primary at 200 DPI, PP-OCRv6 second at 150 with the distance
    graphic    PP-OCRv6 primary, in the last pass; VL models invent on maps
    unrouted   PP-OCRv6 primary — "no regions" is routed to a reader, never to a skip
    tabular    not read in this wave (ocr-plan.md decision 3); the page shows "not yet read"

EACH PASS'S FILE IS ITS OWN RUN: `ocr_run` is keyed on the reading key and `ran_at`, not the
role, so the three PP-OCRv6 documents a page set can yield (primary, second, graphic) carry
distinct `ran_at` values or the loader answers `restart` to the later ones.

Restartable: a document whose output exists for a pass is skipped; a page that fails is
counted in `pages_failed` and left out; a document that will not open is a `failed` run
with no pages. `ran_at` is written once per file and never changes, which is what lets the
loader answer `restart` from one `ocr_run` lookup.

    # on the box
    ./.venv-paddle/bin/python ocr_wave.py run-paddle --text /data/docketyard/text \\
        --blobs /data/docketyard/blobs --out /data/docketyard/ocr
    VLLM_USE_FLASHINFER_SAMPLER=0 ./.venv-vllm/bin/vllm serve rednote-hilab/dots.mocr \\
        --served-model-name dots-mocr --trust-remote-code \\
        --chat-template-content-format string --port 8120 \\
        --gpu-memory-utilization 0.95 --max-model-len 16384
    ./.venv-paddle/bin/python ocr_wave.py dots --text ... --blobs ... --out ...
    python3 ocr_wave.py second --out /data/docketyard/ocr
    python3 ocr_wave.py graphic --out /data/docketyard/ocr
    python3 ocr_wave.py status --out /data/docketyard/ocr
"""

import argparse
import base64
import json
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# --- the router ------------------------------------------------------------------------------

ROUTER = "pp-doclayoutv3+regions"
ROUTER_VERSION = "provisional-1"
REGION_CUT = 13  # more than this: degraded. Midpoint of the medians 8.5 and 18.0 (README § 4)
LAYOUT_MODEL = "PP-DocLayoutV3"
FIGURE_LABELS = {"image", "figure", "chart", "header_image", "footer_image"}
TABLE_LABELS = {"table"}
FURNITURE_LABELS = {"header", "footer", "page_number", "number", "aside_text", "seal"}
CLASSES = ("clean", "degraded", "graphic", "tabular", "unrouted")

# --- the readers -----------------------------------------------------------------------------

PPOCR = {"method": "pp-ocrv6-medium", "render_profile": "150"}  # method_version: the package
PPOCR_WEIGHTS = ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec")
DOTS = {"method": "dots.mocr", "method_version": "1.5", "render_profile": "200"}
DOTS_MODEL = "dots-mocr"
DOTS_SERVER = "http://127.0.0.1:8120/v1"
AGREEMENT = {"method": "normalised-edit-distance", "method_version": "1"}
ROOTS = {
    "route": "route",
    "cache": "ppocr-cache",
    "ppocr": "ppocr-primary",
    "dots": "dots",
    "second": "ppocr-second",
    "graphic": "ppocr-graphic",
}

# The model's shipped document-parsing prompt, as `ocr_run.py` sends it.
DOTS_PROMPT = """Please output the layout information from the PDF image, including each \
layout element's bbox, its category, and the corresponding text content within the bbox.

1. Bbox format: [x1, y1, x2, y2]

2. Layout Categories: The possible categories are ['Caption', 'Footnote', 'Formula', \
'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', \
'Title'].

3. Text Extraction & Formatting Rules:
    - Picture: For the 'Picture' category, the text field should be omitted.
    - Formula: Format its text as LaTeX.
    - Table: Format its text as HTML.
    - All Others (Text, Title, etc.): Format their text as Markdown.

4. Constraints:
    - The output text must be the original text from the image, with no translation.
    - All layout elements must be sorted according to human reading order.

5. Final Output: The entire output must be a single JSON object.
"""


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def shard(root: Path, sha: str) -> Path:
    return root / sha[:2] / f"{sha}.json"


def image_only_documents(text: Path) -> dict[str, int]:
    """sha -> page count, for every extraction record flagged image-only with pages."""
    out = {}
    for path in sorted(text.glob("*/*.json")):
        head = path.read_bytes()[:2048].decode("utf-8", "replace")
        m = re.search(r'"pages":\s*(\d+),\s*"chars":\s*\d+,\s*"image_only":\s*true', head)
        if m and int(m.group(1)) > 0:
            out[path.stem] = int(m.group(1))
    return out


# --- pure functions: the rule, the text, the reading documents (tested off the box) ----------


def classify(regions: list[dict]) -> str:
    """The probe's fixed rule, plus the operator's provisional split of `text`."""
    content = [r for r in regions if r["label"] not in FURNITURE_LABELS]
    if not content:
        return "unrouted"
    if any(r["label"] in TABLE_LABELS for r in content):
        return "tabular"
    total = sum(r["area"] for r in content)
    figure = sum(r["area"] for r in content if r["label"] in FIGURE_LABELS)
    if total > 0 and figure / total >= 0.5:
        return "graphic"
    return "degraded" if len(regions) > REGION_CUT else "clean"


def route_of(cls: str) -> dict:
    return {"class": cls, "method": ROUTER, "method_version": ROUTER_VERSION}


def ppocr_text(lines: list[dict]) -> str:
    """Lines top to bottom then left to right, as `ocr_run.run_ppocr` orders them: a
    ten-pixel vertical band, then x; a line without a box sorts last in its own order."""
    placed = []
    for i, line in enumerate(lines):
        box = line.get("box")
        if box:
            ys = [float(p[1]) for p in box]
            xs = [float(p[0]) for p in box]
            placed.append((round(sum(ys) / len(ys) / 10), min(xs), i, line["text"]))
        else:
            placed.append((float("inf"), 0.0, i, line["text"]))
    return "\n".join(t for *_, t in sorted(placed, key=lambda p: p[:3]))


def dots_text(blocks: list) -> str:
    """The text of a dots answer, block by block; a table as the benchmark writes one."""
    from ocr_run import _table_block  # noqa: PLC0415 — the benchmark's own flattening

    out = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        text = b.get("text") or ""
        if b.get("category") == "Table" and "<table" in text:
            out += _table_block(text)
        elif text.strip():
            out.append(text)
    return "\n".join(out)


def json_array(raw: str):
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def distance(a: str, b: str) -> float:
    """The benchmark's own normaliser and edit distance, as a rate over the longer text."""
    from ocr_score import edit_distance, normalise  # noqa: PLC0415

    na, nb = normalise(a), normalise(b)
    longest = max(len(na), len(nb))
    return 0.0 if longest == 0 else edit_distance(na, nb) / longest


def reading_document(
    sha: str,
    key: dict,
    role: str,
    payload_kind: str,
    engine_pages: list[dict],
    pages: list[dict],
    *,
    pages_failed: int,
    outcome: str = "read",
    ran_at: str | None = None,
) -> dict:
    """The loader's shape. `engine_pages[i]` is what `pages[i].member` points into."""
    return {
        "document_sha256": sha,
        **key,
        "reading_channel": "ocr",
        "reading_role": role,
        "ran_at": ran_at or now(),
        "outcome": outcome,
        "pages_failed": pages_failed,
        "payload_kind": payload_kind,
        "engine": {"pages": engine_pages},
        "pages": pages,
    }


def select_pages(cache: dict, route: dict, classes: set[str], agreement=None):
    """From a document's PP-OCRv6 cache, the reading document's pages of the given classes;
    `agreement(page_no, text)` supplies the second reading's distance, or None."""
    engine_pages, pages, failed = [], [], 0
    for entry in cache["pages"]:
        no = entry["page_no"]
        cls = route["pages"].get(str(no), {}).get("class")
        if cls not in classes:
            continue
        if entry.get("error"):
            failed += 1
            continue
        text = ppocr_text(entry["lines"])
        scores = [ln["score"] for ln in entry["lines"] if ln.get("score") is not None]
        page = {
            "page_no": no,
            "text": text,
            "member": f"engine/pages/{len(engine_pages)}",
            "engine_confidence": round(statistics.fmean(scores), 4) if scores else None,
            "route": route_of(cls),
        }
        if agreement is not None:
            a = agreement(no, text)
            if a is None:
                continue  # no primary to be against: the page is not a second reading
            page["agreement"] = a
        engine_pages.append(entry)
        pages.append(page)
    return engine_pages, pages, failed


def agreement_against(primary: dict[int, str], primary_doc: dict):
    """The second reading's agreement on a page: its distance from the primary's text on
    that page, naming the primary's key. None where the primary did not read the page."""
    against = {k: primary_doc[k] for k in ("method", "method_version", "render_profile")}

    def agreement(no: int, text: str):
        if no not in primary:
            return None
        return {"distance": round(distance(text, primary[no]), 4), **AGREEMENT, "against": against}

    return agreement


# --- rendering ------------------------------------------------------------------------------


def render(pdf: Path, page_index: int, dpi: int, out: Path):
    import fitz  # noqa: PLC0415 — pymupdf

    with fitz.open(pdf) as doc:
        doc[page_index].get_pixmap(dpi=dpi).save(out)


def page_count(pdf: Path) -> int:
    import fitz  # noqa: PLC0415

    with fitz.open(pdf) as doc:
        return doc.page_count


# --- the paddle pass: route + PP-OCRv6 over every page ---------------------------------------


def run_paddle(args) -> int:
    from paddleocr import LayoutDetection, PaddleOCR  # noqa: PLC0415

    try:
        from importlib.metadata import version as pkg_version  # noqa: PLC0415

        ppocr_version = pkg_version("paddleocr")
    except Exception:  # noqa: BLE001
        ppocr_version = "unknown"
    layout = LayoutDetection(model_name=LAYOUT_MODEL)
    ocr = PaddleOCR(
        text_detection_model_name=PPOCR_WEIGHTS[0],
        text_recognition_model_name=PPOCR_WEIGHTS[1],
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    key = {**PPOCR, "method_version": ppocr_version}
    docs = image_only_documents(args.text)
    shas = sorted(docs)
    if args.limit:
        shas = shas[: args.limit]
    route_root, cache_root, primary_root = (
        args.out / ROOTS[k] for k in ("route", "cache", "ppocr")
    )
    tmp = args.out / ".render"
    tmp.mkdir(parents=True, exist_ok=True)
    stats = {"documents": 0, "skipped": 0, "pages": 0, "failed_pages": 0, "failed_docs": 0}
    by_class: dict[str, int] = dict.fromkeys(CLASSES, 0)
    started = time.time()
    for n, sha in enumerate(shas, 1):
        if shard(cache_root, sha).exists() and shard(route_root, sha).exists():
            stats["skipped"] += 1
            continue
        pdf = args.blobs / sha[:2] / sha
        route = {
            "document_sha256": sha,
            "method": ROUTER,
            "method_version": ROUTER_VERSION,
            "layout_model": LAYOUT_MODEL,
            "region_cut": REGION_CUT,
            "dpi": 150,
            "routed_at": now(),
            "pages": {},
        }
        cache = {
            "document_sha256": sha,
            **key,
            "weights": PPOCR_WEIGHTS,
            "ran_at": now(),
            "pages": [],
            "error": None,
        }
        try:
            count = page_count(pdf)
        except Exception as e:  # noqa: BLE001 — a scan that will not open is a failed run
            cache["error"] = f"{type(e).__name__}: {e}"
            count = 0
            stats["failed_docs"] += 1
        for i in range(count):
            png = tmp / f"{sha[:12]}_p{i + 1}.png"
            entry = {"page_no": i + 1, "lines": [], "error": None}
            try:
                render(pdf, i, 150, png)
                regions = []
                for res in layout.predict(str(png)):
                    for box in res.json["res"].get("boxes") or []:
                        poly = box.get("polygon_points") or []
                        regions.append(
                            {
                                "label": box.get("label"),
                                "score": round(float(box.get("score", 0.0)), 4),
                                "area": round(_area(poly), 1),
                            }
                        )
                cls = classify(regions)
                route["pages"][str(i + 1)] = {
                    "class": cls,
                    "regions": len(regions),
                    "labels": sorted({r["label"] for r in regions}),
                }
                by_class[cls] += 1
                for res in ocr.predict(str(png)):
                    r = res.json["res"]
                    texts = r.get("rec_texts") or []
                    scores = r.get("rec_scores") or []
                    boxes = r.get("rec_polys") or r.get("dt_polys") or []
                    for j, text in enumerate(texts):
                        box = boxes[j] if j < len(boxes) else None
                        entry["lines"].append(
                            {
                                "text": text,
                                "score": round(float(scores[j]), 4) if j < len(scores) else None,
                                "box": [[float(p[0]), float(p[1])] for p in box]
                                if box is not None and len(box)
                                else None,
                            }
                        )
            except Exception as e:  # noqa: BLE001 — one page must not end the document
                entry["error"] = f"{type(e).__name__}: {e}"
                stats["failed_pages"] += 1
                if str(i + 1) not in route["pages"]:
                    route["pages"][str(i + 1)] = {
                        "class": "unrouted",
                        "regions": 0,
                        "labels": [],
                        "error": entry["error"],
                    }
            finally:
                png.unlink(missing_ok=True)
            cache["pages"].append(entry)
            stats["pages"] += 1
        _write(shard(route_root, sha), route)
        _write(shard(cache_root, sha), cache)
        # the primary reading document for the pages PP-OCRv6 owns in this wave
        engine_pages, pages, failed = select_pages(cache, route, {"clean", "unrouted"})
        if pages or cache["error"]:
            doc = reading_document(
                sha,
                key,
                "primary",
                "pp-ocrv6.json",
                engine_pages,
                pages,
                pages_failed=failed,
                outcome="failed" if cache["error"] else "read",
                ran_at=cache["ran_at"],
            )
            _write(shard(primary_root, sha), doc)
        stats["documents"] += 1
        if n % 20 == 0 or n == len(shas):
            rate = stats["pages"] / max(time.time() - started, 1)
            print(
                f"  {n}/{len(shas)} docs, {stats['pages']} pages, {rate:.2f} pages/s,"
                f" classes {by_class}",
                flush=True,
            )
    _manifest(
        args.out / ROOTS["ppocr"],
        {**stats, "by_class": by_class, "key": key, "router": route_of("-")},
    )
    print(f"done {stats} in {time.time() - started:.0f}s; classes {by_class}")
    return 0


def _area(polygon) -> float:
    pts = [(float(p[0]), float(p[1])) for p in polygon if len(p) >= 2]
    if len(pts) < 3:
        return 0.0
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1], strict=False):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


# --- the dots pass: degraded pages at 200 DPI through vLLM -----------------------------------


def run_dots(args) -> int:
    route_root, out_root = args.out / ROOTS["route"], args.out / ROOTS["dots"]
    tmp = args.out / ".render"
    tmp.mkdir(parents=True, exist_ok=True)
    routes = sorted(p.stem for p in route_root.glob("*/*.json"))
    if args.limit:
        routes = routes[: args.limit]
    stats = {"documents": 0, "skipped": 0, "no_degraded": 0, "pages": 0, "failed_pages": 0}
    started = time.time()
    for n, sha in enumerate(routes, 1):
        if shard(out_root, sha).exists():
            stats["skipped"] += 1
            continue
        route = json.loads(shard(route_root, sha).read_text(encoding="utf-8"))
        wanted = sorted(int(k) for k, v in route["pages"].items() if v["class"] == "degraded")
        if not wanted:
            stats["no_degraded"] += 1
            continue
        pdf = args.blobs / sha[:2] / sha
        engine_pages, pages, failed = [], [], 0
        for no in wanted:
            png = tmp / f"{sha[:12]}_p{no}.png"
            try:
                render(pdf, no - 1, 200, png)
                raw, blocks = _dots_call(png, args.dots_server, args.dots_model)
            except Exception as e:  # noqa: BLE001
                print(f"  FAILED {sha[:12]} p{no} ({type(e).__name__}: {e})", flush=True)
                failed += 1
                continue
            finally:
                png.unlink(missing_ok=True)
            engine_pages.append({"page_no": no, "raw": raw, "blocks": blocks})
            pages.append(
                {
                    "page_no": no,
                    # `[]` is a blank page and reads as ''; only an UNPARSED answer keeps the prose
                    "text": dots_text(blocks) if blocks is not None else raw.strip(),
                    "member": f"engine/pages/{len(engine_pages) - 1}",
                    "route": route_of("degraded"),
                }
            )
            stats["pages"] += 1
        stats["failed_pages"] += failed
        doc = reading_document(
            sha,
            DOTS,
            "primary",
            "dots.mocr.json",
            engine_pages,
            pages,
            pages_failed=failed,
            outcome="read" if pages else "failed",
        )
        _write(shard(out_root, sha), doc)
        stats["documents"] += 1
        if n % 10 == 0 or n == len(routes):
            rate = stats["pages"] / max(time.time() - started, 1)
            print(
                f"  {n}/{len(routes)} docs, {stats['pages']} pages, {rate:.3f} pages/s", flush=True
            )
    _manifest(out_root, {**stats, "key": DOTS, "server": args.dots_server})
    print(f"done {stats} in {time.time() - started:.0f}s")
    return 0


def _dots_call(png: Path, server: str, model: str, timeout: int = 600):
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 8192,
            "temperature": 0.0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,"
                                + base64.b64encode(png.read_bytes()).decode()
                            },
                        },
                        {"type": "text", "text": DOTS_PROMPT},
                    ],
                }
            ],
        }
    ).encode()
    req = urllib.request.Request(
        server + "/chat/completions", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        answer = json.loads(resp.read())
    choice = answer["choices"][0]
    if choice.get("finish_reason") not in (None, "stop"):
        raise RuntimeError(f"finish_reason {choice.get('finish_reason')}")  # a cut page
    raw = choice["message"]["content"]
    return raw, json_array(raw)


# --- derived passes: the second reading, and the graphic pages ------------------------------


def run_second(args) -> int:
    """PP-OCRv6's cached reading of every degraded page, as the SECOND reading, measured
    against the dots primary. A page dots did not read has no primary to be against and is
    left out — the loader would refuse it."""
    cache_root, route_root, dots_root = (args.out / ROOTS[k] for k in ("cache", "route", "dots"))
    out_root = args.out / ROOTS["second"]
    stats = {"documents": 0, "skipped": 0, "pages": 0, "no_dots": 0}
    for path in sorted(dots_root.glob("*/*.json")):
        sha = path.stem
        if shard(out_root, sha).exists():
            stats["skipped"] += 1
            continue
        dots = json.loads(path.read_text(encoding="utf-8"))
        primary = {p["page_no"]: p["text"] for p in dots.get("pages", [])}
        if not primary:
            stats["no_dots"] += 1
            continue
        cache = json.loads(shard(cache_root, sha).read_text(encoding="utf-8"))
        route = json.loads(shard(route_root, sha).read_text(encoding="utf-8"))
        key = {k: cache[k] for k in ("method", "method_version", "render_profile")}

        agreement = agreement_against(primary, dots)

        engine_pages, pages, failed = select_pages(cache, route, {"degraded"}, agreement)
        if not pages:
            continue
        doc = reading_document(
            sha, key, "second", "pp-ocrv6.json", engine_pages, pages, pages_failed=failed
        )  # its own ran_at: `ocr_run` is keyed on the reading key and ran_at, not the role
        _write(shard(out_root, sha), doc)
        stats["documents"] += 1
        stats["pages"] += len(pages)
    _manifest(out_root, {**stats, "agreement": AGREEMENT})
    print(f"done {stats}")
    return 0


def run_graphic(args) -> int:
    """PP-OCRv6's cached reading of the graphic pages as PRIMARY: maps last (decision 3)."""
    cache_root, route_root = args.out / ROOTS["cache"], args.out / ROOTS["route"]
    out_root = args.out / ROOTS["graphic"]
    stats = {"documents": 0, "skipped": 0, "pages": 0}
    for path in sorted(cache_root.glob("*/*.json")):
        sha = path.stem
        if shard(out_root, sha).exists():
            stats["skipped"] += 1
            continue
        cache = json.loads(path.read_text(encoding="utf-8"))
        route = json.loads(shard(route_root, sha).read_text(encoding="utf-8"))
        key = {k: cache[k] for k in ("method", "method_version", "render_profile")}
        engine_pages, pages, failed = select_pages(cache, route, {"graphic"})
        if not pages:
            continue
        doc = reading_document(
            sha, key, "primary", "pp-ocrv6.json", engine_pages, pages, pages_failed=failed
        )  # its own ran_at, for the same reason as the second reading's
        _write(shard(out_root, sha), doc)
        stats["documents"] += 1
        stats["pages"] += len(pages)
    _manifest(out_root, stats)
    print(f"done {stats}")
    return 0


def status(args) -> int:
    for name, sub in ROOTS.items():
        root = args.out / sub
        files = list(root.glob("*/*.json")) if root.is_dir() else []
        print(f"{name:8s} {sub:15s} {len(files):6d} documents")
    route_root = args.out / ROOTS["route"]
    if route_root.is_dir():
        by_class: dict[str, int] = dict.fromkeys(CLASSES, 0)
        for path in route_root.glob("*/*.json"):
            for v in json.loads(path.read_text(encoding="utf-8"))["pages"].values():
                by_class[v["class"]] = by_class.get(v["class"], 0) + 1
        print("pages by class:", by_class, "total", sum(by_class.values()))
    return 0


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _manifest(root: Path, stats: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "_manifest.json").write_text(
        json.dumps({**stats, "finished_at": now()}, indent=1), encoding="utf-8"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="pass_", required=True)
    for name in ("run-paddle", "dots"):
        p = sub.add_parser(name)
        p.add_argument("--text", required=True, type=Path)
        p.add_argument("--blobs", required=True, type=Path)
        p.add_argument("--out", required=True, type=Path)
        p.add_argument("--limit", type=int, default=0)
        if name == "dots":
            p.add_argument("--dots-server", default=DOTS_SERVER)
            p.add_argument("--dots-model", default=DOTS_MODEL)
    for name in ("second", "graphic", "status"):
        p = sub.add_parser(name)
        p.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    return {
        "run-paddle": run_paddle,
        "dots": run_dots,
        "second": run_second,
        "graphic": run_graphic,
        "status": status,
    }[args.pass_](args)


if __name__ == "__main__":
    sys.exit(main())
