"""A read-only MCP server over the record (capability F7).

The audience already puts regulatory questions to assistants, which answer from training
data and invent docket numbers and dates. Being the grounded source they reach instead is
a distribution channel — but only if what they are handed is as honest as the page a person
would have read. Two constraints travel with this surface, and both are structural here
rather than aspirational:

**Read-only.** No tool writes, subscribes, or spends on a reader's behalf. This module
imports the read side of the store and nothing else; `tests/test_mcp.py` asserts that every
handler is reachable from the read paths alone, so a future tool that writes fails the
suite rather than shipping.

**Every answer carries its caveats.** A human reading a docket sheet sees the coverage page
a click away, "as printed" on every quoted cell, and the standing line that nothing here
says what any party argued. An assistant is handed a string, so the caveats travel IN the
string: each result ends with what the record does not hold, and every record names the
Board's own file. An assistant quoting this record without its caveats is worse than no
source, so the caveats are not optional formatting — they are the payload.

Transport is Streamable HTTP (MCP 2025-11-25): one endpoint, POST for JSON-RPC, and GET
answering 405 because this server never initiates a message. It is stateless — no session
id — which a read-only server can afford and which means a restart strands nobody.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import date as Day
from sqlite3 import Connection

from docketyard.ingest.dockets import find_docket, parse_docket_id
from docketyard.store import activity as activity_store
from docketyard.store import coverage as coverage_store
from docketyard.store import finder
from docketyard.store import gaps as gaps_store
from docketyard.store import pages as pages_store
from docketyard.store import search as search_store
from docketyard.store import sheet as sheet_store
from docketyard.store.db import load_json
from docketyard.store.sheet import present
from docketyard.web import documents, labels, urls

PROTOCOL_VERSION = "2025-11-25"
# what a client that sent no MCP-Protocol-Version header is assumed to speak (the spec's
# own default), so an older client is answered rather than refused
FALLBACK_PROTOCOL_VERSION = "2025-03-26"
SUPPORTED_PROTOCOL_VERSIONS = (PROTOCOL_VERSION, "2025-06-18", FALLBACK_PROTOCOL_VERSION)

SERVER_NAME = "docketyard"

# Handed to the client at initialize, so the standing caveats are in front of the model
# before it asks anything — not only after.
INSTRUCTIONS = """\
Docket Yard is a public record of proceedings before the U.S. Surface Transportation Board \
(STB), the federal agency regulating freight rail. It is operated by RMI Valuation, LLC and \
is NOT the STB; every record links to the agency's own PDF, which is authoritative.

When you use these tools, carry these with the answer:

