"""The document address (ADR 0013 addendum, 2026-08-27): `/document/{sha256}.pdf` answers
with the bytes the record hashed, inline, so a browser shows them; permanent by
construction, because the hash is the identity (ADR 0002).

The instance is a cache and S3 the store (ADR 0012): a file the prune timer removed is
fetched on first request into the blob staging area, hashed on the way in, and served only
if the hash is the one asked for — a wrong file is never served under another's address.
"""

import re
import shutil
import tempfile
from pathlib import Path
from sqlite3 import Connection

from docketyard.capture import records

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MEDIA = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "zip": "application/zip",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
INLINE = {"pdf", "jpg"}  # what a browser can show; the rest is offered as a download
CACHE = "public, max-age=31536000, immutable"  # the bytes at a hash never change


def path_for(sha256: str) -> str:
    return f"/document/{sha256}.pdf"


def held(con: Connection, sha256: str) -> tuple[int, str | None] | None:
    """(size, media_type) if the record holds a document with this hash, else None."""
    row = con.execute(
        "SELECT size_bytes, media_type FROM document WHERE document_sha256 = ?", (sha256,)
    ).fetchone()
    return (row[0], row[1]) if row else None


def local_file(data_dir, sha256: str, *, fetch=None) -> Path | None:
    """The blob on this instance, fetching it from the store if it was pruned. `fetch` is
    injected (s3.signed_get bound to the bucket in production) so the miss path is
    testable; None means no store is configured and a miss is a miss."""
    path = records.blob_path(data_dir, sha256)
    if path.exists():
        return path
    if fetch is None:
        return None
    staging = records.staging_dir(data_dir)
    fd, name = tempfile.mkstemp(dir=staging, prefix="dl-")
    tmp = Path(name)
    try:
        with fetch(f"blobs/{sha256[:2]}/{sha256}") as resp, open(fd, "wb") as out:
            shutil.copyfileobj(resp, out, records.CHUNK)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if records.sha256_of_file(tmp) != sha256:  # the store answered with other bytes
        tmp.unlink(missing_ok=True)
        return None
    records.save_blob(data_dir, tmp)
    return path if path.exists() else None


def headers_for(sha256: str, media_type: str | None) -> tuple[str, dict[str, str]]:
    """Media type and headers: inline for what a browser shows, attachment otherwise;
    cached for a year, validated by the hash itself."""
    kind = media_type or "pdf"
    mime = MEDIA.get(kind, "application/octet-stream")
    disposition = "inline" if kind in INLINE else "attachment"
    return mime, {
        "Content-Disposition": f'{disposition}; filename="{sha256}.{kind}"',
        "Cache-Control": CACHE,
        "ETag": f'"{sha256}"',
        "X-Content-Type-Options": "nosniff",
    }


def viewable(entry) -> list:
    """The attachments a viewer page can show: fetched, and of a kind a browser renders."""
    return [a for a in entry.attachments if a.document_sha256]


def is_sha(text: str) -> bool:
    return bool(SHA_RE.match(text))
