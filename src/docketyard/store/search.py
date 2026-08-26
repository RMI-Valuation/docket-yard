"""One search box (docs/search.md): a docket number is never a search; everything else is an
FTS5 query over captions, party names and decision summaries, rebuilt by ingest.

`rebuild` is the only writer. It derives every row first, on reads, and then replaces the
index in one short write transaction; when nothing the index depends on has changed since
the last build (a signature of the record's newest ids), it does nothing. The index asserts
nothing — every hit is an address whose own page carries the record and its provenance.
Nothing about the reader or the query is stored anywhere.
"""

import re
from dataclasses import dataclass
from sqlite3 import Connection

from docketyard.ingest.dockets import find_docket, parse_docket_id
from docketyard.parties import resolve
from docketyard.store.db import utcnow
from docketyard.web import urls

LIMIT = 50  # results on /search
SUGGEST = 8  # rows /suggest answers
MAX_QUERY = 200  # characters a query is cut to before anything looks at it
MIN_PREFIX = 2  # characters before a prefix query is asked (mirrors the page's script)
_TOKEN = re.compile(r"[0-9A-Za-zÀ-ɏ]+")


@dataclass(frozen=True)
class Hit:
    kind: str
    path: str
    title: str
    fact: str


# --- the index -----------------------------------------------------------------------------


def _family_counts(con: Connection) -> dict[int, tuple[int, str | None]]:
    """family docket_id -> (distinct filings, last filed date): the sheet's own numbers."""
    return {
        fam: (n, last)
        for fam, n, last in con.execute(
            """
            SELECT COALESCE(m.parent_docket_id, m.docket_id), COUNT(DISTINCT f.stb_filing_id),
                   MAX(f.filed_date)
              FROM filing f JOIN docket m ON m.docket_id = f.docket_id GROUP BY 1
            """
        )
    }


def _docket_docs(con: Connection):
    """A family (ADR 0005) is one row: the printed number in the spellings a person types,
    the caption as printed, and every sub-docket's caption. A sub-docket whose caption
    differs from its parent's is a row of its own at its own address (ADR 0013) — the
    thousand line abandonments under AB 55 are each findable — which resolves to the
    family sheet with the sub-docket named (F4)."""
    counts = _family_counts(con)
    rows = con.execute(
        "SELECT docket_id, raw_docket, parent_docket_id, json_extract(latest_payload, '$.title')"
        " FROM docket_current ORDER BY parent_docket_id IS NOT NULL, docket_id"
    ).fetchall()
    parents: dict[int, tuple] = {}
    subs: dict[int, list[str]] = {}
    for docket_id, raw, parent, caption in rows:
        ident = parse_docket_id(raw)
        if ident is None:
            yield "skipped", docket_id, "", "", "", ""
            continue
        caption = caption or ""
        if parent is None:
            parents[docket_id] = (ident, caption)
            continue
        if caption:
            subs.setdefault(parent, []).append(caption)
        p = parents.get(parent)
        if caption and (p is None or caption != p[1]):
            printed = urls.printed_docket(ident)
            head = urls.printed_docket(p[0]) if p else printed
            yield "docket", docket_id, urls.docket_path(ident), printed, caption, f"in {head}"
    for docket_id, (ident, caption) in parents.items():
        printed = urls.printed_docket(ident)
        n, last = counts.get(docket_id, (0, None))
        spellings = f"{printed} {ident.prefix}{ident.sequence}"
        body = " ".join([spellings, caption, *subs.get(docket_id, [])])
        fact = f"{n} filings" + (f", last {last}" if last else "")
        yield "docket", docket_id, urls.docket_path(ident), printed, body, fact


def _party_docs(con: Connection):
    """One row per same_as component under its representative's address (ADR 0015), with
    every live name of every member as the words that find it, and the page's own
    numbers: distinct dockets and filings across the whole component."""
    comps = resolve.Components(con)
    names: dict[int, list[str]] = {}
    for party_id, raw in con.execute(
        "SELECT party_id, raw_name FROM party_name WHERE superseded_by IS NULL"
    ):
        names.setdefault(comps.rep(party_id), []).append(raw)
    dockets: dict[int, set[int]] = {}
    filings: dict[int, set[str]] = {}
    for party_id, family, stb_id in con.execute(
        """
        SELECT DISTINCT l.party_id, COALESCE(p.parent_docket_id, f.docket_id), f.stb_filing_id
          FROM filing_party_link l
          JOIN filing_party_span s ON s.span_id = l.span_id AND s.superseded_by IS NULL
               AND s.role = 'filed_for'
          JOIN filing f ON f.filing_pk = s.filing_pk AND f.filed_for_raw = s.raw_text
          JOIN docket p ON p.docket_id = f.docket_id
         WHERE l.superseded_by IS NULL
        """
    ):
        rep = comps.rep(party_id)
        dockets.setdefault(rep, set()).add(family)
        filings.setdefault(rep, set()).add(stb_id)
    for rep, held in names.items():
        n, d = len(filings.get(rep, ())), len(dockets.get(rep, ()))
        fact = f"{n} filings in {d} dockets" if n else "on record by name only"
        yield "party", rep, urls.party_path(rep), comps.display_name(rep), " ".join(held), fact


