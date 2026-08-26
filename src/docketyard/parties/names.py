"""Cutting a "Filed For" cell into spans, and normalising a name for matching.

Both are judgements, and both are versioned (ADR 0007): SPLIT_VERSION and NORM_VERSION
change whenever a rule does, so an assertion always names the rule that made it. The rules
are the ones the two-year record showed to be safe (docs/party-module.md § What the
record shows today); anything a rule cannot cut safely is left whole at confidence below
one — never silently wrong, never discarded.
"""

import re
from dataclasses import dataclass

SPLIT_METHOD = "split-rules"
SPLIT_VERSION = "1"
NORM_METHOD = "resolve-exact"
NORM_VERSION = "1"

# corporate suffix tokens: a comma followed by one of these is part of a name, not a list
_SUFFIXES = (
    "inc",
    "inc.",
    "incorporated",
    "llc",
    "l.l.c.",
    "llp",
    "l.p.",
    "lp",
    "ltd",
    "ltd.",
    "limited",
    "corp",
    "corp.",
    "corporation",
    "co",
    "co.",
    "company",
    "plc",
    "pllc",
    "p.c.",
    "pc",
    "s.a.",
    "n.a.",
    "gmbh",
    "ag",
    "et al",
    "et al.",
    "association",
    "commission",
    "authority",
    "trust",
    "partnership",
    "cooperative",
    "coop",
    "co-op",
)
_SUFFIX_END = re.compile(
    r"\b(inc\.?|incorporated|llc|l\.l\.c\.|llp|l\.p\.|lp|ltd\.?|limited|corp\.?|corporation|"
    r"co\.?|company|plc|pllc|p\.c\.|pc|s\.a\.|n\.a\.|railroad|railway|rr|ry|association|"
    r"commission|authority|trust|partnership|cooperative|co-op|district|department|county|city|"
    r"port|union|brotherhood|committee|council|board)\s*$",
    re.I,
)
_ON_BEHALF = re.compile(r",?\s+on behalf of\s+", re.I)
_DBA = re.compile(r"\s+(?:d/b/a|dba)\s+", re.I)


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    text: str
    role: str  # filed_for | on_behalf_of
    confidence: float


def fold_repeat(cell: str) -> str:
    """The Board's cell sometimes repeats one party several times over (measured);
    the repeat is folded before anything else. Shared with the sheet's display."""
    for i in range(1, len(cell)):
        if cell.startswith(", ", i):
            unit = cell[:i]
            n, rem = divmod(len(cell) - len(unit), len(unit) + 2)
            if n >= 1 and rem == 0 and cell == ", ".join([unit] * (n + 1)):
                return unit
    return cell


def _starts_with_suffix(text: str) -> bool:
    head = text.strip().lower().split(" ")[0].rstrip(",;")
    return head in _SUFFIXES


def _ends_with_suffix(text: str) -> bool:
    return bool(_SUFFIX_END.search(text.strip()))


def split_cell(cell: str, known: set[str] | frozenset[str] = frozenset()) -> list[Span]:
    """Cut a cell into spans over the ORIGINAL text (offsets index into `cell`). `known`
    is the set of normalised names already on record: an ' and ' between two known names
    is a list even without suffixes."""
    folded = fold_repeat(cell)
    base = 0  # offsets are into the original cell; a folded cell keeps its first unit's
    text = folded
    spans: list[Span] = []
    # 1. ", on behalf of " → the filer, then the represented party
    m = _ON_BEHALF.search(text)
    behalf: tuple[int, int] | None = None
    if m:
        behalf = (m.end(), len(text))
        text_main = text[: m.start()]
    else:
        text_main = text
    # 2. cut the main part on ' and ' / ', ' where both sides look like whole names
    pieces = _cut(text_main, known)
    for start, end, conf in pieces:
        spans.append(Span(base + start, base + end, text_main[start:end], "filed_for", conf))
    if behalf:
        s, e = behalf
        spans.append(Span(base + s, base + e, text[s:e], "on_behalf_of", 1.0 if m else 0.5))
    return spans


def _is_whole(text: str, known: set[str]) -> bool:
    """A piece reads as a whole name: it ends in a corporate suffix, is a name already on
    record, or is an ' and '-list whose every part is."""
    text = text.strip()
    if not text:
        return False
    if _ends_with_suffix(text) or normalise(text) in known:
        return True
    parts = text.split(" and ")
    return len(parts) > 1 and all(_is_whole(p, known) for p in parts)


def _first_item(text: str, seps) -> str:
    """The text up to the first list separator that is not followed by a suffix token
    ('Evergy Metro, Inc., and …' → 'Evergy Metro, Inc.')."""
    for m in seps.finditer(text):
        if not _starts_with_suffix(text[m.end() :]):
            return text[: m.start()]
    return text


def _cut(text: str, known: set[str]) -> list[tuple[int, int, float]]:
    """Two levels: ', ' between whole names is a list; a comma followed by a suffix token
    is part of a name; any other comma is doubt. Then ' and ' between whole names cuts an
    item; ' and ' between anything else is doubt. Doubt keeps the piece whole below 1.0."""
    # level 1: list separators — ', ' and '; ' (an Oxford ', and ' / '; and ' counts too)
    items: list[tuple[int, int]] = []
    doubt = False
    last = 0
    i = 0
    seps = re.compile(r"(?:;|,)\s+(?:and\s+)?")
    for m in seps.finditer(text):
        i = m.start()
        if i < last:
            continue
        left, right = text[last:i], text[m.end() :]
        if _starts_with_suffix(right):
            continue  # ', Inc.' — part of the name
        right_head = _first_item(right, seps)
        if _is_whole(left, known) and _is_whole(right_head, known):
            items.append((last, i))
            last = m.end()
        else:
            doubt = True
    items.append((last, len(text)))
    if doubt:
        return [(0, len(text), 0.6)]
    # level 2: ' and ' inside each item
    out: list[tuple[int, int, float]] = []
    for s, e in items:
        item = text[s:e]
        if " and " not in item:
            out.append((s, e, 1.0))
            continue
        parts = item.split(" and ")
        if all(_is_whole(x, known) for x in parts):
            pos = s
            for x in parts:
                out.append((pos, pos + len(x), 1.0))
                pos += len(x) + len(" and ")
        elif normalise(item) in known:
            # 'Norfolk and Portsmouth Belt Line Railroad Company': one known name with 'and'
            out.append((s, e, 1.0))
        else:
            out.append((s, e, 0.6))  # a person plus a carrier, or a name with 'and': doubt
    return out


_PUNCT = re.compile(r"[^\w\s&]")
_WS = re.compile(r"\s+")
_NORM_WORDS = {
    "incorporated": "inc",
    "corporation": "corp",
    "company": "co",
    "limited": "ltd",
    "railroad": "rr",
    "railway": "ry",
    "and": "&",
}


def normalise(name: str) -> str:
    """The matcher's form of a name: case, punctuation, common corporate words. Part of
    NORM_VERSION — change the rule, bump the version."""
    text = _PUNCT.sub(" ", name.lower())
    words = [_NORM_WORDS.get(w, w) for w in _WS.split(text) if w]
    return " ".join(words)


def trade_name(name: str) -> tuple[str, str | None]:
    """'Ethanol Products, LLC d/b/a POET Biofuels' → ('Ethanol Products, LLC', 'POET Biofuels')."""
    m = _DBA.search(name)
    if not m:
        return name, None
    return name[: m.start()], name[m.end() :]
