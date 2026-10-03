"""What arrived in the record inside a window, across proceedings — the read behind MCP's
`recent_activity`.

Asked for 2026-10-02 by the operator, running a daily brief as a scheduled assistant task: a
fresh session with no memory, which today has to guess search words and diff whole sheets
to find what is new. Two windows, and the caller names which:

- **observed** (the default): when the FORWARD watch saw a record — the same events an alert
  carries (`alerts/build.py`), plus environmental comments. A filing the Board posts three
  days late still falls inside the run that first saw it, so a brief run on a schedule
  misses nothing between runs. A backfill wave never appears here; it is history, not news.
- **board_date**: the Board's own filed, served or received-or-sent date, over everything
  held, waves included. A late posting can fall outside a window that has already been read.

Nothing is stored about the caller: the docket list is an argument, used for one read and
dropped (ADR 0011). Every entry is built by the sheet's own row builders, so a record reads
the same here as on its sheet.
"""

import json
from collections import Counter
from dataclasses import dataclass, replace
from sqlite3 import Connection

from docketyard.store import sheet
from docketyard.store.db import load_json

KINDS = ("filing", "decision", "comment")


@dataclass(frozen=True)
class _Spec:
    table: str
    pk: str
    record_id: str
    date: str
    columns: str
    event_type: str
    # what makes two rows one record across proceedings: the Board's id, and for a comment
    # its row ref too — one comment entered in a docket and its sub-docket is one comment,
    # while two comments the Board gave one number are two (`coverage.py`, the archive wave)
    fold: str


SPECS = {
    "filing": _Spec(
        "filing",
        "filing_pk",
        "stb_filing_id",
        "filed_date",
        sheet.FILING_COLUMNS,
        "filing_observed",
        "r.stb_filing_id",
    ),
    "decision": _Spec(
        "decision_record",
        "decision_pk",
        "stb_decision_id",
        "service_date",
        sheet.DECISION_COLUMNS,
        "decision_observed",
        "r.stb_decision_id",
    ),
    "comment": _Spec(
        "enviro_comment",
        "comment_pk",
        "comment_number",
        "date_received_or_sent",
        sheet.COMMENT_COLUMNS,
        "enviro_comment_observed",
        "r.comment_number || '|' || COALESCE(r.stb_row_ref, '')",
    ),
}


@dataclass(frozen=True)
class Filters:
    """Everything a caller can narrow by. `None` on a type tuple means "not asked"; an empty
    tuple means asked and matching nothing of that kind, so the kind is skipped."""

    kinds: tuple[str, ...] = KINDS
    docket_ids: tuple[int, ...] | None = None  # family-expanded by the caller
    prefix: str | None = None
    exclude_prefixes: tuple[str, ...] = ()
    filing_types: tuple[str, ...] | None = None
    decision_types: tuple[str, ...] | None = None
    party: str | None = None  # words in the Filed For cell as printed; filings only
    deciding_body: str | None = None  # words in the deciding body as printed; decisions only


@dataclass(frozen=True)
class Item:
    entry: sheet.Entry
    docket_id: int
    raw_docket: str
    caption: str | None
    observed_at: str | None  # observed window: the newest forward observation inside it
    first_seen: str | None  # the earliest observation of this record, in any proceeding
    first_mode: str | None  # 'forward' | 'backfill'


@dataclass(frozen=True)
class Activity:
    total: int
    by_kind: Counter
    items: list[Item]


def like(words: str) -> str:
    """A LIKE pattern for words as typed, `%` and `_` meaning themselves (ESCAPE a backslash)."""
    escaped = words.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _where(kind: str, f: Filters) -> tuple[list[str], list] | None:
    """The filters for one kind, or None when they rule the whole kind out. A list of ids
    is bound as ONE JSON value: a watchlist of carrier series expands to thousands of docket
    ids (AB 167 alone is 996), past SQLite's ceiling on bound variables (code review)."""
    where, params = [], []
    if f.docket_ids is not None:
        where.append("r.docket_id IN (SELECT value FROM json_each(?))")
        params.append(json.dumps(f.docket_ids))
    if f.prefix:
        where.append("d.prefix = ?")
        params.append(f.prefix)
    if f.exclude_prefixes:
        where.append("d.prefix NOT IN (SELECT value FROM json_each(?))")
        params.append(json.dumps(f.exclude_prefixes))
    asked_type = f.filing_types is not None or f.decision_types is not None
    if kind == "filing":
        if f.deciding_body or (asked_type and not f.filing_types):
            return None
        if f.filing_types:
            where.append("r.filing_type IN (SELECT value FROM json_each(?))")
            params.append(json.dumps(f.filing_types))
        if f.party:
            where.append("r.filed_for_raw LIKE ? ESCAPE '\\'")
            params.append(like(f.party))
    elif kind == "decision":
        if f.party or (asked_type and not f.decision_types):
            return None
        if f.decision_types:
            where.append("r.decision_type IN (SELECT value FROM json_each(?))")
            params.append(json.dumps(f.decision_types))
        if f.deciding_body:
            where.append("r.deciding_body LIKE ? ESCAPE '\\'")
            params.append(like(f.deciding_body))
    else:  # a comment has no Board type, no filer and no deciding body
        if asked_type or f.party or f.deciding_body:
            return None
    return where, params


