"""The citation resolver (capability F2's second half): a docket or decision citation in
any of the Board's printed forms resolves to its permanent address with no search step.

Forms understood — every docket spelling `urls.lookup` takes (the one definition):
`FD 36873`, `FD_36873_1`, `FD 36873 (Sub-No. 1)`, `STB Finance Docket No. 36873`,
`STB Docket No. AB 55 (Sub-No. 785X)`, `Ex Parte No. 711`, `STB Ex Parte 711`, `Docket
No. NOR 42130`. A decision is the docket plus its service date — `FD 36873 (STB served
Aug. 25, 2026)`, `… served August 25, 2026`, `… decided 8/25/2026` — resolved against the
family's decisions on that date; and `Decision 53210` / `Filing 311981` are the Board's own
record ids. Nothing is guessed: an ambiguous date (two decisions served the same day)
resolves to the sheet, which lists both. The Board's own reporter form (`N S.T.B. n`) and
`Decision No. n` cannot resolve yet — the record does not hold those numbers (they live
inside the documents; extraction later).
"""

import re
from dataclasses import dataclass
from datetime import datetime
from sqlite3 import Connection

from docketyard.ingest.dockets import find_docket
from docketyard.web import urls

_DATE = r"[A-Za-z]+\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}"
_SERVED_RE = re.compile(
    r"\(?\s*(?:STB\s+)?(?:served|decided|service date)\s*:?\s*(" + _DATE + r")\s*\)?", re.I
)
# the Board's own record ids, in the bare form the sheets print (`Decision 53210`); never
# `Decision No. n`, which is a number printed inside the document, and never a year
_RECORD_RE = re.compile(r"^\s*(decision|filing)\s+#?(\d{5,})\s*$", re.I)
_MONTH_NAMES = (
    "january february march april may june july august september october november december"
).split()
_MONTHS = (  # a full name or the usual abbreviation; nothing else is a month
    {m: i for i, m in enumerate(_MONTH_NAMES, 1)}
    | {m[:3]: i for i, m in enumerate(_MONTH_NAMES, 1)}
    | {"sept": 9}
)


@dataclass(frozen=True)
class Resolution:
    kind: (
        str  # 'docket' | 'decision' | 'filing' | 'sheet' (a docket, because the date was ambiguous)
    )
    path: str
    printed: str
    note: str | None = None


def parse_date(text: str) -> str | None:
    """A printed date to ISO; None when it is not one. Nothing is inferred: '8/25/2026',
    'Aug. 25, 2026', 'August 25, 2026', '2026-08-25'."""
    t = text.strip().rstrip(".").replace(",", "")
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            pass
    m = re.match(r"^([A-Za-z]+)\.?\s+(\d{1,2})\s+(\d{4})$", t)
    if m and m.group(1).lower() in _MONTHS:
        try:
            return (
                datetime(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
                .date()
                .isoformat()
            )
        except ValueError:
            return None
    return None


def resolve(con: Connection, text: str) -> Resolution | None:
    text = text.strip()
    if not text:
        return None
    m = _RECORD_RE.match(text)
    if m:  # the Board's own record ids
        kind, stb_id = m.group(1).lower(), m.group(2)
        table, column = (
            ("decision_record", "stb_decision_id")
            if kind == "decision"
            else ("filing", "stb_filing_id")
        )
        if con.execute(f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1", (stb_id,)).fetchone():
            return Resolution(kind, urls.record_path(kind, stb_id), f"{kind.title()} {stb_id}")
        return None
    served = _SERVED_RE.search(text)
    identity = urls.lookup(_SERVED_RE.sub(" ", text) if served else text)
    if identity is None:
        return None
    docket_id = find_docket(con, identity)
    if docket_id is None:
        return None
    printed = urls.printed_docket(identity)
    if served is None:
        return Resolution("docket", urls.docket_path(identity), printed)
    date = parse_date(served.group(1))
    if date is None:
        return Resolution(
            "sheet",
            urls.docket_path(identity),
            printed,
            f"the date {served.group(1)!r} was not read",
        )
    ids = [
        r[0]
        for r in con.execute(
            "SELECT r.stb_decision_id FROM decision_record r"
            " JOIN docket d ON d.docket_id = r.docket_id"
            " WHERE (d.docket_id = ? OR d.parent_docket_id = ?"
            " OR d.docket_id = (SELECT parent_docket_id FROM docket WHERE docket_id = ?))"
            " AND r.service_date = ? ORDER BY r.stb_decision_id",
            (docket_id, docket_id, docket_id, date),
        )
    ]
    if len(ids) == 1:
        return Resolution("decision", urls.decision_path(ids[0]), f"{printed}, served {date}")
    note = (
        f"no decision served {date} is held in {printed}"
        if not ids
        else f"{len(ids)} decisions were served {date} in {printed}; the sheet lists them"
    )
    return Resolution("sheet", urls.docket_path(identity), printed, note)
