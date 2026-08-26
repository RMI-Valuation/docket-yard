#!/usr/bin/env python3
"""Text-layer extraction over every held document, on RMI-AI-MACHINE (architecture.md).

The first batch job on the enrichment box, and the groundwork for the extraction benchmark
(docs/extraction-benchmark.md): every PDF the record holds gets a per-page text layer with
provenance — which tool, which version, when — written beside the blob store as JSON. The
production store is not touched; the internal API that will carry assertions back to the
instance does not exist yet, and this output is what it will carry.

Runs with PyMuPDF if installed, else the `pdftotext` CLI (poppler). Restartable: a document
whose output exists for the same method version is skipped. Nothing here interprets text;
it records what the file says and where, page by page (ADR 0003: layout, not just text).

    python3 extract_text.py /data/docketyard/blobs /data/docketyard/text
"""

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

METHOD = "text-layer"
METHOD_VERSION = "1"
MIN_CHARS_PER_PAGE = 20  # below this on every page, the file is image-only (needs OCR)


def tool():
    try:
        import fitz  # PyMuPDF

        return "pymupdf", fitz.VersionBind, fitz
    except ImportError:
        exe = shutil.which("pdftotext")
        if not exe:
            sys.exit("need PyMuPDF (pip install pymupdf) or poppler's pdftotext")
        version = subprocess.run(
            [exe, "-v"], capture_output=True, text=True, check=False
        ).stderr.split("\n")[0]
        return "pdftotext", version, None


def pages_pymupdf(fitz, path: Path) -> list[str]:
    with fitz.open(path) as doc:
        return [page.get_text("text") for page in doc]


def pages_pdftotext(path: Path) -> list[str]:
    out = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True
    ).stdout
    return out.split("\f")[:-1] or [out]


def is_pdf(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(5) == b"%PDF-"


def main(blobs: Path, out: Path) -> None:
    name, version, fitz = tool()
    out.mkdir(parents=True, exist_ok=True)
    stats = {"seen": 0, "pdf": 0, "extracted": 0, "skipped": 0, "image_only": 0, "failed": 0}
    started = time.time()
    for path in sorted(blobs.glob("*/*")):
        if path.suffix == ".tmp" or not path.is_file():
            continue
        stats["seen"] += 1
        sha = path.name
        target = out / sha[:2] / f"{sha}.json"
        if target.exists():
            try:
                if (
                    json.loads(target.read_text(encoding="utf-8"))["method_version"]
                    == METHOD_VERSION
                ):
                    stats["skipped"] += 1
                    continue
            except (ValueError, KeyError):
                pass
        if not is_pdf(path):
            continue
        stats["pdf"] += 1
        try:
            pages = pages_pymupdf(fitz, path) if fitz else pages_pdftotext(path)
        except Exception as e:  # noqa: BLE001 — one bad file must not stop the batch
            stats["failed"] += 1
            print(f"FAILED {sha} ({type(e).__name__}: {e})", file=sys.stderr)
            continue
        image_only = all(len(p.strip()) < MIN_CHARS_PER_PAGE for p in pages)
        stats["image_only"] += int(image_only)
        record = {
            "document_sha256": sha,
            "size_bytes": path.stat().st_size,
            "method": METHOD,
            "method_version": METHOD_VERSION,
            "tool": name,
            "tool_version": version,
            "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "pages": len(pages),
            "chars": sum(len(p) for p in pages),
            "image_only": image_only,
            "text_sha256": hashlib.sha256("\f".join(pages).encode()).hexdigest(),
            "page_text": pages,
        }
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        stats["extracted"] += 1
        if stats["extracted"] % 500 == 0:
            print(f"{stats} {time.time() - started:.0f}s", flush=True)
    print(f"done {stats} in {time.time() - started:.0f}s using {name} {version}")
    (out / "_manifest.json").write_text(
        encoding="utf-8",
        data=json.dumps(
            {
                **stats,
                "method": METHOD,
                "method_version": METHOD_VERSION,
                "tool": name,
                "tool_version": version,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            }
        ),
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
