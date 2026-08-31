"""Record-table rows → record tables + observed events (filings, decisions, comments).

All three share one shape: rows carry a triple id `docket|record_id|row_id` in data-stb-id,
positional cells, and zero-or-one attachment link per row — with one record appearing on
SEVERAL rows, one per attachment (measured, docs/stb-data-source.md), so rows fold into
records by (docket, record_id). Rows of one record can also straddle a page boundary, i.e.
land in different captures: the folded attachment set is therefore the union of what this
capture shows and what the record already holds, so change-detection converges instead of
oscillating between the halves. Everything else is per-table configuration.

The same traps as dockets ingest apply, plus the date-pair trap in THREE spellings:
filings filter on filingStartDate/filingEndDate, decisions on serviceStartDate/
serviceEndDate, environmental comments on plain startDate/endDate — and every wrong pair
returns an empty envelope with a 200, not an error. So date criteria are positively
verified against the printed date cells, and a date the verifier cannot normalise
quarantines rather than silently skipping.

Environmental comments differ in one way the spec carries rather than the code
special-casing: their rows print the middle part of data-stb-id NOWHERE, so identity is the
comment number corroborated against its own cell's anchor (`id_anchor`).
"""

import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import zip_longest
from sqlite3 import Connection

from docketyard.capture import records
from docketyard.capture.stb import DECISIONS, ENVIRO_COMMENTS, FILINGS
from docketyard.ingest import dockets
from docketyard.ingest.markup import CELL_RE, LINK_RE, ROW_RE, STB_ID_RE, clean, printed_date_to_iso
from docketyard.store import events

# EI (a submitted comment) and EO (the Board's own environmental document) are the only
# prefixes in 2,385 comments measured across 2003, 2010, 2019 and 2026. Naming them
# rather than accepting any prefix is what makes the corroboration promise true: a
# genuinely new prefix is counted as a skipped row, which the poller reports as a
# problem, instead of being keyed into an append-only ledger unnoticed.
_COMMENT_NUMBER_RE = re.compile(r"(?:EI|EO)-\d+")


@dataclass(frozen=True)
class TableSpec:
    action: str
    event_type: str
    record_table: str  # filing | decision_record | enviro_comment
    record_pk: str  # filing_pk | decision_pk | comment_pk
    record_id_column: str  # stb_filing_id | stb_decision_id | comment_number
    attachment_table: str
    date_cell: int
    docket_cell: int
    id_cell: int
    attachment_cell: int
    min_cells: int
    date_criteria: tuple[str, str]  # the pair that actually filters
    payload_cells: dict[str, int] = field(default_factory=dict)
    record_columns: dict[str, str] = field(default_factory=dict)  # column -> payload key
    # Where the record's identity comes from, and what corroborates it. 'stb_id': the middle
    # part of data-stb-id, corroborated by the printed id cell — filings and decisions, both
    # of which print it. 'cell_anchor': the id cell's own text, corroborated by that cell's
    # own data-stb-id attribute — environmental comments, whose rows print the middle part
    # NOWHERE (measured 2026-08-31), so keying on it could not be checked at all.
    id_anchor: str = "stb_id"
    # the record id is also a public, permanent address, so a second docket claiming one
    # already held is an anomaly to report rather than a row to write
    globally_addressed: bool = False
    extra_payload: dict[str, str] = field(default_factory=dict)  # payload key -> TableRow attr


FILINGS_SPEC = TableSpec(
    action=FILINGS,
    event_type="filing_observed",
    record_table="filing",
    record_pk="filing_pk",
    record_id_column="stb_filing_id",
    attachment_table="filing_attachment",
    date_cell=1,
    docket_cell=2,
    id_cell=3,
    attachment_cell=7,
    min_cells=8,
    date_criteria=("filingStartDate", "filingEndDate"),
    payload_cells={"filed_for": 4, "filing_type": 5},
    record_columns={
        "filing_type": "filing_type",
        "filed_date": "date",
        "filed_for_raw": "filed_for",
    },
)

