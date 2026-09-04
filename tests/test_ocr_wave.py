"""`tools/rmi-ai-machine/ocr_wave.py`: the wave's pure half, and its output through the real
loader. The box tool is not a package, so it is loaded from its path; the engines are not
here, so what is tested is the rule, the assembly, and that every reading document it
writes is one `docketyard text load` takes — primary, second with its agreement, graphic.
"""

import importlib.util
from pathlib import Path

from docketyard.store import db
from docketyard.text import load
from tests.test_documents import (  # noqa: F401 — the fixture registers itself here too
    _store_with_document,
    no_store_in_the_environment,
)

TOOL = Path(__file__).resolve().parents[1] / "tools" / "rmi-ai-machine" / "ocr_wave.py"


def _module():
    spec = importlib.util.spec_from_file_location("ocr_wave", TOOL)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _region(label, area=100.0):
    return {"label": label, "score": 0.9, "area": area}


def test_the_rule_is_the_probes_plus_the_provisional_split():
    w = _module()
    assert w.classify([]) == "unrouted"  # "no regions" routes to a reader, never a skip
    assert w.classify([_region("page_number"), _region("header")]) == "unrouted"
    assert w.classify([_region("text")] * 3 + [_region("table")]) == "tabular"
    assert w.classify([_region("text", 100), _region("image", 100)]) == "graphic"
    assert w.classify([_region("text", 100), _region("image", 99)]) == "clean"
    assert w.classify([_region("text")] * w.REGION_CUT) == "clean"
    assert w.classify([_region("text")] * (w.REGION_CUT + 1)) == "degraded"
    # furniture counts toward the region total, as the probe's separability measure did
    assert w.classify([_region("text")] * w.REGION_CUT + [_region("footer")]) == "degraded"
    assert w.ROUTER_VERSION.startswith("provisional")


def test_ppocr_lines_read_top_to_bottom_then_left_to_right():
    w = _module()
    lines = [
        {"text": "right", "score": 0.9, "box": [[300, 10], [400, 10], [400, 20], [300, 20]]},
        {"text": "left", "score": 0.9, "box": [[10, 12], [100, 12], [100, 22], [10, 22]]},
        {"text": "below", "score": 0.9, "box": [[10, 200], [100, 200], [100, 210], [10, 210]]},
        {"text": "boxless", "score": None, "box": None},
    ]
    assert w.ppocr_text(lines) == "left\nright\nbelow\nboxless"


def _cache_and_route(w, sha, texts_by_page, classes):
    cache = {
        "document_sha256": sha,
        "method": "pp-ocrv6-medium",
        "method_version": "3.3.0",
        "render_profile": "150",
        "ran_at": "2026-09-05T00:00:00+00:00",
        "pages": [
            {
                "page_no": no,
                "lines": [{"text": t, "score": 0.8, "box": None} for t in texts.split("\n")],
                "error": None,
            }
            for no, texts in texts_by_page.items()
        ],
        "error": None,
    }
    route = {"document_sha256": sha, "pages": {str(no): {"class": c} for no, c in classes.items()}}
    return cache, route


def test_the_three_derived_readings_load_in_order_and_the_second_carries_its_band(tmp_path):
    w = _module()
    path, sha = _store_with_document(tmp_path)
    texts = {1: "clean typescript page", 2: "faint fax page", 3: "map of the line", 4: "rate table"}
    classes = {1: "clean", 2: "degraded", 3: "graphic", 4: "tabular"}
    cache, route = _cache_and_route(w, sha, texts, classes)
    key = {k: cache[k] for k in ("method", "method_version", "render_profile")}

    def loaded(doc):
        con = db.connect(path)
        out = load.load_reading(con, tmp_path, load.from_reading(doc, b"{}"))
        con.commit()
        con.close()
        return out

    # 1. the PP primary: clean and unrouted pages only
    eng, pages, failed = w.select_pages(cache, route, {"clean", "unrouted"})
    primary = w.reading_document(
        sha,
        key,
        "primary",
        "pp-ocrv6.json",
        eng,
        pages,
        pages_failed=failed,
        ran_at="2026-09-05T00:00:01+00:00",
    )
    assert [p["page_no"] for p in primary["pages"]] == [1]
    assert primary["pages"][0]["route"] == w.route_of("clean")
    assert loaded(primary) == "loaded"
    # 2. the dots primary on the degraded page
    dots = w.reading_document(
        sha,
        w.DOTS,
        "primary",
        "dots.mocr.json",
        [{"page_no": 2, "raw": "[]", "blocks": []}],
        [
            {
                "page_no": 2,
                "text": "faint fax page read well",
                "member": "engine/pages/0",
                "route": w.route_of("degraded"),
            }
        ],
        pages_failed=0,
    )
    assert loaded(dots) == "loaded"
    # 3. PP as the second reading of the degraded page, measured against dots
    agree = w.agreement_against({2: "faint fax page read well"}, dots)
    eng, pages, failed = w.select_pages(cache, route, {"degraded"}, agree)
    second = w.reading_document(
        sha,
        key,
        "second",
        "pp-ocrv6.json",
        eng,
        pages,
        pages_failed=failed,
        ran_at="2026-09-05T00:00:02+00:00",
    )
    assert [p["page_no"] for p in second["pages"]] == [2]
    a = second["pages"][0]["agreement"]
    assert 0 < a["distance"] < 1 and a["against"] == {
        "method": "dots.mocr",
        "method_version": "1.5",
        "render_profile": "200",
    }
    assert loaded(second) == "loaded"
    # 4. maps last: PP primary on the graphic page
    eng, pages, failed = w.select_pages(cache, route, {"graphic"})
    graphic = w.reading_document(
        sha,
        key,
        "primary",
        "pp-ocrv6.json",
        eng,
        pages,
        pages_failed=failed,
        ran_at="2026-09-05T00:00:03+00:00",
    )
    assert [p["page_no"] for p in graphic["pages"]] == [3]
    assert loaded(graphic) == "loaded"
    # what the store holds: three primaries, one second with its band, no tabular row
    con = db.connect(path)
    rows = con.execute(
        "SELECT page_no, reading_role, method, route_class, agreement_distance FROM document_text"
        " WHERE document_sha256 = ? AND superseded_by IS NULL ORDER BY page_no, reading_role",
        (sha,),
    ).fetchall()
    assert rows == [
        (1, "primary", "pp-ocrv6-medium", "clean", None),
        (2, "primary", "dots.mocr", "degraded", None),
        (2, "second", "pp-ocrv6-medium", "degraded", a["distance"]),
        (3, "primary", "pp-ocrv6-medium", "graphic", None),
    ]
    con.close()


def test_a_second_reading_with_no_primary_to_be_against_is_left_out():
    w = _module()
    sha = "e" * 64
    cache, route = _cache_and_route(w, sha, {1: "a", 2: "b"}, {1: "degraded", 2: "degraded"})
    dots = {"method": "dots.mocr", "method_version": "1.5", "render_profile": "200"}
    eng, pages, _ = w.select_pages(cache, route, {"degraded"}, w.agreement_against({1: "a"}, dots))
    assert [p["page_no"] for p in pages] == [1] and len(eng) == 1


def test_a_failed_page_is_counted_and_left_out():
    w = _module()
    sha = "e" * 64
    cache, route = _cache_and_route(w, sha, {1: "a", 2: "b"}, {1: "clean", 2: "clean"})
    cache["pages"][1]["error"] = "RuntimeError: render"
    eng, pages, failed = w.select_pages(cache, route, {"clean"})
    assert [p["page_no"] for p in pages] == [1] and failed == 1
