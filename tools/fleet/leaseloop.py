#!/usr/bin/env python3
"""What both lease loops do the same way, held once: `dots_worker.py` and `hunyuan_worker.py`.

The two loops are twins duplicated on purpose (`hunyuan_worker`'s docstring says why: the dots
loop is interleaved with its server's life). What is NOT interleaved with anything — the page
index, registration, and the three ways a document's bytes fail to arrive — lives here, so a
rule about them changes in one place, and so it can be tested without loading a model. Both
`page_index` and `register_or_exit` had been added to both files in one commit and could only
drift from there (`/code-review`, 2026-09-17); the blob branches lived inside each `main()`,
which loads a model and cannot be called from a test, in a change whose whole point was that a
misclassified failure loops the fleet (`/code-review high`, 2026-09-19).

WHOSE FAULT A MISSING DOCUMENT IS (ADR 0025 addendum, proposals 5 and 6):

    BlobMissing      the document's: not in the store. `blob: ...`, attempt spent, not final
    BlobCorrupt      the store's, and not final either: a document is never written off on one
                     answer from a store having a bad day. Also `blob: ...`
    BlobUnavailable  the environment's: the node or its credential. Every page goes back
                     UNSPENT and the worker exits 4 for the resubmitter to bring back
"""

import time
from pathlib import Path

from pagequeue import BlobCorrupt, BlobMissing

EXIT_ENVIRONMENT = 4


class DocumentFailed(Exception):
    """The document's — its bytes are not here or will not open; not final."""


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + msg, flush=True)


def page_index(no: int, page_count: int) -> int:
    """The 0-based index of page `no` of a document of `page_count` pages, or DocumentFailed.
    Both ends: page 0 would index the LAST page (`doc[-1]`) and read the wrong one silently
    (Copilot on PR #34, 2026-09-17)."""
    if not 1 <= no <= page_count:
        raise DocumentFailed(f"has {page_count} pages, the route says {no}")
    return no - 1


def register_or_exit(q, name: str, pass_: str, producer: dict) -> int | None:
    """Register with the queue, or the environment exit code with the reason logged. A queue
    that is locked, unreachable or refuses the key is the environment's failure, not an
    unclassified crash (Copilot on PR #34, 2026-09-17)."""
    try:
        q.register(name, pass_, producer)
    except Exception as e:  # noqa: BLE001 — every way registration fails is the environment's
        log(f"could not register with the queue ({type(e).__name__}: {e}); exit {EXIT_ENVIRONMENT}")
        return EXIT_ENVIRONMENT
    return None


class Fetched:
    """The one document a remote worker holds, on its scratch disk.

    STREAMED TO DISK, NEVER INTO RAM. A page reader takes a path as readily as bytes, and the
    documents in this record reach 1.07 GB — which is what OOM-killed the instance in August,
    and the smallest box that leases pages has 8 GB (code review). One at a time: a claim is
    usually one document's pages in order, so the next document replaces the last."""

    def __init__(self, q, scratch: Path):
        self.q, self.scratch = q, scratch
        self.sha: str | None = None
        self.path: Path | None = None

    def path_of(self, sha: str) -> Path:
        """The document on disk, fetched if it is not the one held. `BlobMissing` and
        `BlobCorrupt` become `DocumentFailed`; `BlobUnavailable` rises, because it is not the
        document's and the loop must give every page back unspent (`node_unavailable`)."""
        if self.sha == sha and self.path is not None:
            return self.path
        self.drop()  # BEFORE the fetch: a failed fetch must not leave the old name held
        try:
            path = self.q.blob_into(sha, self.scratch / f"doc-{sha}.pdf")
        except BlobMissing as e:
            raise DocumentFailed(f"not in the store: {e}") from e
        except BlobCorrupt as e:
            # the store's, not the page's, and it will not fix itself on a retry — but it is
            # not final either. The coordinator has already printed the alarm.
            raise DocumentFailed(f"the store is corrupt here: {e}") from e
        self.sha, self.path = sha, path
        return path

    def drop(self) -> None:
        """Delete the document held. Up to 1.07 GB, on a scratch disk shared with the renders,
        so the loop calls this in its `finally` too (code review)."""
        if self.path is not None:
            self.path.unlink(missing_ok=True)
        self.sha = self.path = None


def document_failed(q, name: str, job_id: int, sha: str, no: int, e: DocumentFailed) -> None:
    """The page goes back as `blob: ...` with its attempt spent, NOT final: the document is
    re-read at a later seed once its bytes are there. Not the worker's fault either — a worker
    that exited here would be restarted onto the same document, first in claim order, for ever.
    """
    q.fail(name, job_id, f"blob: {e}", final=False)
    log(f"  document {sha[:12]} {e}; p{no} back for a later seed")


def node_unavailable(q, name: str, ids: list[int], i: int, e: Exception) -> int:
    """THE ENVIRONMENT'S, SO NO PAGE PAYS. The node is unreachable or its credential is: every
    page in the fleet would fail identically, so the page in flight and every one after it go
    back UNSPENT and the worker exits for the resubmitter to bring back (ADR 0025 addendum,
    proposal 2). Retrying here is the loop the old bare re-raise produced, minus the traceback.

    THE RELEASE GOES TO THE SAME NODE THAT JUST FAILED, so it may fail too — and an exception
    here would escape as the traceback this whole mapping exists to prevent (ingest review). If
    it does not land, the leases expire instead, and `_reap` SPENDS the attempt rather than
    refunding it: the pages are not lost and no document is counted whole, but they are not
    free either. Said plainly in the log rather than claiming "unspent" when that may not be
    what happened."""
    try:
        q.release(name, ids[i:])
        back = f"{len(ids) - i} released unspent"
    except Exception as release_failed:  # noqa: BLE001 — the node is the fault
        back = (
            f"{len(ids) - i} could NOT be released"
            f" ({type(release_failed).__name__}); they wait for lease expiry,"
            " which spends an attempt each"
        )
    log(f"the node cannot serve documents ({e}); {back}; exit {EXIT_ENVIRONMENT}")
    return EXIT_ENVIRONMENT
