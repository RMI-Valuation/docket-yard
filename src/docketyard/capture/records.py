"""Capture persistence: the raw response is stored before anything parses it.

The capture-first guarantee lives in the call protocol: `save_capture` writes the blob and
a quarantined row (filter_asserted = 0) from nothing but the bytes; `set_verdict` upgrades
the row only after parsing and assertion succeed. A parse failure therefore always leaves
the raw evidence behind.

Blobs are content-addressed on disk (sha256), mirroring ADR 0002: writing the same bytes
twice is a no-op, and a capture row always points at bytes that exist.
"""

import hashlib
import time
from pathlib import Path
from sqlite3 import Connection

from docketyard.store.db import dump_json, utcnow

CHUNK = 1 << 20  # bytes per read when a file is streamed or hashed
STALE_STAGING_SECONDS = 6 * 3600  # a download older than this was left by a killed process


def blob_path(data_dir: str | Path, sha256: str) -> Path:
    return Path(data_dir) / "blobs" / sha256[:2] / sha256


def staging_dir(data_dir: str | Path) -> Path:
    """Where a download is streamed before it is hashed and moved into place: on the blob
    store's own filesystem so the move is a rename. The host's S3 sync and prune skip it
    (infra/deploy: `--exclude ".tmp/*"`; prune_blobs.py)."""
    d = Path(data_dir) / "blobs" / ".tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sweep_staging(data_dir: str | Path, older_than: float = STALE_STAGING_SECONDS) -> int:
    """Remove downloads a killed process left behind (an OOM kill runs no `finally`). Only
    one process fetches documents at a time, so anything older than `older_than` seconds
    is nobody's. Returns the count removed."""
    cutoff = time.time() - older_than
    removed = 0
    for f in staging_dir(data_dir).glob("dl-*"):
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def save_blob(data_dir: str | Path, body: bytes | Path) -> str:
    """Content-address bytes — or a file the downloader streamed onto the blob store's
    filesystem, which is hashed by chunks and moved into place, never read whole. The
    same bytes give the same address either way (ADR 0002)."""
    if isinstance(body, Path):
        return _save_blob_file(data_dir, body)
    sha256 = hashlib.sha256(body).hexdigest()
    path = blob_path(data_dir, sha256)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(body)
        tmp.replace(path)
    return sha256


def _save_blob_file(data_dir: str | Path, src: Path) -> str:
    sha256 = sha256_of_file(src)
    path = blob_path(data_dir, sha256)
    if path.exists():
        if not src.samefile(path):  # the same bytes are already held: the download is surplus
            src.unlink()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        src.replace(path)
    return sha256


def load_blob(data_dir: str | Path, sha256: str) -> bytes:
    return blob_path(data_dir, sha256).read_bytes()


def save_capture(
    con: Connection,
    data_dir: str | Path,
    *,
    source_system: str,
    endpoint: str,
    table_action: str,
    request_params: list[tuple[str, str]],
    body: bytes | Path,
    http_status: int,
    ingest_mode: str,
) -> int:
    """Persist the raw response, quarantined. Nothing here parses the body. A `Path` is a
    download already on the blob filesystem (StbClient.download) and is moved, not read."""
    sha256 = save_blob(data_dir, body)
    cur = con.execute(
        """
        INSERT INTO capture
            (source_system, endpoint, table_action, request_params, response_sha256,
             http_status, filter_asserted, ingest_mode, captured_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (source_system, endpoint, table_action, dump_json(request_params), sha256,
         http_status, ingest_mode, utcnow()),
    )  # fmt: skip
    con.commit()
    assert cur.lastrowid is not None
    return cur.lastrowid


def open_pending(
    con: Connection, data_dir: str | Path, capture_id: int, expected_action: str
) -> bytes | None:
    """The one definition of 'consumable': asserted, unprocessed, and of the expected table.
    Returns the raw body, or None if already processed. Raises on quarantine or on a
    capture of a different table — the wrong parser must never stamp processed_at."""
    row = con.execute(
        "SELECT filter_asserted, processed_at, response_sha256, table_action FROM capture"
        " WHERE capture_id = ?",
        (capture_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"no capture {capture_id}")
    if not row[0]:
        raise ValueError(f"capture {capture_id} is quarantined (filter not asserted)")
    if row[3] != expected_action:
        raise ValueError(f"capture {capture_id} is {row[3]!r}, not {expected_action!r}")
    if row[1] is not None:
        return None
    return load_blob(data_dir, row[2])


def mark_processed(con: Connection, capture_id: int) -> None:
    con.execute("UPDATE capture SET processed_at = ? WHERE capture_id = ?", (utcnow(), capture_id))
    con.commit()


def set_verdict(
    con: Connection,
    capture_id: int,
    *,
    filter_asserted: bool,
    row_count: int,
    reported_total: int,
) -> None:
    """Record the parse/assertion outcome for a capture saved by `save_capture`."""
    con.execute(
        "UPDATE capture SET filter_asserted = ?, row_count = ?, reported_total = ?"
        " WHERE capture_id = ?",
        (int(filter_asserted), row_count, reported_total, capture_id),
    )
    con.commit()
