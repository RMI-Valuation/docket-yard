"""Encode the sampled pages for the check queue: the page as the Board's PDF has it, at
full resolution, thresholded per page.

**The page is not cropped.** A reviewer checking a transcription against a page must see
the page, margins and all; altering the image to suit the display would put them at one
remove from the source. The white margin is measured and reported here because it is a real
property of the renders — a 150 dpi render is the whole PDF page, often legal-size or
oversized with the scan in one corner, and the content is 55-76% of the render on half the
sample — but whether to trim before handing a page to an OCR engine is a **step 2
preprocessing variable to measure**, not something to do to the reviewer's copy.

The threshold is Otsu per page: these are black type on white paper, so dropping the
scanner's grey costs nothing, compresses enormously, and reads more clearly than the
greyscale original on a faint page.
"""

import base64
import io
import json
from pathlib import Path

from PIL import Image

ROOT = Path("e:/DevProjects/docket-yard")
BLANK, BAR, PAD = 0.0012, 0.90, 12  # ink fraction: an empty line, a solid bar, padding


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
    """Where the ink actually is. Measured and reported; not applied to the image."""
    w, h = size
    y0, y1 = edge_trim(ink_profile(mask, size, 0))
    x0, x1 = edge_trim(ink_profile(mask, size, 1))
    return (max(0, x0 - PAD), max(0, y0 - PAD), min(w, x1 + 1 + PAD), min(h, y1 + 1 + PAD))


def main():
    sel = json.loads((ROOT / "data/ocr/selected.json").read_text(encoding="utf-8"))
    out, total, content, fallback = {}, 0, [], []
    for p in sel:
        g = Image.open(ROOT / "data/ocr/pages" / p["png"]).convert("L")
        w, h = g.size
        t = otsu(g.histogram())
        mask = g.point(lambda v, t=t: 255 if v > t else 0).convert("L")
        box = content_box(mask, g.size)
        content.append(((box[2] - box[0]) * (box[3] - box[1])) / (w * h))
        bw = g.point(lambda v, t=t: 255 if v > t else 0, mode="1")
        ink = bw.histogram()[0] / (w * h)
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
            "w": w,
            "h": h,
            # where the ink is, for a reader who wants to fill the frame with it; the
            # image itself is the whole page
            "c": [box[0], box[1], box[2] - box[0], box[3] - box[1]],
        }
        total += len(b.getvalue())
    (ROOT / "data/ocr/pageimg.json").write_text(json.dumps(out), encoding="utf-8")
    print(
        f"{len(out)} pages, whole, {total // 1024} KB raw ({int(total * 1.34) // 1024} KB base64)"
    )
    mean = sum(content) / len(content)
    print(f"ink occupies {mean:.0%} of the render on average, {min(content):.0%} at least")
    print("greyscale fallbacks:", fallback)


if __name__ == "__main__":
    main()
