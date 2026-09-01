"""The span test: does the quoted passage name a DOCUMENT, or only a proceeding?

ADR 0017 D4 makes this the classifier that decides what every published edge IS, which is
why it is a STORED ASSERTION with its own method, version and confidence — a
`citation_judgement` row — and never a predicate computed inside a view. Its default, where
nothing has judged an edge, is to suppress.

The test is what the projected precision was measured with — 98.1% on the
sixty-decision sheet, restated from 98.0% on 2026-09-01 when a defect in the scorer's
registry was fixed (migration 0014's header carries it). Changing the pattern is a new
SPAN_VERSION and a re-measurement of every edge stamped by the old one, not an edit —
and `methods.declare` refuses a bumped version that would collide with the old rank.
"""

import re

SPAN_VERSION = "2026-09-01"

# `served\s+\w+\.?\s+\d` carries an OPTIONAL PERIOD because the Board abbreviates the month:
# "(STB served Mar. 12, 2021)". Without it the test missed two real document-naming spans in
# the sixty decisions and suppressed two true edges — measured 2026-09-01, and the fix
# moved projected recall by two edges while leaving precision unchanged. This is the
# shipping definition and the one every published figure uses.
SPAN_NAMES_DOCUMENT = re.compile(
    r"Decision No\.|slip op|served\s+\w+\.?\s+\d|\bDecision\s+\d{4,6}\b", re.I
)


def names_document(passage: str) -> bool:
    """True when the passage names a document rather than only the proceeding.

    The disjunction ADR 0017 D4 requires — one occurrence naming a document projects the
    edge — is NOT done here. A judgement row is keyed per page, and the fold to the work at
    projection is what makes the test disjunctive across pages: a page whose span names no
    document is filtered out, another page's row for the same target survives, and the
    DISTINCT over the work collapses them. Doing it here as well would be a second, silent
    definition of the same rule.
    """
    return bool(SPAN_NAMES_DOCUMENT.search(passage or ""))
