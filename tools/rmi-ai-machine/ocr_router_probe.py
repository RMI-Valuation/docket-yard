"""Measure PP-DocLayoutV3 as the OCR step's page router (docs/research/ocr-benchmark).

Step 3 left the routing open: no engine wins every tier, so the pipeline needs something
that decides which engine reads a page. This measures the candidate the benchmark named —
`PP-DocLayoutV3`, already on the box as a dependency of PaddleOCR-VL, and layout-detection
only, so it is cheap and it cannot invent text.

WHAT THIS DOES NOT DO, AND WHY. It does not fit a rule. The obvious filter for Textract's
false tables is a column count — every false positive in step 3 is 2-column and every real
table 3+ — and it is refused for the reason step 3 refused it: tuning a threshold against
the tier labels of the very sample being scored is how the party-type rules reached 83.3%
on the sheet they were fitted to. So this tool reports the detector's RAW signal per
operator tier and lets the reader see whether a router exists. One rule is scored beside
it, stated below in advance and taken from the model's own semantics rather than from the
numbers; even that ordering is a choice, so the rule's figures are in-sample and need a
second, unseen sample before any of them ships.

THE RULE, FIXED BEFORE THE FIRST RUN:

    no content region at all             -> blank
    else any region labelled `table`     -> tabular
    else figure-ish area >= half the
      content area                       -> graphic
    else                                 -> text

`text` is deliberately one class: the operator's tiers split it into clean and degraded,
which is image quality rather than structure. That fold is the honest starting position and
it turned out to be too strong — see `separability`, which measures the difference the rule
declines to make instead of asserting it away. It matters because clean and degraded are
~86% of a random draw and route to different engines (PP-OCRv6 and dots.mocr), so this is
the largest routing decision in the pipeline.

    # on the box (PaddlePaddle lives in .venv-paddle)
    ./.venv-paddle/bin/python ocr_router_probe.py run --pages pages --out runs/router
    # anywhere
    python ocr_router_probe.py report --regions runs/router/regions.json
"""

import argparse
import json
import platform
import statistics
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "docs/research/ocr-benchmark/sample.json"

# Which detected labels count as a picture. PP-DocLayoutV3's vocabulary is wider than this;
# the names are matched against what the run actually returns and anything unrecognised is
# reported rather than silently dropped (see `report`).
FIGURE_LABELS = {"image", "figure", "chart", "header_image", "footer_image"}
TABLE_LABELS = {"table"}
# Regions that describe the page furniture rather than its content. They are counted and
# reported, but a page of nothing but these is not a page with content.
FURNITURE_LABELS = {"header", "footer", "page_number", "number", "aside_text", "seal"}

TIERS = ("clean", "degraded", "tabular", "graphic", "blank")
TIMINGS_KEY = "_seconds"  # not a page: `report` lifts it out before counting
FAILURES_KEY = "_failures"  # ditto; present only when a page did not land, and loud in `report`


def selected_pages(sample_path: Path) -> dict[str, str]:
    """`{png name: operator tier}` for the 90 pages the ground truth covers."""
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    return {p["png"]: p["tier"] for p in sample["pages"] if p["selected"]}


def _area(polygon: list[list[float]]) -> float:
    """The shoelace area of a detected region, which may be a rotated quadrilateral."""
    n = len(polygon)
    if n < 3:
        return 0.0
    return (
        abs(
            sum(
                polygon[i][0] * polygon[(i + 1) % n][1] - polygon[(i + 1) % n][0] * polygon[i][1]
                for i in range(n)
            )
        )
        / 2.0
    )


