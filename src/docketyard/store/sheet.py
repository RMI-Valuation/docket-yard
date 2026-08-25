"""The docket-sheet projection: one chronological view per proceeding.

Derived entirely from the registry, the record tables and the event ledger — rebuildable,
never a source of truth (ADR 0006). Filings and decisions of the docket and its
sub-dockets merge into one list, newest first, each entry carrying the identifiers a page
needs to link the Board's own PDF and to cite the record.
"""

from dataclasses import dataclass, field
from sqlite3 import Connection

from docketyard.store.db import load_json


@dataclass(frozen=True)
class Attachment:
    url: str
    label: str | None
    document_sha256: str | None  # None until fetched


@dataclass(frozen=True)
class Entry:
    kind: str  # 'filing' | 'decision'
    date: str | None  # ISO, quoted from the record
    date_printed: str | None
    docket_raw: str  # which docket of the family the entry sits in
    record_id: str  # STB filing id or decision id
    type: str | None
    filed_for_raw: str | None  # filings only; the cell as printed
    deciding_body: str | None  # decisions only
    summary: str | None  # decisions only; the Board's own words as printed
    attachments: list[Attachment] = field(default_factory=list)
    also_in: list[str] = field(default_factory=list)  # other family dockets it was entered in


@dataclass(frozen=True)
class DocketSheet:
    docket_id: int
    raw_docket: str
    prefix: str
    sequence: int
    title: str | None  # latest observation; None if never directly observed
    sub_dockets: list[tuple[int, str, str | None]]  # (docket_id, raw, title)
    entries: list[Entry]
    filings: int
    decisions: int
    last_checked: str | None  # latest capture that touched the family, ISO UTC


def _family(con: Connection, docket_id: int) -> list[tuple[int, str, str | None]]:
    rows = con.execute(
        "SELECT docket_id, raw_docket, latest_payload FROM docket_current"
        " WHERE docket_id = ? OR parent_docket_id = ?"
        " ORDER BY COALESCE(sub_sequence, -1), COALESCE(suffix, '')",
        (docket_id, docket_id),
    ).fetchall()
    return [(d, raw, load_json(p)["title"] if p else None) for d, raw, p in rows]


def _attachments(con: Connection, table: str, pk_col: str, pk: int) -> list[Attachment]:
    return [
        Attachment(url, label, sha)
        for url, label, sha in con.execute(
            f"SELECT source_url, label, document_sha256 FROM {table} WHERE {pk_col} = ?"
            " ORDER BY source_url",
            (pk,),
        )
    ]


def _latest_payload(con: Connection, event_id: int) -> dict:
    row = con.execute("SELECT payload FROM event WHERE event_id = ?", (event_id,)).fetchone()
    return load_json(row[0]) if row else {}


def docket_sheet(con: Connection, docket_id: int) -> DocketSheet | None:
    head = con.execute(
        "SELECT raw_docket, prefix, sequence, latest_payload FROM docket_current"
        " WHERE docket_id = ?",
        (docket_id,),
    ).fetchone()
    if head is None:
        return None
    raw, prefix, sequence, payload = head
    family = _family(con, docket_id)
    ids = [d for d, _, _ in family]
    marks = ",".join("?" for _ in ids)
    entries: list[Entry] = []
    for pk, fam_docket, fid, ftype, fdate, filed_for, event_id in con.execute(
        f"SELECT filing_pk, docket_id, stb_filing_id, filing_type, filed_date,"
        f" filed_for_raw, observed_in_event FROM filing WHERE docket_id IN ({marks})",
        ids,
    ).fetchall():
        p = _latest_payload(con, event_id)
        entries.append(
            Entry(
                kind="filing",
                date=fdate,
                date_printed=p.get("date_printed"),
                docket_raw=next(r for d, r, _ in family if d == fam_docket),
                record_id=fid,
                type=ftype,
                filed_for_raw=filed_for,
                deciding_body=None,
                summary=None,
                attachments=_attachments(con, "filing_attachment", "filing_pk", pk),
            )
        )
    for pk, fam_docket, did, dtype, body, sdate, event_id in con.execute(
        f"SELECT decision_pk, docket_id, stb_decision_id, decision_type, deciding_body,"
        f" service_date, observed_in_event FROM decision_record WHERE docket_id IN ({marks})",
        ids,
    ).fetchall():
        p = _latest_payload(con, event_id)
        entries.append(
            Entry(
                kind="decision",
                date=sdate,
                date_printed=p.get("date_printed"),
                docket_raw=next(r for d, r, _ in family if d == fam_docket),
                record_id=did,
                type=dtype,
                filed_for_raw=None,
                deciding_body=body,
                summary=p.get("summary"),
                attachments=_attachments(con, "decision_attachment", "decision_pk", pk),
            )
        )
    # a record entered in the docket and its sub-docket is one record: fold to the copy
    # nearest the parent (family order) and note where else it was entered
    entries = _fold_family_duplicates(entries, [r for _, r, _ in family])
    # newest first; within a day, decisions before filings, then by record id descending —
    # a stable, explainable order, not a claim about the order things happened within a day
    entries.sort(
        key=lambda e: (e.date or "", e.kind == "decision", _numeric(e.record_id)), reverse=True
    )
    last = con.execute(
        f"SELECT MAX(c.captured_at) FROM capture c JOIN event e ON e.capture_id = c.capture_id"
        f" WHERE e.docket_id IN ({marks})",
        ids,
    ).fetchone()[0]
    return DocketSheet(
        docket_id=docket_id,
        raw_docket=raw,
        prefix=prefix,
        sequence=sequence,
        title=load_json(payload)["title"] if payload else None,
        sub_dockets=[(d, r, t) for d, r, t in family if d != docket_id],
        entries=entries,
        filings=sum(1 for e in entries if e.kind == "filing"),
        decisions=sum(1 for e in entries if e.kind == "decision"),
        last_checked=last,
    )


def _numeric(record_id: str) -> int:
    return int(record_id) if record_id.isdigit() else 0


def _fold_family_duplicates(entries: list[Entry], family_order: list[str]) -> list[Entry]:
    rank = {raw: i for i, raw in enumerate(family_order)}
    by_key: dict[tuple[str, str], list[Entry]] = {}
    for e in entries:
        by_key.setdefault((e.kind, e.record_id), []).append(e)
    folded = []
    for copies in by_key.values():
        copies.sort(key=lambda e: rank.get(e.docket_raw, len(rank)))
        head = copies[0]
        if len(copies) > 1:
            head = Entry(**{**head.__dict__, "also_in": [c.docket_raw for c in copies[1:]]})
        folded.append(head)
    return folded