def _observed(con: Connection, start: str, end: str | None) -> dict[str, list[list]]:
    """[docket_id, record id, newest observation] per kind, for every record the forward
    watch saw inside the window. One pass over the ledger for all three kinds."""
    types = {s.event_type: k for k, s in SPECS.items()}
    marks = ",".join("?" * len(types))
    rows = con.execute(
        "SELECT e.event_type, e.docket_id,"
        " substr(e.source_key, instr(e.source_key, '|') + 1), MAX(c.captured_at)"
        " FROM event e JOIN capture c ON c.capture_id = e.capture_id"
        f" WHERE c.ingest_mode = 'forward' AND e.event_type IN ({marks})"
        " AND c.captured_at >= ?" + (" AND c.captured_at < ?" if end else "") + " GROUP BY 1, 2, 3",
        [*types, start] + ([end] if end else []),
    ).fetchall()
    out: dict[str, list[list]] = {k: [] for k in KINDS}
    for etype, docket_id, rid, seen in rows:
        out[types[etype]].append([docket_id, rid, seen])
    return out


def _candidates(
    con: Connection, kind: str, by: str, start: str, end: str | None, f: Filters, seen_rows
) -> list[tuple]:
    """(kind, pk, docket_id, fold key, board date, observed_at, record id) per matching row."""
    built = _where(kind, f)
    if built is None:
        return []
    where, params = built
    s = SPECS[kind]
    head = (
        f"SELECT '{kind}', r.{s.pk}, r.docket_id, {s.fold}, r.{s.date}, {{seen}}, r.{s.record_id}"
    )
    if by == "observed":
        if not seen_rows:
            return []
        # the window's records as one bound JSON value, joined back to their rows
        sql = (
            "WITH w AS (SELECT json_extract(value, '$[0]') AS docket_id,"
            " json_extract(value, '$[1]') AS rid, json_extract(value, '$[2]') AS seen"
            " FROM json_each(?)) "
            + head.format(seen="w.seen")
            + f" FROM w JOIN {s.table} r ON r.docket_id = w.docket_id AND r.{s.record_id} = w.rid"
            " JOIN docket d ON d.docket_id = r.docket_id"
            + ((" WHERE " + " AND ".join(where)) if where else "")
        )
        return con.execute(sql, [json.dumps(seen_rows), *params]).fetchall()
    where = [f"r.{s.date} >= ?"] + ([f"r.{s.date} <= ?"] if end else []) + where
    sql = (
        head.format(seen="NULL")
        + f" FROM {s.table} r JOIN docket d ON d.docket_id = r.docket_id WHERE "
        + " AND ".join(where)
    )
    return con.execute(sql, [start] + ([end] if end else []) + params).fetchall()


def _copies(con: Connection, kind: str, keys: list[str]) -> dict[str, list[tuple[int, int]]]:
    """fold key -> (pk, docket_id) of every row of each record, in every proceeding it was
    entered in — not only the ones a window or a filter matched, so `also entered in` is
    whole and `first_seen` is the record's, not one copy's (code review: a filing held for
    months under a parent and newly entered in a sub-docket read as new).

    One statement for the page, on the Board's id: there is no index on `stb_filing_id` or
    `stb_decision_id` alone, so a lookup per record was a scan per record — fifty of them on
    a default page, a second on production's store. One scan for all costs one."""
    s = SPECS[kind]
    ids = sorted({k.split("|")[0] for k in keys})
    rows = con.execute(
        f"SELECT {s.fold}, r.{s.pk}, r.docket_id FROM {s.table} r"
        f" WHERE r.{s.record_id} IN (SELECT value FROM json_each(?))",
        (json.dumps(ids),),
    ).fetchall()
    out: dict[str, list[tuple[int, int]]] = {k: [] for k in keys}
    for key, pk, docket_id in rows:
        if key in out:
            out[key].append((pk, docket_id))
    return out