def detect(pages: Path, names: list[str], model_name: str) -> dict:
    """PP-DocLayoutV3 over each page: every region's label, score and area, and the time.

    The detector is the whole point of the candidate — it runs without the 0.9B recogniser
    and without a vLLM server, so a router built on it costs a fraction of a read. Whether
    that holds is a measurement, not an assumption, so each page is timed: PP-OCRv6 reads a
    clean page in 0.4 s, and a router dearer than that would be the expensive half.
    """
    import time  # noqa: PLC0415

    from paddleocr import LayoutDetection  # noqa: PLC0415

    model = LayoutDetection(model_name=model_name)
    out: dict = {}
    timings: dict[str, float] = {}
    for n, name in enumerate(names, 1):
        path = pages / name
        if not path.is_file():
            print(f"  MISSING {name}", flush=True)
            continue
        regions = []
        started = time.perf_counter()
        for res in model.predict(str(path)):
            for box in res.json["res"].get("boxes") or []:
                poly = box.get("polygon_points") or []
                regions.append(
                    {
                        "label": box.get("label"),
                        "score": round(float(box.get("score", 0.0)), 4),
                        "area": round(_area(poly), 1),
                    }
                )
        timings[name] = round(time.perf_counter() - started, 4)
        out[name] = regions
        if n % 10 == 0 or n == len(names):
            print(f"  {n}/{len(names)}", flush=True)
    # POSITIVELY ASSERT THAT THE GEOMETRY PARSED, rather than trusting the key name. `_area`
    # answers 0.0 for a region whose polygon it did not find, and `classify` skips the
    # graphic branch when the areas total zero — so a PaddleX build that named the field
    # `coordinate` instead would produce a complete, plausible run in which every page is
    # `text` and nothing anywhere reported a failure. That is the silent-success shape this
    # project refuses elsewhere; it gets the same treatment here.
    detected = sum(len(v) for v in out.values())
    if detected and not any(r["area"] > 0 for v in out.values() for r in v):
        raise RuntimeError(
            f"{detected} regions detected and every one has zero area — the polygon field "
            "is not where this tool looks for it; the graphic rule would silently never fire"
        )
    out[TIMINGS_KEY] = timings
    return out


# dots.ocr/dots.mocr answer in their own vocabulary. Mapped onto PP-DocLayoutV3's so that
# ONE rule scores both and the comparison is of the detectors, not of two rules. Recorded in
# `run.json` so the mapping is auditable rather than buried here.
DOTS_TO_PP = {
    "Picture": "image",
    "Table": "table",
    "Page-header": "header",
    "Page-footer": "footer",
    "Caption": "figure_title",
    "Footnote": "footnote",
    "Formula": "formula",
    "List-item": "text",
    "Section-header": "paragraph_title",
    "Text": "text",
    "Title": "doc_title",
}

# The model's layout-only prompt: the same contract as `DOTS_PROMPT` in `ocr_run.py` with the
# text field dropped. Asking for categories WITHOUT the transcription is the whole question —
# if the categories are all a router needs, there is no reason to pay for the reading.
DOTS_LAYOUT_PROMPT = """Please output the layout information from the PDF image, including \
each layout element's bbox and its category.

1. Bbox format: [x1, y1, x2, y2]

2. Layout Categories: The possible categories are ['Caption', 'Footnote', 'Formula', \
'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', \
'Title'].

3. Do NOT output the text content of any element. Bbox and category only.

4. All layout elements must be sorted according to human reading order.

5. Final Output: The entire output must be a single JSON object."""


