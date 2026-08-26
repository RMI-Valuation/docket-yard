"""The two passes of the party module: split cells into spans, resolve spans to parties.

Both are re-runnable. A pass never updates a judgement in place: a span whose cell has
changed, whose rule version is old, or whose cut was doubtful is re-cut and superseded
only if the new cut differs; a link is superseded only by a newer method's link. Parties
are minted only from a `filed_for` span the rules cut with full confidence, with the
span's text as their `as_filed` name; a span whose normalised name matches names on two
different components makes no link at all (docs/party-module.md). The operator's seed is
loaded at the start of every run (idempotent) so a mark never mints a stub first.

`Components` is the one definition of "the same entity": every projection builds it once
per request from the live symmetric edges and reads representatives, members and display
names from it.
"""

import json
from sqlite3 import Connection

from docketyard.parties import names
from docketyard.store.db import utcnow

# --- components: the same_as graph, loaded once ------------------------------------------


class Components:
    """Union-find over live symmetric edges. Representative = smallest id in the class."""

    def __init__(self, con: Connection):
        self._parent: dict[int, int] = {}
        for a, b in con.execute(
            "SELECT from_party, to_party FROM party_relationship r"
            " JOIN relationship_vocab v USING (rel_type)"
            " WHERE v.symmetric = 1 AND r.superseded_by IS NULL"
        ):
            self._union(a, b)
        self._con = con
        self._names: dict[int, str] | None = None

    def _find(self, x: int) -> int:
        self._parent.setdefault(x, x)
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def _union(self, a: int, b: int) -> None:
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            lo, hi = min(ra, rb), max(ra, rb)
            self._parent[hi] = lo

    def rep(self, party_id: int) -> int:
        return self._find(party_id)

    def members(self, party_id: int) -> list[int]:
        r = self.rep(party_id)
        return sorted([x for x in self._parent if self._find(x) == r] or [party_id])

    def display_name(self, party_id: int) -> str:
        """Best live name across the whole component: display > legal > as_filed > any."""
        members = self.members(party_id)
        marks = ",".join("?" for _ in members)
        for kind in ("display", "legal", "as_filed"):
            row = self._con.execute(
                f"SELECT raw_name FROM party_name WHERE party_id IN ({marks})"
                f" AND name_kind = ? AND superseded_by IS NULL ORDER BY name_id DESC LIMIT 1",
                (*members, kind),
            ).fetchone()
            if row:
                return row[0]
        row = self._con.execute(
            f"SELECT raw_name FROM party_name WHERE party_id IN ({marks})"
            " AND superseded_by IS NULL ORDER BY name_id LIMIT 1",
            members,
        ).fetchone()
        return row[0] if row else f"party {self.rep(party_id)}"

    def has_name(self, party_id: int, norm: str) -> bool:
        members = self.members(party_id)
        marks = ",".join("?" for _ in members)
        return bool(
            self._con.execute(
                f"SELECT 1 FROM party_name WHERE party_id IN ({marks}) AND norm_name = ?"
                " AND superseded_by IS NULL",
                (*members, norm),
            ).fetchone()
        )


def component_of(con: Connection, party_id: int) -> int:
    return Components(con).rep(party_id)


def display_name(con: Connection, party_id: int) -> str:
    return Components(con).display_name(party_id)


# --- split ---------------------------------------------------------------------------------