- Quote, do not infer. Dates, captions, summaries and comments are reproduced as the Board \
printed them. Nothing in this record says what any party argued or what a filing means. A \
procedural filing takes no position regardless of who filed it.
- Say what is not covered. Coverage is not uniform across time — call `coverage` and repeat \
what it says rather than implying the record is complete.
- Cite the Board's file. Every record carries the STB's own URL; prefer it when the user \
needs the source, and give the docketyard.org address when they need a stable citation.
- Search results are capped and are not counts. For "how many", call `count_filings`, and \
repeat what it says it did not count.
- Page text is served so it can be read and quoted, never as the Board's words. \
`read_page` hands over a page as read from the Board's document, labelled with who read it; \
repeat that label and the link to the Board's own file with anything you quote. Docket Yard \
serves the text as read from the Board's documents. An AI's reading or summary of it may be \
wrong, and what an assistant does with this text is outside Docket Yard's control. Before \
relying on it, review the document itself: the Board's own file is linked. The text is held \
back from Docket Yard's public-domain dedication: it is served for reading on a user's \
request, not for bulk collection or training.
- If a tool returns nothing, say the record holds nothing — never fill the gap from memory. \
Inventing a docket number or a service date is the specific failure this surface exists to \
prevent."""

# The operator's wording (2026-09-16), carried by every answer that hands over page text —
# a snippet or a page — because an assistant quotes the answer it was handed, not the
# instructions it was given at connect.
TEXT_CAVEAT = (
    "Docket Yard serves the text as read from the Board's documents. An AI's reading or"
    " summary of it may be wrong, and what an assistant does with this text is outside Docket"
    " Yard's control. Before relying on it, review the document itself: the Board's own file"
    " is linked."
)
# The page text is held from the CC0 dedication (ADR 0022 D3). Reading it on a user's
# request is permitted; the dedication is not extended by it (the operator, 2026-09-16).
TEXT_LICENCE = (
    "This text is held back from Docket Yard's public-domain dedication: it is served for"
    " reading on a user's request, not for bulk collection or training."
)

_NOT_HELD = (
    "This record does not say what any party argued and does not compute deadlines. The text"
    " inside documents is machine-read, a finding aid: a [page] line names who read it and"
    " links the scan, which is the record. Coverage is not uniform — call `coverage`."
)


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    schema: dict
    run: object  # (Connection, dict, str) -> str


def _obj(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _plural(n: int, noun: str) -> str:
    """An assistant repeats what it is handed, so "1 decisions" would be quoted back."""
    return f"{n:,} {noun}" + ("" if n == 1 else "s")


def _marked(snippet: str, identifiers: str = "") -> str:
    """A search snippet as plain text: the index's control-character marks become « », and
    only the fields holding a match are kept — a record's index body joins the Board's words
    to this record's own spellings of its number (`search.FIELD`), which are not the Board's
    and are not what an assistant should quote. A field made of nothing but the record's own
    identifiers (`identifiers`: its title and fact line) is dropped too, so a search by
    number says nothing matched in the Board's words rather than quoting our spellings (code
    review, 2026-09-16). Empty when nothing else is left."""
    tokens = [t.lower() for t in _TOKENS.findall(identifiers)]
    # and each adjacent pair run together, the index's `FD36873` spelling of `FD 36873`
    known = set(tokens) | {a + b for a, b in zip(tokens, tokens[1:], strict=False)}

    def own(field: str) -> bool:
        plain = field.replace(search_store.MARK_OPEN, " ").replace(search_store.MARK_CLOSE, " ")
        # the other dockets a record was entered in are this record's spellings too (search-v2
        # puts every one in the body): printed numbers, never the Board's words
        plain = _PRINTED_DOCKET.sub(" ", plain)
        words = {t.lower() for t in _TOKENS.findall(plain)}
        return not words or words <= known

    fields = snippet.split(search_store.FIELD)
    kept = [f for f in fields if search_store.MARK_OPEN in f and not own(f)]
    joined = " … ".join(f.strip() for f in kept if f.strip())
    return joined.replace(search_store.MARK_OPEN, "«").replace(search_store.MARK_CLOSE, "»")


_TOKENS = re.compile(r"[^\W_]+")
# a docket number as `urls.printed_docket` prints it: `FD 36873`, `AB 55 (Sub-No. 794X)`
_PRINTED_DOCKET = re.compile(r"\b[A-Z][A-Z0-9]*\s+\d+(?:\s+\(Sub-No\.\s+[0-9A-Z]+\))?")


def _site(host: str, path: str) -> str:
    return f"https://{host}{path}"


# --- the tools themselves -------------------------------------------------------------


def _record_line(h: search_store.Hit, host: str) -> str:
    # the caption first where there is one, the identifier beside it. An assistant
    # handed "[docket] FD 30101 — 0 filings" has been told nothing about the
    # proceeding, which is navigation-review.md § B on the third surface — fixed on
    # the page and in /suggest, and left here until the schema-critic caught it.
    named = f"{h.caption} ({h.title})" if h.caption else h.title
    # why it matched, which for a decision is its summary as the Board printed it: a row
    # reading "[decision] Decision 52200 — FD 29830" told an assistant nothing to judge
    # relevance by (the independent graders, 2026-09-16). « » mark the matched words.
    matched = _marked(h.snippet, f"{h.title} {h.fact}")
    return f"[{h.kind}] {named} — {h.fact} — {_site(host, h.path)}" + (
        f' — matched: "{matched}"' if matched else ""
    )


def _page_line(h: search_store.Hit, host: str) -> str:
    # a page of machine-read text is handed over WITH who read it, the band's operand
    # or its absence, and the scan (ADR 0021 D7): the text is a finding aid, the scan
    # is the record, and an assistant told less would repeat the reading as a fact
    named = f"{h.caption} ({h.title})" if h.caption else h.title
    # the matched passage, since 2026-09-16 (the operator): an assistant choosing which
    # page to read needs to see why each matched. The markers become « » — plain text
    # the answer can carry, where the web tier turns them into tags after escaping
    matched = (
        h.snippet.replace(search_store.MARK_OPEN, "«").replace(search_store.MARK_CLOSE, "»")
        if h.snippet
        else ""
    )
    return (
        f"[page] {named} — {h.fact} — {_site(host, h.path)} — {h.label}"
        + (f" {h.band}" if h.band else "")
        + (f' Matched: "{matched}"' if matched else "")
        + f" The scan: {_site(host, h.scan)}. Machine-read text: check it against the scan."
    )


_SEARCH_FILTERS = (
    "prefix",
    "exclude_prefixes",
    "date_from",
    "date_to",
    "record_type",
    "type",
    "exclude_dockets",
    "sort",
    "page",
)
_SEARCH_KINDS = {
    "filing": ("filings",),
    "decision": ("decisions",),
    "comment": ("comments",),
    "page": ("text",),
}


def _search(con: Connection, args: dict, host: str) -> str:
    text = str(args.get("query", "")).strip()
    if not text:
        return "Nothing was searched for."
    limit = max(1, min(int(args.get("limit", 10) or 10), 50))
    # filtered, the search runs through the query layer `/search` reads (the operator
    # reopened his 2026-09-17 decision on 2026-10-02: an assistant asking about
    # "application September 2026" got one proceeding's filings and nothing else). With no
    # filter the answer is the shape it has always been.
    if any(args.get(k) not in (None, "", []) for k in _SEARCH_FILTERS):
        return _search_filtered(con, args, text, limit, host)
    held = search_store.held_docket(con, text)
    hits = search_store.search(con, text, limit=limit)
    found = search_store.search_pages(con, text, limit=limit)  # clamped to PAGE_LIMIT inside
    pages = found.hits
    lines = []
    if held is not None:
        lines.append(f"That is a docket this record holds: {held.title} — {_site(host, held.path)}")
    if found.folded:
        # An assistant that reported "the record holds 20 pages on this" would be wrong in
        # the one direction that matters: the twenty are capped per document, so a document
        # with forty matching pages contributes three (`search.PAGE_PER_DOCUMENT`).
        lines.append(
            f"At most {search_store.PAGE_PER_DOCUMENT} pages of any one document are listed"
            " below, so a document may hold more matching pages than are shown."
        )
    if found.rebuilding:
        # An assistant told "nothing matched" while the index holds a tenth of the record
        # would report an absence that is not one — the caveat this surface exists to carry.
        lines.append(
            "The text index is being rebuilt, so the words of documents were NOT searched"
            " for this answer. The record below is unaffected; say so if you report it."
        )
    if not hits and not pages and held is None and not found.rebuilding:
        return (
            f"The record holds nothing matching {text!r}. That is an absence in this record, "
            "not proof of absence at the Board."
        )
    lines += [_record_line(h, host) for h in hits]
    lines += [_page_line(h, host) for h in pages]
    if found.truncated and pages:
        # `len(pages)`, not PAGE_LIMIT: `_search` may have asked for fewer than twenty, and
        # the fold makes a short list the common case rather than the odd one. `and pages`
        # because every matched row may be dropped — a comment attachment's pages have no
        # address — and "more pages than the 0 shown" after listing nothing is not a
        # sentence to hand an assistant (code review, 2026-09-04).
        lines.append(f"…and more pages than the {len(pages)} shown; narrow the words.")
    if pages:
        lines += [
            "Read a page with `read_page` and the address above.",
            TEXT_CAVEAT,
            TEXT_LICENCE,
        ]
    return "\n".join(lines)


def _family_ids(con: Connection, docket_id: int) -> set[int]:
    """A docket and its sub-dockets, as its sheet reads them."""
    return {
        d
        for (d,) in con.execute(
            "SELECT docket_id FROM docket WHERE docket_id = ? OR parent_docket_id = ?",
            (docket_id, docket_id),
        )
    }


def _search_filtered(con: Connection, args: dict, text: str, limit: int, host: str) -> str:
    """The words, narrowed: a flat list of the filings, decisions, comments and pages that
    match, each once however many proceedings it was entered in. Docket captions are left
    out — a filter is on what a proceeding holds, and `get_docket_sheet` reads a proceeding."""
    try:
        date_from = _day(args.get("date_from"), "date_from") or ""
        date_to = _day(args.get("date_to"), "date_to") or ""
    except ValueError as e:
        return str(e) if str(e).startswith("`") else "A date must be a real day, YYYY-MM-DD."
    if date_from and date_to and date_from > date_to:
        return (
            f"`date_from` ({date_from}) is after `date_to` ({date_to}); nothing can fall between."
        )
    held_prefixes = {p for (p,) in con.execute("SELECT DISTINCT prefix FROM docket")}
    prefix = str(args.get("prefix") or "").strip().upper()
    if prefix and prefix not in held_prefixes:
        return (
            f"The record holds no docket prefix {prefix!r} (prefixes look like `AB`, `FD`, `NOR`)."
        )
    excluded = _strings(args.get("exclude_prefixes"), "exclude_prefixes", '["MCF"]')
    if isinstance(excluded, str):
        return excluded
    excluded = tuple(sorted({x.upper() for x in excluded}))
    kind = str(args.get("record_type") or "").strip().casefold()
    if kind and kind not in _SEARCH_KINDS:
        return "`record_type` is `filing`, `decision`, `comment` or `page` (the text of documents)."
    kinds = _SEARCH_KINDS[kind] if kind else ("decisions", "filings", "comments", "text")
    sort = str(args.get("sort") or "best").strip().casefold()
    if sort not in ("best", "newest"):
        return "`sort` is `best` (the strongest match first; the default) or `newest`."
    page = args.get("page")
    page = 1 if page is None else page
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        return "`page` must be a whole number, 1 or more."

    notes, scope = [], []
    dockets = _strings(args.get("exclude_dockets"), "exclude_dockets", '["FD 36873"]')
    if isinstance(dockets, str):
        return dockets
    if len(dockets) > _MAX_DOCKETS:
        return f"`exclude_dockets` takes at most {_MAX_DOCKETS} docket numbers a call."
    groups: set[int] = set()
    left_out = []
    placed = search_store.proceedings(con) if dockets else {}
    for asked in dockets:
        identity = urls.lookup(asked)
        docket_id = find_docket(con, identity) if identity else None
        if identity is None or docket_id is None:
            notes.append(
                f"{asked!r} is not a docket number this record holds; nothing was left out for it."
            )
            continue
        # The index places a record under its PROCEEDING by the sheet rule: a sub-docket with
        # no caption of its own, or its parent's, is placed under the parent. Leaving out such
        # a sub-docket can only mean leaving out the proceeding it is part of, and the answer
        # says so rather than claiming a narrower exclusion than it made (code review).
        own = placed.get(docket_id, (docket_id, ""))[0]
        groups |= {placed.get(d, (d, ""))[0] for d in _family_ids(con, docket_id)}
        if own != docket_id:
            row = con.execute(
                "SELECT raw_docket FROM docket WHERE docket_id = ?", (own,)
            ).fetchone()
            parent = parse_docket_id(row[0]) if row else None
            whole = urls.printed_docket(parent) if parent else "its parent"
            notes.append(
                f"{urls.printed_docket(identity)} is searched as part of {whole}, so all of"
                f" {whole} was left out."
            )
            left_out.append(whole)
        else:
            left_out.append(urls.printed_docket(identity))

    ftypes = dtypes = ()
    asked_type = str(args.get("type") or "").strip()
    if asked_type and kind == "comment":
        return "An environmental comment has no Board type, so `type` cannot narrow comments."
    if asked_type:
        ftypes = tuple(_types(con, asked_type)) if kind in ("", "filing", "page") else ()
        dtypes = (
            tuple(_types(con, asked_type, "decision_type"))
            if kind in ("", "decision", "page")
            else ()
        )
        if not ftypes and not dtypes:
            return (
                f"No filing or decision type the Board uses matches {asked_type!r}. A type is"
                " the Board's label; search the words of a decision's summary without `type`."
            )
        scope.append("of the Board's types " + ", ".join(f"'{t}'" for t in (*ftypes, *dtypes)))
        if "comments" in kinds:
            kinds = tuple(k for k in kinds if k != "comments")  # a comment has no Board type

    if prefix:
        scope.insert(0, f"in {prefix} proceedings")
    if excluded:
        scope.append(f"leaving out {', '.join(excluded)} proceedings")
    if left_out:
        scope.append(f"leaving out {', '.join(left_out)} (each with its sub-dockets)")
    if date_from or date_to:
        scope.append(
            f"dated {date_from or 'from the first'} to {date_to or 'the latest held'}"
            " (filed, served, or received or sent, as the Board printed it)"
        )

    q = finder.Query(
        text=text,
        prefixes=(prefix,) if prefix else (),
        date_from=date_from,
        date_to=date_to,
        kinds=kinds,
        ftypes=ftypes,
        dtypes=dtypes,
        sort=sort,
        page=page,
        view="documents",
        exclude_groups=tuple(sorted(groups)),
        exclude_prefixes=excluded,
        page_size=limit,
    )
    out = finder.find(con, q)
    scoped = (", " + "; ".join(scope)) if scope else ""
    lines = notes[:]
    if out.records_rebuilding:
        return "\n".join(
            lines
            + [
                "The search index is being rebuilt, so nothing was searched for this answer."
                " That is not an absence in this record; try again shortly."
            ]
        )
    if out.pages_cut == "budget":
        lines.append(
            "The words matched too many pages to filter in time, so the text of documents was"
            " left out of this answer; the records below are complete. Narrow the words."
        )
    elif out.pages_cut == "rebuilding":
        lines.append(
            "The text index is being rebuilt, so the words of documents were NOT searched"
            " for this answer. The records below are unaffected; say so if you report it."
        )
    if not out.total:
        if out.pages_cut in ("budget", "rebuilding") and "text" in kinds:
            # the words of documents were not searched, so nothing found is not an absence:
            # said beside a warning that the text was skipped, "the record holds nothing"
            # contradicted it (Codex, PR #43)
            lines.append(
                f"No filing, decision or comment matched {text!r}{scoped}, and the text of"
                " documents was not searched, so this is NOT an absence in this record. Narrow"
                " the words, or try again."
            )
        else:
            lines.append(
                f"The record holds nothing matching {text!r}{scoped}. That is an absence in"
                " this record, not proof of absence at the Board."
            )
        return "\n".join(lines)
    first = (page - 1) * limit + 1
    last = first + len(out.documents) - 1
    # "window": unfiltered by placement, the page side ranks only the best PAGE_WINDOW pages,
    # so the total is a floor and "newest" is newest among those — said as `/search` says it
    # ("At least"), never handed over as a count (code review)
    capped = out.pages_cut == "window"
    if capped:
        order = "newest first among what was examined." if sort == "newest" else "strongest first."
    else:
        order = "newest first." if sort == "newest" else "strongest match first."
    lines.append(
        f"Matching {text!r}{scoped}: {'at least ' if capped else ''}{out.total:,} filings,"
        " decisions, comments and pages"
        + (
            f" — the words matched more pages than the best {finder.PAGE_WINDOW:,} examined,"
            " so this is a floor and not a count"
            if capped
            else " — a count of what matched"
        )
        + ", each once however many proceedings it was entered in."
        + (
            f" Showing {first}–{last}, {order}"
            if out.documents
            else f" `page` {page} is past the last of them."
        )
    )
    shown_pages = False
    for h in out.documents:
        if h.kind == "page":
            shown_pages = True
            lines.append(_page_line(h, host))
        else:
            lines.append(_record_line(h, host))
    if out.documents and last < out.total:
        lines.append(f"{out.total - last:,} more: call again with `page` {page + 1}.")
    if shown_pages:
        lines += [
            "Read a page with `read_page` and the address above.",
            TEXT_CAVEAT,
            TEXT_LICENCE,
        ]
    return "\n".join(lines)


def _entry_line(e: sheet_store.Entry, sheet_raw: str) -> str:
    """One entry as the sheet hands it over, shared with `recent_activity` so a record reads
    the same in both. `sheet_raw` is the docket the reader is looking at: an entry entered
    elsewhere in the family says where."""
    who = e.filed_for_raw or e.submitter or e.organisation or ""
    board = e.attachments[0].url if e.attachments else ""
    # the proceeding an entry was actually entered in — a family folds onto one sheet,
    # but attributing a sub-docket's filing to the parent misstates the record
    entered = parse_docket_id(e.docket_raw)
    where = f" — in {urls.printed_docket(entered)}" if entered and e.docket_raw != sheet_raw else ""
    # printed, not raw: `also_in` carries the store's own ids (AB_55_785_X), which
    # resolve at neither docketyard.org nor stb.gov — and the `where` clause one line
    # above already canonicalises the same class of value (ultrareview)
    printed_also = [
        urls.printed_docket(i) for i in map(parse_docket_id, e.also_in) if i is not None
    ]
    also = f" — also entered in {', '.join(printed_also)}" if printed_also else ""
    # a decision's deciding body and its summary as the Board printed it: the JSON twin
    # and the page carry both, and without them an assistant could say only that "a
    # decision" was served and had to open the PDF or guess (the independent graders,
    # 2026-09-16). Quoted, never paraphrased; `present` drops the Board's `--`.
    body, summary = present(e.deciding_body), present(e.summary)
    return (
        # which date it is, so a served date is never quoted as a decided one
        f"{labels.date_kind(e.kind)} {e.date or 'undated'} [{e.kind}] {e.record_id}"
        + (f" — {e.type}" if e.type else "")
        + (f" — {body}" if body else "")
        + (f' — the Board\'s summary, as printed: "{summary}"' if summary else "")
        + where
        + also
        + (f" — as printed: {who}" if who else "")
        + (f" — the Board's file: {board}" if board else "")
    )


def _docket(con: Connection, args: dict, host: str) -> str:
    identity = urls.lookup(str(args.get("docket", "")))
    if identity is None:
        return (
            "That is not a docket number this record can parse"
            " (try `FD 36873`, `AB 55 (Sub-No. 794X)`)."
        )
    docket_id = find_docket(con, identity)
    if docket_id is None:
        return (
            f"The record holds no proceeding numbered {urls.printed_docket(identity)}. "
            "It may exist at the Board and not here."
        )
    # the Board's own dates, so "anything since the last brief?" need not read forty entries
    # and diff them (the operator, 2026-10-02). What the watch OBSERVED since a run is
    # `recent_activity`'s question; this one is about the dates the Board printed.
    try:
        date_from = _day(args.get("date_from"), "date_from")
        date_to = _day(args.get("date_to"), "date_to")
    except ValueError as e:
        return str(e) if str(e).startswith("`") else "A date must be a real day, YYYY-MM-DD."
    if date_from and date_to and date_from > date_to:
        return (
            f"`date_from` ({date_from}) is after `date_to` ({date_to}); nothing can fall between."
        )
    s = sheet_store.docket_sheet(con, docket_id)
    if s is None:
        return "The record holds no sheet for that proceeding."
    limit = max(1, min(int(args.get("limit", 25) or 25), 100))
    head = [
        f"{urls.printed_docket(identity)} — {s.title or '(caption not yet observed)'}",
        f"{_plural(s.filings, 'filing')}, {_plural(s.decisions, 'decision')} and"
        f" {_plural(s.comments, 'environmental comment')} held."
        f" Sheet: {_site(host, urls.docket_path(identity))}",
    ]
    if s.last_checked:
        head.append(f"Last checked against the Board: {s.last_checked}.")
    if s.last_new_entry:
        # not "checked": the last capture that brought this proceeding an entry
        head.append(f"Last new entry observed: {s.last_new_entry}.")
    if s.is_index:
        # a series carries no entries of its own; the assistant is handed the index the page
        # and the JSON both carry, not an empty "Entries, newest first:" (code review)
        head.append(
            f"This number is a series: it holds no record of its own, and the"
            f" {len(s.sub_dockets)} proceedings under it each keep their own."
        )
        if date_from or date_to:
            # an index has no dates to narrow; listing it unremarked read as the series'
            # activity inside the range (code review)
            head.append(
                "`date_from`/`date_to` narrow entries, and a series has none: the list below"
                " is not narrowed. `recent_activity` with this number in `dockets` and"
                " `by: board_date` reads every proceeding under it by date."
            )
        rows = ["Proceedings under this number:"]
        for m in s.sub_dockets[:limit]:
            ident = parse_docket_id(m.raw_docket)
            printed = urls.printed_docket(ident) if ident else m.raw_docket
            rows.append(
                f"- {printed} — {m.title or '(caption not yet observed)'}"
                f" — {_plural(m.filings, 'filing')}, {_plural(m.decisions, 'decision')}"
                + (f" — {_site(host, urls.docket_path(ident))}" if ident else "")
            )
        if len(s.sub_dockets) > limit:
            rows.append(f"…and {len(s.sub_dockets) - limit} more, listed on the sheet.")
        return "\n".join(head + rows + ["", _NOT_HELD])
    entries = s.entries
    rows = ["Entries, newest first:"]
    if date_from or date_to:
        # an undated entry is outside every range, and is said to be rather than dropped
        undated = sum(1 for e in entries if not e.date)
        entries = [
            e
            for e in entries
            if e.date
            and (not date_from or e.date >= date_from)
            and (not date_to or e.date <= date_to)
        ]
        rows = [
            f"Entries the Board dated {date_from or 'from the first'} to"
            f" {date_to or 'the latest held'} (filed, served, or received or sent):"
            f" {len(entries):,} of the {len(s.entries):,} on the sheet, newest first."
            + (f" {_plural(undated, 'undated entry')} cannot fall in a range." if undated else "")
            + " The Board can post an entry days after its date; `recent_activity` windows on"
            " when this record observed it."
        ]
        if not entries:
            rows.append(
                "None. That is an absence in this record, not proof of absence at the Board."
            )
    rows += [f"- {_entry_line(e, s.raw_docket)}" for e in entries[:limit]]
    more = ""
    if len(entries) > limit:
        more = (
            f"\n({len(entries) - limit} older entries not shown — these are the"
            f" {limit} most recent, not the whole sheet. "
            # at the cap, "raise `limit`" sent an assistant round a loop it could not leave
            # (the independent graders, 2026-09-16)
            + (
                "Raise `limit` (at most 100) or read the sheet.)"
                if limit < 100
                else "This tool shows at most 100; the rest are on the sheet:"
                f" {_site(host, urls.docket_path(identity))})"
            )
        )
    return "\n".join(head) + "\n\n" + "\n".join(rows) + more


def _words(text: str | None, board_file: str | None) -> str:
    """The comment's words and its file, said once and without contradicting itself.

    Two independent ternaries promised "its words are in the file below" and then said
    "the Board lists no file for this comment" whenever a comment had neither."""
    if text:
        said = f"\nThe commenter's own words, as the Board printed them:\n{text}"
    elif board_file:
        said = (
            "\nThe Board printed no text for this comment in its table; its words are in"
            " the file below."
        )
    else:
        said = "\nThe Board printed no text for this comment and lists no file for it."
    if board_file:
        said += f"\nThe Board's own file: {board_file}"
    return said


def _comment(con: Connection, args: dict, host: str) -> str:
    number = str(args.get("number", "")).strip().upper()
    rows = con.execute(
        "SELECT d.raw_docket, c.date_received_or_sent, c.submitter_raw, c.organisation_raw,"
        " c.location_raw, c.comment_text_printed, COALESCE(c.stb_row_ref, '') AS ref,"
        " (SELECT a.source_url FROM enviro_comment_attachment a"
        "    WHERE a.comment_pk = c.comment_pk LIMIT 1) AS board_file"
        " FROM enviro_comment c JOIN docket d ON d.docket_id = c.docket_id"
        " WHERE c.comment_number = ?"
        " ORDER BY ref, COALESCE(d.sub_sequence, -1), COALESCE(d.suffix, ''), c.comment_pk",
        (number,),
    ).fetchall()
    if not rows:
        # the hedge a docket miss carries: the comment walk has unfinished months, so a miss
        # here is not a miss at the Board (the independent graders, 2026-09-16)
        return (
            f"The record holds no environmental comment numbered {number}. It may exist at the"
            " Board and not here: call `coverage` for the months the record has not finished."
        )
    # Folded by ROW REF, not by number. One comment entered in a docket and its sub-docket
    # shares a ref and is ONE comment (108 of the 110 repeated numbers measured); two
    # comments the Board gave the same number have different refs and are two. Folding by
    # number would tell an assistant that a cross-posted comment was two different people.
    seen, out = set(), []
    for raw, date, raw_sub, raw_org, raw_loc, raw_text, ref, board_file in rows:
        # `--` is what the Board prints for a cell it has nothing for, and it is
        # truthy. The sheet strips it before any page renders; re-querying the store
        # here handed an assistant "Location: --" as a place (ultrareview).
        submitter, org = present(raw_sub), present(raw_org)
        location, text = present(raw_loc), present(raw_text)
        if ref in seen:
            continue
        seen.add(ref)
        identity = parse_docket_id(raw)
        where = urls.printed_docket(identity) if identity else raw
        out.append(
            f"{number} in {where}, dated {date}."
            + (f" Submitted by: {submitter}." if submitter else "")
            + (f" Organisation: {org}." if org else "")
            + (f" Location: {location}." if location else "")
            + _words(text, board_file)
            + (
                f"\nPermanent address: {_site(host, urls.comment_path(identity, number))}"
                if identity
                else ""
            )
        )
    note = ""
    if len(out) > 1:
        note = (
            "\n\nThe Board has given this number to more than one comment — these are"
            " different comments by different people, each at its own address."
        )
    return (
        "\n\n".join(out)
        + note
        + "\n\nThis is the commenter's own statement, quoted. It is not this record's view,"
        " and it is not the Board's."
    )


# The addresses `search_the_record` and the site hand out: a filing's or a decision's text
# (or record) page, and a comment's under its docket — with `?file=N` and `#pN` if given.
_RECORD_ADDRESS = re.compile(
    r"(?:https?://[^/\s]+)?/(filing|decision)/([A-Za-z0-9]+)(?:/text)?/?"
    r"(?:\?file=(\d+))?(?:#p(\d+))?"
)
_COMMENT_ADDRESS = re.compile(
    r"(?:https?://[^/\s]+)?/d/([^/?#\s]+)(?:/sub/([^/?#\s]+))?/comment/([^/?#\s]+)"
    r"(?:/text)?/?(?:\?file=(\d+))?(?:#p(\d+))?"
)
_RECORD_NAME = re.compile(r"(filing|decision)\s+(\d+)", re.IGNORECASE)
MAX_READ_PAGES = 5  # pages one call hands over
MAX_PAGE_CHARS = 20_000  # a plan sheet's reading can run long; the rest is on the text page


def _small(value, default: int, low: int, high: int) -> int:
    """An integer argument clamped to its range; anything that is not one is the default."""
    if isinstance(value, bool):
        return default
    try:
        n = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(low, min(n, high))


def _located(con: Connection, address: str):
    """(kind, record id, docket_id, file, page) for an address or `decision 46314`, or a
    sentence saying why not. A record entered in a docket and its sub-docket is read under
    the one nearest the parent, as the site addresses it (ADR 0005)."""
    text = address.strip()
    m = _RECORD_ADDRESS.fullmatch(text)
    named = _RECORD_NAME.fullmatch(text)
    if m or named:
        kind, record_id = (m or named).group(1).lower(), (m or named).group(2)
        file, page = (m.group(3), m.group(4)) if m else (None, None)
        table, column = (
            ("decision_record", "stb_decision_id")
            if kind == "decision"
            else ("filing", "stb_filing_id")
        )
        row = con.execute(
            f"SELECT r.docket_id FROM {table} r JOIN docket d ON d.docket_id = r.docket_id"
            f" WHERE r.{column} = ?"
            " ORDER BY COALESCE(d.sub_sequence, -1), COALESCE(d.suffix, '') LIMIT 1",
            (record_id,),
        ).fetchone()
        if row is None:
            return f"The record holds no {kind} {record_id}."
        return kind, record_id, row[0], file, page
    m = _COMMENT_ADDRESS.fullmatch(text)
    if m:
        ident, sub, number, file, page = m.groups()
        identity = urls.parse_docket_path(ident, sub)
        number = number.upper()
        if identity is None:
            return f"{text!r} does not name a docket this record can parse."
        row = con.execute(
            "SELECT c.docket_id FROM enviro_comment c JOIN docket d ON d.docket_id = c.docket_id"
            " WHERE c.comment_number = ? AND d.prefix = ? AND d.sequence = ?"
            " AND COALESCE(d.sub_sequence, -1) = COALESCE(?, -1)"
            " AND COALESCE(d.suffix, '') = COALESCE(?, '')",
            (number, identity.prefix, identity.sequence, identity.sub_sequence, identity.suffix),
        ).fetchone()
        if row is None:
            return f"The record holds no environmental comment {number} in that docket."
        return "comment", number, row[0], file, page
    return (
        f"{text!r} is not an address this tool reads. Pass the address a search result gave"
        " (`https://docketyard.org/decision/46314/text#p3`) or a record (`decision 46314`)."
    )


def _read(con: Connection, args: dict, host: str) -> str:
    """Every read_page answer ends with the text caveat and the licence line — a miss, an
    unread file and a refused address included — as machine-surface.md promises. Two early
    returns carried neither or one (Copilot on PR #38, 2026-09-17), so both are added here,
    once, the way `handle` appends the standing caveats."""
    text = _read_page(con, args, host)
    ending = [line for line in (TEXT_CAVEAT, TEXT_LICENCE) if line not in text]
    return "\n".join([text, *ending]) if ending else text


def _read_page(con: Connection, args: dict, host: str) -> str:
    found = _located(con, str(args.get("address") or ""))
    if isinstance(found, str):
        return found
    kind, record_id, docket_id, file_in_address, page_in_address = found
    # party_map={}: the entry's parties are not read here, and resolving them is a
    # store-wide union-find this answer has no use for (`sheet.one_entry`)
    got = sheet_store.one_entry(con, docket_id, kind, record_id, party_map={})
    if got is None:
        return f"The record holds no {kind} {record_id}."
    context, entry = got
    file = _small(args.get("file", file_in_address), 0, 0, 10_000)
    index = documents.text_pick(entry, file)  # the text page's own rule for `?file=N`
    noun = {"decision": "Decision", "comment": "Environmental comment"}.get(kind, "Filing")
    identity = parse_docket_id(entry.docket_raw)
    printed = urls.printed_docket(identity) if identity else entry.docket_raw
    head = f"{noun} {record_id} — in {printed}" + (f" — {context.title}" if context.title else "")
    if index is None:
        board = entry.attachments[0].url if entry.attachments else "none listed"
        return (
            f"{head}\nThis record holds no page text for it: only a PDF this record has fetched"
            f" is read. The Board's own file: {board}"
        )
    current = entry.attachments[index]
    sha = current.document_sha256 or ""
    readings = {p.page_no: p for p in pages_store.readings(con, sha)}
    count = pages_store.pagination(con, sha)
    routes = pages_store.routes(con, sha)
    # the range is the readings and the page count, never the routes (the text page's rule)
    last = max(max(readings, default=0), (count.page_count or 0) if count else 0)
    text_address = urls.entry_text_path(kind, record_id, entry.docket_raw, index)
    scan = search_store._scan(con, kind, record_id, index, sha)
    lines = [head, f"The Board's own file: {current.url}", f"The scan: {_site(host, scan)}"]
    if last == 0:
        lines.append("No page of this file has been read yet.")
        return "\n".join(lines)
    first = _small(args.get("page", page_in_address), 1, 1, last)
    through = min(last, first + _small(args.get("pages"), 1, 1, MAX_READ_PAGES) - 1)
    engine = False
    for n in range(first, through + 1):
        page, route = readings.get(n), routes.get(n)
        shown = pages_store.state(page, route, count.had_text_layer if count else None)
        where = f"[page {n} of {last}] {_site(host, f'{text_address}#p{n}')} —"
        lines.append("")
        if shown == pages_store.TEXT and page is not None:
            engine = engine or page.reading_channel == "ocr"
            band = pages_store.band(page)
            cut = len(page.text) > MAX_PAGE_CHARS
            lines += [
                f"{where} {pages_store.label(page)}" + (f" {band}" if band else ""),
                f"--- page {n} text begins ---",
                page.text[:MAX_PAGE_CHARS]
                + ("\n[…cut here; the rest is at the page's address]" if cut else ""),
                f"--- page {n} text ends ---",
            ]
        elif shown == pages_store.BLANK and page is not None:
            lines.append(f"{where} Read as blank. {pages_store.label(page)}")
        elif shown == pages_store.TABLE and route is not None:
            lines.append(f"{where} {pages_store.marker(route)} Read it from the scan.")
        else:
            lines.append(f"{where} Not yet read. Read it from the scan.")
    lines.append("")
    if through < last:
        lines.append(
            f"Pages {first} to {through} of {last} shown; pass `page` {through + 1} to go on."
        )
    if engine:
        lines.append(
            "A page machine-read by an engine was read by OCR from a scan: it carries character"
            " errors, more on a degraded scan, and no person has reviewed it. Check any word you"
            " quote against the scan."
        )
    lines += [
        "This is the text as read, never the Board's words: quote it with its label and the"
        " Board's own file.",
        TEXT_CAVEAT,
        TEXT_LICENCE,
    ]
    return "\n".join(lines)


_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_TYPE_LINES = 40  # a type listing longer than this names the rest by count only


def _day(value, name: str) -> str | None:
    """A `YYYY-MM-DD` the caller sent, or None when absent. Anything else raises the
    `ValueError` whose message is handed back — the argument is the caller's, so saying
    what was wrong with it discloses nothing."""
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not _DAY.fullmatch(text):
        raise ValueError(f"`{name}` must be a date written YYYY-MM-DD, not {text!r}.")
    Day.fromisoformat(text)  # 2026-02-30 is shaped right and is not a day
    return text


def _types(con: Connection, asked: str, column: str = "filing_type") -> list[str]:
    """The Board's own types an asked name matches: that type alone when the name IS one
    (case aside), else every type containing it. Matched against the types the store holds,
    so an assistant is told which labels were counted rather than trusted to have guessed the
    Board's spelling. `column` is `filing_type`, or `decision_type` for decisions."""
    table = {"filing_type": "filing", "decision_type": "decision_record"}[column]
    held = [t for (t,) in con.execute(f"SELECT DISTINCT {column} FROM {table}") if t]
    needle = asked.strip().casefold()
    exact = [t for t in held if t.casefold() == needle]
    return exact or sorted(t for t in held if needle in t.casefold())


@dataclass(frozen=True)
class _Scope:
    """The filters `count_filings` and `list_proceedings` share.

    One definition, deliberately: a count and the list of proceedings behind it that
    disagreed about the prefix or the date range would be worse than either alone, and the
    two tools exist precisely so an assistant can move from one to the other (deferred, the
    live-MCP finding 2026-09-17). Everything a caller can narrow with lives here."""

    base: str  # the FROM and WHERE, ready to follow a SELECT list
    params: list
    scope: str  # the same filters in English, for the answer
    since: str | None
    until: str | None


def _scope(con: Connection, args: dict) -> _Scope | str:
    """The shared filters, or the sentence saying why they cannot be built. A string back is
    the refusal to hand the caller, not an exception: every tool here answers in prose."""
    try:
        since = _day(args.get("filed_from"), "filed_from")
        until = _day(args.get("filed_to"), "filed_to")
    except ValueError as e:
        return str(e) if str(e).startswith("`") else "A date must be a real day, YYYY-MM-DD."
    if since and until and since > until:
        return f"`filed_from` ({since}) is after `filed_to` ({until}); nothing can fall between."
    prefix = str(args.get("prefix") or "").strip().upper()
    if (
        prefix
        and con.execute("SELECT 1 FROM docket WHERE prefix = ? LIMIT 1", (prefix,)).fetchone()
        is None
    ):
        return (
            f"The record holds no docket prefix {prefix!r} (prefixes look like `AB`, `FD`, `NOR`)."
        )

    where, params = ["1 = 1"], []
    if prefix:
        where.append("d.prefix = ?")
        params.append(prefix)
    if since:
        where.append("f.filed_date >= ?")
        params.append(since)
    if until:
        where.append("f.filed_date <= ?")
        params.append(until)
    return _Scope(
        base=" FROM filing f JOIN docket d ON d.docket_id = f.docket_id WHERE "
        + " AND ".join(where),
        params=params,
        scope=(f" in {prefix} proceedings" if prefix else "")
        + (
            f", filed {since or 'from the first'} to {until or 'the latest held'}"
            if since or until
            else ""
        ),
        since=since,
        until=until,
    )


def _open_month_caveats(
    con: Connection,
    since: str | None,
    until: str | None,
    *,
    shortfall: str,
    kind: str = "filings",
) -> list[str]:
    """What a filing figure inside this range cannot account for. Shared for the same reason
    `_Scope` is: a count that named its unfinished months and a list that did not would let
    an assistant treat the list as the whole set. Which months, and the walk-start rule, are
    the shared part; `shortfall` is only how each tool says what it is short OF."""
    lines = []
    incomplete, walked = {
        "filings": (coverage_store.filings_incomplete, coverage_store.filings_walked_from),
        "decisions": (coverage_store.decisions_incomplete, coverage_store.decisions_walked_from),
        "environmental comments": (
            coverage_store.comments_incomplete,
            coverage_store.comments_walked_from,
        ),
    }[kind]
    open_months = [
        m
        for m in incomplete(con)
        if (not since or m >= since[:7]) and (not until or m <= until[:7])
    ]
    if open_months:
        lines.append(
            f"Months this record has not finished for {kind}, inside the range {shortfall}:"
            f" {', '.join(coverage_store.month_runs(tuple(open_months)))}."
        )
    walked_from = walked(con)
    if walked_from and (not since or since[:7] < walked_from):
        lines.append(
            f"This record's walk of {kind} begins at {walked_from}: nothing is claimed about"
            f" {kind} the Board dated earlier."
        )
    return lines


def _count(con: Connection, args: dict, host: str) -> str:
    built = _scope(con, args)
    if isinstance(built, str):
        return built
    base, params, scope, since, until = (
        built.base,
        built.params,
        built.scope,
        built.since,
        built.until,
    )

    asked = str(args.get("filing_type") or "").strip()
    lines: list[str] = []
    if not asked:
        # no type asked: the Board's own vocabulary, counted, so the next call can name one
        rows = con.execute(
            "SELECT f.filing_type, COUNT(DISTINCT f.stb_filing_id)"
            + base
            + " GROUP BY 1 ORDER BY 2 DESC, 1",
            params,
        ).fetchall()
        if not rows:
            lines.append(
                f"The record holds no filings{scope}. That is an absence in this record,"
                " not proof of absence at the Board."
            )
        else:
            lines.append(
                f"The Board's filing types{scope}, with the filings this record holds of each:"
            )
            lines += [f"- {t or '(untyped)'}: {n:,}" for t, n in rows[:_TYPE_LINES]]
            if len(rows) > _TYPE_LINES:
                lines.append(f"…and {len(rows) - _TYPE_LINES} rarer types.")
    else:
        types = _types(con, asked)
        if not types:
            return (
                f"No filing type the Board uses matches {asked!r}. Call `count_filings` without"
                " `filing_type` to list the types this record holds. What a decision does —"
                " a notice of interim trail use issued, an exemption granted — is not a filing"
                " type, and this record does not yet count decisions by what they did."
            )
        marks = ", ".join("?" * len(types))
        per_type = con.execute(
            "SELECT f.filing_type, COUNT(DISTINCT f.stb_filing_id), COUNT(DISTINCT f.docket_id)"
            + base
            + f" AND f.filing_type IN ({marks}) GROUP BY 1 ORDER BY 2 DESC, 1",
            params + types,
        ).fetchall()
        filings, proceedings, first, last = con.execute(
            "SELECT COUNT(DISTINCT f.stb_filing_id), COUNT(DISTINCT f.docket_id),"
            # NULLIF: a blank date would sort first and print "filed  to …" (coverage.py's
            # guard; none is held today, measured 2026-09-16)
            " MIN(NULLIF(f.filed_date, '')), MAX(NULLIF(f.filed_date, ''))"
            + base
            + f" AND f.filing_type IN ({marks})",
            params + types,
        ).fetchone()
        named = ", ".join(f"'{t}'" for t in types)
        if not filings:
            lines.append(
                f"The record holds no filings the Board typed {named}{scope}."
                " That is an absence in this record, not proof of absence at the Board."
            )
        else:
            lines.append(
                f"Filings the Board typed {named}{scope}: {_plural(filings, 'filing')} entered in"
                f" {_plural(proceedings, 'proceeding')}, filed {first} to {last}."
            )
            if len(per_type) > 1:
                lines += [
                    f"- {t}: {_plural(n, 'filing')} in {_plural(p, 'proceeding')}"
                    for t, n, p in per_type
                ]
            also = str(args.get("also_has") or "").strip()
            if also:
                others = _types(con, also)
                if not others:
                    lines.append(
                        f"No filing type the Board uses matches {also!r}, so nothing was paired."
                    )
                else:
                    other_marks = ", ".join("?" * len(others))
                    # "both" is two DIFFERENT filings: the phrases may overlap (`trail use` and
                    # `Trail Use Request`), and one filing matching each is not a pair. A filing
                    # is one row per proceeding (UNIQUE (docket_id, stb_filing_id)), so a
                    # proceeding whose matches are all one filing has n = 1 (code review).
                    both, has_other = con.execute(
                        "SELECT SUM(a > 0 AND b > 0 AND n > 1), SUM(b > 0) FROM ("
                        f" SELECT SUM(f.filing_type IN ({marks})) AS a,"
                        f" SUM(f.filing_type IN ({other_marks})) AS b, COUNT(*) AS n"
                        + base
                        + f" AND f.filing_type IN ({marks}, {other_marks})"
                        " GROUP BY f.docket_id)",
                        types + others + params + types + others,
                    ).fetchone()
                    other_named = ", ".join(f"'{t}'" for t in others)
                    lines.append(
                        f"Proceedings holding both one of those and a filing typed {other_named}:"
                        f" {both or 0:,} (of {proceedings:,} holding the first and"
                        f" {has_other or 0:,} holding the second"
                        + ("; both filed inside the range" if since or until else "")
                        + "). Held in the same proceeding says nothing about which came first or"
                        " whether one led to the other."
                    )
            lines.append(
                "A filing entered in more than one proceeding counts once among filings and once in"
                " each proceeding. These are the Board's labels as it typed them: a type names the"
                " kind of filing, not what the filing accomplished, and this count has not read the"
                " documents."
                + (
                    " A Consummation Notice does not say what was consummated — an abandonment, a"
                    " discontinuance or interim trail use."
                    if any("consummat" in t.casefold() for t in types)
                    else ""
                )
            )
    # a count is only as complete as the months under it, so the unfinished ones inside the
    # range are named in the answer rather than left to a `coverage` call nobody makes
    lines += _open_month_caveats(
        con, since, until, shortfall="counted (the count is short by whatever they hold)"
    )
    lines.append(f"What the record holds and does not: {_site(host, '/coverage')}")
    return "\n".join(lines)


_LIST_CAP = 25  # proceedings per call; `offset` reaches the rest
_FILINGS_SHOWN = 6  # matching filings printed per proceeding; the rest are counted


def _list_proceedings(con: Connection, args: dict, host: str) -> str:
    """The proceedings behind a `count_filings` count.

    Asked for "the 20 most recent" of a count it had just been given correctly, an assistant
    could not list them, narrowed by date, and GUESSED a docket number from a search hit
    (the operator, testing the live server, 2026-09-17). That guess is the exact failure this
    surface exists to prevent, and the absence of this tool forced it. A sibling rather than
    a flag on `count_filings` because the assistant's problem was not knowing the capability
    existed: a named tool is in the list it already reads."""
    built = _scope(con, args)
    if isinstance(built, str):
        return built

    asked = str(args.get("filing_type") or "").strip()
    if not asked:
        return (
            "`filing_type` is required here: this tool lists the proceedings behind a count of"
            " one type. Call `count_filings` with no `filing_type` to see the Board's own types"
            " with their counts, then name one."
        )
    types = _types(con, asked)
    if not types:
        return (
            f"No filing type the Board uses matches {asked!r}. Call `count_filings` without"
            " `filing_type` to list the types this record holds. What a decision does —"
            " a notice of interim trail use issued, an exemption granted — is not a filing"
            " type, and this record does not yet list proceedings by what a filing accomplished."
        )
    offset = args.get("offset") or 0
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        return "`offset` must be a whole number of proceedings to skip, 0 or more."

    also = str(args.get("also_has") or "").strip()
    others: list[str] = []
    if also:
        others = _types(con, also)
        if not others:
            # Refused rather than listed without the pairing: listing every proceeding holding
            # the first type would answer a question the caller did not ask, and read as if it
            # had. `count_filings` can say "nothing was paired" beside a number that stands on
            # its own; a list cannot.
            return (
                f"No filing type the Board uses matches {also!r}, so no pairing could be made"
                " and nothing is listed. Call `count_filings` without `filing_type` to see the"
                " Board's types."
            )

    marks = ", ".join("?" * len(types))
    if others:
        other_marks = ", ".join("?" * len(others))
        # The same rule the count uses: "both" is two DIFFERENT filings. The phrases may
        # overlap (`trail use` matches `Trail Use Request` too), and one filing matching each
        # is not a pair — hence `n > 1` (code review, on the count).
        grouped = (
            "SELECT f.docket_id AS docket_id, MAX(NULLIF(f.filed_date, '')) AS latest,"
            f" SUM(f.filing_type IN ({marks})) AS a,"
            f" SUM(f.filing_type IN ({other_marks})) AS b, COUNT(*) AS n"
            + built.base
            + f" AND f.filing_type IN ({marks}, {other_marks})"
            " GROUP BY f.docket_id HAVING a > 0 AND b > 0 AND n > 1"
        )
        gparams = types + others + built.params + types + others
        shown = types + others
    else:
        grouped = (
            "SELECT f.docket_id AS docket_id, MAX(NULLIF(f.filed_date, '')) AS latest"
            + built.base
            + f" AND f.filing_type IN ({marks}) GROUP BY f.docket_id"
        )
        gparams = built.params + types
        shown = types

    (total,) = con.execute(f"SELECT COUNT(*) FROM ({grouped})", gparams).fetchone()
    named = ", ".join(f"'{t}'" for t in types)
    # ONE description of what was matched, used by every sentence below. The refusal used to
    # describe the unpaired set while the number beside it was the paired one — it said
    # "1 proceeding holds a filing typed 'Motion'" where `count_filings` said 2 (code review,
    # 2026-09-18). A figure and its description have to be built together or they drift apart.
    matched = f"a filing the Board typed {named}" + (
        f", and one typed {', '.join(repr(t) for t in others)}" if others else ""
    )
    if not total:
        return (
            f"The record holds no proceeding with {matched}{built.scope}. That is an absence in"
            " this record, not proof of absence at the Board."
        )

    # `docket_id DESC` after the date so a page boundary cannot repeat or skip a proceeding
    # when several share the newest date — an unstable sort under LIMIT/OFFSET drops rows
    # silently, which is worse here than showing none.
    page = con.execute(
        f"{grouped} ORDER BY latest DESC, docket_id DESC LIMIT ? OFFSET ?",
        gparams + [_LIST_CAP, offset],
    ).fetchall()
    if not page:
        # the verb is agreed with the same number `_plural` agrees the noun with: "1
        # proceeding hold" is exactly what that helper's docstring exists to stop
        return (
            f"`offset` {offset} is past the last of them: {_plural(total, 'proceeding')}"
            f" {'holds' if total == 1 else 'hold'} {matched}{built.scope}."
        )

    ids = [r[0] for r in page]
    id_marks = ", ".join("?" * len(ids))
    shown_marks = ", ".join("?" * len(shown))
    rows = con.execute(
        "SELECT f.docket_id, f.filing_type, f.filed_date, f.stb_filing_id"
        + built.base
        + f" AND f.docket_id IN ({id_marks}) AND f.filing_type IN ({shown_marks})"
        " ORDER BY f.filed_date DESC, f.stb_filing_id",
        built.params + ids + shown,
    ).fetchall()
    by_docket: dict[int, list[tuple]] = {}
    for docket_id, filing_type, filed, stb_id in rows:
        by_docket.setdefault(docket_id, []).append((filing_type, filed, stb_id))

    captions = {
        d: (raw, load_json(payload)["title"] if payload else None)
        for d, raw, payload in con.execute(
            f"SELECT docket_id, raw_docket, latest_payload FROM docket_current"
            f" WHERE docket_id IN ({id_marks})",
            ids,
        ).fetchall()
    }

    first, last = offset + 1, offset + len(page)
    lines = [
        f"Proceedings holding {matched}{built.scope}: {total:,}."
        + f" Showing {first}–{last}, newest first by the matching filing's date."
    ]
    for docket_id, *_ in page:
        raw, title = captions.get(docket_id, (None, None))
        identity = parse_docket_id(raw) if raw else None
        printed = urls.printed_docket(identity) if identity else (raw or f"#{docket_id}")
        lines.append(f"- {printed} — {title or '(caption not yet observed)'}")
        # the address belongs to the PROCEEDING, so it goes under its caption: printed after
        # the filings it read as the last filing's (code review, 2026-09-18)
        if identity:
            lines.append(f"    {_site(host, urls.docket_path(identity))}")
        held = by_docket.get(docket_id, [])
        for filing_type, filed, stb_id in held[:_FILINGS_SHOWN]:
            lines.append(f"    {filing_type} — filed {filed or '(no date)'} — {stb_id}")
        # Proceedings are capped but their filings were not, and one proceeding can hold
        # hundreds of a single type — 'Notice Of Intent To Participate (Without Comment)' runs
        # to the hundreds in FD 36873 alone, which is first on an unfiltered page (code review,
        # 2026-09-18). `get_docket_sheet` bounds the same exposure; so does this now.
        if len(held) > _FILINGS_SHOWN:
            lines.append(
                f"    …and {len(held) - _FILINGS_SHOWN:,} more of these types in this"
                " proceeding; its sheet has them all."
            )
    if last < total:
        lines.append(
            f"{total - last:,} more: call again with `offset` {last} for the next"
            f" {min(_LIST_CAP, total - last):,}."
        )
    lines.append(
        "These are the Board's labels as it typed them: a type names the kind of filing, not"
        " what the filing accomplished, and nothing here has read the documents. A filing"
        " entered in more than one proceeding is listed under each, keeping the Board's own"
        " id, which is why one id can appear twice."
        + (
            " Held in the same proceeding says nothing about which came first or whether one"
            " led to the other."
            if others
            else ""
        )
    )
    lines += _open_month_caveats(
        con, built.since, built.until, shortfall="(proceedings in them are missing from this list)"
    )
    return "\n".join(lines)


_BODY_LINES = 12  # deciding bodies listed in a breakdown; the rest are counted


def _printed(column: str) -> str:
    """A cell as printed, with an empty cell and the Board's placeholders all one NULL, so a
    breakdown groups them as one "(none printed)" rather than a line each (code review). The
    placeholders are the sheet's own (`present`), never a second list."""
    blanks = ", ".join(repr(p) for p in sorted(set(sheet_store.PLACEHOLDERS)))
    return f"CASE WHEN TRIM(COALESCE({column}, '')) IN ({blanks}) THEN NULL ELSE {column} END"


def _count_decisions(con: Connection, args: dict, host: str) -> str:
    """How many decisions the Board typed a given way, or issued from a given body, within a
    prefix and a served-date range. Asked for 2026-10-02 beside `recent_activity`: a brief
    could count filings and could not count decisions. A sibling, not a flag on
    `count_filings`, for the reason `list_proceedings` is one — an assistant reads the tool
    list, not a parameter's description. Its members are what `recent_activity` lists with
    `by: board_date`, `record_type: decision` and the same filters, which take the same
    matching rules (`_types`, words in the deciding body)."""
    try:
        since = _day(args.get("served_from"), "served_from")
        until = _day(args.get("served_to"), "served_to")
    except ValueError as e:
        return str(e) if str(e).startswith("`") else "A date must be a real day, YYYY-MM-DD."
    if since and until and since > until:
        return f"`served_from` ({since}) is after `served_to` ({until}); nothing can fall between."
    prefix = str(args.get("prefix") or "").strip().upper()
    if (
        prefix
        and con.execute("SELECT 1 FROM docket WHERE prefix = ? LIMIT 1", (prefix,)).fetchone()
        is None
    ):
        return (
            f"The record holds no docket prefix {prefix!r} (prefixes look like `AB`, `FD`, `NOR`)."
        )
    where, params = ["1 = 1"], []
    if prefix:
        where.append("d.prefix = ?")
        params.append(prefix)
    if since:
        where.append("r.service_date >= ?")
        params.append(since)
    if until:
        where.append("r.service_date <= ?")
        params.append(until)
    scope = (f" in {prefix} proceedings" if prefix else "") + (
        f", served {since or 'from the first'} to {until or 'the latest held'}"
        if since or until
        else ""
    )

    asked = str(args.get("decision_type") or "").strip()
    types: list[str] = []
    if asked:
        types = _types(con, asked, "decision_type")
        if not types:
            held = [t for (t,) in con.execute("SELECT DISTINCT decision_type FROM decision_record")]
            return (
                f"No decision type the Board uses matches {asked!r}. Its types are few and"
                f" general: {', '.join(sorted(t for t in held if t))}. What a decision did — a"
                " notice of interim trail use issued — is in its summary, not its type;"
                " `search_the_record` reads summaries."
            )
        where.append(f"r.decision_type IN ({', '.join('?' * len(types))})")
        params += types
        scope += f", typed {', '.join(repr(t) for t in types)}"
    body = str(args.get("deciding_body") or "").strip()
    if body:
        where.append("r.deciding_body LIKE ? ESCAPE '\\'")
        params.append(activity_store.like(body))
        scope += f", from a deciding body printed with the words {body!r}"
    base = " FROM decision_record r JOIN docket d ON d.docket_id = r.docket_id WHERE " + (
        " AND ".join(where)
    )

    decisions, proceedings, first, last = con.execute(
        "SELECT COUNT(DISTINCT r.stb_decision_id), COUNT(DISTINCT r.docket_id),"
        " MIN(NULLIF(r.service_date, '')), MAX(NULLIF(r.service_date, ''))" + base,
        params,
    ).fetchone()
    lines: list[str] = []
    if not decisions:
        lines.append(
            f"The record holds no decisions{scope}. That is an absence in this record, not proof"
            " of absence at the Board."
        )
    else:
        lines.append(
            f"Decisions{scope}: {_plural(decisions, 'decision')} entered in"
            f" {_plural(proceedings, 'proceeding')}, served {first} to {last}."
        )
        by_type = con.execute(
            f"SELECT {_printed('r.decision_type')}, COUNT(DISTINCT r.stb_decision_id)"
            + base
            + " GROUP BY 1 ORDER BY 2 DESC, 1",
            params,
        ).fetchall()
        if len(by_type) > 1 or not asked:
            lines.append("By the Board's decision type:")
            lines += [f"- {t or '(untyped)'}: {n:,}" for t, n in by_type]
        by_body = con.execute(
            f"SELECT {_printed('r.deciding_body')}, COUNT(DISTINCT r.stb_decision_id)"
            + base
            + " GROUP BY 1 ORDER BY 2 DESC, 1",
            params,
        ).fetchall()
        if len(by_body) > 1 or not body:
            lines.append("By the deciding body, as printed:")
            lines += [
                f"- {present(b) or '(none printed)'}: {n:,}" for b, n in by_body[:_BODY_LINES]
            ]
            if len(by_body) > _BODY_LINES:
                lines.append(f"…and {len(by_body) - _BODY_LINES} rarer bodies.")
        lines.append(
            "A decision entered in more than one proceeding counts once among decisions and once"
            " in each proceeding. Types and deciding bodies are the Board's labels as its table"
            " prints them: neither says what a decision did, and this count has not read the"
            " documents. To list these decisions, call `recent_activity` with `by:"
            " board_date`, `record_type: decision` and the same prefix, dates, type and body."
        )
    lines += _open_month_caveats(
        con,
        since,
        until,
        shortfall="counted (the count is short by whatever they hold)",
        kind="decisions",
    )
    lines.append(f"What the record holds and does not: {_site(host, '/coverage')}")
    return "\n".join(lines)


_RECENT_CAP = 100  # entries per call; `offset` reaches the rest
_MAX_WINDOW_DAYS = 366


def _today(by: str) -> str:
    """The open end of a window: today, written as the window's own bound is."""
    return Day.today().isoformat() if by == "board_date" else datetime.now(UTC).isoformat()


_RECENT_DEFAULT = 50
_MAX_DOCKETS = 50
_KIND_ALIASES = {
    "filing": "filing",
    "filings": "filing",
    "decision": "decision",
    "decisions": "decision",
    "comment": "comment",
    "comments": "comment",
    "environmental comment": "comment",
    "environmental comments": "comment",
}
_KIND_NAMES = {"filing": "filing", "decision": "decision", "comment": "environmental comment"}


def _instant(value, name: str, *, end: bool) -> str | None:
    """A caller's datetime written the way the store writes its own
    (`2026-10-01T06:00:00+00:00`), so the two compare as strings. A bare day is midnight UTC
    at its start — or, closing a window, the midnight after it, so `until: 2026-10-01`
    includes that day."""
    if value is None or value == "":
        return None
    text = str(value).strip()
    try:
        if _DAY.fullmatch(text):
            day = Day.fromisoformat(text)
            if end:
                day += timedelta(days=1)
            return f"{day.isoformat()}T00:00:00+00:00"
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"`{name}` must be a date (YYYY-MM-DD) or a date and time"
            f" (2026-10-01T06:00:00Z), not {text!r}."
        ) from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _strings(value, name: str, example: str) -> tuple[str, ...] | str:
    """A list-of-strings argument (a lone string is taken as a list of one), or the sentence
    refusing it. The body is unauthenticated: a list is only a list because a client sent one."""
    if value in (None, "", []):
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return f"`{name}` is a list of strings, e.g. {example}."
    return tuple(v.strip() for v in value if v.strip())