def detect_dots(pages: Path, names: list[str], server: str, model: str) -> dict:
    """dots.mocr asked for layout ONLY — no transcription — through the same vLLM server.

    Serve it exactly as `ocr_run.py`'s `run_dots_ocr` documents; this only changes the prompt.
    A truncated answer is raised rather than scored, for the reason that runner gives: a
    partial page read as a whole one understates the engine silently.
    """
    import base64  # noqa: PLC0415
    import time  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    out: dict = {}
    timings: dict[str, float] = {}
    failures: list[str] = []
    for n, name in enumerate(names, 1):
        path = pages / name
        if not path.is_file():
            print(f"  MISSING {name}", flush=True)
            failures.append(f"{name}: not on disk")
            continue
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
                                    + base64.b64encode(path.read_bytes()).decode()
                                },
                            },
                            {"type": "text", "text": DOTS_LAYOUT_PROMPT},
                        ],
                    }
                ],
            }
        ).encode()
        req = urllib.request.Request(
            server + "/chat/completions", data=body, headers={"Content-Type": "application/json"}
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                answer = json.loads(resp.read())
        except Exception as e:  # noqa: BLE001 — one page must not end the run
            print(f"  FAILED {name} ({type(e).__name__}: {e})", flush=True)
            failures.append(f"{name}: {type(e).__name__}: {e}")
            continue
        elapsed = time.perf_counter() - started
        choice = answer["choices"][0]
        if choice.get("finish_reason") not in (None, "stop"):
            # A page truncated at max_tokens is a partial answer. Dropping it quietly would
            # shrink the tier denominators, and it would shrink them exactly where the
            # comparison is decided — the dense tabular and degraded pages are the ones that
            # run long. Recorded as a failure so the run cannot be read as complete.
            print(f"  TRUNCATED {name} ({choice.get('finish_reason')})", flush=True)
            failures.append(f"{name}: truncated ({choice.get('finish_reason')})")
            continue
        blocks = _json_array(choice["message"]["content"])
        if blocks is None:
            print(f"  NOT JSON {name} (answered in prose)", flush=True)
            failures.append(f"{name}: answered in prose, not JSON")
            continue
        regions = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            bbox = b.get("bbox") or []
            poly = (
                [
                    [bbox[0], bbox[1]],
                    [bbox[2], bbox[1]],
                    [bbox[2], bbox[3]],
                    [bbox[0], bbox[3]],
                ]
                if len(bbox) == 4
                else []
            )
            category = str(b.get("category"))
            regions.append(
                {
                    "label": DOTS_TO_PP.get(category, category.lower()),
                    "dots_category": category,
                    "score": None,  # the model returns no confidence
                    "area": round(_area(poly), 1),
                }
            )
        timings[name] = round(elapsed, 4)
        out[name] = regions
        if n % 10 == 0 or n == len(names):
            print(f"  {n}/{len(names)}", flush=True)
    # The same positive assertions `detect` makes, for the same reason. A server that is down
    # or on the wrong port answers every page with a refused connection, and without this the
    # tool would write an empty regions.json, a run.json saying `pages_detected: 0`, and exit
    # 0 — a complete-looking run of nothing. A bbox under a different key would be subtler
    # still: every area 0.0, the graphic branch never reached, every page called `text`.
    if not [p for p in out if p != TIMINGS_KEY]:
        raise RuntimeError(
            f"no page was detected — is {server} serving {model}? "
            f"first failure: {failures[0] if failures else 'none recorded'}"
        )
    if not any(r["area"] > 0 for v in out.values() for r in v):
        raise RuntimeError(
            "every region has zero area — the bbox is not where this tool looks for it; "
            "the graphic rule would silently never fire"
        )
    out[TIMINGS_KEY] = timings
    if failures:
        out[FAILURES_KEY] = failures
    return out


def _json_array(raw: str) -> list | None:
    """The JSON array in a model's answer, however it wrapped it. Mirrors `ocr_run.py`."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        text = text.removeprefix("json").strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def classify(regions: list[dict]) -> str:
    """The rule fixed in this module's docstring, applied. No number here is fitted."""
    content = [r for r in regions if r["label"] not in FURNITURE_LABELS]
    if not content:
        return "blank"
    if any(r["label"] in TABLE_LABELS for r in content):
        return "tabular"
    total = sum(r["area"] for r in content)
    figure = sum(r["area"] for r in content if r["label"] in FIGURE_LABELS)
    if total > 0 and figure / total >= 0.5:
        return "graphic"
    return "text"


def _auc(positive: list[float], negative: list[float]) -> float | None:
    """Rank separability of one quantity between two groups — the probability that a random
    positive scores above a random negative, ties counting a half.

    Reported INSTEAD OF a threshold, deliberately. A cut-off chosen to look good on these 90
    pages is the party-type mistake; a rank statistic commits to no cut-off, so there is
    nothing in it to tune. It says whether a signal is there, and nothing about where a line
    should go.
    """
    if not positive or not negative:
        return None
    wins = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in positive for b in negative)
    return wins / (len(positive) * len(negative))


