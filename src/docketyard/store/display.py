"""What the display rule omits from a page's text — ADR 0021 D9, addendum of 2026-09-04.

`document_text_display` IS the display rule (ADR 0022 D4 indexes it), and from migration
0020 its `text` column is `dy_display_text(text)`: the stored reading with email addresses
and North American telephone numbers replaced by a marker. The stored row is untouched —
`document_text.text` remains the document's own words, append-only — and the Board's file
is one click from every text page, so nothing is lost to a reader who needs the detail. What
changes is what a million machine-readable pages hand out at scale.

ONE FUNCTION, THREE USES, BY CONSTRUCTION. FTS5 external content requires a 'delete' to
carry the text exactly as indexed, so what the view shows, what `page_index.enter` indexes
and what `page_index.leave` deletes must be the same bytes. They are, because all three
call this function through SQL. Every connection that reads the view registers it
(`store.db.connect`, the web tier's `_connect` and `_connect_rw`; the dump's two raw
connections and `traffic.py` never read it); a connection that does not cannot read the
view — "no such function" — which is the intended failure for a copy queried raw under
this project's display rule. A raw `ALTER TABLE ... RENAME` also needs it, because SQLite
re-parses every view on a rename; the house idiom runs through `db.connect`, which has it.

A CHANGE TO THE PATTERNS IS A NEW MIGRATION, never an edit here alone: a DROP/CREATE of the
view that stamps `user_version`, with `VERSION` bumped and `search.PAGE_INDEX_FORMAT` (which
carries `VERSION`) moving with it. That dates the rule in the store — what a reader saw on
date D is replayable only if the store says which rule was in force — forces the page index
to be rebuilt, and makes an unmigrated store refuse to serve (`web.app._check_store`).

WHAT THE RULE CANNOT DO, said plainly on the methodology page: a postal address has no
reliable pattern and is not omitted; a telephone number written without separators is left,
because ten-digit runs are also record identifiers. The rule is mechanical and applies to
everyone — counsel's business line and a commenter's home line alike — because telling
the two apart would be an inference about a person, and this project infers nothing about
people (CLAUDE.md § Rules).
"""

import re
from sqlite3 import Connection

FUNCTION = "dy_display_text"
VERSION = "1"  # bump ONLY with the migration that re-creates the view (docstring)
EMAIL_MARKER = "[email omitted]"
PHONE_MARKER = "[phone omitted]"

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@(?:[A-Za-z0-9\-]+\.)+[A-Za-z]{2,}")
# North American numbering plan, WITH separators. A bracketed area code or a country code is
# cue enough on its own; a BARE separated run (202-555-0134) is a telephone number only after
# a telephone word — "tel", "fax", "cell", "call" and their kin — because 3-3-4 with hyphens
# or dots is also how a tariff item, a section and a page-range-then-number are written
# (review finding, 2026-09-04). A date (4-2-2), a ZIP+4 (5-4), a docket number, a dollar
# amount and a case number all fail the shape; a bare ten-digit run is deliberately not
# matched (see the module docstring). An extension is `ext`, `extension`, or an `x` glued to
# its digits: "x 2026 was filed" is a year, not an extension.
_PHONE = re.compile(
    r"(?<![\w.\-])"  # not the tail of a longer number, a decimal or a hyphenated identifier
    r"(?P<cue>(?:tel(?:ephone)?|phone|fax|cell|mobile|direct|voice|office|call)\.?"
    r"(?:\s*(?:no|number)\.?)?:?\s*)?"
    r"(?:(?P<bracket>(?:\+?1[\s.\-]?)?\(\d{3}\)\s?\d{3}[\s.\-]\d{4})"
    r"|(?P<country>\+?1[\s.\-]\d{3}[\s.\-]\d{3}[\s.\-]\d{4})"
    r"|(?P<bare>\d{3}[\s.\-]\d{3}[\s.\-]\d{4}))"
    r"(?:\s?(?:ext\.?|extension)\s?\d{1,5}|\s?x\d{1,5})?"
    r"(?![\w\-])",
    re.IGNORECASE,
)


def _phone(m: re.Match) -> str:
    if m.group("bare") is not None and m.group("cue") is None:
        return m.group(0)  # a separated 3-3-4 with no telephone word: an identifier, left
    return (m.group("cue") or "") + PHONE_MARKER


def mask(text: str | None) -> str | None:
    """The text as displayed: the stored reading with contact details replaced by a marker.
    NULL stays NULL (a reading is never NULL, but a LEFT JOIN may be)."""
    if text is None:
        return None
    if "@" not in text and not any(ch.isdigit() for ch in text):
        return text  # nothing to find; most pages
    return _PHONE.sub(_phone, _EMAIL.sub(EMAIL_MARKER, text))


def register(con: Connection) -> None:
    """Give a connection the function the view needs. Deterministic: the same text always
    masks the same way, so SQLite may cache and reorder calls to it."""
    con.create_function(FUNCTION, 1, mask, deterministic=True)
