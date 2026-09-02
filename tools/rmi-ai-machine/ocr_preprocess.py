"""Build preprocessed variants of the benchmark's 90 pages (docs/research/ocr-benchmark).

The bench measured engines on one rendering: 150 DPI, colour, whole page. Two preprocessing
results already exist and they point in opposite directions — greyscale moved Claude from
6.6% to 5.9% CER and moved Textract by nothing, while PaddleOCR's own orientation and
unwarping steps made PP-OCRv6 *worse* (clean 2.6% → 4.4%, docket recall down 9 points). So
preprocessing is not a thing to choose once and apply everywhere; it is a per-engine
measurement, and this builds the inputs for it.

WHAT EACH VARIANT IS, and why it might matter on this record:

    dpi300      re-rendered from the source PDF at 300 DPI. 150 was chosen to keep the
                sample small; 300 is the floor most OCR documentation assumes, and the
                degraded tier is where small type and fax noise would benefit.
    grey        8-bit greyscale. The one variant with a prior: it helped one API engine and
                not another.
    binarise    Otsu threshold to 1-bit. What a fax already is; the question is whether
                forcing it helps an engine that expects it or destroys faint strokes.
    deskew      rotate by the angle of the dominant text baselines. The degraded tier holds
                skewed photocopies, and a recogniser reading line by line is the kind that
                should care.
    denoise     median blur, aimed at speckle in the photocopied pages.
    crop        crop to the content bounding box. Content is 55-76% of the render on half
                the sample, so a VLM tokenising the whole page spends much of its budget on
                margin.
    maskfig     white out the regions PP-DocLayoutV3 calls a picture, IN PLACE, leaving the
                page its canvas. A figure carries no prose, so nothing the ground truth
                records is lost and the question is clean: does removing a distractor help
                the text around it?
    masktab     the same, plus tables. This one MUST lose characters, because a table's text
                is in the ground truth — it measures the price of sending tables to a second
                pass rather than reading them in place.

`binarise` and `denoise` are computed FROM the greyscale, so each is greyscale plus one
operation. Their comparison baseline is therefore `grey`, not the colour render — read
against colour they would each be credited with whatever greyscale alone is worth. `crop`
and `deskew` keep all three channels, so theirs is the colour render.

NOTHING HERE JUDGES ANYTHING. It writes page sets; `ocr_run.py` reads them and `ocr_score.py`
scores them against the one ground truth, which is unaffected because every variant preserves
what is printed on the page.

    # 300 DPI needs the source PDFs and PyMuPDF, which lives in the other checkout's venv
    ~/docket-yard/.venv/bin/python ocr_preprocess.py render --dpi 300 \\
        --blobs /data/docketyard/blobs --out pages-dpi300
    # the rest are image operations on a page set already rendered
    ./.venv/bin/python ocr_preprocess.py derive --op grey --pages pages --out pages-grey
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "docs/research/ocr-benchmark/sample.json"

OPS = ("grey", "binarise", "deskew", "denoise", "crop", "maskfig", "masktab")

# What `maskfig` and `masktab` white out, in PP-DocLayoutV3's vocabulary. The split is the
# whole point of having two ops: a figure carries no prose, so removing one cannot cost the
# transcription anything and the measurement is clean. A table carries text the ground truth
# records, so removing one MUST lose characters — `masktab` measures how many, which is the
# price of sending tables to a second pass.
MASK_FIGURE = {"image", "figure", "chart"}
MASK_TABLE = {"table"}


def selected(sample_path: Path) -> list[dict]:
    """The 90 pages the ground truth covers, each with its blob sha and page index."""
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    return [p for p in sample["pages"] if p["selected"]]


def render(pages: list[dict], blobs: Path, out: Path, dpi: int) -> int:
    """Re-render each page from its source PDF at `dpi`, named as the 150 DPI set is.

    The name is what ties a render to its ground truth, so it is carried over unchanged
    rather than recomputed — a variant whose files are named differently would score as 90
    missing pages and one would have to notice.
    """
    import fitz  # noqa: PLC0415

    # CHECKED BEFORE ANYTHING IS WRITTEN. A short page set scores as a different, easier or
    # harder sample than the others, so it must not exist — and refusing *after* the loop
    # still leaves the short set on disk for the next command to pick up, which is the
    # failure this guard is for. Fail before the first file.
    absent = [p["png"] for p in pages if not (blobs / p["sha256"][:2] / p["sha256"]).is_file()]
    if absent:
        raise RuntimeError(
            f"{len(absent)} of {len(pages)} pages have no source blob under {blobs}: "
            f"{', '.join(absent[:5])}{' ...' if len(absent) > 5 else ''}"
        )

    out.mkdir(parents=True, exist_ok=True)
    done = 0
    for n, page in enumerate(pages, 1):
        sha = page["sha256"]
        with fitz.open(blobs / sha[:2] / sha) as doc:
            doc[page["page"]].get_pixmap(dpi=dpi).save(out / page["png"])
        done += 1
        if n % 20 == 0 or n == len(pages):
            print(f"  {n}/{len(pages)}", flush=True)
    print(f"rendered {done} at {dpi} dpi into {out}")
    return done


def _deskew_angle(grey, limit: float = 8.0, step: float = 0.25) -> float:
    """The rotation that makes the text lines horizontal, by projection profile.

    THE OBVIOUS IMPLEMENTATION IS THE ONE THAT WAS HERE AND IT WAS WRONG. `minAreaRect` over
    `np.where(mask)` feeds (row, col) into a function that expects (x, y), which reflects the
    frame and negates the angle, and OpenCV has changed the sign convention of that return
    value between versions besides. Measured 2026-09-02: injecting a known -3 deg skew, it
    estimated -5.8 deg and the "correction" left a -11.7 deg residual — it amplified skew
    rather than removing it, and the deskew row of the first preprocessing table described
    that, not deskewing.

    This cannot get the sign wrong, because it does not derive an angle from geometry at all:
    it rotates by each candidate and keeps whichever makes the horizontal ink profile most
    peaked. Text lines stacked horizontally give a high-variance profile; skewed ones smear
    it. The angle returned is therefore, by construction, the angle to rotate by.

    Bounded at +/-`limit`: a scan is skewed by a degree or two, and a wider search finds the
    grid of a table or the hatching on a map instead of the prose.
    """
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    inverted = cv2.bitwise_not(grey)
    _, mask = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if int((mask > 0).sum()) < 100:
        return 0.0
    # The search is over a downscaled copy: the profile's shape is what matters, and a
    # full-resolution rotation per candidate would cost more than the whole benchmark.
    scale = 800.0 / max(mask.shape)
    if scale < 1:
        small = cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        small = mask
    h, w = small.shape
    centre = (w / 2, h / 2)
    best_angle, best_score = 0.0, -1.0
    candidates = np.arange(-limit, limit + step / 2, step)
    for angle in candidates:
        matrix = cv2.getRotationMatrix2D(centre, float(angle), 1.0)
        turned = cv2.warpAffine(small, matrix, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        profile = turned.sum(axis=1, dtype=np.float64)
        score = float(np.var(profile))
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


def _layout_regions(src_dir: Path, names: list[str]) -> dict[str, list[tuple]]:
    """PP-DocLayoutV3's boxes per page, as `(label, x0, y0, x1, y1)`.

    The router already measured this detector (§ Step 4): 0.05 s a page, and its graphic call
    is 100% precise, which is the property that matters here — a region it calls a picture is
    one, so whiting it out does not white out prose.
    """
    from paddleocr import LayoutDetection  # noqa: PLC0415

    model = LayoutDetection(model_name="PP-DocLayoutV3")
    found: dict[str, list[tuple]] = {}
    for n, name in enumerate(names, 1):
        boxes = []
        for res in model.predict(str(src_dir / name)):
            for box in res.json["res"].get("boxes") or []:
                poly = box.get("polygon_points") or []
                if len(poly) < 3:
                    continue
                xs = [pt[0] for pt in poly]
                ys = [pt[1] for pt in poly]
                boxes.append((box.get("label"), min(xs), min(ys), max(xs), max(ys)))
        found[name] = boxes
        if n % 20 == 0 or n == len(names):
            print(f"  detected {n}/{len(names)}", flush=True)
    # THE SAME POSITIVE ASSERTION `ocr_router_probe.py` MAKES, for the same reason. If a
    # PaddleX build names the geometry field something else, every page comes back with no
    # boxes, the mask paints nothing, and the variant is written as byte-identical copies of
    # the base — which scores as a perfect tie and reads as "masking changes nothing".
    # A silent no-op is the one result this must never produce.
    if not any(found.values()):
        raise RuntimeError(
            f"{len(names)} pages detected and not one region among them — the geometry field "
            "is not where this tool looks for it; every mask would be a no-op"
        )
    return found


def derive(pages: list[dict], src_dir: Path, out: Path, op: str) -> int:
    """One image operation over a page set, writing the same file names into `out`."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    out.mkdir(parents=True, exist_ok=True)
    absent = [p["png"] for p in pages if not (src_dir / p["png"]).is_file()]
    if absent:
        # Checked before the layout pass, which costs a GPU model load and 90 detections.
        raise RuntimeError(f"{len(absent)} pages are not in {src_dir}: {', '.join(absent[:5])}")
    regions: dict[str, list[tuple]] = {}
    if op in ("maskfig", "masktab"):
        regions = _layout_regions(src_dir, [p["png"] for p in pages])
        wanted = MASK_FIGURE | (MASK_TABLE if op == "masktab" else set())
        masked_pages = sum(1 for b in regions.values() if any(x[0] in wanted for x in b))
        print(f"  {op}: {masked_pages} of {len(pages)} pages have something to mask")
        # WRITTEN BESIDE THE PAGES, because the published account of this variant is "33 of
        # 90 pages, 6.0% of the page on average, 8 clean and 18 degraded" — and a figure
        # nothing records cannot be checked afterwards. Same argument as `run.json`.
        tiers = {p["png"]: p["tier"] for p in pages}
        masked = {
            name: {
                "tier": tiers[name],
                "regions": [
                    {"label": lb, "box": [x0, y0, x1, y1]}
                    for lb, x0, y0, x1, y1 in boxes
                    if lb in wanted
                ],
            }
            for name, boxes in regions.items()
            if any(x[0] in wanted for x in boxes)
        }
        (out / "masked.json").parent.mkdir(parents=True, exist_ok=True)
        (out / "masked.json").write_text(
            json.dumps({"op": op, "labels": sorted(wanted), "pages": masked}, indent=1),
            encoding="utf-8",
            newline="\n",
        )
    done = 0
    for n, page in enumerate(pages, 1):
        path = src_dir / page["png"]
        if not path.is_file():
            raise RuntimeError(f"{path} is not there — render the base set first")
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if op == "grey":
            result = grey
        elif op == "binarise":
            _, result = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        elif op == "denoise":
            result = cv2.medianBlur(grey, 3)
        elif op == "deskew":
            angle = _deskew_angle(grey)
            if abs(angle) < 0.1:
                result = img  # not worth a resample, and a resample is not free
            else:
                h, w = img.shape[:2]
                matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
                result = cv2.warpAffine(
                    img,
                    matrix,
                    (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE,
                )
        elif op == "crop":
            inverted = cv2.bitwise_not(grey)
            _, mask = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
            coords = cv2.findNonZero(mask)
            if coords is None:
                result = img  # a blank page has no content box; leave it whole
            else:
                x, y, w, h = cv2.boundingRect(coords)
                pad = 12  # a recogniser wants some quiet space around a glyph
                y0, y1 = max(0, y - pad), min(img.shape[0], y + h + pad)
                x0, x1 = max(0, x - pad), min(img.shape[1], x + w + pad)
                result = img[y0:y1, x0:x1]
        elif op in ("maskfig", "masktab"):
            # THE PAGE KEEPS ITS CANVAS. That is the difference from `crop`, which shrank the
            # page and thereby removed the margin that tells a model where the scan ends — the
            # cut lines it then completed are why crop was not carried forward. Whiting a
            # region out in place leaves every edge where it was.
            wanted = MASK_FIGURE | (MASK_TABLE if op == "masktab" else set())
            result = img.copy()
            for label, x0, y0, x1, y1 in regions.get(page["png"], []):
                if label not in wanted:
                    continue
                a, b = max(0, int(y0)), min(img.shape[0], int(y1))
                c, d = max(0, int(x0)), min(img.shape[1], int(x1))
                if b > a and d > c:
                    result[a:b, c:d] = 255
        else:
            raise ValueError(f"unknown op {op}")
        cv2.imwrite(str(out / page["png"]), result)
        done += 1
        if n % 20 == 0 or n == len(pages):
            print(f"  {n}/{len(pages)}", flush=True)
    print(f"{op}: {done} pages into {out}")
    return done


# Each variant is compared against the render it was MADE FROM, not against the colour base
# in every case: `binarise` and `denoise` are computed from the greyscale, so scoring them
# against colour would credit each with whatever greyscale alone is worth.
VARIANT_BASE = {
    "dpi200": "base",
    "dpi250": "base",
    "dpi300": "base",
    "grey": "base",
    "deskew": "base",
    "crop": "base",
    "maskfig": "base",
    "masktab": "base",
    "binarise": "grey",
    "denoise": "grey",
}


def _pct(block: dict | None, key: str) -> str:
    """A percentage from a scored block, or `n/a`. The scorer writes `None` where a metric
    does not apply to a tier, so `.get(key, 0)` hands back the None and multiplying raises."""
    value = (block or {}).get(key)
    return f"{value * 100:5.1f}%" if isinstance(value, (int, float)) else "  n/a"


def compare(
    scores: Path, engine: str, base: Path | None = None, tiers: set[str] | None = None
) -> None:
    """The variant table and the paired per-page test, from the scored runs.

    THE PAIRED TEST IS THE POINT. Every variant reads the same 90 pages, so the per-page
    differences are paired and a mean over them hides how it was earned: a variant that
    improves three pages a lot and worsens forty a little has a flattering mean and is a
    loss. Win/loss/tie and the median say which happened; the mean alone does not.
    """
    import statistics  # noqa: PLC0415

    order = ["base", *VARIANT_BASE]
    loaded = {}
    for v in dict.fromkeys(order):
        # `--base` points at the unpreprocessed run when it already lives elsewhere — the
        # dots.mocr baseline is the scored `runs/dots-mocr.json`, and copying a 200 KB
        # artefact in beside the variants would put the same figures in the tree twice.
        path = base if (v == "base" and base is not None) else scores / f"{v}.json"
        if path.is_file():
            loaded[v] = json.loads(path.read_text(encoding="utf-8"))
    if "base" not in loaded:
        raise RuntimeError(
            f"{base or scores / 'base.json'} is not there — nothing to compare against"
        )
    missing = [v for v in VARIANT_BASE if v not in loaded]
    if missing:
        print(f"not run for {engine}: {', '.join(missing)}\n")

    scored = {v: d["pages_scored"] for v, d in loaded.items()}
    if len(set(scored.values())) != 1:
        # A variant scored over a different page count is a different sample, and comparing
        # its CER with the others' would be comparing two things.
        raise RuntimeError(f"variants scored different page counts: {scored}")

    dk = loaded["base"]["overall"]["dockets"]["truth"]
    dt = loaded["base"]["overall"]["dates"]["truth"]
    print(
        f"{engine}: {loaded['base']['pages_scored']} pages a variant, "
        f"{dk} dockets and {dt} dates in the ground truth"
    )
    print(
        f"\n{'variant':10s} {'CER':>6s} {'clean':>6s} {'degr':>6s} {'tab':>6s} "
        f"{'dockets':>9s} {'dates':>9s} {'labels':>7s} {'invents (worst)':>15s} {'completed':>10s}"
    )
    for v in loaded:
        o, bt = loaded[v]["overall"], loaded[v]["by_tier"]
        # INVENTION IS COUNTED FROM THE PER-PAGE ROWS, NOT TAKEN FROM `by_tier`. Two ways of
        # getting this wrong have already been published. `overall.false_chars` is a key the
        # scorer never writes, so reading it printed a confident 0 everywhere; and
        # `by_tier.graphic.false_chars` is a MEAN over nine pages, so printing it turned
        # "36 characters on one page" into "4". Step 3 states the rule this obeys: report a
        # count of pages and the worst page, never a mean, because the distribution is eight
        # zeros and an outlier and a mean of that says nothing.
        graphic = [p for p in loaded[v]["pages"].values() if p.get("tier") == "graphic"]
        invented = [p.get("false_chars") or 0 for p in graphic]
        hits = sum(1 for c in invented if c > 0)
        worst = max(invented, default=0)
        g = bt.get("graphic") or {}
        print(
            f"{v:10s} {_pct(o, 'cer')} {_pct(bt.get('clean'), 'cer')} "
            f"{_pct(bt.get('degraded'), 'cer')} {_pct(bt.get('tabular'), 'cer')} "
            f"{o['dockets']['hit']:5d}/{o['dockets']['truth']:<3d} "
            f"{o['dates']['hit']:5d}/{o['dates']['truth']:<3d} "
            f"{_pct(g.get('labels'), 'recall')} "
            f"{f'{hits} of {len(graphic)} ({worst:.0f})':>15s} "
            f"{o.get('cut_completed') or 0:10d}"
        )
    print("\n  `invent` is characters asserted on a graphic page that carries none and")
    print("  `completed` is [cut] lines an engine finished: the two invention probes, and")
    print("  the ones a preprocessing step can quietly worsen while CER improves.")
    print("\n  dockets and dates are printed as counts, not rates, because the docket")
    print(f"  denominator is {dk}: one page moves it several points and it cannot referee")
    print(f"  a comparison this close. The {dt} dates can.")

    print("\nPAIRED, per page, each against the render it was made from")
    print(
        f"{'variant':10s} {'vs':>7s} {'n':>4s} {'better':>7s} {'worse':>6s} {'tie':>5s} "
        f"{'median':>9s} {'mean':>9s}"
    )
    for v, against in VARIANT_BASE.items():
        if v not in loaded or against not in loaded:
            continue
        pb, pv = loaded[against]["pages"], loaded[v]["pages"]
        common = [
            k
            for k in pb
            if k in pv
            and pb[k].get("cer") is not None
            and pv[k].get("cer") is not None
            and (tiers is None or pb[k].get("tier") in tiers)
        ]
        if not common:
            print(f"{v:10s} {against:>7s}    no page matches the tier filter")
            continue
        deltas = [pv[k]["cer"] - pb[k]["cer"] for k in common]  # negative: the variant read better
        better = sum(1 for d in deltas if d < -1e-9)
        worse = sum(1 for d in deltas if d > 1e-9)
        print(
            f"{v:10s} {against:>7s} {len(deltas):4d} {better:7d} {worse:6d} "
            f"{len(deltas) - better - worse:5d} {statistics.median(deltas) * 100:+8.2f}pp "
            f"{statistics.mean(deltas) * 100:+8.2f}pp"
        )
    print("\n  n is under the page count because a graphic or blank page carries no CER -")
    print("  it is scored as a label set and as invented characters instead.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="re-render from the source PDFs at a chosen dpi")
    r.add_argument("--dpi", type=int, required=True)
    r.add_argument("--blobs", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--sample", type=Path, default=SAMPLE)

    d = sub.add_parser("derive", help="one image operation over an existing page set")
    d.add_argument("--op", choices=OPS, required=True)
    d.add_argument("--pages", type=Path, required=True)
    d.add_argument("--out", type=Path, required=True)
    d.add_argument("--sample", type=Path, default=SAMPLE)

    c = sub.add_parser("compare", help="the variant table and the paired test, from scored runs")
    c.add_argument(
        "--scores", type=Path, required=True, help="dir of <variant>.json from ocr_score"
    )
    c.add_argument("--engine", required=True, help="which engine these scores are of")
    c.add_argument("--base", type=Path, default=None, help="the unpreprocessed run, if elsewhere")
    c.add_argument(
        "--tiers",
        default=None,
        help="restrict the paired test to these tiers, e.g. clean,degraded — the primarily "
        "text pages, which is where masking a figure is meant to be used",
    )

    args = ap.parse_args(argv)
    if args.cmd == "compare":
        tiers = set(args.tiers.split(",")) if args.tiers else None
        compare(args.scores, args.engine, args.base, tiers)
        return 0
    pages = selected(args.sample)
    print(f"{len(pages)} selected pages")
    if args.cmd == "render":
        render(pages, args.blobs, args.out, args.dpi)
    else:
        derive(pages, args.pages, args.out, args.op)
    return 0


if __name__ == "__main__":
    sys.exit(main())
