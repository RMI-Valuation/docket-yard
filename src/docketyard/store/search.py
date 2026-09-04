"""One search box (docs/search.md): a docket number is never a search; everything else is an
FTS5 query over captions, party names, decision summaries and the words of environmental
comments, rebuilt by ingest — and, by its own query path, over the pages of documents.

TWO INDEXES, TWO WRITERS. The record index (`search_fts`): `rebuild` is its only writer; it
derives every row first, on reads, then replaces the index in one short write transaction,
and does nothing when the record signature has not moved. The page index (`page_fts`,
migration 0018) is kept in step row by row by the loader through `store.page_index`, has
its own signature and build row, and is rebuilt whole only by `rebuild_pages`; `search_pages`
reads it and is never joined to `search()`. Neither index asserts anything — every hit is an
address whose own page carries the record and its provenance, and a page hit carries the
label, the band and the scan (ADR 0021 D7). Nothing about the reader or the query is stored.
"""

import re
from collections import Counter
from dataclasses import dataclass
from sqlite3 import Connection

from docketyard.ingest.dockets import find_docket, parse_docket_id
from docketyard.parties import resolve
from docketyard.store import batches, display, pages
from docketyard.store.db import utcnow
from docketyard.web import urls

LIMIT = 50  # results on /search
SUGGEST = 8  # rows /suggest answers
MAX_QUERY = 200  # characters a query is cut to before anything looks at it
MIN_PREFIX = 2  # characters before a prefix query is asked (mirrors the page's script)
_TOKEN = re.compile(r"[^\W_]+")


# The snippet's markers. NOT "<mark>": `body` holds text the Board printed and words a
# commenter wrote, and handing HTML straight to a template would make every environmental
# comment in the record an injection vector. The web tier escapes the whole string and then
# turns these two control characters into the tags — so the only markup that can survive is
# markup this module put there.
MARK_OPEN, MARK_CLOSE = chr(2), chr(3)
SNIPPET_TOKENS = 18  # words of context FTS5 windows around the match

# What separates one field from the next inside `body`. A snippet windows 18 tokens across
# the whole concatenation and the page renders the result `as-printed` — this project's
# styling for the Board's own words — so a plain space let one window fuse a docket's
# number spellings onto its caption, two different sub-dockets' captions, or a commenter's
# location onto their words, and print the run as though the Board had written it
# (schema-critic, 2026-08-31). `unicode61` treats the middle dot as a separator and
# discards it, so the token stream, the positions, the ranking and phrase queries are all
# exactly what they were; only the seam becomes visible.
FIELD = " · "


@dataclass(frozen=True)
class Hit:
    kind: str
    path: str
    title: str
    fact: str
    caption: str = ""  # the row's own printed name, where its title is only an identifier
    snippet: str = ""  # why it matched, marked with MARK_OPEN/MARK_CLOSE; may be empty
    # A PAGE hit carries the three things ADR 0021 D7 requires before machine-read text may
    # reach a reader through search: who read it, the band's operand or its absence, and the
    # scan one click away. A record hit leaves them empty; a consumer that prints a page hit
    # without them has turned display into assertion, which is what the three are for.
    label: str = ""  # who read the page, how, and at what render
    band: str = ""  # the distance from the second reading, or why there is none
    scan: str = ""  # the record's file, framed, where the page can be checked


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
            yield "skipped", docket_id, "", "", "", "", ""
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
            # the caption travels as its own field as well as in the body: the body is
            # what FINDS the row, the caption is what the row is CALLED, and a results
            # page that prints only the identifier is the whole of navigation-review § B
            yield (
                "docket",
                docket_id,
                urls.docket_path(ident),
                printed,
                caption,
                f"in {head}",
                caption,
            )
    for docket_id, (ident, caption) in parents.items():
        printed = urls.printed_docket(ident)
        n, last = counts.get(docket_id, (0, None))
        # the spellings go LAST: they are how a number is FOUND, and a snippet centred on
        # a caption match should open on the caption, not on four renderings of the number
        spellings = f"{printed} {ident.prefix}{ident.sequence}"
        body = FIELD.join([p for p in [caption, *subs.get(docket_id, []), spellings] if p])
        fact = f"{n} filings" + (f", last {last}" if last else "")
        yield "docket", docket_id, urls.docket_path(ident), printed, body, fact, caption


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
        # a party's title is already a name, which is why it is the one kind that reads
        yield (
            "party",
            rep,
            urls.party_path(rep),
            comps.display_name(rep),
            FIELD.join(held),  # one name per field: a snippet must not fuse two of them
            fact,
            "",
        )