def _record_path(kind: str, record_id: str, raw_docket: str) -> str | None:
    if kind == "decision":
        return urls.decision_path(record_id)
    if kind == "filing":
        return urls.filing_path(record_id)
    ident = parse_docket_id(raw_docket)
    return urls.comment_path(ident, record_id) if ident else None


def _recent(con: Connection, args: dict, host: str) -> str:
    """What arrived in the record inside a window, across every proceeding or a caller's own
    list — the call a scheduled brief makes instead of guessing search words and diffing
    sheets (the operator, 2026-10-02). The list is an argument, used once and dropped:
    nothing here knows or keeps who watches what (ADR 0011)."""
    by = str(args.get("by") or "observed").strip().lower().replace("-", "_")
    if by not in ("observed", "board_date"):
        return "`by` is `observed` (when this record saw it; the default) or `board_date`."
    if not args.get("since"):
        return (
            "`since` is required: the start of the window, a date (YYYY-MM-DD) or a date and"
            " time (2026-10-01T06:00:00Z). A brief passes the time of its last run."
        )
    try:
        if by == "observed":
            start = _instant(args.get("since"), "since", end=False)
            end = _instant(args.get("until"), "until", end=True)
        else:
            start = _day(args.get("since"), "since")
            end = _day(args.get("until"), "until")
    except ValueError as e:
        return str(e) if str(e).startswith("`") else "A date must be a real day, YYYY-MM-DD."
    if start is None:
        return "`since` is required."
    # an observed `until` is exclusive and a Board-date one inclusive, so an empty window
    # is `>=` in the one and `>` in the other
    if end and (start >= end if by == "observed" else start > end):
        return f"`since` ({start}) is not before `until` ({end}); nothing can fall between."
    # A window is bounded, because a call materialises every record in it before paging:
    # `since: 0001-01-01` by the Board's dates read the whole archive, and twenty such calls
    # at once passed the web container's memory cap (Codex security review, PR #43). A brief
    # needs a day or a week; a year back is a later window, not a longer one.
    span = (Day.fromisoformat((end or _today(by))[:10]) - Day.fromisoformat(start[:10])).days
    if span > _MAX_WINDOW_DAYS:
        return (
            f"A window spans at most {_MAX_WINDOW_DAYS} days, and this one spans {span}. Move"
            " `since` later, or set `until` and read the years before in further windows;"
            " `count_filings` and `count_decisions` count over any range."
        )

    asked_kind = str(args.get("record_type") or "").strip().casefold()
    if asked_kind and asked_kind not in _KIND_ALIASES:
        return "`record_type` is `filing`, `decision` or `comment` (an environmental comment)."
    kinds = (_KIND_ALIASES[asked_kind],) if asked_kind else activity_store.KINDS

    notes: list[str] = []
    scope: list[str] = []

    dockets = _strings(args.get("dockets"), "dockets", '["FD 36844", "AB 55 (Sub-No. 794X)"]')
    if isinstance(dockets, str):
        return dockets
    if len(dockets) > _MAX_DOCKETS:
        return f"`dockets` takes at most {_MAX_DOCKETS} docket numbers a call."
    docket_ids = None
    if dockets:
        found: set[int] = set()
        printed, missing = [], []
        for asked in dockets:
            identity = urls.lookup(asked)
            docket_id = find_docket(con, identity) if identity else None
            if identity is None or docket_id is None:
                missing.append(asked)
                continue
            printed.append(urls.printed_docket(identity))
            found |= _family_ids(con, docket_id)  # a docket brings its sub-dockets
        if missing:
            notes.append(
                "Not docket numbers this record holds, so not read: "
                + ", ".join(repr(m) for m in missing)
                + ". They may exist at the Board and not here."
            )
        if not found:
            return "\n".join(notes)
        docket_ids = tuple(sorted(found))
        scope.append(f"in {', '.join(printed)} (each with its sub-dockets)")

    held_prefixes = {p for (p,) in con.execute("SELECT DISTINCT prefix FROM docket")}
    prefix = str(args.get("prefix") or "").strip().upper() or None
    if prefix and prefix not in held_prefixes:
        return (
            f"The record holds no docket prefix {prefix!r} (prefixes look like `AB`, `FD`, `NOR`)."
        )
    if prefix:
        scope.append(f"in {prefix} proceedings")
    excluded = _strings(args.get("exclude_prefixes"), "exclude_prefixes", '["MCF"]')
    if isinstance(excluded, str):
        return excluded
    excluded = tuple(sorted({x.upper() for x in excluded}))
    unknown = [x for x in excluded if x not in held_prefixes]
    if unknown:
        notes.append(
            f"No docket prefix {', '.join(unknown)} is held, so leaving it out changed nothing."
        )
    if excluded:
        scope.append(f"leaving out {', '.join(excluded)} proceedings")

    filing_types = decision_types = None
    asked_type = str(args.get("type") or "").strip()
    if asked_type and kinds == ("comment",):
        return "An environmental comment has no Board type, so `type` cannot narrow comments."
    if asked_type:
        filing_types = tuple(_types(con, asked_type)) if "filing" in kinds else ()
        decision_types = (
            tuple(_types(con, asked_type, "decision_type")) if "decision" in kinds else ()
        )
        if not filing_types and not decision_types:
            return (
                f"No {' or '.join(k for k in kinds if k != 'comment') or 'filing or decision'}"
                f" type the Board uses matches {asked_type!r}. `count_filings` without"
                " `filing_type` lists the filing types this record holds. A type is the"
                " Board's label: what a decision did — a notice of interim trail use issued —"
                " is in its summary, which `search_the_record` reads."
            )
        named = ", ".join(f"'{t}'" for t in (*filing_types, *decision_types))
        scope.append(f"of the Board's types {named}")
    party = str(args.get("party") or "").strip()
    if party:
        if len(party) < 3:
            return "`party` needs at least three characters of the name as the Board prints it."
        scope.append(f"filed for a party printed with the words {party!r}")
    body = str(args.get("deciding_body") or "").strip()
    if body:
        scope.append(f"decided by a body printed with the words {body!r}")

    limit = _small(args.get("limit"), _RECENT_DEFAULT, 1, _RECENT_CAP)
    offset = args.get("offset") or 0
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        return "`offset` must be a whole number of entries to skip, 0 or more."

    result = activity_store.activity(
        con,
        by=by,
        start=start,
        end=end,
        filters=activity_store.Filters(
            kinds=kinds,
            docket_ids=docket_ids,
            prefix=prefix,
            exclude_prefixes=excluded,
            filing_types=filing_types,
            decision_types=decision_types,
            party=party or None,
            deciding_body=body or None,
        ),
        limit=limit,
        offset=offset,
    )

    if by == "observed":
        window = f"observed by this record's forward watch from {start}" + (
            f" up to {end}" if end else " to now"
        )
    else:
        window = f"the Board dated {start} to {end or 'the latest held'}"
    scoped = (", " + "; ".join(scope)) if scope else ""
    lines = notes[:]
    if not result.total:
        names = [_KIND_NAMES[k] + "s" for k in kinds]
        kinds_said = " or ".join([", ".join(names[:-1]), names[-1]] if len(names) > 1 else names)
        lines.append(
            f"The record holds no {kinds_said} {window}{scoped}. That is an absence in this"
            " record, not proof of absence at the Board."
        )
    else:
        counted = ", ".join(
            _plural(result.by_kind[k], _KIND_NAMES[k]) for k in kinds if result.by_kind[k]
        )
        first, last = offset + 1, offset + len(result.items)
        lines.append(
            f"Records {window}{scoped}: {counted}."
            + (
                f" Showing {first}–{last}, newest first by "
                + ("when they were observed." if by == "observed" else "the Board's date.")
                if result.items
                else f" `offset` {offset} is past the last of them."
            )
        )
        captioned: set[str] = set()
        for it in result.items:
            lines.append(_activity_line(it, by, start, host, captioned))
        if result.items and last < result.total:
            lines.append(
                f"{result.total - last:,} more: call again with `offset` {last} for the next"
                f" {min(limit, result.total - last):,}."
            )
        lines.append(
            "A record entered in more than one proceeding is one entry here, under the docket"
            " nearest the top of its family, naming where else it was entered. Types, captions,"
            " summaries and the Filed For cell are the Board's as printed: a type names the kind"
            " of document, not what it accomplished, and nothing here has read the documents."
            + (" `party` matched the printed words, not a resolved party." if party else "")
        )
    lines += _window_caveats(con, by, start, end, kinds)
    return "\n".join(lines)


