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


def _family_totals(con: Connection, ids: list[int]) -> dict:
    """What a family holds, folded by the Board's own identifier — never summed over its
    members. One filing entered in a docket AND its sub-docket is two `filing` rows and one
    filing (ADR 0005), which is the fold the entry list did by construction and a sum over
    per-docket counts would undo."""
    marks = ",".join("?" for _ in ids)
    counts = {}
    for key, table, ident in (
        ("filings", "filing", "stb_filing_id"),
        ("decisions", "decision_record", "stb_decision_id"),
        ("comments", "enviro_comment", "comment_number"),
    ):
        counts[key] = con.execute(
            f"SELECT COUNT(DISTINCT {ident}) FROM {table} WHERE docket_id IN ({marks})", ids
        ).fetchone()[0]
    return counts


def _last_checked(con: Connection, ids: list[int]) -> str | None:
    marks = ",".join("?" for _ in ids)
    return con.execute(
        f"SELECT MAX(c.captured_at) FROM capture c JOIN event e ON e.capture_id = c.capture_id"
        f" WHERE e.docket_id IN ({marks})",
        ids,
    ).fetchone()[0]


# The three row-to-Entry builders, used by BOTH `docket_sheet` and `one_entry`. They are
# module-level and shared on purpose: a record page that built its entry differently from
# the sheet that lists it would drift silently, and the two would disagree about the same
# record. One construction, two callers.

FILING_COLUMNS = (
    "filing_pk, docket_id, stb_filing_id, filing_type, filed_date, filed_for_raw, observed_in_event"
)
DECISION_COLUMNS = (
    "decision_pk, docket_id, stb_decision_id, decision_type, deciding_body, service_date,"
    " observed_in_event"
)
COMMENT_COLUMNS = (
    "comment_pk, docket_id, comment_number, date_received_or_sent, submitter_raw,"
    " organisation_raw, location_raw, comment_text_printed, observed_in_event"
)


def _raw_of(family: list[SubDocket], docket_id: int) -> str:
    return next(m.raw_docket for m in family if m.docket_id == docket_id)


def _filing_entry(con: Connection, row, family: list[SubDocket], parties: list[int]) -> Entry:
    pk, fam_docket, fid, ftype, fdate, filed_for, event_id = row
    p = _latest_payload(con, event_id)
    return Entry(
        kind="filing",
        date=fdate,
        date_printed=p.get("date_printed"),
        docket_raw=_raw_of(family, fam_docket),
        record_id=fid,
        type=ftype,
        filed_for_raw=filed_for,
        deciding_body=None,
        summary=None,
        attachments=_attachments(con, "filing_attachment", "filing_pk", pk),
        parties=parties,
    )


def _decision_entry(con: Connection, row, family: list[SubDocket]) -> Entry:
    pk, fam_docket, did, dtype, body, sdate, event_id = row
    p = _latest_payload(con, event_id)
    return Entry(
        kind="decision",
        date=sdate,
        date_printed=p.get("date_printed"),
        docket_raw=_raw_of(family, fam_docket),
        record_id=did,
        type=dtype,
        filed_for_raw=None,
        deciding_body=body,
        summary=p.get("summary"),
        attachments=_attachments(con, "decision_attachment", "decision_pk", pk),
    )


