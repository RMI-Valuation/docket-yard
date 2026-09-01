"""The docket-sheet projection: one chronological view per proceeding.

Derived entirely from the registry, the record tables and the event ledger — rebuildable,
never a source of truth (ADR 0006). Filings and decisions of the docket and its
sub-dockets merge into one list, newest first, each entry carrying the identifiers a page
needs to link the Board's own PDF and to cite the record.
"""

import re
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
    kind: str  # 'filing' | 'decision' | 'comment'
    date: str | None  # ISO, quoted from the record
    date_printed: str | None
    docket_raw: str  # which docket of the family the entry sits in
    record_id: str  # STB filing id, decision id, or comment number
    type: str | None
    filed_for_raw: str | None  # filings only; the cell as printed
    deciding_body: str | None  # decisions only
    summary: str | None  # decisions only; the Board's own words as printed
    attachments: list[Attachment] = field(default_factory=list)
    also_in: list[str] = field(default_factory=list)  # other family dockets it was entered in
    parties: list[int] = field(default_factory=list)  # component ids the filing was filed for
    # comments only, each as printed. The submitter is NOT `filed_for_raw`: a commenter is
    # not a filer, and saying so in the same field would be an inference the record forbids
    submitter: str | None = None
    organisation: str | None = None
    location: str | None = None
    comment_text: str | None = None


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
    comments: int
    last_activity: str | None  # ISO, or None when nothing is held here


@dataclass(frozen=True)
class Series:
    """The number a proceeding sits under, when it sits under one.

    A sub-docket sheet had no way up: `_family` is asked for the page's OWN id and a
    sub-docket has no children, so the family list came back holding only itself. On AB 167
    that leaves 952 of 995 proceedings as cul-de-sacs — no parent, no siblings, and filter
    chips filtering an empty list (navigation-review.md § C).

    The number alone. A first draft also carried the series' caption and how many
    proceedings it holds; the count was `COUNT(*) … WHERE parent_docket_id = ?`, and
    `docket.parent_docket_id` carries no index, so every sub-docket page scanned all 32,605
    dockets to garnish one line — on the 10,798 addresses crawlers walk most. The series
    page says both the moment the reader arrives (code review, 2026-09-01)."""

    raw_docket: str


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
    comments: int
    last_checked: str | None  # latest capture that touched the family, ISO UTC
    series: Series | None = None  # the number above this one, when this is a sub-docket
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
    comments = {
        d: (n, last)
        for d, n, last in con.execute(
            f"SELECT docket_id, COUNT(DISTINCT comment_number), MAX(date_received_or_sent)"
            f" FROM enviro_comment WHERE docket_id IN ({marks}) GROUP BY docket_id",
            ids,
        )
    }
    out = []
    for d, raw, payload in rows:
        fn, fdate = filings.get(d, (0, None))
        dn, ddate = decisions.get(d, (0, None))
        cn, cdate = comments.get(d, (0, None))
        out.append(
            SubDocket(
                docket_id=d,
                raw_docket=raw,
                title=load_json(payload)["title"] if payload else None,
                filings=fn,
                decisions=dn,
                comments=cn,
                # a proceeding whose only held record is a comment is still active, and
                # the index must not show it as holding nothing
                last_activity=max([x for x in (fdate, ddate, cdate) if x], default=None),
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


PLACEHOLDERS = ("", "--", "---")  # what the Board prints for a cell it has nothing for


def present(cell: str | None) -> str | None:
    """The cell's content, or None when the Board printed a placeholder instead.

    Public because every surface that shows a cell needs it, not just this one: the
    machine-agent surface re-queried the store directly and handed an assistant
    "Location: --" as if it were a place (ultrareview, 2026-08-31)."""
    return None if (cell or "").strip() in PLACEHOLDERS else cell


def _latest_payload(con: Connection, event_id: int) -> dict:
    row = con.execute("SELECT payload FROM event WHERE event_id = ?", (event_id,)).fetchone()
    return load_json(row[0]) if row else {}


def _series(con: Connection, docket_id: int) -> Series | None:
    """The series above a sub-docket, or None for a docket that is nobody's child. Two
    primary-key lookups: the page's own row, then its parent's."""
    row = con.execute(
        "SELECT p.raw_docket FROM docket d JOIN docket p ON p.docket_id = d.parent_docket_id"
        " WHERE d.docket_id = ?",
        (docket_id,),
    ).fetchone()
    return Series(row[0]) if row else None


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
    for pk, fam_docket, number, cdate, submitter, org, location, text, event_id in con.execute(
        f"SELECT comment_pk, docket_id, comment_number, date_received_or_sent, submitter_raw,"
        f" organisation_raw, location_raw, comment_text_printed, observed_in_event"
        f" FROM enviro_comment WHERE docket_id IN ({marks})",
        ids,
    ).fetchall():
        p = _latest_payload(con, event_id)
        entries.append(
            Entry(
                kind="comment",
                date=cdate,
                date_printed=p.get("date_printed"),
                docket_raw=next(m.raw_docket for m in family if m.docket_id == fam_docket),
                record_id=number,
                type=None,
                filed_for_raw=None,
                deciding_body=None,
                summary=None,
                attachments=_attachments(con, "enviro_comment_attachment", "comment_pk", pk),
                # the Board prints "--" for a cell it has nothing for. That is an ABSENCE,
                # and printing it as a person's name or a place ("Pamela Underwood, --")
                # states something the record does not. The store keeps the cell exactly as
                # printed; this projection is where a placeholder stops being content.
                submitter=present(submitter),
                organisation=present(org),
                location=present(location),
                comment_text=present(text),
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
        series=_series(con, docket_id),
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
            and own.comments == 0
            and len(family) - 1 >= SERIES_SUBS
        ),
        entries=entries,
        filings=sum(1 for e in entries if e.kind == "filing"),
        decisions=sum(1 for e in entries if e.kind == "decision"),
        comments=sum(1 for e in entries if e.kind == "comment"),
        last_checked=last,
        parties=resolve.parties_in(con, ids),
    )


_DIGITS = re.compile(r"\d+")


def _numeric(record_id: str) -> int:
    """The sortable part of a record id. Filings and decisions print bare digits; a comment
    prints `EI-34280`, whose digits ARE its sequence — returning 0 for those would leave
    every same-day comment in whatever order the SELECT happened to yield, against this
    module's promise of a stable, explainable order."""
    if record_id.isdigit():
        return int(record_id)
    m = _DIGITS.search(record_id)
    return int(m.group()) if m else 0


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
