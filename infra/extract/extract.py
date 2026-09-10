#!/usr/bin/env python3
"""The text-layer parser, in a container that holds nothing worth stealing (ADR 0024 D2).

    /requests/<name>.json   {"dispatched_at": "...", "documents": ["<64 hex>", ...]}
    /blobs/<ab>/<sha>       read-only, content-addressed
    /spool/<ab>/<sha>.json  the extraction record `docketyard text load` reads

**THIS FILE IMPORTS NOTHING OF DOCKET YARD, AND THAT IS THE POINT.** The container has
`pymupdf` and the standard library: no store, no `DY_EMAIL_KEY`, no network, no blob write
access. A PDF is the least trustworthy input this project handles — it is a program in a
stack machine, fetched from a third party — so the thing that parses it is given nothing to
lose. What leaves this container is JSON on a spool directory, and the loader that reads it
has no PDF library.

**WHY A REQUEST DIRECTORY AND NOT AN INVOCATION.** ADR 0024 D4 says a dispatch is recorded
"before the container is invoked", and the only way for the poller — which runs inside the
`ingest` container — to invoke a sibling container is the Docker socket. Mounting it would
give the poller root on the host, which is a larger privilege than the parser's isolation
buys back: D2's whole argument is that the component touching hostile bytes holds nothing,
and it is defeated if the component that starts it holds everything. So the poller ENQUEUES
— it writes a request file naming the documents — and this service consumes it. Every
property D4 asks for survives: the dispatch row is written and committed before the request
file exists, the list is explicit, and the parser is scoped to it. What changes is that a
spool file may land on the pass after the one that asked for it, which the reconciliation
already tolerates because it compares against runs, not against this pass's own hand-off.

**NEVER A DIRECTORY SCAN** (D2). The blob pool is flat and content-addressed with no type
marker, so a self-scoping container would read every capture body in it — including the
JSON envelopes of every search response the record has ever stored. The names come from the
request file and are checked against the hex alphabet before they touch a path, so a name is
a name and never a traversal.

**A REFUSAL IS A RECORD** (D5). Bytes that are not a PDF, a file that will not open, one
over the page cap: each writes a stub carrying its reason, because a refusal that records
*that* it failed and never *why* is an ADR 0007 assertion missing its reason. A stub is a
successful pass over a file that cannot be read, and the queue's read test is what stops it
being asked for again for ever.
"""

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF: the only third-party import in this container

METHOD = "text-layer"
METHOD_VERSION = "2"  # the extraction record's own shape version, as extract_text.py writes
MIN_CHARS_PER_PAGE = 20  # below this on every page the file is image-only, and OCR's to read
# A PDF declaring more pages than any document in this record plausibly has. The queue's size
# limit does not bound this: a few hundred kilobytes of PDF can declare a million pages, and
# the parse would take the container's memory with it. Refused with a reason rather than
# attempted, exactly as the oversize case is.
MAX_PAGES = 5_000
SHA = re.compile(r"^[0-9a-f]{64}$")
IDLE_SECONDS = float(os.environ.get("DY_EXTRACT_IDLE", "10"))

BLOBS = Path(os.environ.get("DY_EXTRACT_BLOBS", "/blobs"))
SPOOL = Path(os.environ.get("DY_EXTRACT_SPOOL", "/spool"))
REQUESTS = Path(os.environ.get("DY_EXTRACT_REQUESTS", "/requests"))


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def header(sha: str, size: int, version: str) -> dict:
    """What every record carries, read or refused — the loader's key is (tool, tool_version,
    'native'), so these five fields are the reading's identity."""
    return {
        "document_sha256": sha,
        "size_bytes": size,
        "method": METHOD,
        "method_version": METHOD_VERSION,
        "tool": "pymupdf",
        "tool_version": version,
        "extracted_at": now(),
    }


def read_pages(path: Path) -> list[str]:
    """The text of each page, in order. `fitz` is asked for nothing else: no images, no
    annotations, no JavaScript, no rendering (ADR 0024 D8 — extraction quotes, it does not
    interpret)."""
    with fitz.open(path) as doc:
        if doc.page_count > MAX_PAGES:
            raise ValueError(f"{doc.page_count} pages, over the {MAX_PAGES} cap")
        return [page.get_text() for page in doc]