def _decision_docs(con: Connection):
    """Decisions with a printed summary: one row per decision id (a decision entered in a
    docket and its sub-docket is one page), headlined by the docket nearest the parent."""
    for pk, sid, raw, date, summary in con.execute(
        """
        SELECT decision_pk, stb_decision_id, raw_docket, service_date, summary
          FROM (SELECT r.decision_pk, r.stb_decision_id, d.raw_docket, r.service_date,
                       json_extract(e.payload, '$.summary') AS summary,
                       ROW_NUMBER() OVER (PARTITION BY r.stb_decision_id
                                          ORDER BY COALESCE(d.sub_sequence, -1),
                                                   COALESCE(d.suffix, ''),
                                                   r.decision_pk) AS nearest
                  FROM decision_record r
                  JOIN docket d ON d.docket_id = r.docket_id
                  JOIN event e ON e.event_id = r.observed_in_event
                 WHERE TRIM(COALESCE(json_extract(e.payload, '$.summary'), '')) <> '')
         WHERE nearest = 1
        """
    ):
        ident = parse_docket_id(raw)
        printed = urls.printed_docket(ident) if ident else raw
        fact = printed + (f", served {date}" if date else "")
        body = FIELD.join([summary, f"{sid} {printed}"])
        yield "decision", pk, urls.decision_path(sid), f"Decision {sid}", body, fact, ""


# what the Board prints for a cell it has nothing for: never a search term
_PLACEHOLDERS = ("", "--", "---")


def _comment_docs(con: Connection):
    """Environmental comments: one row per comment number, headlined by the docket nearest
    the parent, exactly as a decision is.

    Every comment is indexed, not only those carrying words — half the rows print `--` for
    the text (measured), and their submitter, organisation and location are still terms
    nothing else in the index carries. The body holds the commenter's own words verbatim;
    the index asserts nothing about them, and the page it resolves to says so."""
    for pk, number, raw, date, submitter, org, location, text in con.execute(
        """
        SELECT comment_pk, comment_number, raw_docket, date_received_or_sent,
               submitter_raw, organisation_raw, location_raw, comment_text_printed
          FROM (SELECT c.comment_pk, c.comment_number, d.raw_docket,
                       c.date_received_or_sent, c.submitter_raw, c.organisation_raw,
                       c.location_raw, c.comment_text_printed,
                       -- partitioned by (number, row ref), NOT the number alone. The
                       -- row ref is what separates ONE comment entered in a docket and
                       -- its sub-docket (one ref, fold it) from TWO DIFFERENT comments
                       -- the Board gave the same number (two refs, index both) — measured
                       -- in the archive wave: 108 of the former, 2 of the latter
                       ROW_NUMBER() OVER (PARTITION BY c.comment_number, c.stb_row_ref
                                          ORDER BY COALESCE(d.sub_sequence, -1),
                                                   COALESCE(d.suffix, ''),
                                                   c.comment_pk) AS nearest
                  FROM enviro_comment c
                  JOIN docket d ON d.docket_id = c.docket_id)
         WHERE nearest = 1
        """
    ):
        ident = parse_docket_id(raw)
        printed = urls.printed_docket(ident) if ident else raw
        # "dated", never "received": the Board heads the column "Date Received or Sent" and
        # declines to say which, so the index declines too
        fact = printed + (f", dated {date}" if date else "")
        # the organisation cell repeats the submitter verbatim on the Board's own EO rows
        # (measured), and a term counted twice is a term bm25 over-weights
        cells = [submitter, org if org != submitter else None, location, text]
        words = [w for w in (*cells, number, printed) if (w or "").strip() not in _PLACEHOLDERS]
        # The title is the number AS PRINTED, with no noun in front of it. `EI` rows are
        # submitted comments and `EO` rows are the Board's own environmental documents
        # (measured, 8 of 50 on FD 36873), and migration 0011 declines to type the row
        # because the prefix is inside the number and typing it would be a derived claim.
        # An index is the last place to make one. The kind column beside the hit names the
        # Board's own table, which is a quotation; "Comment EO-3243" would not be.
        # addressed under its docket: the bare number is ambiguous for two of the 34,255
        # the record holds, so the index points at the address that never is
        path = urls.comment_path(ident, number) if ident else urls.comment_short_path(number)
        yield "comment", pk, path, number, FIELD.join(words), fact, ""


# Bumped whenever the index's SHAPE changes — a path scheme, a title, what is folded —
# not just when the record does. Without it `rebuild()` compares only row ids, sees no
# change on deploy, and serves the old paths until unrelated data happens to move. 2:
# comments addressed under their docket, folded by (number, row ref). 3: rows carry their
# own caption (migration 0013), which is what fills the new column on the first pass after
# the deploy — a bump here is the only thing that makes that happen.
INDEX_FORMAT = 3