def _activity_line(
    it: activity_store.Item, by: str, start: str, host: str, captioned: set[str]
) -> str:
    """One entry: the proceeding, the sheet's own line, the record's address here (which
    `read_page` takes), and when it was observed or first held. A caption is printed the
    first time its proceeding appears on a page — FD 36873's runs to 120 characters, and a
    page of its notices repeated it fifty times."""
    ident = parse_docket_id(it.raw_docket)
    printed = urls.printed_docket(ident) if ident else it.raw_docket
    if it.raw_docket in captioned:
        caption = "(caption above)"
    else:
        captioned.add(it.raw_docket)
        caption = it.caption or "(caption not yet observed)"
    path = _record_path(it.entry.kind, it.entry.record_id, it.raw_docket)
    if by == "observed":
        # new, or a record held before the window that the Board's listing changed — an
        # attachment added, a summary corrected — which is why the watch saw it again
        if it.first_seen and it.first_seen < start:
            when = (
                f" — observed {it.observed_at}, held since {it.first_seen}: seen again"
                " because the Board's listing of it changed"
            )
        else:
            when = f" — observed {it.observed_at}, new to this record"
    else:
        how = {"forward": "the forward watch", "backfill": "a backfill wave"}
        when = (
            f" — first held here {it.first_seen}, from {how.get(it.first_mode or '', 'a capture')}"
            if it.first_seen
            else ""
        )
    return (
        f"- {printed} — {caption} — {_entry_line(it.entry, it.raw_docket)}"
        + (f" — here: {_site(host, path)}" if path else "")
        + when
    )


