"""Encode the sampled pages for the check queue: trim the render down to the scan itself,
threshold per page, and embed at full resolution.

A 150 dpi render is the whole PDF page, which is often legal-size or oversized with the
scan sitting in one corner — measured 2026-08-29, the content is 55-76% of the render on
half the sample. Fitting the *page* therefore fits mostly white and the type comes out
small. Both the blank margins and the scanner's solid black bars are trimmed from the
edges inward, never from the middle.

The trim counts ink on the *thresholded* image, not brightness on the grey one: a column
holding a few faint glyphs still averages near-white, and trimming on the mean clipped the
right-hand edge off a light-toner letter (caught 2026-08-29).
"""

import base64
import io
import json
from pathlib import Path

from PIL import Image

ROOT = Path("e:/DevProjects/docket-yard")
BLANK, BAR, PAD = 0.0012, 0.90, 12  # ink fraction: an empty line, a solid bar, padding kept


def otsu(hist):
    total = sum(hist)
    s = sum(i * h for i, h in enumerate(hist))
    sb = wB = 0.0
    best = (128, -1.0)
    for t in range(256):
        wB += hist[t]
        if wB == 0:
            continue
        wF = total - wB
        if wF == 0:
            break
        sb += t * hist[t]
        v = wB * wF * ((sb / wB) - ((s - sb) / wF)) ** 2
        if v > best[1]:
            best = (t, v)
    return best[0]


def ink_profile(mask, size, axis):
    """Ink fraction per row (axis=0) or per column (axis=1), computed in C by resizing."""
    w, h = size
    strip = mask.resize((1, h) if axis == 0 else (w, 1), Image.BOX)
    return [1.0 - v / 255.0 for v in strip.getdata()]


def edge_trim(profile):
    lo, hi = 0, len(profile) - 1
    while lo < hi and (profile[lo] < BLANK or profile[lo] > BAR):
        lo += 1
    while hi > lo and (profile[hi] < BLANK or profile[hi] > BAR):
        hi -= 1
    return lo, hi


def content_box(mask, size):
    w, h = size
    y0, y1 = edge_trim(ink_profile(mask, size, 0))
    x0, x1 = edge_trim(ink_profile(mask, size, 1))
    box = (max(0, x0 - PAD), max(0, y0 - PAD), min(w, x1 + 1 + PAD), min(h, y1 + 1 + PAD))
    cw, ch = box[2] - box[0], box[3] - box[1]
    if cw < w * 0.2 or ch < h * 0.2:  # a near-empty page: trust the render, not the trim
        return (0, 0, w, h)
    return box


def main():
    sel = json.loads((ROOT / "data/ocr/selected.json").read_text(encoding="utf-8"))
    out, total, kept, lost, fallback = {}, 0, [], [], []
    for p in sel:
        g = Image.open(ROOT / "data/ocr/pages" / p["png"]).convert("L")
        full = g.size
        t = otsu(g.histogram())
        mask = g.point(lambda v, t=t: 255 if v > t else 0).convert("L")  # 0 = ink
        box = content_box(mask, full)
        ink_all = mask.histogram()[0]
        ink_kept = mask.crop(box).histogram()[0]
        lost.append(0.0 if ink_all == 0 else 1 - ink_kept / ink_all)
        g = g.crop(box)
        bw = g.point(lambda v, t=t: 255 if v > t else 0, mode="1")
        ink = bw.histogram()[0] / (bw.size[0] * bw.size[1])
        b = io.BytesIO()
        if 0.002 < ink < 0.45:
            bw.save(b, "PNG", optimize=True)
            mime = "image/png"
        else:  # nothing to threshold, or a black-heavy scan: keep the greys
            g.save(b, "JPEG", quality=70, optimize=True)
            mime = "image/jpeg"
            fallback.append(p["png"])
        out[p["png"]] = {
            "m": mime,
            "d": base64.b64encode(b.getvalue()).decode(),
            "w": g.size[0],
            "h": g.size[1],
        }
        total += len(b.getvalue())
        kept.append((g.size[0] * g.size[1]) / (full[0] * full[1]))
    (ROOT / "data/ocr/pageimg.json").write_text(json.dumps(out), encoding="utf-8")
    print(f"{len(out)} pages, {total // 1024} KB raw ({int(total * 1.34) // 1024} KB base64)")
    print(f"area kept: {min(kept):.0%} smallest, {sum(kept) / len(kept):.0%} mean")
    print(f"ink lost to the trim: {max(lost):.4%} worst, {sum(lost) / len(lost):.4%} mean")
    print("greyscale fallbacks:", fallback)


if __name__ == "__main__":
    main()