_CONTROLS = {c: None for c in range(0x20) if c not in (0x09, 0x0A, 0x0D)}


def _plain(text: str) -> str:
    """Text with C0 control characters removed.

    Hygiene, and one invariant: the snippet's markers ARE control characters, and
    `escape()` passes them through, so a record that carried one would put a stray
    `<mark>` on the page. Nothing measured in this record contains one; this makes that a
    property of the index rather than an assumption about the Board."""
    return text.translate(_CONTROLS)


# THE PAGE-TEXT TABLES, whose corrections never touch the record index (docs/ocr-migration.md
# item 11). `signature()` and the web tier's ETag both read MAX(correction_id), so a human
# correction to one page's text — or to one page count — would force a full rebuild of the
# docket/party/decision index and invalidate every cached page site-wide. Excluded by NAME,
# as a set, because migration 0018 gave both tables a `review_target_vocab` row: excluding one
# would leave the other. `page_signature()` below is where they count.
PAGE_TABLES = ("document_text", "document_pagination")
# the predicates, with their placeholders derived from the set — bind PAGE_TABLES to either.
# `web/app.py`'s validators import these rather than spelling the marks out (bughunter, 2026-09-03)
NOT_PAGES = "target_table NOT IN (" + ",".join("?" for _ in PAGE_TABLES) + ")"
IN_PAGES = "target_table IN (" + ",".join("?" for _ in PAGE_TABLES) + ")"

# The page index's format: the display view IS the rule (migration 0018), so the view's
# version belongs here, and a change to what the view shows is a change to what search
# matched. Bump it when the view changes; nothing dates which version was in force on a day.
# the view's migration AND the display rule's own version (`store/display.py`): the index
# holds the view's bytes, so a change to either is a change to what it should hold
PAGE_INDEX_FORMAT = f"display@0020.{display.VERSION}"


def signature(con: Connection) -> str:
    """What the index depends on, as one string: the newest event, name, link, edge and
    correction, and how many names, links and edges have been retired (a re-split or a
    withdrawal supersedes rows without inserting any). Unchanged signature, unchanged
    index. A correction naming a page-text table is not a change to THIS index."""
    return f"{INDEX_FORMAT}." + ".".join(
        str(v or 0)
        for v in con.execute(
            "SELECT (SELECT MAX(event_id) FROM event), (SELECT MAX(name_id) FROM party_name),"
            " (SELECT MAX(link_id) FROM filing_party_link),"
            " (SELECT MAX(edge_id) FROM party_relationship),"
            f" (SELECT MAX(correction_id) FROM correction WHERE {NOT_PAGES}),"
            " (SELECT COUNT(*) FROM party_name WHERE superseded_by IS NOT NULL),"
            " (SELECT COUNT(*) FROM filing_party_link WHERE superseded_by IS NOT NULL),"
            " (SELECT COUNT(*) FROM filing_party_span WHERE superseded_by IS NOT NULL),"
            " (SELECT COUNT(*) FROM party_relationship WHERE superseded_by IS NOT NULL)",
            PAGE_TABLES,
        ).fetchone()
    )


def page_signature(con: Connection) -> str:
    """What the PAGE index depends on: the newest reading, how many readings have been
    retired (a supersession changes what the view shows without a newer id), and the
    newest correction naming a page-text table. Its own signature, because two indexes
    sharing one means either rebuilds the other (migration 0018)."""
    return f"{PAGE_INDEX_FORMAT}." + ".".join(
        str(v or 0)
        for v in con.execute(
            "SELECT (SELECT MAX(text_id) FROM document_text),"
            " (SELECT COUNT(*) FROM document_text WHERE superseded_by IS NOT NULL),"
            f" (SELECT MAX(correction_id) FROM correction WHERE {IN_PAGES})",
            PAGE_TABLES,
        ).fetchone()
    )


def page_built(con: Connection) -> tuple[str | None, int]:
    """(signature the page index was last rebuilt from, its build number)."""
    row = con.execute(
        "SELECT signature, build FROM search_meta WHERE key = 'page_built'"
    ).fetchone()
    return (row[0], row[1]) if row else (None, 0)


PAGE_REBUILD_BATCH = 2000  # rows per write transaction; see `rebuild_pages`
# What `page_built.signature` says while a rebuild is in flight. It deliberately does NOT
# begin with `PAGE_INDEX_FORMAT`, because that is the string `web` tests: an interrupted
# rebuild leaves a HALF-BUILT index, and a half-built index that passed the check would
# quietly answer searches with a fraction of the record.
PAGE_REBUILDING = "rebuilding"