DECISIONS_SPEC = TableSpec(
    action=DECISIONS,
    event_type="decision_observed",
    record_table="decision_record",
    record_pk="decision_pk",
    record_id_column="stb_decision_id",
    attachment_table="decision_attachment",
    date_cell=1,
    docket_cell=3,  # decisions print Decision ID before Docket Number
    id_cell=2,
    attachment_cell=8,
    min_cells=9,
    date_criteria=("serviceStartDate", "serviceEndDate"),
    payload_cells={"decision_type": 5, "deciding_body": 6, "summary": 7},
    record_columns={
        "decision_type": "decision_type",
        "deciding_body": "deciding_body",
        "service_date": "date",
    },
)

# Cells measured from live rows 2026-08-31 (docs/stb-data-source.md): [0] folder button,
# [1] date, [2] comment number, [3] docket, [4] submitter, [5] organisation, [6] the
# comment's words, [7] location, [8] attachment. Nine cells, and [4]/[5] hold a document
# title rather than a person on an EO row — stored as printed either way, because typing
# the row would be a derived claim and this table derives none.
ENVIRO_COMMENTS_SPEC = TableSpec(
    action=ENVIRO_COMMENTS,
    event_type="enviro_comment_observed",
    record_table="enviro_comment",
    record_pk="comment_pk",
    record_id_column="comment_number",
    attachment_table="enviro_comment_attachment",
    date_cell=1,
    docket_cell=3,
    id_cell=2,
    attachment_cell=8,
    min_cells=9,
    # a THIRD spelling, after filings' filingStartDate and decisions' serviceStartDate; the
    # other pairs answer an empty envelope with a 200. Both %m/%d/%Y and ISO are accepted
    # (measured), so the walk's printed form needs no special case
    date_criteria=("startDate", "endDate"),
    id_anchor="cell_anchor",
    globally_addressed=True,
    payload_cells={"submitter": 4, "organisation": 5, "comment_text": 6, "location": 7},
    extra_payload={"row_ref": "record_ref"},
    record_columns={
        "date_received_or_sent": "date",
        "submitter_raw": "submitter",
        "organisation_raw": "organisation",
        "comment_text_printed": "comment_text",
        "location_raw": "location",
        "stb_row_ref": "row_ref",
    },
)

SPECS = {spec.action: spec for spec in (FILINGS_SPEC, DECISIONS_SPEC, ENVIRO_COMMENTS_SPEC)}
SPECS_BY_ATTACHMENT_TABLE = {spec.attachment_table: spec for spec in SPECS.values()}


@dataclass(frozen=True)
class TableRow:
    docket_stb_id: str
    record_id: str  # the identity: the id part, or the id cell's own anchor (see id_anchor)
    row_id: str
    date_printed: str  # the cell as printed — the quoted fact
    date: str | None  # ISO normalisation of the same date, None if it did not parse
    fields: dict[str, str]
    attachment: tuple[str, str] | None  # (url, label) from the attachment cell only
    record_ref: str = ""  # data-stb-id's middle part; the identity for 'stb_id' specs and a
    # corroborating attribute for 'cell_anchor' ones


@dataclass(frozen=True)
class ParsedTable:
    rows: list[TableRow]
    total: int
    skipped: int


def _identity(
    spec: TableSpec, cells: list[str], raw_cells: list[str], parts: list[str]
) -> tuple[str, bool]:
    """The row's record id and whether the row corroborates it.

    'stb_id' (filings, decisions): the middle part of data-stb-id, corroborated by the
    printed id cell — the check that stops a column reorder mis-filing a record.

    'cell_anchor' (environmental comments): no cell prints that middle part, so it could
    not be checked at all. What the row does print is the comment number, in a cell whose
    own link carries the same value in data-stb-id — so the cell corroborates against the
    markup rather than against the row id, and the middle part is kept beside it.
    """
    if spec.id_anchor == "stb_id":
        return parts[1], cells[spec.id_cell] == parts[1]
    anchor = STB_ID_RE.search(raw_cells[spec.id_cell])
    printed = cells[spec.id_cell]
    # The SHAPE is checked as well as the agreement. "the cell equals its own anchor" is
    # satisfied by other cells in the same row — the docket cell prints FD_36873 and
    # carries data-stb-id="FD_36873" — so on its own it is one column reorder away from
    # keying the ledger on a docket number, and a source_key cannot be taken back.
    # A genuinely new prefix quarantines loudly (see _COMMENT_NUMBER_RE), which is the
    # right direction to fail: a number is a permanent address and an append-only key.
    return printed, anchor is not None and anchor.group(1) == printed and bool(
        _COMMENT_NUMBER_RE.fullmatch(printed)
    )


