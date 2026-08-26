"""One search box (docs/search.md): a docket number is never a search; everything else is an
FTS5 query over captions, party names and decision summaries, rebuilt by ingest.

`rebuild` is the only writer and runs after a poll pass or a wave: the set is small (tens of
thousands of rows) and rebuilding it whole is simpler and safer than maintaining it. The
index asserts nothing — every hit is an address whose own page carries the record and its
provenance. Nothing about the reader or the query is stored anywhere.
"""

import re
from dataclasses import dataclass
from sqlite3 import Connection

from docketyard.ingest.dockets import parse_docket_id
from docketyard.parties import resolve
from docketyard.store.db import load_json
from docketyard.web import urls

LIMIT = 50  # results on /search
SUGGEST = 8  # rows /suggest answers
MAX_QUERY = 200  # characters a query is cut to before anything looks at it
_TOKEN = re.compile(r"[0-9A-Za-zÀ-ɏ]+")


@dataclass(frozen=True)
class Hit:
    kind: str
    address: str
    title: str
    fact: str


# --- the index -----------------------------------------------------------------------------


def _docket_docs(con: Connection):
    """Family parents only (ADR 0005): the printed number in every spelling a person types,
    the caption as printed, and the sub-dockets' captions — a search for a sub-docket's
    words finds the family."""
    rows = con.execute(
        """
        SELECT d.docket_id, d.raw_docket, d.latest_payload,
               (SELECT COUNT(*) FROM filing f JOIN docket m ON m.docket_id = f.docket_id
                 WHERE m.docket_id = d.docket_id OR m.parent_docket_id = d.docket_id),
               (SELECT MAX(f.filed_date) FROM filing f JOIN docket m ON m.docket_id = f.docket_id
                 WHERE m.docket_id = d.docket_id OR m.parent_docket_id = d.docket_id)
          FROM docket_current d WHERE d.parent_docket_id IS NULL
        """
    ).fetchall()
    subs: dict[int, list[str]] = {}
    for parent, payload in con.execute(
        "SELECT parent_docket_id, latest_payload FROM docket_current"
        " WHERE parent_docket_id IS NOT NULL AND latest_payload IS NOT NULL"
    ):
        title = load_json(payload).get("title")
        if title:
            subs.setdefault(parent, []).append(title)
    for docket_id, raw, payload, filings, last in rows:
        ident = parse_docket_id(raw)
        if ident is None:
            continue
        printed = urls.printed_docket(ident)
        caption = (load_json(payload).get("title") if payload else None) or ""
        spellings = " ".join(
            {printed, raw, f"{ident.prefix}-{ident.sequence}", f"{ident.prefix}{ident.sequence}"}
        )
        body = " ".join([spellings, caption, *subs.get(docket_id, [])])
        fact = f"{filings} filings" + (f", last {last}" if last else "")
        yield "docket", docket_id, urls.docket_path(ident), printed, caption, body, fact


def _party_docs(con: Connection):
    """One row per same_as component under its representative's address (ADR 0015), with
    every live name of every member as the words that find it."""
    comps = resolve.Components(con)
    names: dict[int, list[str]] = {}
    for party_id, raw in con.execute(
        "SELECT party_id, raw_name FROM party_name WHERE superseded_by IS NULL"
    ):
        names.setdefault(comps.rep(party_id), []).append(raw)
    counts: dict[int, tuple[int, int]] = {}
    for party_id, dockets, filings in con.execute(
        """
        SELECT l.party_id, COUNT(DISTINCT COALESCE(p.parent_docket_id, f.docket_id)),
               COUNT(DISTINCT f.stb_filing_id)
          FROM filing_party_link l
          JOIN filing_party_span s ON s.span_id = l.span_id AND s.superseded_by IS NULL
               AND s.role = 'filed_for'
          JOIN filing f ON f.filing_pk = s.filing_pk AND f.filed_for_raw = s.raw_text
          JOIN docket p ON p.docket_id = f.docket_id
         WHERE l.superseded_by IS NULL GROUP BY l.party_id
        """
    ):
        rep = comps.rep(party_id)
        d, n = counts.get(rep, (0, 0))
        counts[rep] = (d + dockets, n + filings)
    for rep, held in names.items():
        d, n = counts.get(rep, (0, 0))
        fact = f"{n} filings in {d} dockets" if n else "on record by name only"
        yield "party", rep, urls.party_path(rep), comps.display_name(rep), "", " ".join(held), fact


def _decision_docs(con: Connection):
    """Decisions with a printed summary, headlined by their docket."""
    for pk, sid, raw, date, event_id in con.execute(
        "SELECT r.decision_pk, r.stb_decision_id, d.raw_docket, r.service_date,"
        " r.observed_in_event FROM decision_record r JOIN docket d USING (docket_id)"
    ):
        row = con.execute("SELECT payload FROM event WHERE event_id = ?", (event_id,)).fetchone()
        summary = (load_json(row[0]).get("summary") if row and row[0] else None) or ""
        if not summary.strip():
            continue
        ident = parse_docket_id(raw)
        printed = urls.printed_docket(ident) if ident else raw
        fact = f"{printed}" + (f", served {date}" if date else "")
        yield (
            "decision",
            pk,
            urls.decision_path(sid),
            f"Decision {sid}",
            summary,
            f"{sid} {printed} {summary}",
            fact,
        )


def rebuild(con: Connection) -> dict:
    """Replace the whole index from the store. One transaction: a reader sees the old set
    or the new one, never half."""
    counts = {"docket": 0, "party": 0, "decision": 0}
    con.execute("DELETE FROM search_doc")
    for source in (_docket_docs, _party_docs, _decision_docs):
        for kind, ref, address, title, caption, body, fact in source(con):
            con.execute(
                "INSERT INTO search_doc (kind, ref, address, title, body, fact)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (kind, ref, address, title, f"{caption} {body}".strip(), fact),
            )
            counts[kind] += 1
    con.execute("INSERT INTO search_fts (search_fts) VALUES ('rebuild')")
    con.commit()
    return counts


# --- the query -----------------------------------------------------------------------------


def _match(text: str, prefix: bool) -> str | None:
    """An FTS5 MATCH expression from whatever was typed: every token quoted (so nothing a
    reader types is ever FTS syntax), all required, the last one a prefix for as-you-type."""
    tokens = _TOKEN.findall(text[:MAX_QUERY])
    if not tokens:
        return None
    quoted = [f'"{t}"' for t in tokens]
    if prefix:
        quoted[-1] += "*"
    return " ".join(quoted)


def search(con: Connection, text: str, *, limit: int = LIMIT, prefix: bool = False) -> list[Hit]:
    """Ranked hits: bm25 with the title weighted above the body; ties by kind (docket,
    party, decision) then title. A docket number is the caller's fast path, not this."""
    match = _match(text, prefix)
    if match is None:
        return []
    rows = con.execute(
        """
        SELECT d.kind, d.address, d.title, d.fact, bm25(search_fts, 8.0, 1.0) AS rank
          FROM search_fts JOIN search_doc d ON d.doc_id = search_fts.rowid
         WHERE search_fts MATCH ?
         ORDER BY rank, d.kind, d.title LIMIT ?
        """,
        (match, limit),
    ).fetchall()
    return [Hit(kind, address, title, fact) for kind, address, title, fact, _ in rows]