def split_pending(con: Connection, log=print) -> dict:
    """Every filing whose current cell has no live full-confidence span from the current
    rules: new cells, changed cells, doubtful cuts, and cuts by an older rule version. A
    re-cut that produces the same spans is a no-op; a different one supersedes."""
    stats = {"filings": 0, "spans": 0, "superseded": 0, "unchanged": 0}
    known = known_norms(con)
    rows = con.execute(
        """
        SELECT f.filing_pk, f.filed_for_raw, e.capture_id
          FROM filing f JOIN event e ON e.event_id = f.observed_in_event
         WHERE f.filed_for_raw IS NOT NULL AND f.filed_for_raw <> ''
           AND NOT EXISTS (SELECT 1 FROM filing_party_span s
                            WHERE s.filing_pk = f.filing_pk AND s.raw_text = f.filed_for_raw
                              AND s.superseded_by IS NULL AND s.method_version = ?
                              AND s.confidence >= 1)
        """,
        (names.SPLIT_VERSION,),
    ).fetchall()
    now = utcnow()
    for filing_pk, cell, capture_id in rows:
        live = con.execute(
            "SELECT span_id, raw_text, ordinal, span_start, span_end, role, confidence"
            " FROM filing_party_span WHERE filing_pk = ? AND superseded_by IS NULL"
            " ORDER BY ordinal",
            (filing_pk,),
        ).fetchall()
        cut = names.split_cell(cell, known)
        same = [(r[1], r[2], r[3], r[4], r[5], r[6]) for r in live] == [
            (cell, i, s.start, s.end, s.role, s.confidence) for i, s in enumerate(cut)
        ]
        if same and live:
            stats["unchanged"] += 1
            continue
        # the live index allows one span per (filing, cell, ordinal): retire the old cut
        # first, pointing each row at itself until the new first span exists
        if live:
            con.executemany(
                "UPDATE filing_party_span SET superseded_by = span_id WHERE span_id = ?",
                [(r[0],) for r in live],
            )
        first_new = None
        for ordinal, span in enumerate(cut):
            cur = con.execute(
                "INSERT INTO filing_party_span (filing_pk, raw_text, ordinal, span_start,"
                " span_end, span_text, role, asserted_from_capture, source_location, method,"
                " method_version, asserted_at, confidence)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    filing_pk,
                    cell,
                    ordinal,
                    span.start,
                    span.end,
                    span.text,
                    span.role,
                    capture_id,
                    json.dumps({"cell": "filed_for", "start": span.start, "end": span.end}),
                    names.SPLIT_METHOD,
                    names.SPLIT_VERSION,
                    now,
                    span.confidence,
                ),
            )
            first_new = first_new or cur.lastrowid
            stats["spans"] += 1
        if live and first_new:
            con.executemany(
                "UPDATE filing_party_span SET superseded_by = ? WHERE span_id = ?",
                [(first_new, r[0]) for r in live],
            )
            stats["superseded"] += len(live)
        stats["filings"] += 1
    con.commit()
    log(f"split: {stats}")
    return stats


def known_norms(con: Connection) -> set[str]:
    return {
        r[0] for r in con.execute("SELECT norm_name FROM party_name WHERE superseded_by IS NULL")
    }


# --- resolve -------------------------------------------------------------------------------


def resolve_pending(con: Connection, log=print) -> dict:
    """Link every live span that has no live link. Exact match on the normalised name;
    ambiguous → no link; unmatched full-confidence filed_for span → a new party."""
    stats = {"linked": 0, "minted": 0, "ambiguous": 0, "left": 0}
    comps = Components(con)
    rows = con.execute(
        """
        SELECT s.span_id, s.span_text, s.role, s.confidence, s.asserted_from_capture
          FROM filing_party_span s
         WHERE s.superseded_by IS NULL
           AND NOT EXISTS (SELECT 1 FROM filing_party_link l
                            WHERE l.span_id = s.span_id AND l.superseded_by IS NULL)
         ORDER BY s.span_id
        """
    ).fetchall()
    now = utcnow()
    for span_id, text, role, conf, capture_id in rows:
        legal, trade = names.trade_name(text)
        norm = names.normalise(legal)
        candidates = {
            comps.rep(r[0])
            for r in con.execute(
                "SELECT DISTINCT party_id FROM party_name WHERE norm_name = ?"
                " AND superseded_by IS NULL",
                (norm,),
            )
        }
        if len(candidates) > 1:
            stats["ambiguous"] += 1
            continue
        if candidates:
            party_id = candidates.pop()
        elif role == "filed_for" and conf >= 1.0 and norm:
            party_id, created = mint(con, legal, norm, capture_id, span_id, now)
            if trade:
                add_name(con, party_id, trade, "trade", capture_id, span_id, now)
            stats["minted"] += int(created)
        else:
            stats["left"] += 1
            continue
        con.execute(
            "INSERT INTO filing_party_link (span_id, party_id, asserted_from_capture,"
            " source_location, method, method_version, asserted_at, confidence)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1.0)",
            (
                span_id,
                party_id,
                capture_id,
                json.dumps({"span_id": span_id}),
                names.NORM_METHOD,
                names.NORM_VERSION,
                now,
            ),
        )
        stats["linked"] += 1
    con.commit()
    log(f"resolve: {stats}")
    return stats


def mint(con: Connection, raw: str, norm: str, capture_id, span_id, now: str) -> tuple[int, bool]:
    existing = con.execute("SELECT party_id FROM party WHERE founding_key = ?", (norm,)).fetchone()
    if existing:
        return existing[0], False
    party_id = con.execute(
        "INSERT INTO party (founding_key, created_at) VALUES (?, ?)", (norm, now)
    ).lastrowid
    assert party_id is not None
    add_name(con, party_id, raw, "as_filed", capture_id, span_id, now)
    return party_id, True