def parse_response(spec: TableSpec, body: bytes) -> ParsedTable:
    data = dockets.parse_envelope(body)
    rows, skipped = [], 0
    for tr in ROW_RE.findall(data.get("rows", "")):
        stb_id = STB_ID_RE.search(tr)
        raw_cells = CELL_RE.findall(tr)
        cells = [clean(c) for c in raw_cells]
        parts = stb_id.group(1).split("|") if stb_id else []
        # the printed docket cell must corroborate the triple id, so a column reorder
        # cannot silently mis-file a record
        if (
            len(parts) != 3
            or len(cells) < spec.min_cells
            or cells[spec.docket_cell] != parts[0]
            or dockets.parse_docket_id(parts[0]) is None
        ):
            skipped += 1
            continue
        record_id, corroborated = _identity(spec, cells, raw_cells, parts)
        if not corroborated:
            skipped += 1
            continue
        # links are read from the attachment cell only — a docket or title link elsewhere
        # in the row must never become a "document"
        links = [html.unescape(u) for u in LINK_RE.findall(raw_cells[spec.attachment_cell])]
        attachment = (links[0], cells[spec.attachment_cell]) if links else None
        rows.append(
            TableRow(
                docket_stb_id=parts[0],
                record_id=record_id,
                record_ref=parts[1],
                row_id=parts[2],
                date_printed=cells[spec.date_cell],
                date=printed_date_to_iso(cells[spec.date_cell]),
                fields={name: cells[i] for name, i in spec.payload_cells.items()},
                attachment=attachment,
            )
        )
    return ParsedTable(rows=rows, total=int(data.get("total") or 0), skipped=skipped)


def assert_filter(spec: TableSpec, criteria: list[tuple[str, str]], parsed: ParsedTable) -> bool:
    verdict = dockets.assert_preamble(
        criteria,
        have_rows=bool(parsed.rows),
        total=parsed.total,
        skipped=parsed.skipped,
        verifiable=dockets.DOCKET_CRITERIA | set(spec.date_criteria),
    )
    if verdict is not None:
        return verdict
    checks = dict(criteria)
    if not dockets.docket_criteria_hold(
        checks, (dockets.parse_docket_id(r.docket_stb_id) for r in parsed.rows)
    ):
        return False
    bounds = {
        name: printed_date_to_iso(checks[name]) for name in spec.date_criteria if name in checks
    }
    if any(value is None for value in bounds.values()):
        return False  # a date the verifier cannot read is a date it cannot verify
    start = bounds.get(spec.date_criteria[0])
    end = bounds.get(spec.date_criteria[1])
    for row in parsed.rows:
        if bounds and row.date is None:
            return False
        if start is not None and row.date < start:  # type: ignore[operator]
            return False
        if end is not None and row.date > end:  # type: ignore[operator]
            return False
    return True


