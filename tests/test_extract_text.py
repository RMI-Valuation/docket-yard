"""`tools/rmi-ai-machine/extract_text.py` v2: a record for every file it saw.

The box tool is not a package, so it is loaded from its path. Its reader is injected: the
box has PyMuPDF, this suite has neither it nor poppler, and the shape of the record is what
the pagination pass and the loader read.
"""

import importlib.util
import json
from pathlib import Path

from docketyard.text import load, paginate

TOOL = Path(__file__).resolve().parents[1] / "tools" / "rmi-ai-machine" / "extract_text.py"
PDF = b"%PDF-1.4 fake"
PAGES = ["abandonment in Perry County", ""]


def _module():
    spec = importlib.util.spec_from_file_location("extract_text", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _blobs(tmp_path, files):
    blobs = tmp_path / "blobs"
    for sha, body in files.items():
        (blobs / sha[:2]).mkdir(parents=True, exist_ok=True)
        (blobs / sha[:2] / sha).write_bytes(body)
    return blobs


def _reader(fail_on=()):
    def pages(path: Path):
        if path.name in fail_on:
            raise RuntimeError("cannot open")
        return list(PAGES)

    return ("fakepdf", "0.1", pages)


def test_every_file_seen_gets_a_record_and_a_failed_open_is_retried(tmp_path):
    et = _module()
    good, image, broken = "a" * 64, "b" * 64, "c" * 64
    blobs = _blobs(tmp_path, {good: PDF, image: b"\xff\xd8\xff a jpeg", broken: PDF})
    out = tmp_path / "text"
    stats = et.main(blobs, out, reader=_reader(fail_on={broken}))
    assert (stats["seen"], stats["pdf"], stats["extracted"], stats["failed"]) == (3, 2, 1, 1)
    records = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in out.glob("*/*.json")}
    assert set(records) == {good, image, broken}  # a record for EVERY file
    assert records[good]["page_text"] == PAGES and "outcome" not in records[good]
    assert records[image]["outcome"] == "not-paginable" and "page_text" not in records[image]
    assert records[broken]["outcome"] == "failed" and "cannot open" in records[broken]["note"]
    for r in records.values():
        assert (r["tool"], r["tool_version"], r["method_version"]) == ("fakepdf", "0.1", "2")
    # a restart: the good file and the non-PDF are skipped, the failed open is tried again
    stats = et.main(blobs, out, reader=_reader())
    assert (stats["skipped"], stats["extracted"], stats["failed"]) == (2, 1, 0)
    # and a v1 record that read pages is done: the bump to v2 added stubs, not readings
    v1 = json.loads((out / "aa" / f"{good}.json").read_text(encoding="utf-8")) | {
        "method_version": "1"
    }
    (out / "aa" / f"{good}.json").write_text(json.dumps(v1), encoding="utf-8")
    assert et.main(blobs, out, reader=_reader())["skipped"] == 3
    assert "page_text" in json.loads((out / "cc" / f"{broken}.json").read_text(encoding="utf-8"))


def test_the_stubs_are_what_the_passes_read(tmp_path):
    """The pagination pass writes the outcome the stub names; the loader records the run
    and no pages. Both are the reason the stubs exist (coverage denominator, 2026-09-03)."""
    et = _module()
    image, broken = "b" * 64, "c" * 64
    blobs = _blobs(tmp_path, {image: b"not a pdf", broken: PDF})
    out = tmp_path / "text"
    et.main(blobs, out, reader=_reader(fail_on={broken}))
    allowed = frozenset({"paginated", "not-paginable", "failed"})
    rows = {p.stem: paginate.read_file(p, allowed) for p in out.glob("*/*.json")}
    assert (rows[image].outcome, rows[image].page_count) == ("not-paginable", None)
    assert (rows[broken].outcome, rows[broken].had_text_layer) == ("failed", None)
    readings = {p.stem: load.read_file(p) for p in out.glob("*/*.json")}
    assert readings[image].header.outcome == "skipped" and readings[image].body()[1] == ()
    assert readings[broken].header.outcome == "failed" and readings[broken].body()[1] == ()
