"""Permanent addresses (ADR 0013), built from and parsed with the one docket identity.

`/d/FD-36873`, `/d/FD-36873/sub/1`, `/d/S5M-1-A` (suffix on a parent),
`/d/AB-55/sub/785X` (suffix on a sub), `/decision/{id}`, `/filing/{id}`. Canonical form is
upper-case; anything else resolves and redirects to canonical. Whatever a person types or
pastes — the Board's own `FD_36873_1`, the printed `FD 36873 (Sub-No. 1)`, `fd 36873` —
goes through `lookup`, which normalises it into the ingest parser's grammar so there is one
definition of identity.
"""

import re

from docketyard.ingest.dockets import ParsedDocket, parse_docket_id

# suffixes are letters-led (X, A, L, M, C observed); an all-digit third part is a sub-number
_PARENT_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)-(\d+)(?:-([A-Za-z][A-Za-z0-9]*))?$")
_SUB_RE = re.compile(r"^(\d+)([A-Za-z][A-Za-z0-9]*)?$")
# the words a citation wraps a number in; "Sub-No." is the sub-number's own and is folded first
_LOOKUP_NOISE_RE = re.compile(
    r"\(|\)|sub\.?\s*-?\s*no\.?|\bnos?\.|\bSTB\b|\bSurface Transportation Board\b|\bDocket\b|[,;]",
    re.I,
)
_LONG_FORMS = (  # the Board's long names, to the prefix the registry uses
    (re.compile(r"\bfinance\s+docket\b", re.I), "FD"),
    (re.compile(r"\bex\s+parte\b", re.I), "EP"),
)
_SEP_RE = re.compile(r"[\s_\-.]+")

_CITE_LONG = {"FD": "STB Finance Docket No.", "EP": "STB Ex Parte No."}


def docket_path(identity: ParsedDocket) -> str:
    head = f"/d/{identity.prefix}-{identity.sequence}"
    if identity.sub_sequence is None:
        return f"{head}-{identity.suffix}" if identity.suffix else head
    return f"{head}/sub/{identity.sub_sequence}{identity.suffix or ''}"


def parse_docket_path(ident: str, sub: str | None = None) -> ParsedDocket | None:
    m = _PARENT_RE.match(ident)
    if not m:
        return None
    prefix, sequence, parent_suffix = m.groups()
    if sub is None:
        return ParsedDocket(
            prefix.upper(), int(sequence), None, parent_suffix.upper() if parent_suffix else None
        )
    if parent_suffix:  # a suffix belongs to one level only
        return None
    s = _SUB_RE.match(sub)
    if not s or int(s.group(1)) == 0:
        return None
    return ParsedDocket(
        prefix.upper(), int(sequence), int(s.group(1)), (s.group(2) or "").upper() or None
    )


def lookup(text: str) -> ParsedDocket | None:
    """Normalise anything a person might type — or cite — into the ingest parser's grammar:
    `fd 36873`, `FD_36873_1`, `FD 36873 (Sub-No. 1)`, `STB Finance Docket No. 36873`,
    `Ex Parte No. 711`, `Docket No. NOR 42130`."""
    cleaned = text.strip()
    for pattern, prefix in _LONG_FORMS:
        cleaned = pattern.sub(prefix, cleaned)
    cleaned = _LOOKUP_NOISE_RE.sub(" ", cleaned)
    tokens = [t for t in _SEP_RE.split(cleaned) if t]
    if not tokens:
        return None
    # split a trailing '785X' into '785' 'X' so a sub-number and its suffix are separate parts
    parts: list[str] = []
    for token in tokens:
        m = re.match(r"^(\d+)([A-Za-z][A-Za-z0-9]*)$", token)
        parts.extend(m.groups() if m else (token,))
    return parse_docket_id("_".join(parts))


def printed_docket(identity: ParsedDocket) -> str:
    """The short form practitioners write: FD 36873, FD 36873 (Sub-No. 1), AB 55 (Sub-No. 785X)."""
    head = f"{identity.prefix} {identity.sequence}"
    if identity.sub_sequence is None:
        return f"{head}-{identity.suffix}" if identity.suffix else head
    return f"{head} (Sub-No. {identity.sub_sequence}{identity.suffix or ''})"


def cite_docket(identity: ParsedDocket) -> str:
    """The long citation form: STB Finance Docket No. 36873 (Sub-No. 1); STB Docket No. AB 55."""
    long = _CITE_LONG.get(identity.prefix)
    number = (
        f"{identity.sequence}"
        if long
        else printed_docket(ParsedDocket(identity.prefix, identity.sequence, None, None))
    )
    head = f"{long} {number}" if long else f"STB Docket No. {number}"
    if identity.sub_sequence is None:
        return (
            f"{head}-{identity.suffix}"
            if identity.suffix and long
            else (head if not identity.suffix else f"{head}-{identity.suffix}")
        )
    return f"{head} (Sub-No. {identity.sub_sequence}{identity.suffix or ''})"


EXPLAINED = ("FD", "AB", "NOR", "EP", "MCF")  # prefixes with an explainer page of their own


def explainer_path(prefix: str) -> str:
    """The explainer for a docket prefix: its own page, or its row on the index (P2)."""
    p = prefix.upper()
    return f"/about/{p}" if p in EXPLAINED else f"/about/prefixes#{p}"


def party_path(party_id: int) -> str:
    """A party's permanent address (ADR 0015): its id, never a slug. /p/1234"""
    return f"/p/{party_id}"


