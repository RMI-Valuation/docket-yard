"""Dockets-table rows → the docket registry + docket_observed / docket_inferred events.

The traps this module answers (docs/stb-data-source.md):
- the positive filter assertion: a capture is asserted only when every sent criterion is
  positively verified against the returned rows — an unverifiable criterion, a dropped-row
  parse, or zero rows against a non-empty result all quarantine the capture;
- docket identity arrives as data-stb-id `PREFIX_SEQUENCE[_SUB][_SUFFIX]` where a missing
  sub part and `_0` both mean the parent docket, and suffix case varies — normalised for
  identity, raw kept always.
"""

import html
import re
from dataclasses import dataclass
from sqlite3 import Connection, IntegrityError

from docketyard.capture.records import load_blob
from docketyard.capture.stb import DISPLAY_CAP
from docketyard.store import events
from docketyard.store.db import load_json, utcnow

SOURCE_SYSTEM = "stb-ajax"

_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S)
_STB_ID_RE = re.compile(r'data-stb-id="([^"]+)"')
# The sub part is optional AND `0` when present means the parent: FD_36873 and FD_36339_0
# are both parent-docket spellings (both observed live, 2026-08-25).
_DOCKET_ID_RE = re.compile(r"^([A-Za-z]+)_(\d+)(?:_(\d+))?(?:_([A-Za-z0-9]+))?$")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class ParsedDocket:
    prefix: str
    sequence: int
    sub_sequence: int | None
    suffix: str | None

    def parent(self) -> "ParsedDocket | None":
        if self.sub_sequence is None and self.suffix is None:
            return None
        return ParsedDocket(self.prefix, self.sequence, None, None)


@dataclass(frozen=True)
class DocketRow:
    stb_id: str
    title: str


@dataclass(frozen=True)
class ParsedResponse:
    rows: list[DocketRow]
    total: int
    skipped: int  # <tr> elements that did not yield a coherent row — markup drift signal


def parse_docket_id(raw: str) -> ParsedDocket | None:
    m = _DOCKET_ID_RE.match(raw.strip())
    if not m:
        return None
    prefix, sequence, sub, suffix = m.groups()
    return ParsedDocket(
        prefix=prefix.upper(),
        sequence=int(sequence),
        sub_sequence=int(sub) if sub is not None and int(sub) != 0 else None,
        suffix=suffix.upper() if suffix else None,
    )


def _clean(fragment: str) -> str:
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", fragment))).strip()


def _parse_rows(rows_html: str) -> tuple[list[DocketRow], int]:
    out, skipped = [], 0
    for tr in _ROW_RE.findall(rows_html):
        stb_id = _STB_ID_RE.search(tr)
        cells = _CELL_RE.findall(tr)
        # the printed docket-number cell must corroborate the id, so a column reorder
        # cannot silently store the wrong cell as a title
        if not stb_id or len(cells) < 3 or _clean(cells[1]) != stb_id.group(1):
            skipped += 1
            continue
        out.append(DocketRow(stb_id=stb_id.group(1), title=_clean(cells[2])))
    return out, skipped


def parse_response(body: bytes) -> ParsedResponse:
    """Decode one AJAX response body. Raises ValueError for anything abnormal —
    including WordPress's bare `0` body for an expired nonce, which is valid JSON."""
    try:
        payload = load_json(body.decode("utf-8", "replace"))
    except ValueError as e:
        raise ValueError(f"response is not JSON: {body[:120]!r}") from e
    if not isinstance(payload, dict) or not payload.get("success"):
        raise ValueError(f"endpoint reported failure: {body[:120]!r}")
    data = payload.get("data") or {}
    rows, skipped = _parse_rows(data.get("rows", ""))
    return ParsedResponse(rows=rows, total=int(data.get("total") or 0), skipped=skipped)


_VERIFIABLE_CRITERIA = {"docketNum_one", "docketNum_two"}


def assert_filter(criteria: list[tuple[str, str]], parsed: ParsedResponse) -> bool:
    """Positively assert the response is what the request asked for.

    Quarantines (returns False) on: dropped rows (markup drift), a non-empty reported
    total with nothing parsed, any criterion this function cannot verify, zero rows
    against non-empty criteria (the endpoint answers a mis-named criterion with zero
    rows and no error), and any row not matching the criteria (a mis-formatted
    criterion returns the full unfiltered set with a 200).
    """
    if parsed.skipped:
        return False
    if parsed.total > 0 and not parsed.rows:
        return False
    if not criteria:
        return True
    if any(name not in _VERIFIABLE_CRITERIA for name, _ in criteria):
        return False
    if not parsed.rows:
        return False
    checks = dict(criteria)
    want_prefix = checks["docketNum_one"].upper() if "docketNum_one" in checks else None
    want_sequence = int(checks["docketNum_two"]) if "docketNum_two" in checks else None
    for row in parsed.rows:
        row_id = parse_docket_id(row.stb_id)
        if row_id is None:
            return False
        if want_prefix is not None and row_id.prefix != want_prefix:
            return False
        if want_sequence is not None and row_id.sequence != want_sequence:
            return False
    return True


