"""The decided-date extraction pass: the `Decided:` lines a decision's document prints, quoted.

ADR 0023's addendum of 2026-09-16, accepted 2026-10-03, and migration 0034. The operator chose
to build this pass and nothing downstream of it: what lands here is a QUOTATION of a line,
never the decision's date (decision 9). A compilation reprints a run of earlier decisions'
`Decided:` lines, every one of them a true quotation of a different decision; choosing which
line is a decision's own date is a consumer's job, no consumer is built, and the table stays
held from the public snapshot.

WHAT IT READS (decision 3). The page's row in `document_text_display` chooses the reading — the
one a reader is shown — and the pass reads `document_text.text` through that `text_id`, never
the view's masked text, so `printed_text` and its spans are the stored bytes. A page whose
displayed reading is a person's is skipped and nothing is written for it: 0019 binds
`reading_channel = 'human'` to `method = 'human'`, and a model row cannot claim to have read a
person's correction.

HOW IT WRITES (decisions 5 and 6). Reading a page first retires every live machine row of this
`METHOD` on that page, whatever its version or text, dated in the same transaction; then it
writes what it found, and points each retired row at the new row on the same `(page_no,
ordinal)`, or leaves it pointing at itself. A line a newer version no longer finds therefore
does not stay live. Every run also retires, at itself, every row whose `text_id` has left the
display — the page's text replaced, or a person's reading now shown in its place.

WHEN IT READS (decision 8). One `extraction_run` row per (document, method, version, channel)
says a pass read EVERY displayed page of that document on that channel at `ran_at`. A channel
is read again only when a displayed text on it was asserted at or after that row's `ran_at`,
or when the method's version moves; an unchanged page is not rewritten. A run that finds no
line still writes its row, which is what separates read-and-found-nothing from not-yet-read
(ADR 0018 D10).
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from sqlite3 import Connection

from docketyard.citator import methods

# the walk's selection of decision-carried documents, so the two passes read the same bytes
from docketyard.citator.walk import _DOCUMENTS
from docketyard.store import supersede
from docketyard.store.db import utcnow

METHOD = "decided-line"
# Any change to the line rule, the join, the spans or the parse below is a new version
# (decision 7): a row says which rule quoted it.
VERSION = "2026-10-03"

# A `Decided:` line: the label at the start of a line, as the Board prints it. Case as printed;
# the label is a heading the Board's template sets, not prose.
_DECIDED = re.compile(r"^[ \t]*Decided:", re.MULTILINE)
# a next line that opens with a label of its own — "Served:", "Vice Chairman Primus:" — is not
# the date the empty `Decided:` was waiting for
_LABEL = re.compile(r"^\s*[A-Z][\w.' -]{0,40}:")

_MONTHS = {
    m: i
    for i, names in enumerate(
        (
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sept", "sep"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ),
        start=1,
    )
    for m in names
}
# Spacing as the Board's templates and its OCR produce it, measured on the 2026-09-17 copy:
# "March 20,1997", "June 23 , 1998", "September1, 2026", "January, 22, 2004". A wider reading of
# the same printed date, never a correction of it; "April 21, 20004" still reads as nothing.
_DATE = re.compile(r"\b([A-Za-z]+)\.?,?\s*(\d{1,2})\s*,?\s*(\d{4})\b")

# The page each document DISPLAYS, with the reading behind it. The display view chooses; the
# stored text is read through its `text_id`, never the view's masked `text`.
_PAGES = """
SELECT v.text_id, v.page_no, v.reading_channel, v.reading_role, v.render_profile,
       t.method, t.method_version, t.asserted_at, t.text
  FROM document_text_display v
  JOIN document_text t ON t.text_id = v.text_id
 WHERE v.document_sha256 = ?
 ORDER BY v.page_no