def add_name(
    con, party_id, raw, kind, capture_id, span_id, now, method=None, version=None, location=None
) -> bool:
    """One live name per (party, norm, kind); a CHECK or FK failure raises, never ignored."""
    norm = names.normalise(raw)
    if con.execute(
        "SELECT 1 FROM party_name WHERE party_id = ? AND norm_name = ? AND name_kind = ?"
        " AND superseded_by IS NULL",
        (party_id, norm, kind),
    ).fetchone():
        return False
    con.execute(
        "INSERT INTO party_name (party_id, raw_name, norm_name, name_kind,"
        " asserted_from_capture, source_location, method, method_version, asserted_at,"
        " confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0)",
        (
            party_id,
            raw.strip(),
            norm,
            kind,
            capture_id,
            json.dumps(location or ({"span_id": span_id} if span_id else {})),
            method or names.NORM_METHOD,
            version or names.NORM_VERSION,
            now,
        ),
    )
    return True


# --- the seed ------------------------------------------------------------------------------


def load_seed(con: Connection, log=print) -> dict:
    """The operator's seed (parties/seed.py): parties, names and relationships with method
    'human' and this file as the source. Idempotent. A seed party whose name is already a
    cell-minted party's founding name is joined to it by a same_as edge, so the seed never
    creates a second component for an entity the record already holds."""
    from docketyard.parties import seed

    now = utcnow()
    stats = {"parties": 0, "names": 0, "relationships": 0, "joined": 0}
    ids: dict[str, int] = {}
    for row_no, (legal, others, note) in enumerate(seed.PARTIES):
        norm = names.normalise(legal)
        loc = {"file": "parties/seed.py", "row": row_no, "note": note}
        row = con.execute("SELECT party_id FROM party WHERE founding_key = ?", (norm,)).fetchone()
        if row:
            party_id = row[0]
        else:
            party_id = con.execute(
                "INSERT INTO party (founding_key, created_at) VALUES (?, ?)", (norm, now)
            ).lastrowid
            stats["parties"] += 1
        assert party_id is not None
        ids[legal] = party_id
        for kind, name in [("legal", legal), *others]:
            # a cell already minted a party from this exact name: one entity, joined
            other = con.execute(
                "SELECT party_id FROM party WHERE founding_key = ? AND party_id <> ?",
                (names.normalise(name), party_id),
            ).fetchone()
            if other and _join(con, party_id, other[0], now, loc):
                stats["joined"] += 1
            stats["names"] += int(
                add_name(
                    con,
                    party_id,
                    name,
                    kind,
                    None,
                    None,
                    now,
                    method="human",
                    version=seed.SEED_VERSION,
                    location=loc,
                )
            )
    for row_no, (src, rel, dst, when, note) in enumerate(seed.RELATIONSHIPS):
        cur = con.execute(
            "INSERT OR IGNORE INTO party_relationship (from_party, to_party, rel_type,"
            " effective_date, source_location, method, method_version, asserted_at, confidence)"
            " VALUES (?, ?, ?, ?, ?, 'human', ?, ?, 1.0)",
            (
                ids[src],
                ids[dst],
                rel,
                when,
                json.dumps({"file": "parties/seed.py", "row": row_no, "note": note}),
                seed.SEED_VERSION,
                now,
            ),
        )
        stats["relationships"] += cur.rowcount
    con.commit()
    log(f"seed: {stats}")
    return stats


def _join(con: Connection, a: int, b: int, now: str, loc: dict) -> bool:
    lo, hi = min(a, b), max(a, b)
    cur = con.execute(
        "INSERT OR IGNORE INTO party_relationship (from_party, to_party, rel_type,"
        " source_location, method, method_version, asserted_at, confidence)"
        " VALUES (?, ?, 'same_as', ?, 'human', ?, ?, 1.0)",
        (lo, hi, json.dumps(loc), "seed-join", now),
    )
    return cur.rowcount > 0


def run(con: Connection, log=print) -> dict:
    """Seed, split, resolve — what the poller and a wave call after ingest. A party minted
    by resolve can make an earlier doubtful cut cuttable, so split runs again until a
    round mints nothing; the passes are idempotent, so the extra rounds are cheap."""
    out = {"seed": load_seed(con, log), "split": split_pending(con, log)}
    out["resolve"] = resolve_pending(con, log)
    for _ in range(3):
        if not out["resolve"]["minted"]:
            break
        again = split_pending(con, log)
        if not again["spans"]:
            break
        for k, v in again.items():
            out["split"][k] += v
        more = resolve_pending(con, log)
        for k, v in more.items():
            out["resolve"][k] += v
    return out