def _comment_entry(con: Connection, row, family: list[SubDocket]) -> Entry:
    pk, fam_docket, number, cdate, submitter, org, location, text, event_id = row
    p = _latest_payload(con, event_id)
    return Entry(
        kind="comment",
        date=cdate,
        date_printed=p.get("date_printed"),
        docket_raw=_raw_of(family, fam_docket),
        record_id=number,
        type=None,
        filed_for_raw=None,
        deciding_body=None,
        summary=None,
        attachments=_attachments(con, "enviro_comment_attachment", "comment_pk", pk),
        # the Board prints "--" for a cell it has nothing for. That is an ABSENCE, and
        # printing it as a person's name or a place ("Pamela Underwood, --") states
        # something the record does not. The store keeps the cell exactly as printed; this
        # projection is where a placeholder stops being content.
        submitter=present(submitter),
        organisation=present(org),
        location=present(location),
        comment_text=present(text),
    )


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

    # A parent that holds no records of its own AND carries a run of sub-dockets is
    # a carrier's series, not a case: measured 2026-08-30, every one of the fourteen
    # largest families (AB 167 with 995 sub-dockets, AB 55 with 765, AB 290 with 391)
    # holds zero filings and zero decisions directly, while FD 33388 — one merger with
    # phases — holds 325. Both halves are needed: 142 families have more than five subs
    # and no records of their own, but a two-member family whose records all sit in the
    # one sub-docket is still a case, and leading with a one-row index would bury it
    # (code review, 2026-08-30).
    is_index = (
        own is not None
        and own.filings == 0
        and own.decisions == 0
        and own.comments == 0
        and len(family) - 1 >= SERIES_SUBS
    )
    if is_index:
        # Decided BEFORE the entries are built, because a series does not build them. The
        # page has never rendered them and the JSON twin now matches the page (operator,
        # 2026-09-01): on AB 167 that was 2,628 entries assembled with a payload and an
        # attachment query EACH, and then discarded — 399 KB of prose over 866 records of
        # work, on every request (navigation-review.md A7, deferred 2026-08-30). Each
        # proceeding keeps its own entries on its own sheet, which the index links.
        return DocketSheet(
            docket_id=docket_id,
            raw_docket=raw,
            prefix=prefix,
            sequence=sequence,
            title=load_json(payload)["title"] if payload else None,
            series=_series(con, docket_id),
            sub_dockets=[m for m in family if m.docket_id != docket_id],
            is_index=True,
            entries=[],
            # counted, never summed over the members: one filing entered in a docket AND
            # its sub-docket is two `filing` rows and one filing, which is the fold the
            # entry list used to do (ADR 0005)
            **_family_totals(con, ids),
            last_checked=_last_checked(con, ids),
            # the Parties block is not rendered on a series, so it is not resolved either
            parties=[],
        )

    entries: list[Entry] = []
    filing_rows = con.execute(
        f"SELECT {FILING_COLUMNS} FROM filing WHERE docket_id IN ({marks})", ids
    ).fetchall()
    # THE FAMILY'S DOCKET IDS, NOT THE FILING PKS. `components_of_filings` filters
    # `WHERE f.docket_id IN (...)`, and this passed `filing_pk` values until 2026-09-02.
    # It returned the right answer by accident — the map is keyed by filing_pk and a store's
    # pk range usually covers its docket ids, so the lookup still hit — while making the join
    # scan every filing with a party span on every sheet built. `one_entry` passing a single
    # pk is where the accident stopped working: it matched no docket and answered `[]`.
    party_map = resolve.components_of_filings(con, ids)
    entries += [_filing_entry(con, r, family, party_map.get(r[0], [])) for r in filing_rows]
    entries += [
        _decision_entry(con, r, family)
        for r in con.execute(
            f"SELECT {DECISION_COLUMNS} FROM decision_record WHERE docket_id IN ({marks})", ids
        ).fetchall()
    ]
    entries += [
        _comment_entry(con, r, family)
        for r in con.execute(
            f"SELECT {COMMENT_COLUMNS} FROM enviro_comment WHERE docket_id IN ({marks})", ids
        ).fetchall()
    ]
    # a record entered in the docket and its sub-docket is one record: fold to the copy
    # nearest the parent (family order) and note where else it was entered
    entries = _fold_family_duplicates(entries, [m.raw_docket for m in family])
    entries.sort(key=lambda e: sort_key(e.kind, e.date, e.record_id), reverse=True)
    last = _last_checked(con, ids)
    return DocketSheet(
        docket_id=docket_id,
        raw_docket=raw,
        prefix=prefix,
        sequence=sequence,
        title=load_json(payload)["title"] if payload else None,
        series=_series(con, docket_id),
        sub_dockets=[m for m in family if m.docket_id != docket_id],
        is_index=False,  # decided above; a series returns before it reaches here
        entries=entries,
        filings=sum(1 for e in entries if e.kind == "filing"),
        decisions=sum(1 for e in entries if e.kind == "decision"),
        comments=sum(1 for e in entries if e.kind == "comment"),
        last_checked=last,
        parties=resolve.parties_in(con, ids),
    )


