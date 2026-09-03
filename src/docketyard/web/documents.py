"""The document address (ADR 0013 addendum, 2026-08-27): `/document/{sha256}.{ext}` answers
with the bytes the record hashed — inline for what a browser shows, a download otherwise —
permanent by construction, because the hash is the identity (ADR 0002).

The instance is a cache and S3 the store (ADR 0012): a file the prune timer removed is
fetched on first request into the blob staging area, hashed on the way in, and moved into
place only if the hash is the one asked for — a wrong file is never served under another's
address.
"""

import hashlib
import os
import re
import tempfile
import threading
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
UNKNOWN = "bin"  # a document whose kind nothing sniffed: served as an opaque download
CACHE = "public, max-age=31536000, immutable"  # the bytes at a hash never change


class StoreMismatch(RuntimeError):
    """The store answered a hash with other bytes: the loudest thing this path can say."""


_in_flight: dict[str, threading.Lock] = {}  # sha -> the lock of the fetch under way
_in_flight_guard = threading.Lock()


def _fetch_lock(sha256: str) -> threading.Lock:
    with _in_flight_guard:
        return _in_flight.setdefault(sha256, threading.Lock())


def is_sha(text: str) -> bool:
    return bool(SHA_RE.match(text))


def ext_for(media_type: str | None) -> str:
    return media_type if media_type in MEDIA else UNKNOWN


def address_parts(name: str) -> tuple[str, str] | None:
    """`{sha}.{ext}` or a bare `{sha}` -> (sha, ext or ''); None when it is no hash."""
    sha, _, ext = name.partition(".")
    return (sha, ext) if is_sha(sha) else None


def held(con: Connection, sha256: str) -> str | None:
    """The media type of the document the record holds at this hash; None if not held
    (an unknown kind is held too: the row's NULL comes back as UNKNOWN)."""
    row = con.execute(
        "SELECT media_type FROM document WHERE document_sha256 = ?", (sha256,)
    ).fetchone()
    return None if row is None else ext_for(row[0])


def local_file(data_dir, sha256: str, *, fetch=None) -> Path | None:
    """The blob on this instance, fetching it from the store if it was pruned. `fetch` is
    injected (s3.from_env() in production) so the miss path is testable; None means no
    store is configured and a miss is a miss. The bytes are hashed as they arrive, once;
    a wrong answer raises StoreMismatch and leaves nothing behind."""
    path = records.blob_path(data_dir, sha256)
    if path.exists():
        return path
    if fetch is None:
        return None
    with _fetch_lock(sha256):  # a browser's parallel Range requests: one fetch, the rest wait
        if path.exists():
            return path
        return _fetch_into_place(data_dir, sha256, path, fetch)


def _fetch_into_place(data_dir, sha256: str, path: Path, fetch) -> Path:
    fd, name = tempfile.mkstemp(dir=records.staging_dir(data_dir), prefix="ws-")
    tmp = Path(name)
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as out, fetch(f"blobs/{sha256[:2]}/{sha256}") as resp:
            for chunk in iter(lambda: resp.read(records.CHUNK), b""):
                out.write(chunk)
                digest.update(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != sha256:
        tmp.unlink(missing_ok=True)
        raise StoreMismatch(
            f"store answered {sha256[:12]} with bytes hashing {digest.hexdigest()[:12]}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.replace(path)  # atomic; two concurrent misses both land the same bytes
    return path


def headers_for(sha256: str, ext: str) -> tuple[str, dict[str, str]]:
    """Media type and headers: inline for what a browser shows, attachment otherwise;
    cached for a year, validated by the hash itself."""
    mime = MEDIA.get(ext, "application/octet-stream")
    disposition = "inline" if ext in INLINE else "attachment"
    return mime, {
        "Content-Disposition": f'{disposition}; filename="{sha256}.{ext}"',
        "Cache-Control": CACHE,
        "ETag": f'"{sha256}"',
        "X-Content-Type-Options": "nosniff",
    }


# kinds whose record page shows the file in a frame. A comment's does not — it is addressed
# at /comment/<number> and links the Board's own file — so the rule lives HERE rather than
# at each call site: the sheet, the record page and the text page all ask this one function,
# and guarding them one at a time is how the third one gets missed (code review, 2026-08-31).
VIEWABLE_KINDS = ("filing", "decision")
PAGINABLE = {"pdf"}  # what the text passes read: a page count and a text layer come from a PDF


def has_frame(entry) -> bool:
    """Whether the record's page shows a file in a frame at all — the one rule, in the one
    place, rather than a kind list repeated in a template."""
    return entry.kind in VIEWABLE_KINDS


def text_index(entry) -> int | None:
    """The first file the text page can show, or None — the gate for offering the text
    page at all. A static property of the file list, so a page validated by `stamp()` may
    read it without depending on the page tables (docs/deferred.md, 2026-09-03)."""
    return pick(entry, 0, PAGINABLE)


def pick(entry, file: int, kinds) -> int | None:
    """The attachment `?file=N` means — or the first of the wanted kinds, or None. ONE rule
    for the record page's frame (`INLINE`) and the text page (`PAGINABLE`), so `?file=N`
    names the same file on both wherever it can, and the text page's scan link lands on the
    file whose text is shown. A `file` outside the wanted set falls back to the first."""
    if entry.kind not in VIEWABLE_KINDS:
        return None
    ok = [i for i, a in enumerate(entry.attachments) if a.document_sha256 and a.media_type in kinds]
    if not ok:
        return None
    return file if file in ok else ok[0]


def viewable_index(entry) -> int | None:
    """The first attachment a record page can frame — fetched, of a kind a browser renders,
    on a record kind that HAS a frame — or None. One rule for the sheet's link and the
    record's button."""
    if entry.kind not in VIEWABLE_KINDS:
        return None
    for i, a in enumerate(entry.attachments):
        if a.document_sha256 and a.media_type in INLINE:
            return i
    return None
