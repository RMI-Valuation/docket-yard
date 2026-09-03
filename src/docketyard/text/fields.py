"""What the passes over the extraction directory share: the refusal, the field rules, the
head of a record, and the one definition of a page's text digest.

`text_sha256` is the digest `document_text.text_sha256` carries — migration 0018 calls it a
writer obligation SQLite cannot enforce, and it is what a re-read compares to decide whether
anything changed. Two writers with two rules would supersede identical text or keep changed
text; so there is one rule, here: SHA-256 of the text as UTF-8. A string JSON permits but
UTF-8 cannot encode (a lone surrogate, which PyMuPDF emits from a broken CMap) is refused
here rather than at the store's bind, where it would escape as a bare `UnicodeEncodeError`.
"""

import hashlib
import json
from pathlib import Path

HEAD = 4096  # bytes: every header field of an extraction record sits inside this


class Unreadable(ValueError):
    """Input a pass cannot turn into rows: malformed, or naming no document. A reader's
    finding, counted by `store.batches`; raised from a writer it is counted as `failed`."""


def text_field(d: dict, key: str, *, allow_slash: bool = True) -> str:
    value = d.get(key)
    if not isinstance(value, str) or not value:
        raise Unreadable(f"{key} is {value!r}, not a non-empty string")
    if not allow_slash and "/" in value:
        raise Unreadable(f"{key} {value!r} carries '/', which a review key cannot parse back")
    return value


def sha_field(d: dict, key: str = "document_sha256") -> str:
    sha = text_field(d, key)
    if len(sha) != 64:
        raise Unreadable(f"{key} is not 64 characters")
    return sha


def text_sha256(text: str) -> str:
    try:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    except UnicodeEncodeError as e:
        raise Unreadable(f"text is not encodable as UTF-8: {e.reason}") from None


def read_head(path: Path) -> dict:
    """An extraction record's header fields, without reading its text. The record is a JSON
    object whose LAST member is `page_text`; everything before it is parsed as an object of
    its own. A file with no `page_text` in its first bytes is parsed whole, which is the
    correct (slow) answer for a stub and the correct (loud) answer for a corrupt file."""
    with path.open("rb") as f:
        head = f.read(HEAD).decode("utf-8", "replace")
    cut = head.find('"page_text"')
    if cut < 0 or not head[:cut].rstrip().rstrip(",").strip().lstrip("{").strip():
        return json.loads(path.read_text(encoding="utf-8"))  # no marker, or nothing before it
    return json.loads(head[:cut].rstrip().rstrip(",") + "}")