_DIGITS = re.compile(r"\d+")


def sort_key(kind: str, date: str | None, record_id: str) -> tuple:
    """THE SHEET'S ORDER, in one place, because two callers now compute it.

    Newest first; within a day, decisions before filings, then by record id descending — a
    stable, explainable order, not a claim about the order things happened within a day.
    Callers sort `reverse=True`.

    `docket_sheet` applies this to fully-built `Entry` objects. `neighbours` applies it to
    bare tuples read straight from SQL, because building the entries to find two of them is
    what makes the viewer O(docket). If those two ever computed the order differently, the
    viewer's "next" would point somewhere the sheet does not list it — the same silent drift
    the shared entry builders above exist to prevent, one function along."""
    return (date or "", kind == "decision", _numeric(record_id))


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


@dataclass(frozen=True)
class EntryContext:
    """Enough of a sheet to render or serialise ONE record: the docket it is addressed
    under, and that docket's title. Nothing else, because everything else on `DocketSheet`
    costs the whole docket to compute."""

    docket_id: int
    raw_docket: str
    prefix: str
    sequence: int
    title: str | None


def one_entry(
    con: Connection,
    docket_id: int,
    kind: str,
    record_id: str,
    family: list[SubDocket] | None = None,
    party_map: dict[int, list[int]] | None = None,
) -> tuple[EntryContext, Entry] | None:
    """One record's entry, without building the sheet that lists it.

    THIS EXISTS BECAUSE BUILDING THE SHEET TO READ ONE ROW OFF IT TOOK PRODUCTION DOWN.
    The record page and its JSON twin want an entry and the docket's title; they used to
    call `docket_sheet` and scan `entries` for it, which assembles every filing, decision
    and comment in the family — with a payload and an attachment query EACH — and throws
    the rest away. On FD 35087, which holds 12,031 of the record's 34,255 comments, that
    was 21.5 seconds a page (measured 2026-09-02), and this site's own sitemap offers a
    crawler all 12,031 of those addresses. Three outages in a day, one of them 6 h 52 m in
    which the record stopped being kept.

    The cost here is the number of COPIES of this one record across the family — one,
    usually — not the size of the docket.

    It mirrors `docket_sheet` deliberately in the two places where the answer could
    otherwise differ: a series builds no entries, so it has none to give; and a record
    entered in both a docket and its sub-docket is ONE record, folded to the copy nearest
    the parent with the others named in `also_in` (ADR 0005). The Entry itself is built by
    the same three functions the sheet uses, so the page cannot drift from the list.
    """
    head = con.execute(
        "SELECT raw_docket, prefix, sequence, latest_payload FROM docket_current"
        " WHERE docket_id = ?",
        (docket_id,),
    ).fetchone()
    if head is None:
        return None
    raw, prefix, sequence, payload = head
    # `neighbours` has already computed this and passes it in: it builds THREE entries from
    # one family (the record and its two neighbours), and `_family` runs four grouped
    # queries over every member. Recomputing it per entry was most of what the viewer's
    # targeted path still cost after the sheet went away.
    family = _family(con, docket_id) if family is None else family
    own = next((m for m in family if m.docket_id == docket_id), None)
    # A series holds no records of its own and `docket_sheet` returns it with `entries=[]`,
    # so nothing is addressable under it. Same answer here, reached the same way.
    if (
        own is not None
        and own.filings == 0
        and own.decisions == 0
        and own.comments == 0
        and len(family) - 1 >= SERIES_SUBS
    ):
        return None

    ids = [m.docket_id for m in family]
    marks = ",".join("?" for _ in ids)
    if kind == "filing":
        rows = con.execute(
            f"SELECT {FILING_COLUMNS} FROM filing"
            f" WHERE stb_filing_id = ? AND docket_id IN ({marks})",
            (record_id, *ids),
        ).fetchall()
        # family docket ids — see above. `entry_and_neighbours` builds this ONCE for the
        # three entries it assembles: the join is family-wide and the union-find behind it
        # is store-wide, so paying it per entry put most of the cost back.
        parties = resolve.components_of_filings(con, ids) if party_map is None else party_map
        copies = [_filing_entry(con, r, family, parties.get(r[0], [])) for r in rows]
    elif kind == "decision":
        rows = con.execute(
            f"SELECT {DECISION_COLUMNS} FROM decision_record"
            f" WHERE stb_decision_id = ? AND docket_id IN ({marks})",
            (record_id, *ids),
        ).fetchall()
        copies = [_decision_entry(con, r, family) for r in rows]
    elif kind == "comment":
        rows = con.execute(
            f"SELECT {COMMENT_COLUMNS} FROM enviro_comment"
            f" WHERE comment_number = ? AND docket_id IN ({marks})",
            (record_id, *ids),
        ).fetchall()
        copies = [_comment_entry(con, r, family) for r in rows]
    else:
        raise ValueError(f"unknown kind {kind!r}")

    if not copies:
        return None
    folded = _fold_family_duplicates(copies, [m.raw_docket for m in family])
    context = EntryContext(
        docket_id=docket_id,
        raw_docket=raw,
        prefix=prefix,
        sequence=sequence,
        title=load_json(payload)["title"] if payload else None,
    )
    return context, folded[0]


