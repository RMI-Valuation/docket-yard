"""Registers: one page each over rows the record already holds, no inference and no
extraction (docs/registers.md). Each is a projection — rebuildable, never a source of
truth — of a decision or filing type the Board itself printed.

- court actions (capability D4's first slice): every decision the Board typed
  `Notice Of Court Action`, by docket — the record of a rulemaking or decision being taken
  to court, in the Board's own words on the sheet;
- protective orders (D7's first slice): every filing the Board typed
  `Motion For Protective Order`, by docket, with the parties it was filed for.
"""

from dataclasses import dataclass, field
from sqlite3 import Connection

from docketyard.parties import resolve
from docketyard.store.db import load_json

COURT_ACTION = "notice of court action"  # matched case-insensitively against decision_type
PROTECTIVE_ORDER = "protective order"  # any filing type naming one


@dataclass(frozen=True)
class Entry:
    kind: str
    record_id: str
    date: str | None
    type: str | None
    filed_for_raw: str | None = None
    parties: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class DocketGroup:
    raw_docket: str
    title: str | None
    entries: list[Entry]  # newest first


@dataclass(frozen=True)
class Register:
    groups: list[DocketGroup]  # newest first
    names: dict[int, str]  # party id -> display name, for every party an entry names


def _newest_first(groups: dict[int, DocketGroup]) -> list[DocketGroup]:
    return sorted(
        groups.values(), key=lambda g: (g.entries[0].date or "", g.raw_docket), reverse=True
    )


def _title(payload: str | None) -> str | None:
    return load_json(payload)["title"] if payload else None


def court_actions(con: Connection) -> Register:
    groups: dict[int, DocketGroup] = {}
    for docket_id, raw, payload, did, date, dtype in con.execute(
        "SELECT d.docket_id, d.raw_docket, d.latest_payload, r.stb_decision_id, r.service_date,"
        " r.decision_type FROM decision_record r JOIN docket_current d ON d.docket_id = r.docket_id"
        " WHERE LOWER(r.decision_type) = ? ORDER BY r.service_date DESC, r.stb_decision_id DESC",
        (COURT_ACTION,),
    ):
        g = groups.get(docket_id)
        if g is None:
            g = groups[docket_id] = DocketGroup(raw, _title(payload), [])
        g.entries.append(Entry("decision", did, date, dtype))
    return Register(_newest_first(groups), {})


def protective_orders(con: Connection) -> Register:
    rows = con.execute(
        "SELECT d.docket_id, d.raw_docket, d.latest_payload, f.filing_pk, f.stb_filing_id,"
        " f.filed_date, f.filing_type, f.filed_for_raw FROM filing f"
        " JOIN docket_current d ON d.docket_id = f.docket_id"
        " WHERE LOWER(f.filing_type) LIKE ? ORDER BY f.filed_date DESC, f.stb_filing_id DESC",
        (f"%{PROTECTIVE_ORDER}%",),
    ).fetchall()
    comps = resolve.Components(con)
    parties = resolve.components_of_filings(con, sorted({r[0] for r in rows}), comps=comps)
    groups: dict[int, DocketGroup] = {}
    for docket_id, raw, payload, pk, fid, date, ftype, filed_for in rows:
        g = groups.get(docket_id)
        if g is None:
            g = groups[docket_id] = DocketGroup(raw, _title(payload), [])
        g.entries.append(Entry("filing", fid, date, ftype, filed_for, parties.get(pk, [])))
    names = {
        p: comps.display_name(p) for g in groups.values() for e in g.entries for p in e.parties
    }
    return Register(_newest_first(groups), names)
