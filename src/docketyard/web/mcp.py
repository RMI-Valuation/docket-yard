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
from datetime import date as Day
from sqlite3 import Connection

from docketyard.ingest.dockets import find_docket, parse_docket_id
from docketyard.store import coverage as coverage_store
from docketyard.store import search as search_store
from docketyard.store import sheet as sheet_store
from docketyard.store.sheet import present
from docketyard.web import urls

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
- If a tool returns nothing, say the record holds nothing — never fill the gap from memory. \
Inventing a docket number or a service date is the specific failure this surface exists to \
prevent."""

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


def _site(host: str, path: str) -> str:
    return f"https://{host}{path}"


# --- the tools themselves -------------------------------------------------------------


def _search(con: Connection, args: dict, host: str) -> str:
    text = str(args.get("query", "")).strip()
    if not text:
        return "Nothing was searched for."
    limit = max(1, min(int(args.get("limit", 10) or 10), 50))
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
    for h in hits:
        # the caption first where there is one, the identifier beside it. An assistant
        # handed "[docket] FD 30101 — 0 filings" has been told nothing about the
        # proceeding, which is navigation-review.md § B on the third surface — fixed on
        # the page and in /suggest, and left here until the schema-critic caught it.
        named = f"{h.caption} ({h.title})" if h.caption else h.title
        lines.append(f"[{h.kind}] {named} — {h.fact} — {_site(host, h.path)}")
    for h in pages:
        # a page of machine-read text is handed over WITH who read it, the band's operand
        # or its absence, and the scan (ADR 0021 D7): the text is a finding aid, the scan
        # is the record, and an assistant told less would repeat the reading as a fact
        named = f"{h.caption} ({h.title})" if h.caption else h.title
        lines.append(
            f"[page] {named} — {h.fact} — {_site(host, h.path)} — {h.label}"
            + (f" {h.band}" if h.band else "")
            + f" The scan: {_site(host, h.scan)}. Machine-read text: check it against the scan."
        )
    if found.truncated and pages:
        # `len(pages)`, not PAGE_LIMIT: `_search` may have asked for fewer than twenty, and
        # the fold makes a short list the common case rather than the odd one. `and pages`
        # because every matched row may be dropped — a comment attachment's pages have no
        # address — and "more pages than the 0 shown" after listing nothing is not a
        # sentence to hand an assistant (code review, 2026-09-04).
        lines.append(f"…and more pages than the {len(pages)} shown; narrow the words.")
    return "\n".join(lines)


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
    if s.is_index:
        # a series carries no entries of its own; the assistant is handed the index the page
        # and the JSON both carry, not an empty "Entries, newest first:" (code review)
        head.append(
            f"This number is a series: it holds no record of its own, and the"
            f" {len(s.sub_dockets)} proceedings under it each keep their own."
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
    rows = ["Entries, newest first:"]
    for e in s.entries[:limit]:
        who = e.filed_for_raw or e.submitter or e.organisation or ""
        board = e.attachments[0].url if e.attachments else ""
        # the proceeding an entry was actually entered in — a family folds onto one sheet,
        # but attributing a sub-docket's filing to the parent misstates the record
        entered = parse_docket_id(e.docket_raw)
        where = (
            f" — in {urls.printed_docket(entered)}"
            if entered and e.docket_raw != s.raw_docket
            else ""
        )
        # printed, not raw: `also_in` carries the store's own ids (AB_55_785_X), which
        # resolve at neither docketyard.org nor stb.gov — and the `where` clause one line
        # above already canonicalises the same class of value (ultrareview)
        printed_also = [
            urls.printed_docket(i) for i in map(parse_docket_id, e.also_in) if i is not None
        ]
        also = f" — also entered in {', '.join(printed_also)}" if printed_also else ""
        rows.append(
            f"- {e.date or 'undated'} [{e.kind}] {e.record_id}"
            + (f" — {e.type}" if e.type else "")
            + where
            + also
            + (f" — as printed: {who}" if who else "")
            + (f" — the Board's file: {board}" if board else "")
        )
    more = ""
    if len(s.entries) > limit:
        more = (
            f"\n({len(s.entries) - limit} older entries not shown — these are the"
            f" {limit} most recent, not the whole sheet. Raise `limit` or read the sheet.)"
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
        return f"The record holds no environmental comment numbered {number}."
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


def _types(con: Connection, asked: str) -> list[str]:
    """The Board's own filing types an asked name matches: that type alone when the name IS
    one (case aside), else every type containing it. Matched against the types the store
    holds, so an assistant is told which labels were counted rather than trusted to have
    guessed the Board's spelling."""
    held = [t for (t,) in con.execute("SELECT DISTINCT filing_type FROM filing") if t]
    needle = asked.strip().casefold()
    exact = [t for t in held if t.casefold() == needle]
    return exact or sorted(t for t in held if needle in t.casefold())


def _count(con: Connection, args: dict, host: str) -> str:
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
    scope = (f" in {prefix} proceedings" if prefix else "") + (
        f", filed {since or 'from the first'} to {until or 'the latest held'}"
        if since or until
        else ""
    )
    base = " FROM filing f JOIN docket d ON d.docket_id = f.docket_id WHERE " + " AND ".join(where)

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
    open_months = [
        m
        for m in coverage_store.filings_incomplete(con)
        if (not since or m >= since[:7]) and (not until or m <= until[:7])
    ]
    if open_months:
        lines.append(
            "Months this record has not finished for filings, inside the range counted"
            " (the count is short by whatever they hold):"
            f" {', '.join(coverage_store.month_runs(tuple(open_months)))}."
        )
    walked_from = coverage_store.filings_walked_from(con)
    if walked_from and (not since or since[:7] < walked_from):
        lines.append(
            f"This record's walk of filings begins at {walked_from}: nothing is claimed about"
            " filings the Board dated earlier."
        )
    lines.append(f"What the record holds and does not: {_site(host, '/coverage')}")
    return "\n".join(lines)


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
        " Board's words.",
        _obj(
            {
                "query": {"type": "string", "description": "What to look for."},
                "limit": {
                    "type": "integer",
                    "description": "Results, 1-50. Default 10: up to that many record"
                    " lines, and up to 20 [page] lines whatever is asked.",
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


def tool_definitions() -> list[dict]:
    return [
        {"name": t.name, "title": t.title, "description": t.description, "inputSchema": t.schema}
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