def _window_caveats(
    con: Connection, by: str, start: str, end: str | None, kinds: tuple[str, ...]
) -> list[str]:
    """What the window cannot account for, said in the answer rather than left to a
    `coverage` call a scheduled brief never makes."""
    c = coverage_store.watch(con)
    lines = []
    if by == "observed":
        if c.forward_since and start < c.forward_since:
            lines.append(
                f"The forward watch began at {c.forward_since}; nothing earlier was observed by"
                " it. History is added in backfill waves, which this window never shows —"
                " `by: board_date` reads the Board's dates over everything held."
            )
        # only the outages a late entry can fall inside (`gaps.CITED`): a documents or
        # delivery gap does not interrupt observation, and naming one told a brief the watch
        # had stopped when it had not (Codex, PR #43)
        hit = [
            g
            for g in c.gaps
            if g.failure in gaps_store.CITED
            and (not end or g.started_at < end)
            and (g.ended_at is None or g.ended_at >= start)
        ]
        if hit:
            lines.append(
                "Inside this window the watch was not keeping the record: "
                + "; ".join(f"{g.started_at} to {g.ended_at or 'open'} ({g.failure})" for g in hit)
                + ". Entries the Board posted then were observed later, in the window that"
                " observed them."
            )
        # the sheet's rule, not the newest capture of any table: the OLDEST of the record
        # tables' latest checks, so filings polled after decisions or comments stopped cannot
        # vouch for all three (Codex, PR #43)
        checked = sheet_store.last_polled(con)
        if checked:
            lines.append(f"Last checked against the Board: {checked}.")
    else:
        lines.append(
            "Filtered by the Board's own dates, over everything held, backfill waves included."
            " The Board can post an entry days after its date, so a window already read can"
            " gain entries; `by: observed` (the default) does not miss them."
        )
        for kind, walked in (
            ("filings", "filing"),
            ("decisions", "decision"),
            ("environmental comments", "comment"),
        ):
            if walked in kinds:
                lines += _open_month_caveats(
                    con,
                    start,
                    end,
                    shortfall=f"({kind} in them are missing from this list)",
                    kind=kind,
                )
    return lines