def _mark_page_build(con: Connection, signature: str, build: int, log=None) -> None:
    """Under the retry like every other write here: the mark is the FIRST thing a rebuild
    takes the lock for, so a contended store used to fail before a single row moved."""
    _under_lock(
        con,
        "INSERT INTO search_meta (key, signature, build, built_at) VALUES ('page_built', ?, ?, ?)"
        " ON CONFLICT (key) DO UPDATE SET signature = excluded.signature,"
        " build = excluded.build, built_at = excluded.built_at",
        log or (lambda _: None),
        "mark",
        [(signature, build, utcnow())],
    )


def rebuild_pages(
    con: Connection, *, force: bool = False, batch: int = PAGE_REBUILD_BATCH, log=None
) -> dict:
    """The page index from the display view, whole. The loader keeps `page_fts` in step
    row by row (`store.page_index`), so this is for recovery and for a change to the view —
    a `PAGE_INDEX_FORMAT` bump — not for every pass; ~1.1M rows is minutes, not seconds.

    IT IS BATCHED BECAUSE IT USED TO HOLD THE WRITE LOCK FOR ITS WHOLE RUN. FTS5's own
    `'rebuild'` reads the content view inside one transaction, and with migration 0020's
    `dy_display_text` running once per row that was 8 m 49 s at 1,104,935 rows, then
    27 m 26 s at the v2026.09.3 deploy — and the poller lost its 01:03 pass to it
    (`deferred.md`, 2026-09-04). Two things change here:

    - THE PER-ROW PYTHON IS OUTSIDE THE WRITE LOCK. The masking function runs in the SELECT
      that reads the view, in no transaction at all; only the FTS insert of each batch is
      inside `BEGIN IMMEDIATE`. That is where the time went, and it now costs the poller
      nothing.
    - THE LOCK IS RELEASED BETWEEN BATCHES, so a writer waiting on it — Litestream's
      checkpoint, the poller — gets in within a batch rather than within a rebuild.

    Measured 2026-09-04 on a synthetic 100,000-page store, a second writer probing for the
    write lock every 10 ms: refused on 8 of 21 probes before (each probe waiting 250 ms, so
    it was shut out for the run) against 0 of 255 after, for 3.2 s of wall time against
    4.0 s. The 25% is what the extra commits and the keyset paging cost, and it buys a
    poller that never waits. The production figure at 1.1M rows on the instance is NOT
    verified — this box is an order of magnitude faster per row — and the next real rebuild
    is what confirms it.

    A HALF-BUILT INDEX IS NEVER SERVED. The build is not atomic any more, so `page_built`
    is marked `rebuilding` before the first row is touched and only set to the real
    signature after the last: `web` refuses to start against anything that does not begin
    with `PAGE_INDEX_FORMAT`, so an interrupted rebuild is refused rather than served
    short. Re-running needs no `--force` — `rebuilding` matches no signature.

    Keyset paging, not OFFSET: the view is ordered by `text_id` and each batch resumes after
    the last one's, so the scan stays linear.
    """
    sig = page_signature(con)
    last, build = page_built(con)
    if sig == last and not force:
        return {"unchanged": True, "build": build}
    say = log or (lambda _: None)
    # THE MARK GOES DOWN BEFORE THE FIRST ROW IS TOUCHED, and it is a claim as well as a
    # warning: `page_index` refuses to write while it stands, so the loader cannot index a
    # row this scan is about to index again — a duplicate rowid an external-content FTS5
    # accepts in silence and a later 'delete' half-clears.
    _mark_page_build(con, PAGE_REBUILDING, build, say)
    # 'delete-all', not 'rebuild': 'rebuild' is the whole read-and-index in one transaction,
    # which is the thing being taken apart. This empties the index and reads nothing.
    _under_lock(con, "INSERT INTO page_fts (page_fts) VALUES ('delete-all')", say, "delete-all")
    rows = after = 0
    while True:
        # OUTSIDE any transaction: this is where `dy_display_text` runs, once per row.
        chunk = con.execute(
            "SELECT text_id, text FROM document_text_display WHERE text_id > ?"
            " ORDER BY text_id LIMIT ?",
            (after, batch),
        ).fetchall()
        if not chunk:
            break
        _under_lock(con, "INSERT INTO page_fts (rowid, text) VALUES (?, ?)", say, "batch", chunk)
        rows += len(chunk)
        after = chunk[-1][0]
        say(f"  page index: {rows} rows")
    # The store may have moved under the scan — the loader refuses to start while the mark
    # stands, but a load ALREADY RUNNING when this began does not see it. Say so rather than
    # stamping a signature the index does not answer to: the operator re-runs, and until
    # they do, the next `rebuild_pages` finds `sig != last` and rebuilds anyway.
    moved = page_signature(con) != sig
    _mark_page_build(con, sig, build + 1, say)
    out = {"build": build + 1, "pages": rows}
    if moved:
        out["moved"] = True
        say("  the page signature moved while this ran: something wrote readings. Re-run.")
    return out


