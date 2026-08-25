"""Shared HTML-fragment parsing for the STB result tables.

The endpoint returns rows as HTML strings, not records. Regexes are deliberately tolerant
of attributes and spacing; anything they cannot make coherent is COUNTED as skipped by the
callers, never silently dropped.
"""

import html
import re

ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S)
STB_ID_RE = re.compile(r'data-stb-id="([^"]+)"')
LINK_RE = re.compile(r'href="(https?://[^"]+)"')
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# dates are printed M/D/YYYY; normalised to ISO for storage — same date, never computed
_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def clean(fragment: str) -> str:
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", fragment))).strip()


def printed_date_to_iso(cell: str) -> str | None:
    m = _DATE_RE.match(cell.strip())
    if not m:
        return None
    month, day, year = m.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"
