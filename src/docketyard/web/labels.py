"""Presentation labels for the sheet's kind column.

A short label derived from the Board's own filing-type string so the column scans; the
full type still appears on the entry. This groups the record's *type labels* for display —
it says nothing about what a document argues, and never looks at who filed it (a filing
from the Board itself is labelled by its type like any other).
"""

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
    ("miscellaneous", "Misc."),
)


def kind_label(kind: str, filing_type: str | None) -> str:
    if kind == "decision":
        return "Decision"
    text = (filing_type or "").lower()
    for needle, label in _RULES:
        if needle in text:
            return label
    return (filing_type or "Filing").split("/")[0].split("(")[0].strip()[:14] or "Filing"


def filter_key(kind: str, filing_type: str | None) -> str:
    """The data attribute the filter chips match on."""
    return kind_label(kind, filing_type).lower().rstrip(".")