def _under_lock(con: Connection, sql: str, log, what: str, rows: list | None = None) -> None:
    """One write transaction, waited out when another writer holds the lock.

    The batched rebuild takes the write lock hundreds of times where FTS5's `'rebuild'` took
    it once, so a transient SQLITE_BUSY that the old shape never met would now empty the
    index and stop — leaving `web` refusing to start until a whole rebuild lands. It waits
    the lock out by the one rule the passes use (`batches.under_lock`), and replay is safe
    because the rollback leaves nothing and `rows` is still in memory.
    """

    def do():
        con.execute("BEGIN IMMEDIATE")
        if rows is None:
            con.execute(sql)
        else:
            con.executemany(sql, rows)
        con.commit()

    batches.under_lock(con, do, what=f"the page index's {what}", log=log)


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
    counts = {"docket": 0, "party": 0, "decision": 0, "comment": 0, "skipped": 0}
    for source in (_docket_docs, _party_docs, _decision_docs, _comment_docs):
        for kind, ref, path, title, body, fact, caption in source(con):
            counts[kind] += 1
            if kind != "skipped":
                rows.append(
                    # every text column, not only the two the snippet reads today:
                    # "no marker can come from the record" should be true of the row
                    (kind, ref, path, _plain(title), _plain(body), _plain(fact), _plain(caption))
                )
    con.execute("BEGIN IMMEDIATE")
    con.execute("DELETE FROM search_doc")
    con.executemany(
        "INSERT INTO search_doc (kind, ref, path, title, body, fact, caption)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
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


def rebuild_or_report(con: Connection, problems: list[str]) -> dict | None:
    """What a pass calls: the index is a convenience and the record comes first, so a
    failure is rolled back and reported as a problem, never raised."""
    try:
        return rebuild(con)
    except Exception as e:  # noqa: BLE001
        con.rollback()
        problems.append(f"search rebuild failed ({type(e).__name__}: {e})")
        return None


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


def _shown_snippet(snippet: str, caption: str) -> str:
    """The snippet, unless it would only repeat the caption printed beside it.

    A snippet is worth a line when it says something the row's own name does not: which of
    a family's sub-captions matched, the sentence of a decision summary, the words a
    commenter wrote. For a docket whose caption IS the matched text, it would print the
    same string twice, so it is dropped. An unmarked snippet is dropped too — FTS5 returns
    the leading text of a column it found no match in, and leading text is not a reason."""
    if MARK_OPEN not in snippet:
        return ""
    core = snippet.replace(MARK_OPEN, "").replace(MARK_CLOSE, "").strip("… ")
    return "" if core and core in caption else snippet


def search(
    con: Connection,
    text: str,
    *,
    limit: int = LIMIT,
    prefix: bool = False,
    with_snippet: bool = True,
) -> list[Hit]:
    """Ranked hits: bm25 with the title weighted above the body; ties by kind then title,
    the kinds ordering as they sort (comment, decision, docket, party). A docket number is
    the caller's fast path, not this.

    Each row carries WHY it matched: `snippet()` over the body, marked with the two control
    characters the web tier turns into tags. The index has always held these words — 89.4%
    of rows have an identifier for a title and the words that found them in the body — and
    the results page printed none of them (navigation-review.md § B). No schema change and
    no rebuild is needed for this; the caption beside it is what needed the column."""
    match = _match(text, prefix)
    if match is None:
        return []
    # `with_snippet=False` is not a micro-optimisation. The ORDER BY is an explicitly
    # weighted `bm25(...)`, which defeats FTS5's internal rank ordering, so SQLite sorts
    # externally and evaluates the whole select list for EVERY matching row before the
    # LIMIT bites — a common word matches tens of thousands, and a third of the index is
    # comment bodies, the longest text it carries. `/suggest` fires on a two-character
    # prefix per keystroke from an unauthenticated endpoint and then discards the snippet,
    # so it must not ask for one (schema-critic, 2026-08-31).
    excerpt_sql = "snippet(search_fts, 1, ?, ?, '…', ?)" if with_snippet else "''"
    params: tuple = (MARK_OPEN, MARK_CLOSE, SNIPPET_TOKENS) if with_snippet else ()
    rows = con.execute(
        f"""
        SELECT d.kind, d.path, d.title, d.fact, d.caption,
               {excerpt_sql} AS excerpt,
               bm25(search_fts, 8.0, 1.0) AS rank
          FROM search_fts JOIN search_doc d ON d.doc_id = search_fts.rowid
         WHERE search_fts MATCH ?
         ORDER BY rank, d.kind, d.title LIMIT ?
        """,
        (*params, match, limit),
    ).fetchall()
    return [
        Hit(kind, path, title, fact, caption, _shown_snippet(excerpt or "", caption or ""))
        for kind, path, title, fact, caption, excerpt, _ in rows
    ]


PAGE_LIMIT = 20  # page hits, on every surface: docs/search.md publishes the number
# ONE DOCUMENT MAY NOT TAKE THE WHOLE SECTION. A phrase printed on every page of a
# 300-page environmental assessment ranks twenty of that one document's pages and buries
# every other document that matched — and a reader sees a full section with no sign that
# anything is missing. The record path cannot fail this way: its grain is one row per
# docket. This one's is one row per PAGE, so the ranked rows are folded to a few per
# document before they are cut to twenty (`deferred.md`, 2026-09-04).
PAGE_PER_DOCUMENT = 3  # page hits any one document may take of the twenty
# Ranked rows scanned per hit shown, so the fold has something to keep. Scanning deeper is
# not what a search costs, PROVIDED the fold reads no text — measured 2026-09-04 on a
# 40,000-page store whose pages average 3,827 characters, a term matching every page: 36.7 ms
# at a window of 21, 49.0 ms if all 201 rows are read through the masking view, 37.6 ms as
# this is written. The first measurement of this said 4 ms and was taken on 800-character
# pages, where masking is too cheap to see; the shape of the store decides this one.
PAGE_OVERFETCH = 10

# Index rows a search met that the display view NO LONGER SHOWS. It is the one signal that
# `page_fts` has drifted from `document_text_display` — a human row inserted without
# `leave`, a store restored from a replica — and it was computed and read by nobody
# (`deferred.md`, 2026-09-04). A process counter, not a store query: the drift can only be
# seen by asking the view about every one of 1.1M index rows, which is the masking function
# 1.1M times and no way to run a scrape. `web` runs one uvicorn worker, so this is the whole
# of the process's answer.
#
# It counts DRIFT ONLY, not everything `PageResults.dropped` counts. A comment's attachment
# has text and no text address to show it at, so its pages are dropped from every search of
# a healthy store; counting those here would have moved this in proportion to traffic and
# buried the signal it exists to carry (code review, 2026-09-04).
_stale_page_rows = 0


def stale_page_rows() -> int:
    """Stale page-index rows met by searches since this process started. Monotonic."""
    return _stale_page_rows


@dataclass(frozen=True)
class PageResults:
    hits: list[Hit]
    truncated: bool  # the index matched more pages than were asked for
    dropped: int  # index rows with no display row or no record: a stale index shows here
    # A rebuild is in flight and the index holds a FRACTION of the record. `web` refuses to
    # START against this, but a process already running would answer a search short with a
    # 200 and no sign — a coverage claim the store cannot support. The surfaces say it
    # instead (code review, 2026-09-04).
    rebuilding: bool = False
    # Matching pages held back because their document already had `PAGE_PER_DOCUMENT` shown.
    # Counted so the surfaces can say "and more pages in some of them" rather than let a
    # reader believe twenty is all the record holds.
    folded: int = 0


def search_pages(con: Connection, text: str, *, limit: int = PAGE_LIMIT) -> PageResults:
    """Pages of documents whose displayed text matches, ranked — ITS OWN QUERY PATH over
    `page_fts` (ADR 0022 D4; migration 0018), never joined to `search()`.

    `ORDER BY rank LIMIT` is the shape FTS5 optimises: the internal ordering, the select
    list — the snippet — evaluated only for the rows that survive the LIMIT. The shipped
    `search()` cannot use it because its `bm25()` carries explicit weights, which is why
    that path must not be handed a million more rows; this one has one column and no
    weights, so it can. Measured on the production index (docs/search.md): milliseconds
    for a rare phrase, about a second for the widest word in the record.

    The rowids are `document_text.text_id`s, read back through `pages.by_text_ids` in one
    query — the same select the text page uses, so a hit's label and band are the page's
    own (ADR 0021 D7). The view they index IS the display rule, so a hit shows what the page
    shows, contact details already omitted (migration 0020).

    One hit per page. A document attached to several records is addressed under the
    earliest-filed filing that carries it, else the earliest-served decision; a comment's
    attachment has no text address and is not a hit (`documents.VIEWABLE_KINDS`). The limit
    is clamped to `PAGE_LIMIT` for every caller: the number is a published promise, not a
    default."""
    limit = max(1, min(limit, PAGE_LIMIT))
    # One row, before the query: a rebuild in flight means the index holds a fraction of the
    # record, and answering "3 pages" out of a tenth of it is a coverage claim the store
    # cannot support. `web` refuses to START against this; a process already running gets
    # here instead, and says so.
    rebuilding = page_built(con)[0] == PAGE_REBUILDING
    match = _match(text, prefix=False)
    if match is None:
        return PageResults([], False, 0, rebuilding=rebuilding)
    if rebuilding:
        return PageResults([], False, 0, rebuilding=True)
    # The rowids first and the snippet second, for a reason that was reproduced: FTS5
    # computes `snippet()` from the content view, and an index row whose view row has gone
    # — a human correction inserted by hand without `leave(primary)`, which `page_index`'s
    # docstring names as the review layer's debt — makes it raise "database disk image is
    # malformed" before any row returns. Asked for the snippet only on rows the view still
    # shows, a stale row is counted in `dropped` instead of taking every search down.
    # Scanned in rank order, deeper than the twenty shown, because the fold below throws
    # rows away and a scan of exactly twenty would leave the section short.
    window = limit * PAGE_OVERFETCH
    ids = [
        text_id
        for (text_id,) in con.execute(
            "SELECT rowid FROM page_fts WHERE page_fts MATCH ? ORDER BY rank LIMIT ?",
            (match, window + 1),  # one more: is there more beyond the window?
        )
    ]
    truncated = len(ids) > window  # the index matched more than was even looked at
    ids = ids[:window]
    # THE FOLD READS NO TEXT. `document_text_display.text` is `dy_display_text(t.text)`, two
    # regex passes per row in Python, and folding two hundred rows to twenty would have run
    # it on a hundred and eighty rows nobody sees. SQLite evaluates a view's expression only
    # for the columns selected (verified against the view), so asking it for `text_id` and
    # `document_sha256` alone costs no masking at all — and the text is fetched below, for
    # the twenty that survive (code review, 2026-09-04).
    shas: dict[int, str] = {}
    if ids:
        marks = ",".join("?" for _ in ids)
        shas = dict(
            con.execute(
                "SELECT text_id, document_sha256 FROM document_text_display"
                f" WHERE text_id IN ({marks})",
                ids,
            )
        )
    records: dict[str, tuple | None] = {}
    per_document: Counter = Counter()
    keep: list[int] = []
    dropped = folded = stale = 0
    for text_id in ids:
        if len(keep) >= limit:
            truncated = True  # rows still ranked below the ones kept
            break
        if text_id not in shas:
            # THE DRIFT: an index row the display view no longer shows (`page_index`'s
            # docstring). This is the one that means something is wrong.
            stale += 1
            dropped += 1
            continue
        sha = shas[text_id]
        if per_document[sha] >= PAGE_PER_DOCUMENT:
            folded += 1  # this document has had its share; a later one gets the slot
            continue
        if sha not in records:
            records[sha] = _record_of(con, sha)
        if records[sha] is None:
            # NOT drift: a comment's attachment has text and no text address to show it at
            # (`documents.VIEWABLE_KINDS`), so this is the expected outcome for a healthy
            # store and is counted in `dropped` without touching the drift signal.
            dropped += 1
            continue
        per_document[sha] += 1
        keep.append(text_id)

    found = pages.by_text_ids(con, keep)
    hits: list[Hit] = []
    for text_id in keep:
        if text_id not in found:  # the view answered a moment ago; belt and braces
            stale += 1
            dropped += 1
            continue
        sha, page = found[text_id]
        record = records[sha]
        assert record is not None  # only rows with a record reach `keep`
        excerpt = con.execute(
            "SELECT snippet(page_fts, 0, ?, ?, '…', ?) FROM page_fts"
            " WHERE rowid = ? AND page_fts MATCH ?",
            (MARK_OPEN, MARK_CLOSE, SNIPPET_TOKENS, text_id, match),
        ).fetchone()[0]
        kind, record_id, index, raw_docket, caption = record
        identity = parse_docket_id(raw_docket)
        printed = urls.printed_docket(identity) if identity else raw_docket
        noun = "Decision" if kind == "decision" else "Filing"
        # `rebuild()` strips the markers from every record row before indexing, so on that
        # path no marker can come from the record. The page index holds the view's bytes
        # unstripped, so a page whose own text carries one is shown without a snippet
        # rather than with a mark the record put there.
        excerpt = "" if MARK_OPEN in page.text or MARK_CLOSE in page.text else excerpt
        hits.append(
            Hit(
                "page",
                urls.text_path(kind, record_id, index) + f"#p{page.page_no}",
                f"{noun} {record_id}, page {page.page_no}",
                f"in {printed}",
                caption or "",
                _shown_snippet(excerpt or "", caption or ""),
                label=pages.label(page),
                band=pages.band(page),
                scan=urls.viewer_path(kind, record_id, index),
            )
        )
    global _stale_page_rows
    _stale_page_rows += stale
    return PageResults(
        hits, truncated or bool(folded), dropped, rebuilding=rebuilding, folded=folded
    )


# The record that carries a document, and the file's index among the record's attachments
# ordered as the sheet orders them (`sheet._attachments`: by source URL), so `?file=N` names
# the same file on the text page and the record page. The earliest-filed record first (an
# undated row last, not first — SQLite sorts NULL first), then its id, then the parent docket
# before its sub-docket (a filing entered under both is two rows: the rule every "nearest the
# parent" query in this file uses; schema-critic, 2026-09-04), then the URL: a document a
# record carries twice resolves to one index. Two literal statements rather than one
# templated one, so each can be read and pasted whole.
_FILING_OF = """
SELECT r.stb_filing_id,
       (SELECT COUNT(*) FROM filing_attachment b
         WHERE b.filing_pk = a.filing_pk AND b.source_url < a.source_url),
       k.raw_docket, json_extract(k.latest_payload, '$.title')
  FROM filing_attachment a
  JOIN filing r ON r.filing_pk = a.filing_pk
  JOIN docket_current k ON k.docket_id = r.docket_id
 WHERE a.document_sha256 = ?
 ORDER BY r.filed_date IS NULL, r.filed_date, r.stb_filing_id,
          COALESCE(k.sub_sequence, -1), COALESCE(k.suffix, ''), a.source_url LIMIT 1
"""
_DECISION_OF = """
SELECT r.stb_decision_id,
       (SELECT COUNT(*) FROM decision_attachment b
         WHERE b.decision_pk = a.decision_pk AND b.source_url < a.source_url),
       k.raw_docket, json_extract(k.latest_payload, '$.title')
  FROM decision_attachment a
  JOIN decision_record r ON r.decision_pk = a.decision_pk
  JOIN docket_current k ON k.docket_id = r.docket_id
 WHERE a.document_sha256 = ?
 ORDER BY r.service_date IS NULL, r.service_date, r.stb_decision_id,
          COALESCE(k.sub_sequence, -1), COALESCE(k.suffix, ''), a.source_url LIMIT 1
"""


def _record_of(con: Connection, sha: str):
    """(kind, record id, attachment index, raw docket, caption) for the record that carries
    the document — a filing before a decision — or None. Indexed by migration 0021."""
    for kind, sql in (("filing", _FILING_OF), ("decision", _DECISION_OF)):
        row = con.execute(sql, (sha,)).fetchone()
        if row is not None:
            return (kind, row[0], row[1], row[2], row[3])
    return None


def held_docket(con: Connection, text: str) -> Hit | None:
    """The fast path: a docket number the record holds. The exact identity if it is held;
    else its family, which is where a sub-docket's entries are anyway (ADR 0005); else
    nothing — and then the words are a search like any other."""
    identity = urls.lookup(text)
    if identity is None:
        return None
    # the ingest grammar reads a trailing word as a suffix ("AB 55 Peoria" → suffix PEORIA);
    # the fast path applies only when every typed token is part of the number itself
    if identity.suffix and len(identity.suffix) > 3:  # a word read as a suffix (X, A, L, M, C)
        return None
    typed = {t.lower() for t in _TOKEN.findall(text)} - {"sub", "no"}
    parts = [identity.prefix, str(identity.sequence), identity.sub_sequence, identity.suffix]
    number = {str(part).lower() for part in parts if part is not None}
    if typed != number:
        return None
    for candidate in (identity, identity.parent()):
        if candidate is None:
            continue
        docket_id = find_docket(con, candidate)
        if docket_id is None:
            continue
        printed = urls.printed_docket(candidate)
        # the caption too: the fast path is the row a reader reaches most often, and it
        # would be the one row still answering with a bare number
        row = con.execute(
            "SELECT json_extract(latest_payload, '$.title') FROM docket_current"
            " WHERE docket_id = ?",
            (docket_id,),
        ).fetchone()
        return Hit(
            "docket",
            urls.docket_path(candidate),
            printed,
            "the docket sheet",
            (row[0] if row else "") or "",
        )
    return None