def _decision_docs(con: Connection):
    """Decisions with a printed summary: one row per decision id (a decision entered in a
    docket and its sub-docket is one page), headlined by the docket nearest the parent."""
    for pk, sid, raw, date, summary in con.execute(
        """
        SELECT r.decision_pk, r.stb_decision_id, d.raw_docket, r.service_date,
               json_extract(e.payload, '$.summary') AS summary
          FROM decision_record r
          JOIN docket d ON d.docket_id = r.docket_id
          JOIN event e ON e.event_id = r.observed_in_event
         WHERE TRIM(COALESCE(json_extract(e.payload, '$.summary'), '')) <> ''
         GROUP BY r.stb_decision_id
        HAVING MIN(COALESCE(d.sub_sequence, -1)) = COALESCE(d.sub_sequence, -1)
        """
    ):
        ident = parse_docket_id(raw)
        printed = urls.printed_docket(ident) if ident else raw
        fact = printed + (f", served {date}" if date else "")
        body = f"{sid} {printed} {summary}"
        yield "decision", pk, urls.decision_path(sid), f"Decision {sid}", body, fact


def signature(con: Connection) -> str:
    """What the index depends on, as one string: the newest event, name, link, edge and
    correction. Unchanged signature, unchanged index."""
    return ".".join(
        str(v or 0)
        for v in con.execute(
            "SELECT (SELECT MAX(event_id) FROM event), (SELECT MAX(name_id) FROM party_name),"
            " (SELECT MAX(link_id) FROM filing_party_link),"
            " (SELECT MAX(edge_id) FROM party_relationship),"
            " (SELECT MAX(correction_id) FROM correction)"
        ).fetchone()
    )


def built(con: Connection) -> tuple[str | None, int]:
    """(signature the index was built from, its build number) — the number is part of the
    web tier's version stamp, so a rebuild is never hidden by a 304."""
    row = con.execute("SELECT signature, build FROM search_meta WHERE key = 'built'").fetchone()
    return (row[0], row[1]) if row else (None, 0)


def rebuild(con: Connection, *, force: bool = False) -> dict:
    """Replace the whole index from the store, unless nothing it depends on has changed.
    Every row is derived on reads first; the write is one short transaction, so a reader
    sees the old set or the new one, never half, and other writers wait seconds, not
    minutes."""
    sig = signature(con)
    last, build = built(con)
    if sig == last and not force:
        return {"unchanged": True, "build": build}
    rows: list[tuple] = []
    counts = {"docket": 0, "party": 0, "decision": 0, "skipped": 0}
    for source in (_docket_docs, _party_docs, _decision_docs):
        for kind, ref, path, title, body, fact in source(con):
            counts[kind] += 1
            if kind != "skipped":
                rows.append((kind, ref, path, title, body, fact))
    con.execute("BEGIN IMMEDIATE")
    con.execute("DELETE FROM search_doc")
    con.executemany(
        "INSERT INTO search_doc (kind, ref, path, title, body, fact) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    con.execute("INSERT INTO search_fts (search_fts) VALUES ('rebuild')")
    con.execute(
        "INSERT INTO search_meta (key, signature, build, built_at) VALUES ('built', ?, ?, ?)"
        " ON CONFLICT (key) DO UPDATE SET signature = excluded.signature,"
        " build = excluded.build, built_at = excluded.built_at",
        (sig, build + 1, utcnow()),
    )
    con.commit()
    counts["build"] = build + 1
    return counts


# --- the query -----------------------------------------------------------------------------


def _match(text: str, prefix: bool) -> str | None:
    """An FTS5 MATCH expression from whatever was typed: every token quoted (so nothing a
    reader types is ever FTS syntax), all required, the last one a prefix for as-you-type
    once it is long enough to be an index lookup rather than a vocabulary scan."""
    tokens = _TOKEN.findall(text[:MAX_QUERY])
    if not tokens:
        return None
    if prefix and len(tokens[-1]) < MIN_PREFIX:
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
        SELECT d.kind, d.path, d.title, d.fact, bm25(search_fts, 8.0, 1.0) AS rank
          FROM search_fts JOIN search_doc d ON d.doc_id = search_fts.rowid
         WHERE search_fts MATCH ?
         ORDER BY rank, d.kind, d.title LIMIT ?
        """,
        (match, limit),
    ).fetchall()
    return [Hit(kind, path, title, fact) for kind, path, title, fact, _ in rows]


def held_docket(con: Connection, text: str) -> Hit | None:
    """The fast path: a docket number the record holds. The exact identity if it is held;
    else its family, which is where a sub-docket's entries are anyway (ADR 0005); else
    nothing — and then the words are a search like any other."""
    identity = urls.lookup(text)
    if identity is None:
        return None
    for candidate in (identity, identity.parent()):
        if candidate is not None and find_docket(con, candidate) is not None:
            printed = urls.printed_docket(candidate)
            return Hit("docket", urls.docket_path(candidate), printed, "the docket sheet")
    return None