def ingest_capture(con: Connection, data_dir, capture_id: int) -> dict:
    """Consume one asserted filings/decisions capture. Idempotent; skips reprocessing."""
    action = con.execute(
        "SELECT table_action FROM capture WHERE capture_id = ?", (capture_id,)
    ).fetchone()
    spec = SPECS.get(action[0]) if action else None
    if spec is None:
        raise ValueError(f"capture {capture_id} has no observations parser")
    body = records.open_pending(con, data_dir, capture_id, spec.action)
    if body is None:
        return {"already_processed": True}
    parsed = parse_response(spec, body)
    stats = {
        "rows": len(parsed.rows),
        "markup_skipped": parsed.skipped,
        "records": 0,
        "new_records": 0,
        "new_dockets": 0,
        "events": 0,
        "suppressed": 0,
        "attachments": 0,
        "id_collisions": 0,
    }
    for (docket_stb_id, record_id), group in _grouped(parsed.rows).items():
        stats["records"] += 1
        identity = dockets.parse_docket_id(docket_stb_id)
        assert identity is not None  # unparseable ids were counted skipped in parse
        docket_id, minted = dockets.register_docket(
            con,
            identity,
            docket_stb_id,
            capture_id,
            printed_in_dockets_table=False,
            inferred_from=f"{spec.record_table}:{record_id}",
        )
        stats["new_dockets"] += minted
        record_pk = _find_record(con, spec, docket_id, record_id)
        if record_pk is None and spec.globally_addressed:
            # The record's id doubles as a PUBLIC ADDRESS (/comment/EI-34280), which ADR
            # 0013 makes permanent. The store keys on (docket, id) because global
            # uniqueness is measured, not structural — 2,385 comments sampled across 2003,
            # 2010, 2019 and 2026 held no collision, but that is 11% of the archive. So a
            # second docket claiming an id already held is COUNTED and reported here,
            # loudly, during the wave that would find it — never silently minted as a
            # second record sharing one address.
            stats["id_collisions"] += _elsewhere(con, spec, docket_id, record_id)
        labels = {url: label for row in group if row.attachment for url, label in [row.attachment]}
        known = _known_attachments(con, spec, record_pk) if record_pk else set()
        first = group[0]
        payload: dict[str, object] = dict(first.fields)
        payload["date_printed"] = first.date_printed
        payload["date"] = first.date
        for key, attr in spec.extra_payload.items():
            # deterministic across the group, not `first`: a record legitimately spans
            # several rows AND several pages, so arrival order differs between captures.
            # Measured 1:1 today, so this is a no-op that stays one if that ever changes —
            # the alternative is a payload that flips every pass and doubles the events.
            payload[key] = min(getattr(r, attr) for r in group)
        payload["attachments"] = sorted(known | set(labels))
        source_key = f"{identity.canonical()}|{record_id}"
        event_id = None
        if events.latest_payload_by_key(con, spec.event_type, source_key) != payload:
            event_id = events.append(
                con,
                event_type=spec.event_type,
                capture_id=capture_id,
                docket_id=docket_id,
                occurred_at=first.date,
                payload=payload,
                source_key=source_key,
            )
            if event_id is not None:
                stats["events"] += 1
            else:
                stats["suppressed"] += 1
        if event_id is None and record_pk is None:
            # the ledger already holds this exact observation (e.g. a run that died
            # between the event and the record): recover the event rather than fail
            event_id = _latest_event_id(con, spec.event_type, source_key)
        record_pk, created = _upsert_record(
            con, spec, docket_id, record_id, payload, event_id, record_pk
        )
        stats["new_records"] += int(created)
        for url, label in labels.items():
            cur = con.execute(
                f"INSERT OR IGNORE INTO {spec.attachment_table}"
                f" ({spec.record_pk}, source_url, label) VALUES (?, ?, ?)",
                (record_pk, url, label),
            )
            stats["attachments"] += cur.rowcount
    records.mark_processed(con, capture_id)
    return stats


def _grouped(rows: list[TableRow]) -> dict[tuple[str, str], list[TableRow]]:
    out: dict[tuple[str, str], list[TableRow]] = {}
    for row in rows:
        out.setdefault((row.docket_stb_id, row.record_id), []).append(row)
    return out


def _find_record(con: Connection, spec: TableSpec, docket_id: int, record_id: str) -> int | None:
    row = con.execute(
        f"SELECT {spec.record_pk} FROM {spec.record_table}"
        f" WHERE docket_id = ? AND {spec.record_id_column} = ?",
        (docket_id, record_id),
    ).fetchone()
    return row[0] if row else None


def _elsewhere(con: Connection, spec: TableSpec, docket_id: int, record_id: str) -> int:
    """1 when this record id is already held under a DIFFERENT docket, else 0."""
    row = con.execute(
        f"SELECT 1 FROM {spec.record_table} WHERE {spec.record_id_column} = ?"
        f" AND docket_id <> ? LIMIT 1",
        (record_id, docket_id),
    ).fetchone()
    return 1 if row else 0