# The three record tables as the ORDERING pass reads them: enough to sort by and to name a
# row with, and nothing else. `docket_sheet` reads the same tables through the column lists
# above and then builds an Entry per row, with a payload query and an attachment query EACH;
# that is the cost this pass exists to avoid.
_ORDER_SOURCES = (
    ("filing", "stb_filing_id", "filed_date", "filing"),
    ("decision_record", "stb_decision_id", "service_date", "decision"),
    ("enviro_comment", "comment_number", "date_received_or_sent", "comment"),
)


@dataclass(frozen=True)
class RecordView:
    """Everything a page about ONE record renders, and not a docket's worth more."""

    context: EntryContext
    entry: Entry
    prev: Entry | None
    next: Entry | None
    party_names: dict[int, str]  # rep -> display name, the entry's own components only


def entry_and_neighbours(
    con: Connection, docket_id: int, kind: str, record_id: str
) -> RecordView | None:
    """One record, and the records either side of it in sheet order, WITHOUT the sheet.

    THE RECORD PAGE'S RAIL IS THE ONLY O(docket) READ LEFT. `/filing/<id>` and
    `/decision/<id>` were made cheap with `one_entry` after building the sheet to read one
    row off it took production down (2026-09-02); this pass exists so the rail can name the
    entry's neighbours and its parties without going back to `docket_sheet`. It never
    assembles an entry it is going to throw away, which is the whole difference.

    Measured on a 2026-09-02 production copy, re-run 2026-09-04 when the rail came back, on
    FD 35087 — 12,031 comments, the worst docket in the record: `docket_sheet` 235.3 ms,
    `one_entry` 8.5 ms, this 22.6 ms. So the page pays 2.7x `one_entry` where it hurts most
    and stays 10x under the read that caused the outage; over 40 ordinary records the median
    is 1.09 ms against 1.28 ms, which is the case a crawler actually meets.

    The order is `sort_key`'s, and the fold is `docket_sheet`'s: a record entered in a docket
    AND its sub-docket is ONE record, kept as the copy nearest the parent (ADR 0005). Both
    have to match the sheet exactly, or "next" points at something the sheet does not list.

    Returns FULLY-BUILT entries, the target's and both neighbours', because the template
    needs each one's attachments to choose which file its link opens. All three go through
    `one_entry`, so they are constructed by the same three builders the sheet uses and cannot
    drift from it — and all three share one `family`, which is why they are one call and not
    three: `_family` runs four grouped queries over every member of the family, and paying
    that per entry was most of what this path still cost once the sheet was gone.

    `None` when nothing is addressable here — a series, or no such record.
    """
    family = _family(con, docket_id)
    own = next((m for m in family if m.docket_id == docket_id), None)
    # A series builds no entries, so nothing is addressable under it and nothing neighbours
    # anything. `docket_sheet` and `one_entry` reach the same answer the same way.
    if (
        own is not None
        and own.filings == 0
        and own.decisions == 0
        and own.comments == 0
        and len(family) - 1 >= SERIES_SUBS
    ):
        return None

    ids = [m.docket_id for m in family]
    marks = ",".join("?" for _ in ids)
    raw_of = {m.docket_id: m.raw_docket for m in family}
    rank = {m.raw_docket: i for i, m in enumerate(family)}

    # THE ORDERING PASS RUNS FIRST, before anything is built. If the record is not in the
    # order there is nothing to build, and when it is, this is what says which three entries
    # to assemble — so nothing is assembled and discarded.
    best: dict[tuple[str, str], tuple[str, str, str, str | None]] = {}
    for table, id_col, date_col, entry_kind in _ORDER_SOURCES:
        for row_docket, rid, date in con.execute(
            f"SELECT docket_id, {id_col}, {date_col} FROM {table} WHERE docket_id IN ({marks})",
            ids,
        ):
            raw = raw_of[row_docket]
            key = (entry_kind, rid)
            prior = best.get(key)
            # the fold, by the same rule `_fold_family_duplicates` uses: family order, which
            # is the copy nearest the parent. `also_in` is not computed — the neighbour links
            # do not show it, and the entry the reader is ON is built by `one_entry`.
            if prior is None or rank.get(raw, len(rank)) < rank.get(prior[2], len(rank)):
                best[key] = (entry_kind, rid, raw, date)

    ordered = sorted(best.values(), key=lambda r: sort_key(r[0], r[3], r[1]), reverse=True)
    here = next((i for i, r in enumerate(ordered) if r[0] == kind and r[1] == record_id), None)
    if here is None:
        return None

    sides = [i for i in (here - 1, here + 1) if 0 <= i < len(ordered)]
    # Built ONCE for the three entries, and ONLY when one of them is a filing — a decision or
    # a comment is not filed for anybody, so a comment-only stretch of a sheet pays nothing.
    # `components_of_filings` runs a family-wide join over a store-wide union-find, and
    # `one_entry` builds both per call, so three calls rebuilt them three times (code review,
    # 2026-09-03).
    comps = None
    party_map = None
    if "filing" in {kind, *(ordered[i][0] for i in sides)}:
        comps = resolve.Components(con)
        party_map = resolve.components_of_filings(con, ids, comps)

    def entry_at(i: int) -> Entry | None:
        got = one_entry(
            con, docket_id, ordered[i][0], ordered[i][1], family=family, party_map=party_map
        )
        return got[1] if got else None

    here_got = one_entry(con, docket_id, kind, record_id, family=family, party_map=party_map)
    if here_got is None:  # in the order and unbuildable: the sheet would not list it either
        return None
    context, entry = here_got

    # the entry's OWN components, named from the union-find already built. A component with
    # no live name renders as `party <id>` — `Components.display_name`'s documented last
    # resort, and what the sheet's Parties block shows too, so the rail says what the list
    # says rather than dropping the link (code review, 2026-09-03).
    names = (
        {rep: comps.display_name(rep) for rep in dict.fromkeys(entry.parties)}
        if comps is not None
        else {}
    )
    return RecordView(
        context,
        entry,
        entry_at(here - 1) if here > 0 else None,
        entry_at(here + 1) if here + 1 < len(ordered) else None,
        names,
    )