def _coverage(con: Connection, args: dict, host: str) -> str:
    c = coverage_store.coverage(con)
    return (
        "What this record holds, measured, not claimed:\n"
        f"- {_plural(c.dockets, 'proceeding')}, {_plural(c.filings, 'filing')},"
        f" {_plural(c.decisions, 'decision')},"
        f" {_plural(c.comments, 'environmental comment')}.\n"
        f"- Entries the Board dated {c.record_from} to {c.record_to}.\n"
        f"- The forward watch has run since {c.forward_since}.\n"
        f"- {c.documents:,} of the Board's own files are held by content hash;"
        f" {c.attachments_unfetched:,} listed files are not yet fetched.\n"
        # By table, never unioned: a month the comment walk has not finished says nothing
        # about filings and decisions, and one merged list told the reader it did
        # (navigation-review.md A3). A machine reading this makes the same mistake a
        # person does.
        + (
            "- Months not yet complete (neither walked nor watched), for filings and decisions:"
            f" {', '.join(coverage_store.month_runs(c.records_incomplete))}.\n"
            if c.records_incomplete
            else ""
        )
        + (
            "- Months not yet complete (neither walked nor watched), for environmental comments:"
            f" {', '.join(coverage_store.month_runs(c.comments_incomplete))}.\n"
            if c.comments_incomplete
            else ""
        )
        # History, outages and the by-design limits. A grader found this tool naming none of
        # them while the instructions above tell an assistant to repeat what the page says
        # (deferred, the independent graders, 2026-09-16): an assistant that cannot see the
        # page was answering as if the record were uniform and unbroken.
        + (
            f"- Before {c.backfill_from} a sheet is not the docket's complete history and does"
            " not claim to be. From then on, filings and decisions were added in dated waves:"
            f" {c.backfill_filings:,} filings and {c.backfill_decisions:,} decisions, counted"
            " once per docket they were entered in.\n"
            if c.backfill_from
            else "- History before the forward watch began is being added in dated waves; until"
            " then a sheet is not the docket's complete history and does not claim to be.\n"
        )
        + (
            "- The early years are thin because the Board's own table is, not because months are"
            " still to come. Filings the record holds, by the Board's year: "
            + " · ".join(f"{year}: {n:,}" for year, n in c.early_filing_years)
            + ".\n"
            if c.records_walked_from and len(c.early_filing_years) > 1
            else ""
        )
        # An outage is not a by-design limit and is never folded in with one: it is a period
        # the watch was not keeping the record, and silence about it would read as "none".
        + (
            "- Outages, periods when the watch was not keeping the record and entries were"
            " caught up late: "
            + "; ".join(f"{g.started_at} to {g.ended_at or 'open'} ({g.failure})" for g in c.gaps)
            + ". Any alert that carried the late entries said so.\n"
            if c.gaps
            else "- No outage has been recorded since the watch began.\n"
        )
        + "\nWhat is not here, by design:\n"
        + "".join(f"- {head}{rest}\n" for head, rest in coverage_store.BY_DESIGN_LIMITS)
        + f"\nThe page a person would read: {_site(host, '/coverage')}"
    )


