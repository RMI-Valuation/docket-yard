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
_LOOKUP_NOISE_RE = re.compile(r"\(|\)|sub\.?\s*-?\s*no\.?|no\.", re.I)
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
    """Normalise anything a person might type into the ingest parser's grammar."""
    cleaned = _LOOKUP_NOISE_RE.sub(" ", text.strip())
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


def decision_path(stb_decision_id: str) -> str:
    return f"/decision/{stb_decision_id}"


def filing_path(stb_filing_id: str) -> str:
    return f"/filing/{stb_filing_id}"