"""


@dataclass
class Line:
    ordinal: int
    printed_text: str
    decided_date: str | None
    spans: list[list] = field(default_factory=list)  # [start, end, raw], ADR 0026's shape


@dataclass
class Summary:
    documents: int = 0  # (document, channel) pairs read
    skipped: int = 0  # read before at this version, nothing new displayed
    pages: int = 0
    lines: int = 0
    retired: int = 0  # rows retired because their page was read again
    stale: int = 0  # rows retired because their text left the display
    human_pages: int = 0  # pages a person's reading displays, not read


def parse(printed: str) -> str | None:
    """The ISO reading of a quoted line, or None when it will not parse. A reading, never a
    correction: `October 15, 2016` printed is 2016-10-15, whatever the decision's body says."""
    after = printed.split(":", 1)[1] if ":" in printed else printed
    m = _DATE.search(after)
    if not m:
        return None
    month = _MONTHS.get(m.group(1).lower())
    if month is None:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(2))).isoformat()
    except ValueError:  # February 30 is shaped right and is not a day
        return None


def lines(text: str) -> list[Line]:
    """Every `Decided:` line on one page's text, in order, with its spans into that text.

    Decision 7: the line as printed. When nothing follows the colon, the line and the next
    non-empty line joined by one space — unless that next line opens with a label of its own.
    """
    out: list[Line] = []
    for ordinal, m in enumerate(_DECIDED.finditer(text)):
        start = m.start() + (len(m.group(0)) - len(m.group(0).lstrip()))
        end = text.find("\n", start)
        end = len(text) if end < 0 else end
        first = text[start:end].rstrip()
        spans = [[start, start + len(first), " ".join(first.split())]]
        printed = first
        if not first[len("Decided:") :].strip():
            # nothing after the colon: the date is on the next non-empty line, if that line is
            # not a label of its own
            pos = end
            while pos < len(text):
                nxt_end = text.find("\n", pos + 1)
                nxt_end = len(text) if nxt_end < 0 else nxt_end
                raw = text[pos:nxt_end]
                if raw.strip():
                    if not _LABEL.match(raw):
                        lead = len(raw) - len(raw.lstrip())
                        body = raw.strip()
                        s = pos + lead
                        spans.append([s, s + len(body), " ".join(body.split())])
                        printed = f"{first.strip()} {body}"
                    break
                pos = nxt_end
        out.append(
            Line(
                ordinal=ordinal,
                printed_text=printed.strip(),
                decided_date=parse(printed),
                spans=spans,
            )
        )
    return out


def _documents(con: Connection) -> list[str]:
    """Every document a decision carries — the walk's own selection, so the two passes read
    the same set of bytes."""
    return sorted({sha for sha, *_ in con.execute(_DOCUMENTS)})


def _retire_stale(con: Connection, now: str) -> int:
    """Decision 6: a quotation whose text is no longer displayed is retired, dated, at
    itself. A replacement that lands later is a new row; nothing repoints across runs."""
    stale = [
        r
        for (r,) in con.execute(
            "SELECT decided_id FROM decision_decided_date d"
            " WHERE d.superseded_by IS NULL AND d.text_id IS NOT NULL"
            " AND NOT EXISTS (SELECT 1 FROM document_text_display v WHERE v.text_id = d.text_id)"
        )
    ]
    for row_id in stale:
        supersede.retire(con, "decision_decided_date", "decided_id", row_id, at=now)
    return len(stale)


def _last_run(con: Connection, sha: str, channel: str) -> str | None:
    row = con.execute(
        "SELECT ran_at FROM extraction_run WHERE document_sha256 = ? AND method = ?"
        " AND method_version = ? AND reading_channel = ?",
        (sha, METHOD, VERSION, channel),
    ).fetchone()
    return row[0] if row else None


