"""Dockets-table rows → the docket registry + docket_observed / docket_inferred events.

Also home to the docket-identity helpers every other ingester needs: parsing the
data-stb-id, the canonical spelling used for event keys, registry upsert with provenance for
anything minted outside the dockets table, and the shared front half of the positive filter
assertion.

The traps this module answers (docs/stb-data-source.md):
- the positive filter assertion: a capture is asserted only when every sent criterion is
  positively verified against the returned rows — an unverifiable criterion, a dropped-row
  parse, or zero rows against a non-empty result all quarantine the capture;
- docket identity arrives as data-stb-id `PREFIX_SEQUENCE[_SUB][_SUFFIX]` where a missing
  sub part and `_0` both mean the parent docket, and suffix case varies — normalised for
  identity, raw kept always.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from sqlite3 import Connection, IntegrityError

from docketyard.capture import records
from docketyard.capture.stb import DISPLAY_CAP, DOCKETS
from docketyard.ingest.markup import CELL_RE, ROW_RE, STB_ID_RE, clean
from docketyard.store import events
from docketyard.store.db import load_json

SOURCE_SYSTEM = "stb-ajax"

# The sub part is optional AND `0` when present means the parent: FD_36873 and FD_36339_0
# are both parent-docket spellings (both observed live, 2026-08-25). Prefixes can contain
# digits (S5M, S5A — census 2026-08-25) but always start with a letter.
_DOCKET_ID_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)_(\d+)(?:_(\d+))?(?:_([A-Za-z0-9]+))?$")


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

    def canonical(self) -> str:
        """One spelling per identity — the event source_key form."""
        suffix = f"_{self.suffix}" if self.suffix else ""
        return f"{self.prefix}_{self.sequence}_{self.sub_sequence or 0}{suffix}"


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


def _parse_rows(rows_html: str) -> tuple[list[DocketRow], int]:
    out, skipped = [], 0
    for tr in ROW_RE.findall(rows_html):
        stb_id = STB_ID_RE.search(tr)
        cells = CELL_RE.findall(tr)
        # the printed docket-number cell must corroborate the id, so a column reorder
        # cannot silently store the wrong cell as a title
        if not stb_id or len(cells) < 3 or clean(cells[1]) != stb_id.group(1):
            skipped += 1
            continue
        out.append(DocketRow(stb_id=stb_id.group(1), title=clean(cells[2])))
    return out, skipped


def parse_envelope(body: bytes) -> dict:
    """Decode the AJAX JSON envelope. Raises ValueError for anything abnormal —
    including WordPress's bare `0` body for an expired nonce, which is valid JSON."""
    try:
        payload = load_json(body.decode("utf-8", "replace"))
    except ValueError as e:
        raise ValueError(f"response is not JSON: {body[:120]!r}") from e
    if not isinstance(payload, dict) or not payload.get("success"):
        raise ValueError(f"endpoint reported failure: {body[:120]!r}")
    return payload.get("data") or {}


# `[\w ]+`, not `\w+`: a table name can be TWO WORDS. The live endpoint answers
# "There are no environmental comments available at this time." and `\w+` cannot span
# the space, so the detector silently failed to recognise the one table whose empty
# weeks are ordinary — quarantining every quiet week and never running the proof that
# exists to tell a quiet table from a broken one (ultrareview, 2026-08-31). The tests
# missed it because their fixture said "dockets", which is one word.
_NO_RESULTS_RE = re.compile(r"There are no [\w ]+ available")


def is_no_results_envelope(body: bytes) -> bool:
    """The endpoint's `{"success": false, "data": {"error": "There are no X available"}}`.
    Measured 2026-08-25: a page past the last one AND the wrong date-field pair return
    this identical envelope — so on a first page it is the trap and must quarantine; only
    after a page that passed the assertion does it mean end-of-results."""
    try:
        payload = load_json(body.decode("utf-8", "replace"))
    except ValueError:
        return False
    if not isinstance(payload, dict) or payload.get("success"):
        return False
    data = payload.get("data")
    error = data.get("error") if isinstance(data, dict) else None
    return bool(error and _NO_RESULTS_RE.search(str(error)))


def parse_response(body: bytes) -> ParsedResponse:
    data = parse_envelope(body)
    rows, skipped = _parse_rows(data.get("rows", ""))
    return ParsedResponse(rows=rows, total=int(data.get("total") or 0), skipped=skipped)


# --- the positive filter assertion, shared halves ------------------------------------

# `docketNum_three` is the SUB-sequence: measured against the live endpoint 2026-08-31,
# which echoes the criteria it understood — `one=AB, two=290` answers 392 rows, and
# `one=AB, two=290, three=423` answers 1, naming "Sub Sequence Number = 423".
DOCKET_CRITERIA = {"docketNum_one", "docketNum_two", "docketNum_three"}