def _known_attachments(con: Connection, spec: TableSpec, record_pk: int) -> set[str]:
    return {
        r[0]
        for r in con.execute(
            f"SELECT source_url FROM {spec.attachment_table} WHERE {spec.record_pk} = ?",
            (record_pk,),
        )
    }


def _latest_event_id(con: Connection, event_type: str, source_key: str) -> int | None:
    row = con.execute(
        "SELECT event_id FROM event WHERE source_key = ? AND event_type = ?"
        " ORDER BY event_id DESC LIMIT 1",
        (source_key, event_type),
    ).fetchone()
    return row[0] if row else None


def _upsert_record(
    con: Connection,
    spec: TableSpec,
    docket_id: int,
    record_id: str,
    payload: dict,
    event_id: int | None,
    record_pk: int | None,
) -> tuple[int, bool]:
    columns = {col: payload.get(key) for col, key in spec.record_columns.items()}
    if record_pk is not None:
        if event_id is not None:  # observation changed: mirror it and point at the event
            sets = ", ".join(f"{col} = ?" for col in columns)
            con.execute(
                f"UPDATE {spec.record_table} SET {sets}, observed_in_event = ?"
                f" WHERE {spec.record_pk} = ?",
                (*columns.values(), event_id, record_pk),
            )
        return record_pk, False
    if event_id is None:
        raise RuntimeError(f"no ledger event to anchor new {spec.record_table} {record_id}")
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    cur = con.execute(
        f"INSERT INTO {spec.record_table}"
        f" (docket_id, {spec.record_id_column}, {names}, observed_in_event)"
        f" VALUES (?, ?, {marks}, ?)",
        (docket_id, record_id, *columns.values(), event_id),
    )
    assert cur.lastrowid is not None
    return cur.lastrowid, True


REFUSAL_REST_DAYS = 7  # a URL the host refused is not asked for again this soon
RECHECK_AFTER_DAYS = 30  # a held file is fetched again no sooner than this (errata, ADR 0002)
RECHECK_MAX_BYTES = 64 << 20  # the watch re-fetches files up to this; larger ones (a 1.07 GB
# application, measured) are the operator's `fetch attachments --refresh`, not every cycle's
_EMPTY_SHA = hashlib.sha256(b"").hexdigest()


def recently_refused(con: Connection, days: int = REFUSAL_REST_DAYS) -> set[str]:
    """URLs whose latest fetch was refused (a non-200, or an empty body) within `days`:
    the attempt is on record as a capture; asking again every pass is not politeness."""
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")
    latest: dict[str, bool] = {}
    for url, status, sha in con.execute(
        "SELECT endpoint, http_status, response_sha256 FROM capture"
        " WHERE captured_at > ? ORDER BY capture_id",
        (since,),
    ):
        latest[url] = status != 200 or sha == _EMPTY_SHA
    return {url for url, refused in latest.items() if refused}


# Built from SPECS rather than named by hand: these two drive the errata re-check (ADR
# 0002) and the PUBLISHED re-check cycle length, so a table left out of them silently has
# no replacement detection and quietly shortens a number the coverage page prints.
_HELD_URLS = " UNION ".join(
    f"SELECT source_url FROM {spec.attachment_table} WHERE document_sha256 IS NOT NULL"
    for spec in SPECS.values()
)
_HELD_URLS_UNDER = " UNION ".join(  # the same, bounded by the held document's size
    f"SELECT a.source_url FROM {spec.attachment_table} a JOIN document d"
    " ON d.document_sha256 = a.document_sha256 WHERE d.size_bytes <= ?"
    for spec in SPECS.values()
)
_LAST_FETCH = (
    "SELECT endpoint, MAX(captured_at) AS at FROM capture"
    " WHERE table_action = 'document_fetch' GROUP BY endpoint"
)


