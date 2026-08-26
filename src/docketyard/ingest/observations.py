"""Filings- and decisions-table rows → record tables + observed events.

Both tables share one shape: rows carry a triple id `docket|record_id|row_id` in
data-stb-id, positional cells, and zero-or-one attachment link per row — with one filing
appearing on SEVERAL rows, one per attachment (measured, docs/stb-data-source.md), so rows
fold into records by (docket, record_id). Rows of one record can also straddle a page
boundary, i.e. land in different captures: the folded attachment set is therefore the union
of what this capture shows and what the record already holds, so change-detection converges
instead of oscillating between the halves. Everything else is per-table configuration.

The same traps as dockets ingest apply, plus the date-pair trap: filings filter on
filingStartDate/filingEndDate (the officialFilingStartDate pair returns zero rows with no
error), so date criteria are positively verified against the printed date cells — and a
date value the verifier cannot normalise quarantines rather than silently skipping.
"""

import html
from dataclasses import dataclass, field
from sqlite3 import Connection

from docketyard.capture import records
from docketyard.capture.stb import DECISIONS, FILINGS
from docketyard.ingest import dockets
from docketyard.ingest.markup import CELL_RE, LINK_RE, ROW_RE, STB_ID_RE, clean, printed_date_to_iso
from docketyard.store import events


@dataclass(frozen=True)
class TableSpec:
    action: str
    event_type: str
    record_table: str  # filing | decision_record
    record_pk: str  # filing_pk | decision_pk
    record_id_column: str  # stb_filing_id | stb_decision_id
    attachment_table: str
    date_cell: int
    docket_cell: int
    id_cell: int
    attachment_cell: int
    min_cells: int
    date_criteria: tuple[str, str]  # the pair that actually filters
    payload_cells: dict[str, int] = field(default_factory=dict)
    record_columns: dict[str, str] = field(default_factory=dict)  # column -> payload key


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

SPECS = {spec.action: spec for spec in (FILINGS_SPEC, DECISIONS_SPEC)}
SPECS_BY_ATTACHMENT_TABLE = {spec.attachment_table: spec for spec in SPECS.values()}


@dataclass(frozen=True)
class TableRow:
    docket_stb_id: str
    record_id: str
    row_id: str
    date_printed: str  # the cell as printed — the quoted fact
    date: str | None  # ISO normalisation of the same date, None if it did not parse
    fields: dict[str, str]
    attachment: tuple[str, str] | None  # (url, label) from the attachment cell only


@dataclass(frozen=True)
class ParsedTable:
    rows: list[TableRow]
    total: int
    skipped: int


def parse_response(spec: TableSpec, body: bytes) -> ParsedTable:
    data = dockets.parse_envelope(body)
    rows, skipped = [], 0
    for tr in ROW_RE.findall(data.get("rows", "")):
        stb_id = STB_ID_RE.search(tr)
        raw_cells = CELL_RE.findall(tr)
        cells = [clean(c) for c in raw_cells]
        parts = stb_id.group(1).split("|") if stb_id else []
        # the printed docket and id cells must corroborate the triple id, so a column
        # reorder cannot silently mis-file a record
        if (
            len(parts) != 3
            or len(cells) < spec.min_cells
            or cells[spec.docket_cell] != parts[0]
            or cells[spec.id_cell] != parts[1]
            or dockets.parse_docket_id(parts[0]) is None
        ):
            skipped += 1
            continue
        # links are read from the attachment cell only — a docket or title link elsewhere
        # in the row must never become a "document"
        links = [html.unescape(u) for u in LINK_RE.findall(raw_cells[spec.attachment_cell])]
        attachment = (links[0], cells[spec.attachment_cell]) if links else None
        rows.append(
            TableRow(
                docket_stb_id=parts[0],
                record_id=parts[1],
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
        labels = {url: label for row in group if row.attachment for url, label in [row.attachment]}
        known = _known_attachments(con, spec, record_pk) if record_pk else set()
        first = group[0]
        payload: dict[str, object] = dict(first.fields)
        payload["date_printed"] = first.date_printed
        payload["date"] = first.date
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
) -> list[AttachmentRef]:
    """Attachment rows across both record tables, oldest first. `observed_in` restricts
    to records whose latest observation came from captures of that ingest mode — the
    poller fetches the watch's own files first; a backfill wave's backlog is the wave's."""
    out: list[AttachmentRef] = []
    for spec in SPECS.values():
        conds = []
        params: tuple = ()
        if unfetched_only:
            conds.append("a.document_sha256 IS NULL")
        if observed_in:
            conds.append(
                f"a.{spec.record_pk} IN (SELECT r.{spec.record_pk} FROM {spec.record_table} r"
                " JOIN event e ON e.event_id = r.observed_in_event"
                " JOIN capture c ON c.capture_id = e.capture_id WHERE c.ingest_mode = ?)"
            )
            params = (observed_in,)
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        out += [
            AttachmentRef(spec, r[0], r[1], r[2])
            for r in con.execute(
                f"SELECT a.{spec.record_pk}, a.source_url, a.document_sha256"
                f" FROM {spec.attachment_table} a{where} ORDER BY 1",
                params,
            )
        ]
    return out[:limit] if limit is not None else out
