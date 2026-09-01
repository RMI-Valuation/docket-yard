"""The parties directory: a page before it is a search (navigation-review.md § C).

`/parties` is one of the three things in the masthead, and it was a heading, a sentence and
an empty search box — 10,108 parties, not one of them named, no list, no alphabet. A reader
who does not already know a name could not reach a single party page from it.

Everything here is counted from the record on request and memoised by the web tier against
the store stamp, like `/stats` and `/weeks`. Nothing is asserted: a party's own page carries
its names, its provenance and the rule that resolved them.
"""

from dataclasses import dataclass
from sqlite3 import Connection

from docketyard.parties import resolve

BUSIEST = 50  # named on the front of the directory; the alphabet holds the rest
OTHER = "0"  # the bucket key for a name starting with a digit or punctuation


@dataclass(frozen=True)
class PartyRow:
    party_id: int  # the component's representative — its permanent address (ADR 0015)
    name: str
    filings: int
    dockets: int


@dataclass(frozen=True)
class Letter:
    key: str  # 'A'…'Z', or OTHER
    label: str
    parties: int


@dataclass(frozen=True)
class Directory:
    parties: int
    busiest: list[PartyRow]
    letters: list[Letter]


def _bucket(name: str) -> str:
    """The alphabet entry a name files under. 40 of 10,108 names begin with a digit or
    punctuation (measured 2026-09-01) — one bucket for all of them rather than a dozen
    pages holding four parties each.

    The length test is not decoration: `"ß".upper()` is `"SS"`, which would mint a
    two-character bucket and serve it at `/parties/SS` (code review, 2026-09-01). Anything
    that is not one ASCII letter after upper-casing — an accent, a digit, a quote — files
    under the same bucket the label names."""
    upper = (name or "")[:1].upper()
    return upper if len(upper) == 1 and upper.isalpha() and upper.isascii() else OTHER


def _label(key: str) -> str:
    return key if key != OTHER else "0–9 and other"


def _counts(con: Connection, comps: resolve.Components) -> dict[int, tuple[int, int]]:
    """Per component: distinct filings, and the docket families they were filed in. The
    same unit and the same join the search index publishes, so the two never disagree."""
    filings: dict[int, set] = {}
    dockets: dict[int, set] = {}
    for party_id, family, stb_id in con.execute(
        """
        SELECT DISTINCT l.party_id, COALESCE(p.parent_docket_id, f.docket_id), f.stb_filing_id
          FROM filing_party_link l
          JOIN filing_party_span s ON s.span_id = l.span_id AND s.superseded_by IS NULL
               AND s.role = 'filed_for'
          JOIN filing f ON f.filing_pk = s.filing_pk AND f.filed_for_raw = s.raw_text
          JOIN docket p ON p.docket_id = f.docket_id
         WHERE l.superseded_by IS NULL
        """
    ):
        rep = comps.rep(party_id)
        filings.setdefault(rep, set()).add(stb_id)
        dockets.setdefault(rep, set()).add(family)
    return {rep: (len(v), len(dockets.get(rep, ()))) for rep, v in filings.items()}


def rows(con: Connection) -> list[PartyRow]:
    """Every component, named once and counted once. Sorted by name, case-folded, so the
    alphabet reads as a reader expects rather than as ASCII does."""
    comps = resolve.Components(con)
    names = resolve.display_names(con, comps)
    counts = _counts(con, comps)
    out = [
        PartyRow(rep, name, *counts.get(rep, (0, 0)))
        for rep, name in names.items()
        if name  # a component with no live name has no page worth linking
    ]
    out.sort(key=lambda r: (r.name.casefold(), r.party_id))
    return out


def directory(rows: list[PartyRow]) -> Directory:
    """The front of the directory, from the one list the web tier memoises."""
    letters: dict[str, int] = {}
    for r in rows:
        letters[_bucket(r.name)] = letters.get(_bucket(r.name), 0) + 1
    busiest = sorted(rows, key=lambda r: (-r.filings, r.name.casefold()))[:BUSIEST]
    return Directory(
        parties=len(rows),
        busiest=busiest,
        letters=[
            Letter(k, _label(k), n)
            # A–Z first and the digits last, whatever ASCII thinks
            for k, n in sorted(letters.items(), key=lambda kv: (kv[0] == OTHER, kv[0]))
        ],
    )


def letter(rows: list[PartyRow], key: str) -> list[PartyRow]:
    """Every party filed under one entry of the alphabet, in name order."""
    return [r for r in rows if _bucket(r.name) == key]