def recheck_urls(
    con: Connection,
    *,
    limit: int | None,
    after_days: int | None = None,
    max_bytes: int | None = None,
) -> list[str]:
    """Held URLs due a re-fetch — last asked for more than `after_days` ago (None: however
    recently, the operator asked), the longest-unchecked first, `limit` distinct URLs —
    so the whole record is walked again a slice per pass and a replaced file (an erratum)
    is noticed within one cycle. The capture ledger is the last-checked column: any
    attempt that left a capture, a refusal included, moved the URL to the back of the
    line. One query; nothing is materialised."""
    since = (
        (datetime.now(UTC) - timedelta(days=after_days)).isoformat(timespec="seconds")
        if after_days is not None
        else "\uffff"
    )
    held, size = (
        (_HELD_URLS, ()) if max_bytes is None else (_HELD_URLS_UNDER, (max_bytes,) * len(SPECS))
    )
    return [
        url
        for (url,) in con.execute(
            f"SELECT a.source_url FROM ({held}) a LEFT JOIN ({_LAST_FETCH}) c"
            " ON c.endpoint = a.source_url WHERE COALESCE(c.at, '') <= ?"
            " ORDER BY COALESCE(c.at, ''), a.source_url LIMIT ?",
            (*size, since, -1 if limit is None else limit),
        )
    ]


def held_url_count(con: Connection, max_bytes: int | None = None) -> int:
    """How many distinct URLs the re-check walks: the published cycle is computed from it."""
    if max_bytes is None:
        return con.execute(f"SELECT COUNT(*) FROM ({_HELD_URLS})").fetchone()[0]
    return con.execute(
        f"SELECT COUNT(*) FROM ({_HELD_URLS_UNDER})", (max_bytes,) * len(SPECS)
    ).fetchone()[0]


@dataclass(frozen=True)
class AttachmentRef:
    spec: TableSpec
    record_pk: int
    url: str
    document_sha256: str | None


def attachments(
    con: Connection,
    *,
    unfetched_only: bool,
    limit: int | None = None,
    observed_in: str | None = None,
    urls: list[str] | None = None,  # only these (a re-check slice); None = no restriction
) -> list[AttachmentRef]:
    """Attachment rows across both record tables, oldest first. `observed_in` restricts
    to records whose latest observation came from captures of that ingest mode — the
    poller fetches the watch's own files first; a backfill wave's backlog is the wave's."""
    out: list[AttachmentRef] = []
    per_spec: list[list[AttachmentRef]] = []
    rest = recently_refused(con) if unfetched_only else set()
    for spec in SPECS.values():
        conds = []
        params: tuple = ()
        if unfetched_only:
            conds.append("a.document_sha256 IS NULL")
        if urls is not None:
            conds.append(f"a.source_url IN ({','.join('?' for _ in urls)})")
            params += tuple(urls)
        if observed_in:
            conds.append(
                f"a.{spec.record_pk} IN (SELECT r.{spec.record_pk} FROM {spec.record_table} r"
                " JOIN event e ON e.event_id = r.observed_in_event"
                " JOIN capture c ON c.capture_id = e.capture_id WHERE c.ingest_mode = ?)"
            )
            params += (observed_in,)  # never `=`: it would drop the `urls` bindings above
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        found = [
            AttachmentRef(spec, r[0], r[1], r[2])
            for r in con.execute(
                f"SELECT a.{spec.record_pk}, a.source_url, a.document_sha256"
                f" FROM {spec.attachment_table} a{where} ORDER BY 1",
                params,
            )
            if r[1] not in rest
        ]
        per_spec.append(found)
        out += found
    if limit is None:
        return out
    if limit <= 0:
        return []
    if len(out) <= limit:
        return out
    # Round-robin across the tables, not the first `limit` of a concatenation. Specs are
    # concatenated in order, so a filings backlog larger than the limit would take every
    # slot on every pass and a comment's file would never be fetched at all — the newest
    # table starving behind the oldest, forever and silently.
    fair: list[AttachmentRef] = []
    for row in zip_longest(*per_spec):
        for ref in row:
            if ref is not None:
                fair.append(ref)
                if len(fair) == limit:
                    return fair
    return fair