# --- projections ---------------------------------------------------------------------------


def _filed_for_links(con: Connection, docket_ids: list[int]):
    """(filing_pk, stb_filing_id, party_id) for live filed_for links on current cells."""
    marks = ",".join("?" for _ in docket_ids)
    return con.execute(
        f"""
        SELECT f.filing_pk, f.stb_filing_id, l.party_id
          FROM filing f
          JOIN filing_party_span s ON s.filing_pk = f.filing_pk AND s.raw_text = f.filed_for_raw
               AND s.superseded_by IS NULL AND s.role = 'filed_for'
          JOIN filing_party_link l ON l.span_id = s.span_id AND l.superseded_by IS NULL
         WHERE f.docket_id IN ({marks})
        """,
        docket_ids,
    ).fetchall()


def parties_in(con: Connection, docket_ids: list[int]) -> list[dict]:
    """The Parties block: each component on record in the family, its display name, how
    many distinct records named it (a record entered in two family dockets counts once,
    as the sheet folds it), and whether it is the agency."""
    from docketyard.parties import seed

    comps = Components(con)
    records: dict[int, set[str]] = {}
    for _, stb_id, party_id in _filed_for_links(con, docket_ids):
        records.setdefault(comps.rep(party_id), set()).add(stb_id)
    agency = names.normalise(seed.AGENCY)
    out = [
        {
            "party_id": rep,
            "name": comps.display_name(rep),
            "filings": len(ids),
            "agency": comps.has_name(rep, agency),
        }
        for rep, ids in records.items()
    ]
    out.sort(key=lambda p: (-p["filings"], p["name"]))
    return out


def components_of_filings(con: Connection, docket_ids: list[int]) -> dict[int, list[int]]:
    """filing_pk → component representatives it was filed for (the sheet's filter)."""
    comps = Components(con)
    out: dict[int, list[int]] = {}
    for filing_pk, _, party_id in _filed_for_links(con, docket_ids):
        rep = comps.rep(party_id)
        if rep not in out.setdefault(filing_pk, []):
            out[filing_pk].append(rep)
    return out


SEARCH_LIMIT = 50


def search(con: Connection, text: str) -> tuple[list[dict], bool]:
    """The browse view: components whose any live name contains the text, with the dockets
    they appear in. Returns (results, truncated). A convenience, not an address."""
    norm = names.normalise(text).replace("_", " ").strip()
    if not norm:
        return [], False
    comps = Components(con)
    reps = sorted(
        {
            comps.rep(r[0])
            for r in con.execute(
                "SELECT DISTINCT party_id FROM party_name WHERE superseded_by IS NULL"
                " AND norm_name LIKE ? ESCAPE '\\'",
                (f"%{norm.replace('%', '')}%",),
            )
        }
    )
    truncated = len(reps) > SEARCH_LIMIT
    out = []
    for rep in reps[:SEARCH_LIMIT]:
        members = comps.members(rep)
        marks = ",".join("?" for _ in members)
        dockets = con.execute(
            f"""
            SELECT d.docket_id, d.raw_docket, COUNT(DISTINCT f.stb_filing_id)
              FROM filing_party_link l
              JOIN filing_party_span s ON s.span_id = l.span_id AND s.superseded_by IS NULL
                   AND s.role = 'filed_for'
              JOIN filing f ON f.filing_pk = s.filing_pk AND f.filed_for_raw = s.raw_text
              JOIN docket d ON d.docket_id = COALESCE(
                   (SELECT parent_docket_id FROM docket WHERE docket_id = f.docket_id), f.docket_id)
             WHERE l.superseded_by IS NULL AND l.party_id IN ({marks})
             GROUP BY d.docket_id ORDER BY 3 DESC, d.raw_docket
            """,
            members,
        ).fetchall()
        aliases = con.execute(
            f"SELECT raw_name, name_kind, method, method_version FROM party_name"
            f" WHERE party_id IN ({marks}) AND superseded_by IS NULL ORDER BY name_id",
            members,
        ).fetchall()
        out.append(
            {
                "party_id": rep,
                "name": comps.display_name(rep),
                "dockets": dockets,
                "aliases": aliases,
                "members": len(members),
            }
        )
    return out, truncated
