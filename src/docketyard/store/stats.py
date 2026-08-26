"""The stats page: what the record holds and what moves, measured — never typed. The
published prose lives in `docs/stats.md`; this module is what it describes.

Filings and decisions are counted by the Board's own identifier, so one filing entered
under a parent and a sub-docket counts once — the same unit `coverage` reports. Months
are by the Board's own dates (filed / served), so a month's number is what the record
holds dated in that month, whichever wave observed it. Nothing here is about readers or
subscribers (ADR 0011).
"""

import re
from dataclasses import dataclass
from datetime import date
from sqlite3 import Connection

from docketyard.ingest.dockets import ParsedDocket, parse_docket_id
from docketyard.store.db import load_json

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class Month:
    month: str  # YYYY-MM
    filings: int
    decisions: int


@dataclass(frozen=True)
class Year:
    year: int
    filings: int
    decisions: int
    partial: bool  # the current year, or one the backfill has not finished


@dataclass(frozen=True)
class Busiest:
    docket: ParsedDocket
    title: str | None
    filings: int


@dataclass(frozen=True)
class Stats:
    filings: int
    decisions: int
    documents: int
    document_bytes: int
    dockets: int
    parties: int
    months: list[Month]  # oldest first, every month from the earliest dated record to today
    years: list[Year]  # the same numbers by calendar year
    by_prefix: list[tuple[str, int, int]]  # (prefix, dockets in registry, filings held)
    by_body: list[tuple[str | None, int]]  # deciding body as printed (None: blank), decisions
    busiest: list[Busiest]  # most filings this calendar year, folded by docket family
    year: int


def month_keys(first: str, today: date) -> list[str]:
    """Every YYYY-MM from `first` to the month of `today`, inclusive."""
    y, m = int(first[:4]), int(first[5:])
    out = []
    while (y, m) <= (today.year, today.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def stats(con: Connection, today: date | None = None) -> Stats:
    today = today or date.today()
    q = con.execute

    def one(sql: str) -> int:
        return q(sql).fetchone()[0]

    per_month: dict[str, list[int]] = {}
    for m, n in q(
        "SELECT substr(filed_date, 1, 7), COUNT(DISTINCT stb_filing_id) FROM filing"
        " WHERE filed_date IS NOT NULL GROUP BY 1"
    ):
        per_month.setdefault(m, [0, 0])[0] = n
    for m, n in q(
        "SELECT substr(service_date, 1, 7), COUNT(DISTINCT stb_decision_id) FROM decision_record"
        " WHERE service_date IS NOT NULL GROUP BY 1"
    ):
        per_month.setdefault(m, [0, 0])[1] = n
    # Dates are shape-checked at ingest, not range-checked: a Board-side typo must neither
    # stretch the table to 2062 nor hang the walk. Only well-formed months up to today count.
    this_month = today.strftime("%Y-%m")
    keys = sorted(k for k in per_month if _MONTH.match(k) and k <= this_month)
    months: list[Month] = []
    if keys:
        for k in month_keys(keys[0], today):
            f, d = per_month.get(k, [0, 0])
            months.append(Month(k, f, d))

    year = today.year
    years: list[Year] = []
    for m in months:
        y = int(m.month[:4])
        if not years or years[-1].year != y:
            years.append(Year(y, 0, 0, y == year))
        last = years[-1]
        years[-1] = Year(y, last.filings + m.filings, last.decisions + m.decisions, last.partial)
    ranked = q(
        """
        SELECT root.docket_id, root.raw_docket, COUNT(DISTINCT f.stb_filing_id) AS n
          FROM filing f
          JOIN docket d ON d.docket_id = f.docket_id
          JOIN docket root ON root.docket_id = COALESCE(d.parent_docket_id, d.docket_id)
         WHERE f.filed_date >= ? AND f.filed_date < ?
         GROUP BY root.docket_id ORDER BY n DESC, root.raw_docket LIMIT 10
        """,
        (f"{year}-01-01", f"{year + 1}-01-01"),
    ).fetchall()
    busiest = []
    for docket_id, raw, n in ranked:
        ident = parse_docket_id(raw)
        if ident is None:
            continue
        row = q("SELECT latest_payload FROM docket_current WHERE docket_id = ?", (docket_id,))
        payload = (row.fetchone() or [None])[0]
        busiest.append(Busiest(ident, load_json(payload)["title"] if payload else None, n))

    documents, document_bytes = q(
        "SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM document"
    ).fetchone()
    return Stats(
        filings=one("SELECT COUNT(DISTINCT stb_filing_id) FROM filing"),
        decisions=one("SELECT COUNT(DISTINCT stb_decision_id) FROM decision_record"),
        documents=documents,
        document_bytes=document_bytes,
        dockets=one("SELECT COUNT(*) FROM docket"),
        parties=one("SELECT COUNT(*) FROM party"),
        months=months,
        years=years,
        by_prefix=q(
            """
            SELECT d.prefix, COUNT(DISTINCT d.docket_id), COALESCE(fc.n, 0)
              FROM docket d
              LEFT JOIN (SELECT fd.prefix, COUNT(DISTINCT f.stb_filing_id) AS n
                           FROM filing f JOIN docket fd ON fd.docket_id = f.docket_id
                          GROUP BY fd.prefix) fc ON fc.prefix = d.prefix
             GROUP BY d.prefix ORDER BY 2 DESC
            """
        ).fetchall(),
        by_body=q(
            "SELECT deciding_body, COUNT(DISTINCT stb_decision_id) FROM decision_record"
            " GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall(),
        busiest=busiest,
        year=year,
    )
