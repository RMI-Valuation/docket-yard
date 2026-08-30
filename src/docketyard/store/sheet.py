"""The docket-sheet projection: one chronological view per proceeding.

Derived entirely from the registry, the record tables and the event ledger — rebuildable,
never a source of truth (ADR 0006). Filings and decisions of the docket and its
sub-dockets merge into one list, newest first, each entry carrying the identifiers a page
needs to link the Board's own PDF and to cite the record.
"""

from dataclasses import dataclass, field
from sqlite3 import Connection

from docketyard.parties import resolve
from docketyard.store.db import load_json

# a family this size with nothing held on the parent is a series, not a case; the
# measured split (2026-08-30) puts 142 families above it and every counterexample —
# FD 33388, FD 32760, EP 542 — below it or holding records of its own
SERIES_SUBS = 5


@dataclass(frozen=True)
class Attachment:
    url: str
    label: str | None
    document_sha256: str | None  # None until fetched
    media_type: str | None = None  # the document table's kind, once fetched


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
    parties: list[int] = field(default_factory=list)  # component ids the filing was filed for


@dataclass(frozen=True)
class SubDocket:
    """One proceeding in a family, as the index lists it. A row with no held records is
    kept and shown: the Board opened the proceeding, and saying so — with its exact
    number — is the answer for anyone hunting a pre-1996 abandonment the record cannot
    hold (the operator, 2026-08-30)."""

    docket_id: int
    raw_docket: str
    title: str | None
    filings: int
    decisions: int
    last_activity: str | None  # ISO, or None when nothing is held here


@dataclass(frozen=True)
class DocketSheet:
    docket_id: int
    raw_docket: str
    prefix: str
    sequence: int
    title: str | None  # latest observation; None if never directly observed
    sub_dockets: list[SubDocket]
    is_index: bool  # the parent holds no records of its own: it is a series, not a case
    entries: list[Entry]
    filings: int
    decisions: int
    last_checked: str | None  # latest capture that touched the family, ISO UTC
    parties: list[dict] = field(default_factory=list)  # the Parties block (party module)


def _family(con: Connection, docket_id: int) -> list[SubDocket]:
    """The docket and its sub-dockets, each with what the record holds for it. Counted in
    two grouped queries, not one per member: AB 167 has 995 sub-dockets."""
    rows = con.execute(
        "SELECT docket_id, raw_docket, latest_payload FROM docket_current"
        " WHERE docket_id = ? OR parent_docket_id = ?"
        " ORDER BY COALESCE(sub_sequence, -1), COALESCE(suffix, '')",
        (docket_id, docket_id),
    ).fetchall()
    ids = [d for d, _, _ in rows]
    marks = ",".join("?" for _ in ids)
    filings = {
        d: (n, last)
        for d, n, last in con.execute(
            f"SELECT docket_id, COUNT(DISTINCT stb_filing_id), MAX(filed_date)"
            f" FROM filing WHERE docket_id IN ({marks}) GROUP BY docket_id",
            ids,
        )
    }
    decisions = {
        d: (n, last)
        for d, n, last in con.execute(
            f"SELECT docket_id, COUNT(DISTINCT stb_decision_id), MAX(service_date)"
            f" FROM decision_record WHERE docket_id IN ({marks}) GROUP BY docket_id",
            ids,
        )
    }
    out = []
    for d, raw, payload in rows:
        fn, fdate = filings.get(d, (0, None))
        dn, ddate = decisions.get(d, (0, None))
        out.append(
            SubDocket(
                docket_id=d,
                raw_docket=raw,
                title=load_json(payload)["title"] if payload else None,
                filings=fn,
                decisions=dn,
                last_activity=max([x for x in (fdate, ddate) if x], default=None),
            )
        )
    return out


def _attachments(con: Connection, table: str, pk_col: str, pk: int) -> list[Attachment]:
    return [
        Attachment(url, label, sha, kind)
        for url, label, sha, kind in con.execute(
            f"SELECT a.source_url, a.label, a.document_sha256, d.media_type FROM {table} a"
            " LEFT JOIN document d ON d.document_sha256 = a.document_sha256"
            f" WHERE a.{pk_col} = ? ORDER BY a.source_url",
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
    own = next((m for m in family if m.docket_id == docket_id), None)
    ids = [m.docket_id for m in family]
    marks = ",".join("?" for _ in ids)
    entries: list[Entry] = []
    filing_rows = con.execute(
        f"SELECT filing_pk, docket_id, stb_filing_id, filing_type, filed_date,"
        f" filed_for_raw, observed_in_event FROM filing WHERE docket_id IN ({marks})",
        ids,
    ).fetchall()
    party_map = resolve.components_of_filings(con, [r[0] for r in filing_rows])
    for pk, fam_docket, fid, ftype, fdate, filed_for, event_id in filing_rows:
        p = _latest_payload(con, event_id)
        entries.append(
            Entry(
                kind="filing",
                date=fdate,
                date_printed=p.get("date_printed"),
                docket_raw=next(m.raw_docket for m in family if m.docket_id == fam_docket),
                record_id=fid,
                type=ftype,
                filed_for_raw=filed_for,
                deciding_body=None,
                summary=None,
                attachments=_attachments(con, "filing_attachment", "filing_pk", pk),
                parties=party_map.get(pk, []),
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
                docket_raw=next(m.raw_docket for m in family if m.docket_id == fam_docket),
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
    entries = _fold_family_duplicates(entries, [m.raw_docket for m in family])
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
        sub_dockets=[m for m in family if m.docket_id != docket_id],
        # A parent that holds no records of its own AND carries a run of sub-dockets is
        # a carrier's series, not a case: measured 2026-08-30, every one of the fourteen
        # largest families (AB 167 with 995 sub-dockets, AB 55 with 765, AB 290 with 391)
        # holds zero filings and zero decisions directly, while FD 33388 — one merger with
        # phases — holds 325. Both halves are needed: 142 families have more than five subs
        # and no records of their own, but a two-member family whose records all sit in the
        # one sub-docket is still a case, and leading with a one-row index would bury it
        # (code review, 2026-08-30).
        is_index=(
            own is not None
            and own.filings == 0
            and own.decisions == 0
            and len(family) - 1 >= SERIES_SUBS
        ),
        entries=entries,
        filings=sum(1 for e in entries if e.kind == "filing"),
        decisions=sum(1 for e in entries if e.kind == "decision"),
        last_checked=last,
        parties=resolve.parties_in(con, ids),
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