def _median(values: list[float]) -> float:
    """The real median, interpolated on an even count. Taking the upper-middle value instead
    published a clean-tier median of 9.0 where the 38 pages actually sit at 8.5."""
    return statistics.median(values) if values else 0.0


def separability(
    regions_by_page: dict[str, list[dict]], tiers: dict[str, str], pages: list[str]
) -> None:
    """Clean against degraded — the split the rule declines to make, asked of the counts.

    The rule folds clean and degraded together because layout detection is structure, not
    image quality. The raw table then showed the two tiers fragmenting into very different
    numbers of regions, so "layout cannot see it" is too strong a claim to leave standing,
    and it is measured here instead of repeated. THE FEATURES ARE THE ONES THE RAW TABLE
    ALREADY PRINTED — no quantity was invented after seeing the answer — and no threshold is
    fitted. It is a lead for the second, unseen sample, not a router.
    """
    clean = [p for p in pages if tiers[p] == "clean"]
    degraded = [p for p in pages if tiers[p] == "degraded"]
    # `figure regions` is reported BOTH WAYS because the answer moves with the definition:
    # `header_image`/`footer_image` are a letterhead, not a picture of anything, and folding
    # them in with `image` is a judgement. Printing one number would hide that the judgement
    # is doing some of the work.
    features = {
        "regions per page": lambda p: float(len(regions_by_page[p])),
        "figure regions (all)": lambda p: float(
            sum(1 for r in regions_by_page[p] if r["label"] in FIGURE_LABELS)
        ),
        "figure regions (image)": lambda p: float(
            sum(1 for r in regions_by_page[p] if r["label"] == "image")
        ),
    }
    print("\nCLEAN vs DEGRADED - the split the rule declines to make (ranks, no cut-off)")
    print(f"  {len(clean)} clean, {len(degraded)} degraded. AUC 0.50 is no signal, 1.00 is")
    print("  perfect separation. A threshold is deliberately NOT chosen here.")
    for name, fn in features.items():
        c = [fn(p) for p in clean]
        d = [fn(p) for p in degraded]
        auc = _auc(d, c)  # degraded is the positive class
        shown = "  n/a" if auc is None else f"{auc:.3f}"
        print(
            f"  {name:24s} clean median {_median(c):5.1f}   "
            f"degraded median {_median(d):5.1f}   AUC {shown}"
        )