def parse_party_id(text: str) -> int | None:
    """ASCII digits only (str.isdigit admits superscripts and other scripts' digits, which
    int() may reject or read as a second spelling of the same address); no sign, no
    length beyond any id the store will hold."""
    if not text or len(text) > 12 or not text.isascii() or not text.isdigit():
        return None
    return int(text)


def party_feed_path(party_id: int) -> str:
    return f"{party_path(party_id)}/feed"


def week_path(monday) -> str:
    """A fixed Monday–Sunday week, addressed by its Monday: /week/2026-08-17."""
    return f"/week/{monday.isoformat()}"


def record_path(kind: str, record_id: str) -> str:
    """Filings and decisions only. A comment's address needs the docket that holds it, so
    a caller with a sheet entry in hand asks `entry_path`, which knows all three kinds.

    A comment reaching here would silently become `/filing/EI-34280`, a live 404 — so it
    raises instead. Found by review after the address moved and `viewer.html`'s prev/next
    kept calling this with whatever kind the neighbouring entry happened to be."""
    if kind == "comment":
        raise ValueError("a comment is addressed under its docket: use comment_path()")
    return decision_path(record_id) if kind == "decision" else filing_path(record_id)


def confirm_url(site: str, token: str) -> str:
    return f"https://{site}/s/confirm/{token}"


def unsubscribe_url(site: str, token: str) -> str:
    return f"https://{site}/s/unsubscribe/{token}"


def viewer_path(kind: str, record_id: str, index: int = 0) -> str:
    """The record's file shown beside the record; `index` picks among several files."""
    return record_path(kind, record_id) + "/view" + (f"?file={index}" if index else "")


def text_path(kind: str, record_id: str, index: int = 0) -> str:
    """The record's text, page by page, beside the record (ADR 0021 D7): one address per
    record and not per page — `#p4` anchors the page. 1.1M page addresses against 74k
    records would be a crawler's address space, and a crawler walking one is this site's
    one real outage (2026-09-02). `index` picks among several files, as the viewer does."""
    return record_path(kind, record_id) + "/text" + (f"?file={index}" if index else "")


def entry_path(kind: str, record_id: str, docket_raw: str) -> str:
    """The permanent address of a sheet entry, whatever kind it turns out to be.

    A sheet holds filings, decisions AND comments since migration 0011, so anything
    holding "the entry next to this one" holds a kind it did not choose. Four callers
    spelled the branch themselves — the sheet's rows, the record page, the JSON twin and
    `viewer.html`'s prev/next — and the fourth was never taught the third kind: every
    viewer page whose neighbour was a comment answered 500 (`/filing/240630/view`, AB 290
    Sub-No. 324X, reported 2026-08-31). This is the one place that branch lives now.

    `docket_raw` is the entry's own docket, which for a comment the sheet has already
    folded to the copy nearest the parent — the same copy `_comment_canonical` addresses,
    so this returns the canonical address rather than one that redirects.
    """
    if kind != "comment":
        return record_path(kind, record_id)
    identity = parse_docket_id(docket_raw)
    # A link is not the place to raise. Every raw docket in the registry parsed once to be
    # created, so this is defensive; the short form is a real address if it ever fires —
    # a 301 for all but the two numbers the record holds twice, which name both.
    return comment_path(identity, record_id) if identity else comment_short_path(record_id)


def entry_viewer_path(kind: str, record_id: str, docket_raw: str, index: int | None) -> str:
    """Where a link to a sheet entry goes: its file beside the record when it has one a
    browser shows, the record itself when it has not. `index` is `viewable_index`'s answer,
    which is None for every comment — a comment has no viewer page, its files hang on its
    own page — so a comment arrives here and leaves through `entry_path`."""
    if index is None:
        return entry_path(kind, record_id, docket_raw)
    return viewer_path(kind, record_id, index)


def document_path(sha256: str, media_type: str | None = None) -> str:
    """A document's permanent address: its bytes by content hash (ADR 0013 addendum). The
    suffix names what the bytes are (pdf, jpg, zip, xlsx, docx; bin when unknown) so a
    saved file opens; any other suffix at the same hash answers 301 to this one."""
    return f"/document/{sha256}.{media_type or 'bin'}"


def decision_path(stb_decision_id: str) -> str:
    return f"/decision/{stb_decision_id}"


def filing_path(stb_filing_id: str) -> str:
    return f"/filing/{stb_filing_id}"


def comment_path(identity: ParsedDocket, comment_number: str) -> str:
    """An environmental comment's permanent address, nested under the docket that holds it:
    `/d/FD-35952/comment/EI-25366`.

    The bare number is NOT the address, and the archive wave is why. A comment number was
    measured unique across 2,385 sampled comments and is not: of the 34,255 the record
    holds, `EI-25366` and `EI-25367` each name TWO different people's comments, in two
    different dockets, on two different dates (`docs/stb-data-source.md`). The store was
    keyed `(docket, number)` from the first migration, so this address is that key spelled
    out — it cannot go ambiguous later however the Board numbers things.

    `comment_short_path` keeps the citable bare form; its route redirects here."""
    return f"{docket_path(identity)}/comment/{comment_number.strip().upper()}"


def comment_short_path(comment_number: str) -> str:
    """The bare number a person would cite. It resolves to exactly one comment for 34,253
    of the 34,255 held and 301s to that comment's address; where two comments share a
    number it answers with both rather than picking one of them silently."""
    return f"/comment/{comment_number.strip().upper()}"
