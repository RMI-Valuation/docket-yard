"""Search built out (docs/search-v2.md): results grouped by proceeding, filtered, sorted and
paged. `/search` reads this; `/suggest` and MCP keep `search.search()` and its kinds.

A result is a PROCEEDING by the sheet rule (`search.proceedings`). Records reach proceedings
through their placements (`search_place`), and pages through the records that carry their
document (`search_document`), so one rule places both. Everything read here is derived; every
hit is an address whose own page carries the record and its provenance, and a page hit keeps
who read it, the band and the scan (ADR 0021 D7).

`web` is ONE uvicorn worker, so the page side is bounded and says when it was: unfiltered, it
ranks the best `PAGE_WINDOW` pages; filtered, it matches every page under `PAGE_BUDGET`
seconds and, past that, answers from records alone and says the words were too broad."""

import json
import time
from dataclasses import dataclass, field
from sqlite3 import Connection, OperationalError

from docketyard.store import pages, search
from docketyard.store.search import MARK_CLOSE, MARK_OPEN, SNIPPET_TOKENS, Hit

PAGE_SIZE = 20  # proceedings a results page shows
DOCUMENT_PAGE_SIZE = 50  # items the flat list of documents shows
EVIDENCE = 3  # matched items shown under a proceeding
WITHIN_EVIDENCE = 200  # shown when the search is within one proceeding
PAGE_WINDOW = 5000  # ranked pages examined when nothing is filtered (docs/search-v2.md)
PAGE_BUDGET = 1.5  # seconds the page side may take when a filter must see every page
# Below this many matching pages the filter is applied to the matches; above it, the pages
# the filter admits are gathered first and the matches intersected with them (measured on the
# 2026-09-17 restore: `the` over AB since 2020, 2.1 s joined, 0.3 s intersected).
DIRECT_MATCHES = 20_000
PARTY_STRIP = 5
PROGRESS_STEPS = 10_000  # SQLite VM steps between looks at the clock

KINDS = ("captions", "decisions", "filings", "comments", "text", "parties")
# what each kind is called on the page, in the order the filter offers them
KIND_LABELS = {
    "captions": "Docket captions and numbers",
    "decisions": "Decisions",
    "filings": "Filings",
    "comments": "Environmental comments",
    "text": "Text of documents",
    "parties": "Parties",
}
_KIND = {
    "docket": "captions",
    "decision": "decisions",
    "filing": "filings",
    "comment": "comments",
    "party": "parties",
}
# the strength of a match, for best-match order: a proceeding's own caption or number, then a
# record entered in it, then only the text of a page
_TIER = {"docket": 0, "decision": 1, "filing": 1, "comment": 1, "page": 2}
_SHOWN_ORDER = {"docket": 0, "decision": 1, "filing": 2, "comment": 3, "page": 4}


@dataclass(frozen=True)
class Vocabulary:
    """What a filter may name: the values the index holds, never typed freehand."""

    prefixes: tuple[str, ...]
    filing_types: tuple[str, ...]
    decision_types: tuple[str, ...]


def vocabulary(con: Connection) -> Vocabulary:
    """Read from the placements' indexes, so it costs a walk of an index, not of a table."""
    rows = con.execute("SELECT DISTINCT prefix FROM search_place ORDER BY 1")
    prefixes = tuple(r[0] for r in rows)
    types = con.execute(
        "SELECT DISTINCT type_kind, type FROM search_place WHERE type IS NOT NULL ORDER BY 1, 2"
    ).fetchall()
    return Vocabulary(
        prefixes,
        tuple(t for k, t in types if k == "filing"),
        tuple(t for k, t in types if k == "decision"),
    )


@dataclass(frozen=True)
class Query:
    text: str = ""
    prefixes: tuple[str, ...] = ()
    date_from: str = ""
    date_to: str = ""
    kinds: tuple[str, ...] = KINDS
    ftypes: tuple[str, ...] = ()
    dtypes: tuple[str, ...] = ()
    sort: str = "best"  # or "newest"
    page: int = 1
    within: int | None = None  # one proceeding: "N more matches in this proceeding"
    view: str = "proceedings"  # or "documents": the flat list (the operator's decision 1)

    @property
    def dated(self) -> bool:
        return bool(self.date_from or self.date_to)

    @property
    def filtered(self) -> bool:
        """A filter a placement must pass. `within` narrows too, but is not one a party or a
        caption fails."""
        return bool(self.prefixes or self.dated or self.ftypes or self.dtypes)


