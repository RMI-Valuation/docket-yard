"""The docket index: every proceeding the Board has opened, by its number.

`/coverage` states the record holds 32,623 dockets and offers no way to look at any of them;
the prefix explainers dead-end after saying "the registry holds 6,643 AB dockets"
(navigation-review.md § C). This is the list behind those sentences.

**By number, not by year.** The review asked for prefix and year, and the record cannot
supply the year: a docket row carries a caption and nothing else — no opening date — so a
year could only be inferred from the entries held against it, and **16,805 of 21,807
families hold no entry at all** (measured 2026-09-01). An index by year would silently omit
three quarters of the registry or invent a date for it. The Board's own number is complete,
is its own ordering, and is what a reader hunting a pre-1996 abandonment actually has.
What is held is shown per row, so the emptiness is visible rather than hidden.
"""

from dataclasses import dataclass
from sqlite3 import Connection

BAND = 1000  # a band of docket numbers: /dockets/FD/36000 is FD 36000–36999, for ever
DIRECT = 1000  # a prefix holding this many families or fewer is listed without bands


@dataclass(frozen=True)
class DocketRow:
    raw_docket: str
    prefix: str
    sequence: int
    title: str | None
    filings: int
    decisions: int
    comments: int

    @property
    def held(self) -> int:
        return self.filings + self.decisions + self.comments

    @property
    def band(self) -> int:
        return (self.sequence // BAND) * BAND


@dataclass(frozen=True)
class Band:
    start: int
    dockets: int
    held: int  # families in this band holding at least one entry


@dataclass(frozen=True)
class Prefix:
    prefix: str
    dockets: int  # families: numbers the Board opened directly
    subs: int  # sub-dockets under them, listed on their series' own sheet
    held: int
    bands: list[Band]  # empty when the prefix is listed without bands

    @property
    def banded(self) -> bool:
        return self.dockets > DIRECT


def _counts(con: Connection) -> dict[int, list[int]]:
    """Filings, decisions and comments per FAMILY — a sub-docket's entries count toward the
    number a reader is looking at (ADR 0005). Three grouped queries, never one per docket:
    the registry holds 21,807 families."""
    counts: dict[int, list[int]] = {}
    for table, ident, slot in (
        ("filing", "stb_filing_id", 0),
        ("decision_record", "stb_decision_id", 1),
        ("enviro_comment", "comment_number", 2),
    ):
        for family, n in con.execute(
            f"SELECT COALESCE(d.parent_docket_id, d.docket_id), COUNT(DISTINCT t.{ident})"
            f" FROM {table} t JOIN docket d ON d.docket_id = t.docket_id GROUP BY 1"
        ):
            counts.setdefault(family, [0, 0, 0])[slot] = n
    return counts


def sub_counts(con: Connection) -> dict[str, int]:
    """Sub-dockets per prefix — not listed here, but counted so the page can reconcile its
    own total with the one `/coverage` and `/stats` publish."""
    return dict(
        con.execute(
            "SELECT prefix, COUNT(*) FROM docket WHERE parent_docket_id IS NOT NULL GROUP BY 1"
        )
    )


def rows(con: Connection) -> list[DocketRow]:
    """Every family in the registry, in the Board's own order: prefix, then number."""
    counts = _counts(con)
    return [
        DocketRow(raw, prefix, sequence, title, *counts.get(docket_id, (0, 0, 0)))
        for docket_id, raw, prefix, sequence, title in con.execute(
            "SELECT d.docket_id, d.raw_docket, d.prefix, d.sequence,"
            " json_extract(c.latest_payload, '$.title')"
            " FROM docket d LEFT JOIN docket_current c ON c.docket_id = d.docket_id"
            " WHERE d.parent_docket_id IS NULL ORDER BY d.prefix, d.sequence"
        )
    ]


def prefixes(rows: list[DocketRow], subs: dict[str, int] | None = None) -> list[Prefix]:
    """One entry per prefix the registry holds, largest first.

    `subs` is the sub-docket count per prefix, which this index does not list but must
    still publish: `/coverage` and `/stats` count every docket (32,605) and this page counts
    the 21,807 opened directly, so a page saying only its own number would contradict them —
    the defect § C found between `/stats` and `/parties` (code review, 2026-09-01)."""
    subs = subs or {}
    by_prefix: dict[str, list[DocketRow]] = {}
    for r in rows:
        by_prefix.setdefault(r.prefix, []).append(r)
    out = []
    for prefix, group in by_prefix.items():
        bands: dict[int, list[int]] = {}
        for r in group:
            b = bands.setdefault(r.band, [0, 0])
            b[0] += 1
            b[1] += 1 if r.held else 0
        out.append(
            Prefix(
                prefix=prefix,
                dockets=len(group),
                subs=subs.get(prefix, 0),
                held=sum(1 for r in group if r.held),
                bands=(
                    [Band(s, n, h) for s, (n, h) in sorted(bands.items())]
                    if len(group) > DIRECT
                    else []
                ),
            )
        )
    return sorted(out, key=lambda p: (-p.dockets, p.prefix))


def of_prefix(rows: list[DocketRow], prefix: str, band: int | None = None) -> list[DocketRow]:
    """The families of one prefix, or of one band of its numbers."""
    return [r for r in rows if r.prefix == prefix and (band is None or r.band == band)]
