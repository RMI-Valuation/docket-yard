"""The month words a printed date may use, read one way by every surface that reads one.

Full names and the abbreviations the Board actually prints, counted over 200,000 production
pages for the citation resolver (2026-09-05). `sept` is in this map because it was MEASURED at
1,335 occurrences — more than `march` — and a three-letter-prefix rule would have dropped every
one of them. Nothing else is a month.

The citation resolver (`web/cite.py`) reads its month words here. `citator/resolve.MONTHS` and
`citator/decided._MONTHS` still hold their own copies of the same table; a test holds the three
equal until they read this one too (deferred, the release review of 2026-09-10). Only the table
is shared: each reader's grammar around it is its own and versioned with it — `resolve.SERVED`
moves only with a SPAN_VERSION bump — so the parsers are deliberately not merged here.
"""

MONTHS: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