def assert_preamble(
    criteria: list[tuple[str, str]],
    *,
    have_rows: bool,
    total: int,
    skipped: int,
    verifiable: set[str],
) -> bool | None:
    """The front half of every table's assertion. Returns a verdict when it can be
    settled without per-row checks; None means "go on to the per-row checks".

    Quarantines on: dropped rows (markup drift), a non-empty reported total with nothing
    parsed, any criterion this table cannot verify, and zero rows against non-empty
    criteria (a mis-named criterion returns zero rows with no error).
    """
    if skipped:
        return False
    if total > 0 and not have_rows:
        return False
    if not criteria:
        return True
    if any(name not in verifiable for name, _ in criteria):
        return False
    if not have_rows:
        return False
    return None


def docket_criteria_hold(checks: dict[str, str], identities: Iterable[ParsedDocket | None]) -> bool:
    """Every row's docket matches the docketNum criteria (a mis-FORMATTED criterion
    returns the full unfiltered set with a 200 — this is the check that catches it)."""
    want_prefix = checks["docketNum_one"].upper() if "docketNum_one" in checks else None
    want_sequence = int(checks["docketNum_two"]) if "docketNum_two" in checks else None
    want_sub = int(checks["docketNum_three"]) if "docketNum_three" in checks else None
    for identity in identities:
        if identity is None:
            return False
        if want_prefix is not None and identity.prefix != want_prefix:
            return False
        if want_sequence is not None and identity.sequence != want_sequence:
            return False
        if want_sub is not None and identity.sub_sequence != want_sub:
            return False
    return True


def assert_filter(criteria: list[tuple[str, str]], parsed: ParsedResponse) -> bool:
    verdict = assert_preamble(
        criteria,
        have_rows=bool(parsed.rows),
        total=parsed.total,
        skipped=parsed.skipped,
        verifiable=DOCKET_CRITERIA,
    )
    if verdict is not None:
        return verdict
    return docket_criteria_hold(dict(criteria), (parse_docket_id(r.stb_id) for r in parsed.rows))


def hit_display_cap(total: int) -> bool:
    return total >= DISPLAY_CAP


# --- the registry --------------------------------------------------------------------


def canonical_of(con: Connection, docket_id: int) -> str:
    """The one spelling per identity, read back from the registry — the form event
    `source_key`s are built from, so anything naming a record across tables can rebuild
    the same string without re-parsing a raw docket number."""
    prefix, sequence, sub, suffix = con.execute(
        "SELECT prefix, sequence, sub_sequence, suffix FROM docket WHERE docket_id = ?",
        (docket_id,),
    ).fetchone()
    return ParsedDocket(prefix, sequence, sub, suffix).canonical()


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
        parent_id = upsert_docket(con, parent, parent.canonical())
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


def register_docket(
    con: Connection,
    identity: ParsedDocket,
    raw: str,
    capture_id: int,
    *,
    printed_in_dockets_table: bool,
    inferred_from: str,
) -> tuple[int, int]:
    """Find or create the docket and its parent, with provenance for anything minted
    outside the dockets table: a minted parent is always `docket_inferred`; the docket
    itself is too when it was seen only on a filing/decision row. A synthesised parent
    spelling is corrected on first direct observation. Returns (docket_id, minted)."""
    parent = identity.parent()
    parent_new = parent is not None and find_docket(con, parent) is None
    self_new = find_docket(con, identity) is None
    docket_id = upsert_docket(con, identity, raw)
    if printed_in_dockets_table:
        con.execute(
            "UPDATE docket SET raw_docket = ? WHERE docket_id = ? AND raw_docket <> ?",
            (raw, docket_id, raw),
        )
    minted = 0
    if parent_new:
        assert parent is not None
        parent_id = find_docket(con, parent)
        assert parent_id is not None
        minted += 1
        events.append(
            con,
            event_type="docket_inferred",
            capture_id=capture_id,
            docket_id=parent_id,
            payload={"inferred_from": inferred_from},
            source_key=f"inferred:{parent.canonical()}",
        )
    if self_new:
        minted += 1
        if not printed_in_dockets_table:
            events.append(
                con,
                event_type="docket_inferred",
                capture_id=capture_id,
                docket_id=docket_id,
                payload={"inferred_from": inferred_from},
                source_key=f"inferred:{identity.canonical()}",
            )
    return docket_id, minted


# --- ingest --------------------------------------------------------------------------


def ingest_capture(con: Connection, data_dir, capture_id: int) -> dict:
    """Consume one asserted dockets capture. Idempotent; already-processed is skipped."""
    body = records.open_pending(con, data_dir, capture_id, DOCKETS)
    if body is None:
        return {"already_processed": True}
    parsed = parse_response(body)
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
        docket_id, minted = register_docket(
            con,
            identity,
            docket_row.stb_id,
            capture_id,
            printed_in_dockets_table=True,
            inferred_from=docket_row.stb_id,
        )
        stats["new_dockets"] += minted
        payload = {"title": docket_row.title}
        if events.latest_payload(con, "docket_observed", docket_id) != payload:
            appended = events.append(
                con,
                event_type="docket_observed",
                capture_id=capture_id,
                docket_id=docket_id,
                payload=payload,
                source_key=identity.canonical(),
            )
            if appended is not None:
                stats["events"] += 1
            else:
                stats["suppressed"] += 1
    records.mark_processed(con, capture_id)
    return stats