def _first_seen(con: Connection, kind: str, pks: list[int]) -> tuple[str | None, str | None]:
    """When this record first entered the store, and by which mode — over the source keys of
    every copy's own latest event, which every observation of that copy shares."""
    s = SPECS[kind]
    row = con.execute(
        "SELECT c.captured_at, c.ingest_mode FROM event e2"
        " JOIN capture c ON c.capture_id = e2.capture_id"
        " WHERE e2.event_type = ? AND e2.source_key IN ("
        f"  SELECT e.source_key FROM {s.table} r JOIN event e ON e.event_id = r.observed_in_event"
        f"  WHERE r.{s.pk} IN (SELECT value FROM json_each(?)))"
        " ORDER BY c.captured_at, e2.event_id LIMIT 1",
        (s.event_type, json.dumps(pks)),
    ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def _caption(con: Connection, docket_id: int) -> str | None:
    """The proceeding's own caption, else its parent's — a sub-docket the Board listed with
    no caption of its own is still that proceeding."""
    for (payload,) in con.execute(
        "SELECT latest_payload FROM docket_current WHERE docket_id = ?"
        " UNION ALL SELECT p.latest_payload FROM docket d"
        " JOIN docket_current p ON p.docket_id = d.parent_docket_id WHERE d.docket_id = ?",
        (docket_id, docket_id),
    ):
        title = load_json(payload).get("title") if payload else None
        if title:
            return title
    return None


def _dockets(con: Connection, ids: set[int]) -> dict[int, tuple[str, tuple]]:
    """docket_id -> (raw docket, the order that puts the copy nearest its parent first): the
    rule the sheet (`sheet._family`) and the search index (`search._NEAREST`) both lead with,
    so a record is listed under the same docket on all three."""
    return {
        d: (raw, (-1 if sub is None else sub, suffix or "", d))
        for d, raw, sub, suffix in con.execute(
            "SELECT docket_id, raw_docket, sub_sequence, suffix FROM docket"
            " WHERE docket_id IN (SELECT value FROM json_each(?))",
            (json.dumps(sorted(ids)),),
        )
    }


def activity(
    con: Connection,
    *,
    by: str,
    start: str,
    end: str | None,
    filters: Filters,
    limit: int,
    offset: int,
) -> Activity:
    """`start` is inclusive. For `observed`, both bounds are the store's own UTC timestamps
    (`2026-10-01T00:00:00+00:00`) and `end` is exclusive; for `board_date` they are days and
    `end` is inclusive, as the Board's dates have no time."""
    seen = _observed(con, start, end) if by == "observed" else {}
    rows = []
    for kind in filters.kinds:
        rows += _candidates(con, kind, by, start, end, filters, seen.get(kind, []))

    # one item per record: the matched copies grouped by the record's fold key
    groups: dict[tuple, list[tuple]] = {}
    for row in rows:
        groups.setdefault((row[0], row[3]), []).append(row)
    heads = []
    for (kind, fold_key), matched in groups.items():
        observed = max((c[5] for c in matched if c[5]), default=None)
        heads.append((kind, fold_key, matched, observed))

    def order(h):
        kind, _, matched, observed = h
        _, _, _, _, date, _, rid = matched[0]
        return (observed or "", sheet.sort_key(kind, date, rid))

    heads.sort(key=order, reverse=True)
    by_kind = Counter(h[0] for h in heads)

    page = heads[offset : offset + limit]
    copies: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for kind in KINDS:
        keys = [key for k, key, _, _ in page if k == kind]
        if keys:
            copies.update({(kind, key): c for key, c in _copies(con, kind, keys).items()})
    meta = _dockets(
        con,
        {r[2] for _, _, matched, _ in page for r in matched}
        | {d for found in copies.values() for _, d in found},
    )

    def nearest(docket_id: int) -> tuple:
        return meta.get(docket_id, ("", (0, "", docket_id)))[1]

    items = []
    for kind, fold_key, matched, observed in page:
        # the lead is the nearest copy the window and filters MATCHED — a record listed under
        # a prefix the caller left out would contradict the filter it passed
        lead = min(matched, key=lambda r: nearest(r[2]))
        pk, docket_id = lead[1], lead[2]
        others = sorted((d for _, d in copies[(kind, fold_key)] if d != docket_id), key=nearest)
        s = SPECS[kind]
        row = con.execute(f"SELECT {s.columns} FROM {s.table} WHERE {s.pk} = ?", (pk,)).fetchone()
        raw = meta.get(docket_id, ("",))[0]
        # the builders read only which docket of the family a row sits in
        family = [sheet.SubDocket(docket_id, raw, None, 0, 0, 0, None)]
        if kind == "filing":
            entry = sheet._filing_entry(con, row, family, [])
        elif kind == "decision":
            entry = sheet._decision_entry(con, row, family)
        else:
            entry = sheet._comment_entry(con, row, family)
        if others:
            entry = replace(entry, also_in=[meta.get(d, ("",))[0] for d in others])
        first, mode = _first_seen(con, kind, [p for p, _ in copies[(kind, fold_key)]] or [pk])
        items.append(
            Item(
                entry=entry,
                docket_id=docket_id,
                raw_docket=raw,
                caption=_caption(con, docket_id),
                observed_at=observed,
                first_seen=first,
                first_mode=mode,
            )
        )
    return Activity(total=len(heads), by_kind=by_kind, items=items)