TOOLS: tuple[Tool, ...] = (
    Tool(
        "search_the_record",
        "Search the STB record",
        "Search proceedings, parties, decisions and environmental comments by their own"
        " words, and the pages of the Board's documents by their machine-read text. A docket"
        " number is answered directly. Returns permanent addresses, never a guess: if the"
        " record holds nothing, it says so. A [page] line is text a machine read from a"
        " scan, labelled with who read it and its distance from a second reading; it is a"
        " finding aid, and the scan it links to is the record — never quote it as the"
        " Board's words. Any filter — a prefix, prefixes or dockets to leave out, a date range,"
        " a record type, the Board's own type, `sort`, `page` — returns instead one list of"
        " the filings, decisions, comments and pages that match, with a total and pages.",
        _obj(
            {
                "query": {"type": "string", "description": "What to look for."},
                "limit": {
                    "type": "integer",
                    "description": "Results, 1-50. Default 10: up to that many record"
                    " lines, and up to that many [page] lines, never more than 20. Filtered:"
                    " the size of a page of results.",
                },
                "prefix": {"type": "string", "description": "Only this docket prefix, e.g. `AB`."},
                "exclude_prefixes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": 'Docket prefixes to leave out, e.g. ["MCF"].',
                },
                "exclude_dockets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": _MAX_DOCKETS,
                    "description": "Proceedings to leave out, each with its sub-dockets, e.g."
                    ' ["FD 36873"].',
                },
                "date_from": {
                    "type": "string",
                    "description": "YYYY-MM-DD, inclusive: the Board's filed, served, or"
                    " received-or-sent date.",
                },
                "date_to": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "record_type": {
                    "type": "string",
                    "enum": ["filing", "decision", "comment", "page"],
                    "description": "Only one kind; `page` is the text of documents.",
                },
                "type": {
                    "type": "string",
                    "description": "The Board's filing or decision type, or words in it;"
                    " each type matched is named.",
                },
                "sort": {
                    "type": "string",
                    "enum": ["best", "newest"],
                    "description": "Filtered: strongest match first (default) or newest.",
                },
                "page": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Filtered: which page of results, from 1.",
                },
            },
            ["query"],
        ),
        _search,
    ),
    Tool(
        "get_docket_sheet",
        "Read a proceeding's docket sheet",
        "One chronological sheet for a proceeding: its filings, decisions and environmental"
        " comments, each with the Board's own file. Accepts anything a person would write —"
        " `FD 36873`, `AB 55 (Sub-No. 794X)`, `Docket No. NOR 42130`.",
        _obj(
            {
                "docket": {"type": "string", "description": "The docket number."},
                "limit": {"type": "integer", "description": "Entries, 1-100. Default 25."},
                "date_from": {
                    "type": "string",
                    "description": "YYYY-MM-DD, inclusive: only entries the Board dated from"
                    " this day (filed, served, or received or sent).",
                },
                "date_to": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
            },
            ["docket"],
        ),
        _docket,
    ),
    Tool(
        "get_environmental_comment",
        "Read an environmental comment",
        "One environmental comment by its Board number (`EI-34282`), with the commenter's"
        " own words as the Board printed them. Quotation, never a characterisation.",
        _obj({"number": {"type": "string", "description": "e.g. EI-34282."}}, ["number"]),
        _comment,
    ),
    Tool(
        "read_page",
        "Read the text of a page of a Board document",
        "The text of one page, or a few, of a filing's, decision's or environmental comment's"
        " file, as read from the Board's document (its own text layer, or OCR of a scan),"
        " labelled with who read it, with the Board's own file and the scan. Pass the address"
        " a `search_the_record` [page] line gave (`https://docketyard.org/decision/46314/text#p3`)"
        " or a record (`decision 46314`). The text is a reading, never the Board's words, and"
        " is served for a user's question, not for collection.",
        _obj(
            {
                "address": {
                    "type": "string",
                    "description": "A text or record address, or `filing N` / `decision N`.",
                },
                "page": {
                    "type": "integer",
                    "description": "The first page, from 1. Default: the address's #pN, else 1.",
                },
                "pages": {
                    "type": "integer",
                    "description": f"How many pages, 1-{MAX_READ_PAGES}. Default 1.",
                },
                "file": {
                    "type": "integer",
                    "description": "Which of the record's files, from 0. Default: the"
                    " address's ?file=N, else the first with text.",
                },
            },
            ["address"],
        ),
        _read,
    ),
    Tool(
        "count_filings",
        "Count filings by the Board's own filing type",
        "How many filings the Board typed a given way — `Consummation Notice`, `Trail Use"
        " Agreement Reached` — and in how many proceedings, optionally within a docket prefix"
        " (`AB`) and a filed-date range, and how many of those proceedings also hold a filing"
        " of a second type. Search results are capped and are never counts; this is the tool"
        " for 'how many'. Without `filing_type` it lists the Board's types with their counts."
        " It counts the Board's labels, not what the documents did.",
        _obj(
            {
                "filing_type": {
                    "type": "string",
                    "description": "The Board's filing type, or words in it (`trail use`"
                    " matches every trail-use type; each type counted is named).",
                },
                "prefix": {"type": "string", "description": "A docket prefix, e.g. `AB`."},
                "filed_from": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "filed_to": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "also_has": {
                    "type": "string",
                    "description": "A second filing type: how many of the proceedings counted"
                    " also hold one.",
                },
            },
            [],
        ),
        _count,
    ),
    Tool(
        "list_proceedings",
        "List the proceedings behind a count",
        "The proceedings a `count_filings` count is made of, newest first by the matching"
        " filing's date — each with its docket number, the Board's caption, the matching"
        " filings with their dates and the Board's own ids, and its address here. Takes the"
        " same filters as `count_filings`, so the same arguments give the members of the same"
        f" count. At most {_LIST_CAP} a call; `offset` reaches the rest. Use this instead of"
        " inferring which proceedings a count refers to.",
        _obj(
            {
                "filing_type": {
                    "type": "string",
                    "description": "The Board's filing type, or words in it (`trail use`"
                    " matches every trail-use type). Required.",
                },
                "prefix": {"type": "string", "description": "A docket prefix, e.g. `AB`."},
                "filed_from": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "filed_to": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "also_has": {
                    "type": "string",
                    "description": "A second filing type: list only proceedings that also hold"
                    " one, as a separate filing.",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": f"Proceedings to skip, for the page after the first"
                    f" {_LIST_CAP}.",
                },
            },
            ["filing_type"],
        ),
        _list_proceedings,
    ),
    Tool(
        "count_decisions",
        "Count decisions by the Board's type and deciding body",
        "How many decisions the Board served, in how many proceedings, optionally within a"
        " docket prefix and a served-date range, of a decision type (`Notice of Exemption`,"
        " `Environmental Review`) or from a deciding body (`Entire Board`, `Director Of"
        " Proceedings`, `Office of Chief Counsel`), with a breakdown by type and by body."
        " Search results are capped and are never counts; this is the tool for 'how many"
        " decisions'. It counts the Board's labels, not what a decision did. `recent_activity`"
        " with `by: board_date` and `record_type: decision` lists them.",
        _obj(
            {
                "decision_type": {
                    "type": "string",
                    "description": "The Board's decision type, or words in it; each type"
                    " counted is named.",
                },
                "deciding_body": {
                    "type": "string",
                    "description": "Words in the deciding body as printed (`Entire Board`).",
                },
                "prefix": {"type": "string", "description": "A docket prefix, e.g. `AB`."},
                "served_from": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "served_to": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
            },
            [],
        ),
        _count_decisions,
    ),
    Tool(
        "recent_activity",
        "What is new in the record",
        "Filings, decisions and environmental comments that arrived inside a window, across"
        " every proceeding or a list you pass: the call for 'what is new since my last run'."
        " `by: observed` (the default) is when this record's forward watch saw each one, so a"
        " filing the Board posted late still lands in the run that first saw it; `by:"
        " board_date` is the Board's own filed, served or received date over everything held."
        " Narrow by prefix, prefixes to leave out (`MCF`), record type, the Board's own filing"
        " or decision type, words in the Filed For cell as printed, or the deciding body. Each"
        " entry is in the sheet's form, with the Board's own file. Nothing about the caller is"
        " kept: a watchlist is yours, passed as `dockets` for one call.",
        _obj(
            {
                "since": {
                    "type": "string",
                    "description": "Start, inclusive: YYYY-MM-DD, or a date and time"
                    " (2026-10-01T06:00:00Z) when `by` is `observed`. Required.",
                },
                "until": {
                    "type": "string",
                    "description": "End: a time is exclusive, a day includes itself. Default: now.",
                },
                "by": {
                    "type": "string",
                    "enum": ["observed", "board_date"],
                    "description": "Which time the window is on. Default `observed`.",
                },
                "dockets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": _MAX_DOCKETS,
                    "description": "Only these proceedings, each with its sub-dockets, e.g."
                    ' ["FD 36844"]. Used for this call only.',
                },
                "prefix": {"type": "string", "description": "Only this docket prefix, e.g. `AB`."},
                "exclude_prefixes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": 'Docket prefixes to leave out, e.g. ["MCF"].',
                },
                "record_type": {
                    "type": "string",
                    "enum": ["filing", "decision", "comment"],
                    "description": "Only one kind of record.",
                },
                "type": {
                    "type": "string",
                    "description": "The Board's filing or decision type, or words in it"
                    " (`trail use`, `Notice of Exemption`); each type matched is named.",
                },
                "party": {
                    "type": "string",
                    "description": "Words in the Filed For cell as the Board printed it"
                    " (`Union Pacific`); filings only. A match on the words, not a resolved"
                    " party.",
                },
                "deciding_body": {
                    "type": "string",
                    "description": "Words in the deciding body as printed (`Entire Board`,"
                    " `Director Of Proceedings`); decisions only.",
                },
                "limit": {
                    "type": "integer",
                    "description": f"Entries, 1-{_RECENT_CAP}. Default {_RECENT_DEFAULT}.",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Entries to skip, for the next page.",
                },
            },
            ["since"],
        ),
        _recent,
    ),
    Tool(
        "coverage",
        "What this record does and does not hold",
        "The measured extent of the record: how many proceedings, filings, decisions and"
        " comments, the dates they span, and what is not yet held. Call this before"
        " characterising the record as complete.",
        _obj({}, []),
        _coverage,
    ),
)