@dataclass
class _Item:
    kind: str
    key: int  # doc_id for a record, text_id for a page
    score: float  # bm25 for a record, rank position for a ranked page; lower is stronger
    date: str | None
    doc_id: int  # the record; for a page, the record carrying its document


@dataclass
class Proceeding:
    docket_id: int
    path: str  # "" when the docket number does not parse
    number: str
    caption: str
    fact: str
    hits: list[Hit]
    matched: int  # items matched in this proceeding
    pages: int  # of which pages of text
    by_caption: bool = False  # its own caption or number matched

    @property
    def more(self) -> int:
        """Matches not shown under it: the caption is shown as the heading."""
        return self.matched - len(self.hits) - (1 if self.by_caption else 0)


@dataclass
class Results:
    query: Query
    proceedings: list[Proceeding] = field(default_factory=list)
    parties: list[Hit] = field(default_factory=list)
    total: int = 0
    # "" | "window": the best PAGE_WINDOW pages of more were examined | "budget": the page
    # side ran out of time and was left out | "rebuilding": the page index is being rebuilt
    pages_cut: str = ""
    pages_matched: int | None = None  # pages the words matched, when counted
    documents: list[Hit] = field(default_factory=list)  # the flat view's page of items

    @property
    def exact(self) -> bool:
        return not self.pages_cut

    @property
    def page_count(self) -> int:
        size = DOCUMENT_PAGE_SIZE if self.query.view == "documents" else PAGE_SIZE
        return max(1, -(-self.total // size))


def find(con: Connection, q: Query) -> Results:
    out = Results(q)
    match = search._match(q.text, prefix=False) if q.text.strip() else None
    if q.text.strip() and match is None:
        return out
    if match is None and not q.filtered:
        return out  # nothing typed and nothing filtered is not a search
    groups: dict[int, list[_Item]] = {}

    def add(group: int, item: _Item) -> None:
        groups.setdefault(group, []).append(item)

    for group, item in _records(con, q, match):
        add(group, item)
    if match is not None and "text" in q.kinds:
        for group, item in _pages(con, q, match, out):
            add(group, item)
    if (
        match is not None
        and "parties" in q.kinds
        and not q.filtered
        and q.within is None
        and q.page == 1
    ):
        out.parties = search.search(con, q.text, limit=PARTY_STRIP, kinds=("party",))
    if q.view == "documents":
        return _documents(con, q, match, groups, out)
    order = _order(con, q, groups)
    out.total = len(order)
    start = (max(1, q.page) - 1) * PAGE_SIZE
    shown = order[start : start + PAGE_SIZE]
    out.proceedings = [_proceeding(con, q, match, gid, groups[gid]) for gid in shown]
    return out


# --- records --------------------------------------------------------------------------------


def _filters(q: Query, alias: str = "p") -> tuple[str, list]:
    """The placement filter as SQL. Every column is prefixed `+` so SQLite reaches placements
    by `doc_id` and never through the prefix/date index: probed per record through that index
    a filter took 2.6 s where it takes 7 ms (measured, 2026-09-17)."""
    where, args = [], []
    if q.prefixes:
        where.append(f"+{alias}.prefix IN ({','.join('?' for _ in q.prefixes)})")
        args += q.prefixes
    if q.date_from:
        where.append(f"+{alias}.date >= ?")
        args.append(q.date_from)
    if q.date_to:
        where.append(f"+{alias}.date <= ?")
        args.append(q.date_to)
    typed = []
    if q.ftypes:
        typed.append(
            f"(+{alias}.type_kind = 'filing' AND +{alias}.type IN"
            f" ({','.join('?' for _ in q.ftypes)}))"
        )
        args += q.ftypes
    if q.dtypes:
        typed.append(
            f"(+{alias}.type_kind = 'decision' AND +{alias}.type IN"
            f" ({','.join('?' for _ in q.dtypes)}))"
        )
        args += q.dtypes
    if typed:
        where.append("(" + " OR ".join(typed) + ")")
    if q.within is not None:
        where.append(f"+{alias}.group_docket_id = ?")
        args.append(q.within)
    return (" AND ".join(where) or "1"), args


def _record_kinds(q: Query) -> list[str]:
    return [kind for kind, name in _KIND.items() if name in q.kinds and kind != "party"]


def _records(con: Connection, q: Query, match: str | None):
    kinds = _record_kinds(q)
    if not kinds:
        return
    where, args = _filters(q)
    marks = ",".join("?" for _ in kinds)
    if match is not None:
        rows = con.execute(
            f"""
            WITH m AS MATERIALIZED (
              SELECT rowid AS doc_id, bm25(search_fts, 8.0, 1.0) AS score
                FROM search_fts WHERE search_fts MATCH ?)
            SELECT d.kind, m.doc_id, m.score, p.group_docket_id, p.date
              FROM m CROSS JOIN search_doc d ON d.doc_id = m.doc_id
                     CROSS JOIN search_place p ON p.doc_id = m.doc_id
             WHERE d.kind IN ({marks}) AND {where}
            """,
            (match, *kinds, *args),
        )
    else:
        # a browse: filters and no words, records only (nothing to rank a page by)
        rows = con.execute(
            f"""
            SELECT d.kind, p.doc_id, 0.0, p.group_docket_id, p.date
              FROM search_place p CROSS JOIN search_doc d ON d.doc_id = p.doc_id
             WHERE d.kind IN ({marks}) AND {where.replace("+p.", "p.")}
            """,
            (*kinds, *args),
        )
    for kind, doc_id, score, group, date in rows:
        yield group, _Item(kind, doc_id, score, date, doc_id)


# --- pages ----------------------------------------------------------------------------------


def _pages(con: Connection, q: Query, match: str, out: Results):
    if search.page_built(con)[0] == search.PAGE_REBUILDING:
        out.pages_cut = "rebuilding"
        return []
    deadline = time.perf_counter() + PAGE_BUDGET

    def over() -> int:
        return 1 if time.perf_counter() > deadline else 0

    con.set_progress_handler(over, PROGRESS_STEPS)
    try:
        return _pages_bounded(con, q, match, out)
    except OperationalError as e:
        if "interrupted" not in str(e):
            raise
        out.pages_cut = "budget"
        return []
    finally:
        con.set_progress_handler(None, 0)


_OWNERS = """
    SELECT b.ord, b.text_id, m.doc_id, p.group_docket_id, p.date
      FROM b CROSS JOIN document_text t ON t.text_id = b.text_id
             CROSS JOIN search_document m ON m.document_sha256 = t.document_sha256
             CROSS JOIN search_place p ON p.doc_id = m.doc_id
     WHERE {where}
"""


def _pages_bounded(con: Connection, q: Query, match: str, out: Results):
    where, args = _filters(q)
    if not q.filtered:
        ids = [
            r[0]
            for r in con.execute(
                "SELECT rowid FROM page_fts WHERE page_fts MATCH ? ORDER BY rank LIMIT ?",
                (match, PAGE_WINDOW + 1),
            )
        ]
        if len(ids) > PAGE_WINDOW:
            out.pages_cut = "window"
            ids = ids[:PAGE_WINDOW]
        return _owned(con, ids, where, args, ranked=True)
    ids = [r[0] for r in con.execute("SELECT rowid FROM page_fts WHERE page_fts MATCH ?", (match,))]
    out.pages_matched = len(ids)
    if len(ids) <= DIRECT_MATCHES:
        return _owned(con, ids, where, args, ranked=False)
    # many matches: gather the pages the filter admits, and intersect
    admitted: dict[int, list[tuple[int, int, str | None]]] = {}
    for text_id, doc_id, group, date in con.execute(
        f"""
        WITH d AS MATERIALIZED (SELECT p.doc_id, p.group_docket_id, p.date
                                  FROM search_place p WHERE {where.replace("+p.", "p.")})
        SELECT t.text_id, d.doc_id, d.group_docket_id, d.date
          FROM d CROSS JOIN search_document m ON m.doc_id = d.doc_id
                 CROSS JOIN document_text t ON t.document_sha256 = m.document_sha256
                                           AND t.superseded_by IS NULL
        """,
        args,
    ):
        admitted.setdefault(text_id, []).append((doc_id, group, date))
    found = []
    for text_id in ids:
        for doc_id, group, date in admitted.get(text_id, ()):
            found.append((group, _Item("page", text_id, 0.0, date, doc_id)))
    return _dedupe(found)


def _owned(con: Connection, ids: list[int], where: str, args: list, *, ranked: bool):
    if not ids:
        return []
    rows = con.execute(
        "WITH b AS MATERIALIZED (SELECT CAST(key AS INTEGER) AS ord, value AS text_id"
        " FROM json_each(?))" + _OWNERS.format(where=where),
        (json.dumps(ids), *args),
    )
    return _dedupe(
        (group, _Item("page", text_id, float(ord_) if ranked else 0.0, date, doc_id))
        for ord_, text_id, doc_id, group, date in rows
    )


def _dedupe(items):
    """One page counts once in a proceeding, however many of its records carry the document
    there (a docket and its folded sub-docket are two attachment rows in one group)."""
    seen: set[tuple[int, int]] = set()
    out = []
    for group, item in items:
        if (group, item.key) not in seen:
            seen.add((group, item.key))
            out.append((group, item))
    return out


# --- order ----------------------------------------------------------------------------------


def _order(con: Connection, q: Query, groups: dict[int, list[_Item]]) -> list[int]:
    for items in groups.values():
        # a record matched through two placements in one proceeding is one item
        seen: set[tuple[str, int]] = set()
        items[:] = [i for i in items if not ((i.kind, i.key) in seen or seen.add((i.kind, i.key)))]
    if q.sort == "newest" or not q.text.strip():  # a browse matched nothing to rank
        latest = {
            gid: max((i.date for i in items if i.date), default=None)
            for gid, items in groups.items()
        }
        undated = [gid for gid, d in latest.items() if d is None]
        latest.update(_last_activity(con, undated))
        dated = sorted(
            (gid for gid in groups if latest.get(gid)), key=lambda g: latest[g], reverse=True
        )
        return dated + sorted(gid for gid in groups if not latest.get(gid))

    def strength(gid: int):
        items = groups[gid]
        tier = min(_TIER[i.kind] for i in items)
        best = min(i.score for i in items if _TIER[i.kind] == tier)
        if tier == 2 and best == 0.0:  # unranked pages (a filter saw every page): by count
            best = -sum(1 for i in items if i.kind == "page")
        return (tier, best, gid)

    return sorted(groups, key=strength)


def _last_activity(con: Connection, gids: list[int]) -> dict[int, str]:
    """A proceeding matched only by its caption sorts by its last dated entry under Newest."""
    if not gids:
        return {}
    rows = con.execute(
        "SELECT group_docket_id, MAX(date) FROM search_place"
        " WHERE group_docket_id IN (SELECT value FROM json_each(?)) GROUP BY 1",
        (json.dumps(gids),),
    )
    return {gid: date for gid, date in rows if date}


# --- what a result shows --------------------------------------------------------------------


def _documents(con, q: Query, match: str | None, groups: dict[int, list[_Item]], out: Results):
    """The flat list: every matched filing, decision, comment and page once, however many
    proceedings it was placed in, ordered as proceedings are — by strength of match, or
    newest first."""
    seen: dict[tuple[str, int], _Item] = {}
    for items in groups.values():
        for item in items:
            if item.kind != "docket":
                seen.setdefault((item.kind, item.key), item)
    if q.sort == "newest" or not q.text.strip():
        order = sorted(seen.values(), key=lambda i: (i.date or "", -i.score), reverse=True)
    else:
        order = sorted(seen.values(), key=lambda i: (_TIER[i.kind], i.score, i.key))
    out.total = len(order)
    start = (max(1, q.page) - 1) * DOCUMENT_PAGE_SIZE
    shown = order[start : start + DOCUMENT_PAGE_SIZE]
    hits = _record_hits(con, match, [i for i in shown if i.kind != "page"])
    hits.update(_page_hits(con, match, [i for i in shown if i.kind == "page"]))
    out.documents = [hits[(i.kind, i.key)] for i in shown if (i.kind, i.key) in hits]
    return out


def _proceeding(con: Connection, q: Query, match: str | None, gid: int, items: list[_Item]):
    head = con.execute(
        "SELECT path, title, caption, fact FROM search_doc WHERE kind = 'docket' AND ref = ?",
        (gid,),
    ).fetchone()
    if head:
        path, number, caption, fact = head
    else:  # an unparseable docket is a proceeding without an address
        (raw,) = con.execute("SELECT raw_docket FROM docket WHERE docket_id = ?", (gid,)).fetchone()
        path, number, caption, fact = "", raw, "", ""
    ranked = sorted(items, key=lambda i: (_SHOWN_ORDER[i.kind], i.score, -(len(i.date or ""))))
    if q.sort == "newest" or not q.text.strip():
        ranked = sorted(items, key=lambda i: i.date or "", reverse=True)
    limit = WITHIN_EVIDENCE if q.within is not None else EVIDENCE
    chosen = [i for i in ranked if i.kind != "docket"][:limit]
    hits = _record_hits(con, match, [i for i in chosen if i.kind != "page"])
    hits.update(_page_hits(con, match, [i for i in chosen if i.kind == "page"]))
    return Proceeding(
        gid,
        path,
        number,
        caption,
        fact,
        [hits[(i.kind, i.key)] for i in chosen if (i.kind, i.key) in hits],
        matched=len(items),
        pages=sum(1 for i in items if i.kind == "page"),
        by_caption=any(i.kind == "docket" for i in items),
    )


def _record_hits(con: Connection, match: str | None, items: list[_Item]) -> dict:
    if not items:
        return {}
    ids = [i.key for i in items]
    marks = ",".join("?" for _ in ids)
    rows = con.execute(
        "SELECT doc_id, kind, path, title, fact, caption FROM search_doc"
        f" WHERE doc_id IN ({marks})",
        ids,
    ).fetchall()
    snippets: dict[int, str] = {}
    if match is not None:
        for doc_id in ids:  # one FTS lookup per shown row, never over every match
            row = con.execute(
                "SELECT snippet(search_fts, 1, ?, ?, '…', ?) FROM search_fts"
                " WHERE search_fts MATCH ? AND rowid = ?",
                (MARK_OPEN, MARK_CLOSE, SNIPPET_TOKENS, match, doc_id),
            ).fetchone()
            snippets[doc_id] = row[0] if row else ""
    return {
        (kind, doc_id): Hit(
            kind,
            path,
            title,
            fact,
            caption,
            search._shown_snippet(snippets.get(doc_id, ""), caption),
        )
        for doc_id, kind, path, title, fact, caption in rows
    }


def _page_hits(con: Connection, match: str | None, items: list[_Item]) -> dict:
    """A page under a proceeding links the record that places it THERE (search-v2), with who
    read it, the band and the scan (ADR 0021 D7)."""
    if not items or match is None:
        return {}
    found = pages.by_text_ids(con, [i.key for i in items])
    out = {}
    for item in items:
        if item.key not in found:
            continue  # the view no longer shows it: a stale index row, never a 500
        sha, page = found[item.key]
        kind, ref, path, title, fact = con.execute(
            "SELECT kind, ref, path, title, fact FROM search_doc WHERE doc_id = ?", (item.doc_id,)
        ).fetchone()
        record_id = path.rsplit("/", 1)[1]
        index = _attachment_index(con, kind, ref, sha)
        base = path + "/text" + (f"?file={index}" if index else "")
        excerpt = con.execute(
            "SELECT snippet(page_fts, 0, ?, ?, '…', ?) FROM page_fts"
            " WHERE rowid = ? AND page_fts MATCH ?",
            (MARK_OPEN, MARK_CLOSE, SNIPPET_TOKENS, item.key, match),
        ).fetchone()
        excerpt = excerpt[0] if excerpt else ""
        if MARK_OPEN in page.text or MARK_CLOSE in page.text:
            excerpt = ""  # a marker the record put there is never shown as ours
        out[("page", item.key)] = Hit(
            "page",
            f"{base}#p{page.page_no}",
            f"{title}, page {page.page_no}",
            fact,  # the record's docket and date: the flat list's only context
            "",
            search._shown_snippet(excerpt, ""),
            label=pages.label(page),
            band=pages.band(page),
            scan=search._scan(con, kind, record_id, index, sha),
            record=path,
            record_name=title,
        )
    return out


_ATTACHMENT = {
    "filing": ("filing_attachment", "filing_pk"),
    "decision": ("decision_attachment", "decision_pk"),
    "comment": ("enviro_comment_attachment", "comment_pk"),
}


def _attachment_index(con: Connection, kind: str, ref: int, sha: str) -> int:
    """The file's position among the record's files, ordered as the sheet orders them (by
    source URL), so `?file=N` names the same file on the text page and the record page."""
    table, fk = _ATTACHMENT[kind]
    row = con.execute(
        f"SELECT (SELECT COUNT(*) FROM {table} b WHERE b.{fk} = a.{fk}"
        f" AND b.source_url < a.source_url) FROM {table} a"
        f" WHERE a.{fk} = ? AND a.document_sha256 = ? ORDER BY a.source_url LIMIT 1",
        (ref, sha),
    ).fetchone()
    return row[0] if row else 0