def extract(sha: str, version: str) -> dict:
    """One document's record: the pages, or a stub saying why not."""
    path = BLOBS / sha[:2] / sha
    if not path.is_file():
        # the poller named a document whose bytes this box does not hold — the blob cache is
        # pruned, so this is expected rather than exceptional, and it is a refusal with a
        # reason so the attempt is on record instead of vanishing
        return header(sha, 0, version) | {"outcome": "failed", "note": "no blob on this box"}
    size = path.stat().st_size
    try:
        with path.open("rb") as f:
            if f.read(5) != b"%PDF-":
                return header(sha, size, version) | {
                    "outcome": "not-paginable",
                    "note": "not a PDF",
                }
        pages = read_pages(path)
    except Exception as e:  # noqa: BLE001 — one hostile file must not stop the service
        return header(sha, size, version) | {
            "outcome": "failed",
            "note": f"{type(e).__name__}: {e}"[:500],
        }
    return header(sha, size, version) | {
        "pages": len(pages),
        "chars": sum(len(p) for p in pages),
        "image_only": all(len(p.strip()) < MIN_CHARS_PER_PAGE for p in pages),
        "text_sha256": hashlib.sha256("\f".join(pages).encode()).hexdigest(),
        "page_text": pages,
    }


def write(record: dict) -> Path:
    """`<sha>.json.tmp` then rename (ADR 0024 D9). The header alone asserts a page count, so
    a file truncated mid-write would publish a count whose text never loads — every pass, for
    ever. The rename is atomic within the volume; the temporary name is the target's so two
    passes over one document cannot collide on a shared scratch name."""
    target = SPOOL / record["document_sha256"][:2] / f"{record['document_sha256']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)
    return target


def documents(request: Path) -> tuple[list[str], int]:
    """The names in a request and how many were dropped, each checked against the hex
    alphabet BEFORE it is a path. A name that is not a digest is dropped and counted: the
    request comes from the poller, but a parser that trusts its input because of who wrote it
    is a parser that can be made to read `../../data/docketyard.sqlite`."""
    body = json.loads(request.read_text(encoding="utf-8"))
    named = body.get("documents") or []
    kept = [s for s in named if isinstance(s, str) and SHA.match(s)]
    return kept, len(named) - len(kept)


def remaining(request: Path, shas: list[str], at: str) -> None:
    """Rewrite the request with what is still to do, atomically."""
    tmp = request.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"dispatched_at": at, "documents": shas}, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(request)


def serve_one(request: Path) -> dict:
    """One request, POPPING EACH DOCUMENT BEFORE IT IS PARSED.

    THE ORDER IS THE WHOLE POINT, and it is not the obvious one. A document that takes the
    container down — a decompression bomb inside the size cap, one enormous page — is killed
    by the memory limit, which is SIGKILL: no handler runs, no stub is written, nothing is
    recorded. If the request still named that document, `restart: unless-stopped` would bring
    the container back to the same oldest request, the same first document, and the same kill,
    for ever: every later request unread and the halt's own canary never reaching the parser.
    That is the head-of-line block ADR 0024 weighed against silent mass exhaustion, arriving
    through the door the ADR did not consider (code review, 2026-09-10).

    Popping first costs a crash the in-flight document's parse — no spool file, so nothing
    lands — which is exactly the case `EXTRACT_ATTEMPTS` exists for: the poller counts the
    dispatch, asks twice more, and then stops asking. A document that kills the parser is
    supposed to exhaust its attempts. It is not supposed to take the queue with it.
    """
    version = fitz.VersionBind
    named, dropped = documents(request)
    at = json.loads(request.read_text(encoding="utf-8")).get("dispatched_at", "")
    counts = {"read": 0, "refused": 0, "bad_name": dropped}
    while named:
        sha, named = named[0], named[1:]
        remaining(request, named, at)
        record = extract(sha, version)
        write(record)
        counts["read" if "page_text" in record else "refused"] += 1
    request.unlink(missing_ok=True)
    return counts


def main() -> int:
    for path in (SPOOL, REQUESTS):
        path.mkdir(parents=True, exist_ok=True)
    print(f"extract: pymupdf {fitz.VersionBind}, blobs {BLOBS}, spool {SPOOL}", flush=True)
    while True:
        pending = sorted(p for p in REQUESTS.glob("*.json") if p.is_file())
        for request in pending:
            started = time.time()
            try:
                counts = serve_one(request)
            except Exception as e:  # noqa: BLE001 — a malformed request must not end the loop
                print(f"extract: {request.name} FAILED ({type(e).__name__}: {e})", flush=True)
                request.unlink(missing_ok=True)
                continue
            print(
                f"extract: {request.name} {counts} in {time.time() - started:.1f}s",
                flush=True,
            )
        time.sleep(IDLE_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