def report(regions_by_page: dict, tiers: dict[str, str]) -> None:
    """The raw signal first, the fixed rule second. The raw table is the measurement."""
    regions_by_page = dict(regions_by_page)  # the timings come out of a copy, not the caller's
    seconds = regions_by_page.pop(TIMINGS_KEY, None)
    failures = regions_by_page.pop(FAILURES_KEY, None)
    if failures:
        # Printed FIRST and unmissably: every figure below is over a shrunken denominator.
        print(f"!! {len(failures)} PAGES DID NOT LAND — this run is not the full sample:")
        for f in failures[:10]:
            print(f"     {f}")
        print()
    pages = [p for p in tiers if p in regions_by_page]
    missing = [p for p in tiers if p not in regions_by_page]
    if missing:
        print(f"NOT DETECTED ({len(missing)}): {', '.join(sorted(missing)[:5])}...\n")

    vocabulary = Counter(r["label"] for p in pages for r in regions_by_page[p])
    known = FIGURE_LABELS | TABLE_LABELS | FURNITURE_LABELS
    unknown = {label for label in vocabulary if label not in known}
    print(
        f"{len(pages)} pages, {sum(vocabulary.values())} regions, "
        f"{len(vocabulary)} distinct labels\n"
    )
    print("LABEL VOCABULARY (what the detector actually returned)")
    for label, n in vocabulary.most_common():
        kind = (
            "table"
            if label in TABLE_LABELS
            else "figure"
            if label in FIGURE_LABELS
            else "furniture"
            if label in FURNITURE_LABELS
            else "text-ish"
        )
        print(f"  {label:20s} {n:5d}  ({kind})")
    if unknown:
        print(
            "\n  treated as text-ish because this tool does not name them: "
            f"{', '.join(sorted(unknown))}"
        )

    print("\nRAW SIGNAL BY OPERATOR TIER - pages of each tier carrying each signal")
    print(
        f"  {'tier':10s} {'pages':>5s} {'>=1 table':>9s} {'>=1 figure':>10s} "
        f"{'no content':>11s} {'regions/pg':>11s}"
    )
    for tier in TIERS:
        rows = [regions_by_page[p] for p in pages if tiers[p] == tier]
        if not rows:
            continue
        has_table = sum(1 for r in rows if any(x["label"] in TABLE_LABELS for x in r))
        has_figure = sum(1 for r in rows if any(x["label"] in FIGURE_LABELS for x in r))
        empty = sum(1 for r in rows if not [x for x in r if x["label"] not in FURNITURE_LABELS])
        per_page = sum(len(r) for r in rows) / len(rows)
        print(
            f"  {tier:10s} {len(rows):5d} {has_table:9d} {has_figure:10d} "
            f"{empty:11d} {per_page:11.1f}"
        )

    print("\nTHE FIXED RULE - confusion against the operator's tiers")
    print("  clean and degraded are one predicted class (`text`): the rule is structural,")
    print("  and that is 86% of a random draw routing to two different engines.")
    predicted = {p: classify(regions_by_page[p]) for p in pages}
    classes = ("blank", "tabular", "graphic", "text")
    heading = "actual \\ predicted"
    print("\n  " + heading.ljust(22) + "".join(f"{c:>10s}" for c in classes))
    for tier in TIERS:
        rows = [p for p in pages if tiers[p] == tier]
        if not rows:
            continue
        counts = Counter(predicted[p] for p in rows)
        print(f"  {tier:22s}" + "".join(f"{counts.get(c, 0):10d}" for c in classes))

    print("\n  per-class, treating `text` as the union of clean and degraded:")
    truth = {p: ("text" if tiers[p] in ("clean", "degraded") else tiers[p]) for p in pages}
    for cls in classes:
        tp = sum(1 for p in pages if predicted[p] == cls and truth[p] == cls)
        fp = sum(1 for p in pages if predicted[p] == cls and truth[p] != cls)
        fn = sum(1 for p in pages if predicted[p] != cls and truth[p] == cls)
        prec = f"{tp / (tp + fp) * 100:5.1f}%" if tp + fp else "   n/a"
        rec = f"{tp / (tp + fn) * 100:5.1f}%" if tp + fn else "   n/a"
        print(
            f"  {cls:10s} actual={tp + fn:3d} predicted={tp + fp:3d}  "
            f"precision {prec}  recall {rec}   ({tp} right, {fp} wrong, {fn} missed)"
        )

    separability(regions_by_page, tiers, pages)

    if seconds:
        vals = sorted(float(v) for v in seconds.values())
        total = sum(vals)
        print(
            f"\nCOST  {total:.1f}s for {len(vals)} pages - {total / len(vals):.2f}s a page "
            f"(median {_median(vals):.2f}s, worst {vals[-1]:.2f}s)"
        )
        print("  against the reads it routes to: PP-OCRv6 0.4s, dots.mocr 6.5s a page.")

    wrong = [(p, truth[p], predicted[p]) for p in sorted(pages) if predicted[p] != truth[p]]
    print(f"\n{len(wrong)} pages the rule places wrongly:")
    for page, actual, pred in wrong:
        labels = Counter(r["label"] for r in regions_by_page[page])
        top = ", ".join(f"{k} x{v}" for k, v in labels.most_common(4)) or "no regions"
        print(f"  {page:26s} {actual:9s} -> {pred:9s}  [{top}]")


