"""Presentation labels and display helpers.

A short kind label is derived from the Board's own filing-type string so the column scans;
the full type still appears on the entry. This groups the record's *type labels* for
display — it says nothing about what a document argues, and never looks at who filed it (a
filing from the Board itself is labelled by its type like any other).
"""

from docketyard.store import registers

_RULES: tuple[tuple[str, str], ...] = (
    ("motion", "Motion"),
    ("petition", "Motion"),
    ("reply", "Reply"),
    ("notice of intent", "Notice"),
    ("notice", "Notice"),
    ("comment", "Comments"),
    ("discovery", "Discovery"),
    ("status report", "Report"),
    ("report", "Report"),
    ("letter", "Letter"),
    ("supplement", "Supplement"),
    ("modify", "Supplement"),
    ("complaint", "Complaint"),
    ("nomination", "Nomination"),
    ("application", "Application"),
    ("brief", "Brief"),
    ("errata", "Errata"),
    ("support statem", "Statement"),
    ("statement", "Statement"),
    ("miscellaneous", "Misc."),
)

# the Board's docket-prefix names, only the ones its own materials spell out
PREFIX_NAMES = {
    "FD": "Finance Docket",
    "AB": "Abandonment",
    "EP": "Ex Parte",
    "NOR": "Formal Complaint",
    "MCF": "Motor Carrier Finance",
    "WB": "Waybill Data",
    "SO": "Service Order",
    "SDM": "System Diagram Map",
}


def kind_label(kind: str, filing_type: str | None) -> str:
    if kind == "decision":
        return "Decision"
    if kind == "comment":
        # the Board's own name for the table these come from; the row carries no type
        return "Comment"
    text = (filing_type or "").lower()
    for needle, label in _RULES:
        if needle in text:
            return label
    first = (filing_type or "Filing").split("/")[0].split("(")[0].strip().split(" ")[0]
    return first or "Filing"


def filter_key(kind: str, filing_type: str | None) -> str:
    """The data attribute the filter chips match on."""
    return kind_label(kind, filing_type).lower().rstrip(".")


def register_link(kind: str, entry_type: str | None) -> tuple[str, str] | None:
    """(path, label) of the register an entry belongs to, or None.

    The sheet had a protective-order badge and no court-action one: same machinery, one of
    the two wired up, so 341 court notices across 290 dockets sat in a register no sheet
    entry pointed at (navigation-review.md A8). Both badges now read the register modules'
    own matching rules, so a sheet cannot claim membership the register would deny — and
    the rules are the Board's own printed type, never an inference about the document.
    """
    text = (entry_type or "").lower()
    if kind == "decision" and text == registers.COURT_ACTION:
        return "/court", "in the court-action register"
    if kind == "filing" and registers.PROTECTIVE_ORDER in text:
        return "/protective", "in the protective-order register"
    return None


def prefix_name(prefix: str) -> str:
    return PREFIX_NAMES.get(prefix, f"{prefix} docket")


def display_filed_for(raw: str) -> str:
    """The Board's cell sometimes repeats one party several times over (measured). Show a
    repeated identical run once; the raw cell is untouched in the store and on the record."""
    for i in range(1, len(raw)):
        if raw.startswith(", ", i):
            unit = raw[:i]
            n, rem = divmod(len(raw) - len(unit), len(unit) + 2)
            if n >= 1 and rem == 0 and raw == ", ".join([unit] * (n + 1)):
                return unit
    return raw


def plural(n: int, noun: str, plural_form: str | None = None) -> str:
    word = noun if n == 1 else (plural_form or noun + "s")
    return f"{n:,} {word}"