def read_document(con: Connection, sha: str, out: Summary, *, now: str | None = None) -> None:
    """One document, every machine channel its display shows. The caller commits."""
    now = now or utcnow()
    machine = methods.machine_channels(con)
    by_channel: dict[str, list[tuple]] = {}
    for row in con.execute(_PAGES, (sha,)).fetchall():
        text_id, page_no, channel, role, *_ = row
        if role == "human" or channel not in machine:
            out.human_pages += 1  # decision 3: a person's reading is not a model's to quote
            continue
        by_channel.setdefault(channel, []).append(row)
    for channel, pages in sorted(by_channel.items()):
        if not any((p[8] or "").strip() for p in pages):
            continue  # nothing to read is not a reading (the walk's rule)
        ran = _last_run(con, sha, channel)
        # decision 8: read when never read at this version, or a displayed text on this
        # channel was asserted at or after the run that read it
        if ran is not None and all(p[7] < ran for p in pages):
            out.skipped += 1
            continue
        found = 0
        for text_id, page_no, _, _, render, engine, engine_version, _, text in pages:
            # decision 5: retire every live machine row of this METHOD on this page first
            old = {
                ordinal: decided_id
                for decided_id, ordinal in con.execute(
                    "SELECT decided_id, ordinal FROM decision_decided_date"
                    " WHERE document_sha256 = ? AND page_no = ? AND method = ?"
                    " AND reading_channel <> ? AND superseded_by IS NULL",
                    (sha, page_no, METHOD, methods.HUMAN),
                )
            }
            for decided_id in old.values():
                supersede.retire(con, "decision_decided_date", "decided_id", decided_id, at=now)
            out.retired += len(old)
            ocr = channel == "ocr"
            for line in lines(text or ""):
                new_id = con.execute(
                    "INSERT INTO decision_decided_date (document_sha256, date_kind, page_no,"
                    " ordinal, reading_channel, method, method_version, render_profile,"
                    " reading_method, reading_method_version, printed_text, decided_date,"
                    " text_id, source_location, asserted_from_document, asserted_at,"
                    " confidence, confidence_state)"
                    " VALUES (?, 'decided', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0,"
                    " 'unmeasured')",
                    (
                        sha,
                        page_no,
                        line.ordinal,
                        channel,
                        METHOD,
                        VERSION,
                        render,
                        engine if ocr else None,
                        engine_version if ocr else None,
                        line.printed_text,
                        line.decided_date,
                        text_id,
                        json.dumps({"page": page_no, "spans": line.spans}),
                        sha,
                        now,
                    ),
                ).lastrowid
                if line.ordinal in old:  # the retired row points at its replacement
                    con.execute(
                        "UPDATE decision_decided_date SET superseded_by = ? WHERE decided_id = ?",
                        (new_id, old[line.ordinal]),
                    )
                found += 1
            out.pages += 1
        out.lines += found
        out.documents += 1
        con.execute(
            "INSERT INTO extraction_run (document_sha256, method, method_version,"
            " reading_channel, outcome, pages_read, targets_emitted, ran_at)"
            " VALUES (?, ?, ?, ?, 'read', ?, ?, ?)"
            " ON CONFLICT (document_sha256, method, method_version, reading_channel) DO UPDATE"
            " SET outcome = excluded.outcome, pages_read = excluded.pages_read,"
            " targets_emitted = excluded.targets_emitted, ran_at = excluded.ran_at",
            (sha, METHOD, VERSION, channel, len(pages), found, now),
        )


def run(con: Connection, *, limit: int | None = None, log=print) -> Summary:
    """The pass over every decision-carried document, committed per document so a run killed
    part-way keeps what it read and the poller is never locked out for the whole pass."""
    out = Summary()
    for n, sha in enumerate(_documents(con)):
        if limit is not None and out.documents >= limit:
            break
        read_document(con, sha, out)
        con.commit()
        if n and n % 2000 == 0:
            log(f"  {n:,} documents: {out.lines:,} lines on {out.pages:,} pages")
    # AFTER the documents, not before: a page read above retired its old rows and pointed each
    # at its replacement on the same (page, ordinal) (decision 6). What is still stale now is a
    # page no longer read — its text gone from the display — and retires at itself.
    out.stale = _retire_stale(con, utcnow())
    con.commit()
    return out