def _provenance(args: argparse.Namespace, model_name: str, pages: int) -> dict:
    """What produced this run, in the shape `ocr_run.py` writes: a figure that cannot say
    which weights and which package version made it cannot be checked later."""

    def version(module: str) -> str | None:
        try:
            import importlib.metadata as md  # noqa: PLC0415

            return md.version(module)
        except Exception:  # noqa: BLE001 — an absent package is a fact, not a failure
            return None

    dots = args.cmd == "run-dots"
    run = {
        "engine": model_name if dots else "pp-doclayoutv3",
        "purpose": "page router candidate, layout detection only",
        "weights": model_name,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "host": platform.node(),
        "pages": str(args.pages),
        "pages_detected": pages,
        "python": platform.python_version(),
        "packages": {
            m: version(m)
            for m in ("paddleocr", "paddlex", "paddlepaddle-gpu", "paddlepaddle", "vllm", "torch")
            if version(m)
        },
        "rule": {
            "order": [
                "blank if no content region",
                "tabular if any table",
                "graphic if figure area >= 0.5 of content area",
                "text otherwise",
            ],
            "fitted": False,
            "note": "stated before the first run; in-sample figures until a second sample",
        },
        "figure_labels": sorted(FIGURE_LABELS),
        "table_labels": sorted(TABLE_LABELS),
        "furniture_labels": sorted(FURNITURE_LABELS),
    }
    if dots:
        # The comparison is only honest if one rule scores both, so dots' vocabulary is
        # mapped onto PP-DocLayoutV3's. The mapping is a judgement and belongs in the record.
        run["prompt"] = "layout only, no text"
        run["server"] = args.dots_server
        run["sampling"] = {"max_tokens": 8192, "temperature": 0.0}
        run["category_mapping"] = dict(sorted(DOTS_TO_PP.items()))
        # ASKED OF THE LIVE SERVER, as `ocr_run.py` asks the live PaddleOCR-VL pipeline:
        # `--served-model-name` is an alias the operator chose, so recording it alone would
        # say nothing about which weights answered. The server knows its own model id.
        served = _served_model(args.dots_server)
        run["weights"] = served or f"{model_name} (alias only; server was not reachable)"
    return run


def _served_model(server: str) -> str | None:
    """What the vLLM server says it is serving, or None if it cannot be asked."""
    import urllib.request  # noqa: PLC0415

    try:
        with urllib.request.urlopen(server.rstrip("/") + "/models", timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception:  # noqa: BLE001 — an unreachable server is a fact for the record
        return None
    served = [m.get("root") or m.get("id") for m in data.get("data") or []]
    return ", ".join(str(m) for m in served if m) or None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="detect layout over the benchmark's selected pages")
    r.add_argument("--pages", type=Path, required=True, help="directory of page PNGs")
    r.add_argument("--out", type=Path, required=True, help="where regions.json is written")
    r.add_argument("--sample", type=Path, default=SAMPLE)
    r.add_argument("--model", default="PP-DocLayoutV3")

    d = sub.add_parser("run-dots", help="the same, from dots.mocr asked for layout only")
    d.add_argument("--pages", type=Path, required=True)
    d.add_argument("--out", type=Path, required=True)
    d.add_argument("--sample", type=Path, default=SAMPLE)
    d.add_argument("--dots-server", default="http://127.0.0.1:8120/v1")
    d.add_argument("--dots-model", default="dots-mocr")

    p = sub.add_parser("report", help="the contingency table and the fixed rule")
    p.add_argument("--regions", type=Path, required=True)
    p.add_argument("--sample", type=Path, default=SAMPLE)

    args = ap.parse_args(argv)
    tiers = selected_pages(args.sample)

    if args.cmd in ("run", "run-dots"):
        args.out.mkdir(parents=True, exist_ok=True)
        names = sorted(tiers)
        if args.cmd == "run-dots":
            print(f"{len(names)} selected pages, {args.dots_model} (layout only)")
            regions = detect_dots(args.pages, names, args.dots_server, args.dots_model)
            args.model = args.dots_model
        else:
            print(f"{len(names)} selected pages, model {args.model}")
            regions = detect(args.pages, names, args.model)
        out = args.out / "regions.json"
        out.write_text(json.dumps(regions, indent=1), encoding="utf-8", newline="\n")
        run = _provenance(args, args.model, len(regions) - 1)
        (args.out / "run.json").write_text(
            json.dumps(run, indent=1), encoding="utf-8", newline="\n"
        )
        print(f"  -> {out}\n  run recorded: {args.out / 'run.json'}")
        return 0

    report(json.loads(args.regions.read_text(encoding="utf-8")), tiers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
