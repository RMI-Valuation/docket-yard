"""Attachment fetching: bytes → content-addressed documents, capture-first.

Every fetch is itself a capture (the blob IS the response body), so a document's
provenance chain is complete: attachment row → document → document_source → capture.
Errata detection (ADR 0002): refreshing a URL whose attachment already holds a hash and
getting different bytes records the new document, chains it via supersedes_sha256, and
appends a document_replaced event. Detection is hash-level (method recorded on the event);
a byte change with identical content (regenerated PDFs) would false-positive, and the
extracted-text comparison belongs to the extraction milestone.

One URL is fetched once per run no matter how many records share it (the same document
appears under a docket and its sub-docket — measured), and every sharing record gets its
own document_source association.
"""

from collections.abc import Callable
from pathlib import Path
from sqlite3 import Connection

from docketyard.capture import records
from docketyard.ingest import observations
from docketyard.store import events
from docketyard.store.db import utcnow

FETCH_ACTION = "document_fetch"
DETECTION_METHOD = "sha256-compare"
DETECTION_METHOD_VERSION = 1

_EXTENSION_TYPES = {".pdf": "pdf", ".xlsx": "xlsx", ".zip": "zip", ".jpg": "jpg",
                    ".jpeg": "jpg", ".docx": "docx"}  # fmt: skip

# production: StbClient.fetcher(data_dir) — a file streamed onto the blob filesystem;
# a test may hand back bytes for a small fake document
Fetcher = Callable[[str], tuple[int, bytes | Path]]


def media_type_for(url: str, body: bytes) -> str | None:
    """What the bytes are, sniffed from magic numbers; the URL extension only
    disambiguates zip containers (xlsx/docx are zips) or fills in when nothing sniffs."""
    ext = _EXTENSION_TYPES.get(Path(url.split("?")[0]).suffix.lower())
    if body.startswith(b"%PDF-"):
        return "pdf"
    if body.startswith(b"\xff\xd8"):
        return "jpg"
    if body.startswith(b"PK\x03\x04"):
        return ext if ext in ("xlsx", "docx") else "zip"
    return ext


def fetch_attachments(
    con: Connection,
    data_dir,
    fetch: Fetcher,
    *,
    limit: int | None = None,
    refresh: bool = False,
    observed_in: str | None = None,
    ingest_mode: str = "forward",
) -> dict:
    """Fetch attachments into the store. `fetch` is injected — in production a
    `StbClient.download` bound to the data directory, which streams each file to disk;
    a test's fetcher may return bytes — so the pipeline is testable without the network."""
    records.sweep_staging(data_dir)  # what a killed run left half-written
    by_url: dict[str, list[observations.AttachmentRef]] = {}
    for ref in observations.attachments(
        con, unfetched_only=not refresh, limit=limit, observed_in=observed_in
    ):
        by_url.setdefault(ref.url, []).append(ref)
    stats = {"fetched": 0, "unchanged": 0, "new_documents": 0, "replaced": 0, "failed": 0}
    for url, owners in by_url.items():
        old_sha = next((o.document_sha256 for o in owners if o.document_sha256), None)
        body: bytes | Path = b""
        try:
            status, body = fetch(url)
            if status != 200:  # an error page is not the document, whatever the client did
                raise RuntimeError(f"HTTP {status}")
            # what the document table needs, read before save_capture moves a streamed file
            if isinstance(body, Path):
                size = body.stat().st_size
                with body.open("rb") as f:
                    head = f.read(16)
            else:
                size, head = len(body), body[:16]
        except Exception as e:  # noqa: BLE001 — one bad URL must not strand the batch
            print(f"  FAILED {url} ({type(e).__name__}: {e})")
            stats["failed"] += 1
            if isinstance(body, Path):
                body.unlink(missing_ok=True)
            continue
        capture_id = records.save_capture(
            con,
            data_dir,
            source_system="stb-dcms",
            endpoint=url,
            table_action=FETCH_ACTION,
            request_params=[("url", url)],
            body=body,
            http_status=status,
            ingest_mode=ingest_mode,
        )
        # a fetch has no table filter to assert and is consumed by definition: the
        # verdict is "not applicable" (NULL counts), and it never appears as pending work
        now = utcnow()
        con.execute(
            "UPDATE capture SET filter_asserted = 1, processed_at = ? WHERE capture_id = ?",
            (now, capture_id),
        )
        sha256 = con.execute(
            "SELECT response_sha256 FROM capture WHERE capture_id = ?", (capture_id,)
        ).fetchone()[0]
        stats["fetched"] += 1
        if old_sha == sha256:
            stats["unchanged"] += 1
            con.commit()
            continue
        stats["new_documents"] += con.execute(
            "INSERT OR IGNORE INTO document (document_sha256, size_bytes, media_type,"
            " first_seen_at) VALUES (?, ?, ?, ?)",
            (sha256, size, media_type_for(url, head), now),
        ).rowcount
        for owner in owners:
            docket_id, record_id = _owner(con, owner)
            filing_id = record_id if owner.spec is observations.FILINGS_SPEC else None
            decision_id = record_id if owner.spec is observations.DECISIONS_SPEC else None
            con.execute(
                "INSERT OR IGNORE INTO document_source (document_sha256, source_url,"
                " stb_filing_id, stb_decision_id, supersedes_sha256, capture_id, observed_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sha256, url, filing_id, decision_id, old_sha, capture_id, now),
            )
            if old_sha is not None:
                # a reverted erratum (A→B→A) re-meets an existing row: keep its chain link
                con.execute(
                    "UPDATE document_source SET supersedes_sha256 = ?"
                    " WHERE document_sha256 = ? AND source_url = ?"
                    " AND supersedes_sha256 IS NULL",
                    (old_sha, sha256, url),
                )
            con.execute(
                f"UPDATE {owner.spec.attachment_table} SET document_sha256 = ?"
                " WHERE source_url = ?",
                (sha256, url),
            )
        if old_sha is not None:
            stats["replaced"] += 1
            events.append(
                con,
                event_type="document_replaced",
                capture_id=capture_id,
                docket_id=_owner(con, owners[0])[0],
                document_sha256=sha256,
                payload={
                    "source_url": url,
                    "old": old_sha,
                    "new": sha256,
                    "method": DETECTION_METHOD,
                    "method_version": DETECTION_METHOD_VERSION,
                },
                source_key=url,
            )
        con.commit()
    return stats


def _owner(con: Connection, ref: observations.AttachmentRef) -> tuple[int, str]:
    spec = ref.spec
    row = con.execute(
        f"SELECT docket_id, {spec.record_id_column} FROM {spec.record_table}"
        f" WHERE {spec.record_pk} = ?",
        (ref.record_pk,),
    ).fetchone()
    assert row is not None  # attachment rows reference their record by FK
    return row[0], row[1]