def hit_display_cap(total: int) -> bool:
    return total >= DISPLAY_CAP


def find_docket(con: Connection, identity: ParsedDocket) -> int | None:
    row = con.execute(
        """
        SELECT docket_id FROM docket
         WHERE prefix = ? AND sequence = ?
           AND COALESCE(sub_sequence, -1) = COALESCE(?, -1)
           AND COALESCE(suffix, '') = COALESCE(?, '')
        """,
        (identity.prefix, identity.sequence, identity.sub_sequence, identity.suffix),
    ).fetchone()
    return row[0] if row else None


def upsert_docket(con: Connection, identity: ParsedDocket, raw: str) -> int:
    """Find or create a docket row (creating an unobserved parent first). Idempotent."""
    found = find_docket(con, identity)
    if found is not None:
        return found
    parent = identity.parent()
    parent_id = None
    if parent is not None:
        parent_id = upsert_docket(con, parent, f"{identity.prefix}_{identity.sequence}_0")
    try:
        cur = con.execute(
            """
            INSERT INTO docket (raw_docket, prefix, sequence, sub_sequence, suffix,
                                parent_docket_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                raw,
                identity.prefix,
                identity.sequence,
                identity.sub_sequence,
                identity.suffix,
                parent_id,
            ),
        )
    except IntegrityError:
        # a concurrent writer won the race on docket_identity; converge on their row
        return upsert_docket(con, identity, raw)
    assert cur.lastrowid is not None
    return cur.lastrowid


def ingest_capture(con: Connection, data_dir, capture_id: int) -> dict:
    """Consume one asserted capture into the registry and the ledger. Idempotent; a
    capture already processed is skipped outright."""
    row = con.execute(
        "SELECT filter_asserted, processed_at, response_sha256 FROM capture WHERE capture_id = ?",
        (capture_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"no capture {capture_id}")
    if not row[0]:
        raise ValueError(f"capture {capture_id} is quarantined (filter not asserted)")
    if row[1] is not None:
        return {"already_processed": True}
    parsed = parse_response(load_blob(data_dir, row[2]))
    stats = {
        "rows": len(parsed.rows),
        "markup_skipped": parsed.skipped,
        "unparsed": 0,
        "new_dockets": 0,
        "events": 0,
        "suppressed": 0,  # same source_key twice in one capture with a differing payload
    }
    for docket_row in parsed.rows:
        identity = parse_docket_id(docket_row.stb_id)
        if identity is None:
            stats["unparsed"] += 1
            continue
        parent = identity.parent()
        row_is_new = find_docket(con, identity) is None
        parent_minted = row_is_new and parent is not None and find_docket(con, parent) is None
        docket_id = upsert_docket(con, identity, docket_row.stb_id)
        stats["new_dockets"] += int(row_is_new) + int(parent_minted)
        # first direct observation corrects a synthesised parent spelling; afterwards
        # raw_docket tracks the most recently printed form
        con.execute(
            "UPDATE docket SET raw_docket = ? WHERE docket_id = ? AND raw_docket <> ?",
            (docket_row.stb_id, docket_id, docket_row.stb_id),
        )
        if parent_minted:
            # a parent the source has not printed yet: recorded as inferred, with the
            # capture that implied it as provenance (never as a fake observation)
            assert parent is not None
            parent_id = find_docket(con, parent)
            assert parent_id is not None
            events.append(
                con,
                event_type="docket_inferred",
                capture_id=capture_id,
                docket_id=parent_id,
                payload={"inferred_from": docket_row.stb_id},
                source_key=f"inferred:{identity.prefix}_{identity.sequence}",
            )
        payload = {"title": docket_row.title}
        if events.latest_payload(con, "docket_observed", docket_id) != payload:
            appended = events.append(
                con,
                event_type="docket_observed",
                capture_id=capture_id,
                docket_id=docket_id,
                payload=payload,
                source_key=docket_row.stb_id,
            )
            if appended is not None:
                stats["events"] += 1
            else:
                stats["suppressed"] += 1
    con.execute("UPDATE capture SET processed_at = ? WHERE capture_id = ?", (utcnow(), capture_id))
    con.commit()
    return stats