BY_NAME = {t.name: t for t in TOOLS}


# Every tool only reads this record. Said to the client, not only enforced here: a client that
# is not told treats an unmarked tool as one that writes, and ChatGPT asks the reader to
# confirm every call (its developer-mode guide, read 2026-09-17).
READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


def tool_definitions() -> list[dict]:
    return [
        {
            "name": t.name,
            "title": t.title,
            "description": t.description,
            "inputSchema": t.schema,
            "annotations": dict(READ_ONLY),
        }
        for t in TOOLS
    ]


# --- the JSON-RPC surface -------------------------------------------------------------


def _result(request_id, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _error(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: dict, *, con: Connection, host: str, version: str) -> dict | None:
    """One JSON-RPC message in, one response out — or None for a notification, which the
    transport answers with 202 and no body."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "not a JSON-RPC 2.0 message")
    method = message.get("method")
    request_id = message.get("id")
    if method is None:  # a response to something we never asked; nothing to do
        return None
    if request_id is None:  # a notification
        return None
    if method == "initialize":
        # the guard tools/call already has: `or {}` does NOT short-circuit past a truthy
        # non-dict, so `params: [1,2]` was an unhandled 500 from one line — the defect
        # fixed for the sibling branch and not carried across to this one (ultrareview)
        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return _error(request_id, -32602, "params must be an object")
        # falling back to the version the route negotiated from the header, which it has
        # already validated: a client that set the header and left protocolVersion out of
        # params gets its own version back rather than ours
        asked = params.get("protocolVersion") or version
        return _result(
            request_id,
            {
                # an unknown request gets the newest version we speak, not the oldest we
                # tolerate: a client that supports only newer versions would otherwise be
                # handed 2025-03-26 and disconnect
                "protocolVersion": (
                    asked if asked in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
                ),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": _server_version()},
                "instructions": INSTRUCTIONS,
            },
        )
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": tool_definitions()})
    if method == "tools/call":
        # the body is unauthenticated and arbitrary: `params` and `arguments` are only
        # dicts because a client chose to send dicts, so they are checked rather than
        # trusted — otherwise `params.get` on a list is an unhandled 500 from one line
        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return _error(request_id, -32602, "params must be an object")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "arguments must be an object")
        name = params.get("name")
        tool = BY_NAME.get(name) if isinstance(name, str) else None
        if tool is None:
            return _error(request_id, -32602, f"Unknown tool: {name}")
        try:
            text = tool.run(con, arguments, host)
        except Exception as e:  # noqa: BLE001 — a tool failure is a result, not a transport error
            # The detail goes to the operator's log, not to the caller. Echoing it handed
            # an unauthenticated client internal messages — "no such table: …" names the
            # schema, and nothing an assistant does with that is good.
            print(f"mcp: {tool.name} failed: {type(e).__name__}: {e}")
            return _result(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "That request failed inside this record. Nothing is implied"
                                " about the Board's own record by the failure; try again or"
                                " read the page directly."
                            ),
                        }
                    ],
                    "isError": True,
                },
            )
        # The caveats are appended HERE, once, rather than by each tool. Three return paths
        # skipped them while a test claimed every tool carried them; a tool cannot forget
        # to do what it does not do (ultrareview).
        return _result(
            request_id,
            {
                "content": [{"type": "text", "text": f"{text}\n\n{_NOT_HELD}"}],
                "isError": False,
            },
        )
    return _error(request_id, -32601, f"Method not found: {method}")


def _server_version() -> str:
    from docketyard import __version__

    return __version__


def discovery(host: str) -> dict:
    """`/.well-known/mcp.json`: enough for a client to find the endpoint without being told.

    A convenience, not a claim of conformance — the transport spec defines the endpoint's
    behaviour, not this document's shape."""
    return {
        "name": SERVER_NAME,
        "description": (
            "A read-only surface over the public record of proceedings before the U.S."
            " Surface Transportation Board. Not the STB; every record links the agency's"
            " own file."
        ),
        "version": _server_version(),
        "protocolVersion": PROTOCOL_VERSION,
        "transport": {"type": "streamable-http", "url": _site(host, "/mcp")},
        "capabilities": {"tools": {}},
        "tools": [{"name": t.name, "title": t.title} for t in TOOLS],
        "documentation": _site(host, "/api"),
        # NOT a single licence string: the raw index is dedicated to the public domain, but
        # the party module this surface can return in search results is derived work held
        # back from that dedication pending a licence review (see /data). Labelling the
        # whole surface CC0 would be a licence promise over something not dedicated.
        "licence": {
            "record": "CC0-1.0",
            "note": (
                "The raw index is dedicated to the public domain (CC0 1.0). Party-module"
                " results — entity resolution, aliases, successions — are derived work"
                " NOT covered by that dedication, pending a licence review."
            ),
            "url": _site(host, "/data"),
        },
        "readOnly": True,
    }
