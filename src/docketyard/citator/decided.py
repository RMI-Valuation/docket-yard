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

WHEN IT WRITES (decision 8). One `extraction_run` row per (document, method, version,
channel) says a pass read EVERY displayed page of that document on that channel at `ran_at`,
and a run that finds no line still writes it — what separates read-and-found-nothing from
not-yet-read (ADR 0018 D10). An unchanged page is not rewritten: a page whose live quotations
already name its displayed text, at this version, with the lines this reading finds, is left
as it is. THE PASS READS EVERY DOCUMENT TO KNOW THAT, rather than skipping one whose texts
were all asserted before its last `ran_at`. The clock rule lost pages (code review and the
schema critic, 2026-10-03): the text loader stamps `asserted_at` when a batch starts and
commits it later, so a text committed after a run began could carry an earlier stamp and be
skipped for ever; and a page going back to an older reading, after a person's correction was
withdrawn, carried an old stamp and was never quoted again. Reading the record costs about a
minute; skipping by identity, not by clock, is what keeps an unchanged page unwritten.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from sqlite3 import Connection

from docketyard.citator import methods
from docketyard.store import supersede
from docketyard.store.db import dump_json, utcnow

METHOD = "decided-line"
# Any change to the line rule, the join, the spans or the parse below is a new version
# (decision 7): a row says which rule quoted it.
VERSION = "2026-10-03"

# A `Decided:` line: the label at the start of a line, as the Board prints it. Case as printed;
# the label is a heading the Board's template sets, not prose.
_DECIDED = re.compile(r"^[ \t]*Decided:", re.MULTILINE)
# a next line that opens with a label of its own — "Served:", "Vice Chairman Primus:" — is not
# the date the empty `Decided:` was waiting for
# no digits in it: "September 30 2016 Served:" is the date the label waited for, with a
# label after it, not a label (code review, 2026-10-03)
_LABEL = re.compile(r"^\s*[A-Z][A-Za-z.' -]{0,40}:")

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
    unchanged: int = 0  # pages whose live quotations already quote their displayed text
    pages: int = 0
    lines: int = 0
    retired: int = 0  # rows retired because their page was read again
    stale: int = 0  # rows retired because their text left the display
    human_pages: int = 0  # pages a person's reading displays, not read


def parse(printed: str) -> str | None:
    """The ISO reading of a quoted line, or None when it will not parse. A reading, never a
    correction: `October 15, 2016` printed is 2016-10-15, whatever the decision's body says."""
    after = printed.split(":", 1)[1] if ":" in printed else printed
    # the first match whose word is a month: "No 12 2004 … October 5, 2017" reads the second
    for m in _DATE.finditer(after):
        month = _MONTHS.get(m.group(1).lower())
        if month is None:
            continue
        try:
            return date(int(m.group(3)), month, int(m.group(2))).isoformat()
        except ValueError:  # February 30 is shaped right and is not a day
            return None
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
    """Every document a decision carries: the set `citator.walk` reads, without the family
    closure it builds beside it, which adds no document."""
    return [
        sha
        for (sha,) in con.execute(
            "SELECT DISTINCT document_sha256 FROM decision_attachment"
            " WHERE document_sha256 IS NOT NULL ORDER BY 1"
        )
    ]


def _retire_stale(con: Connection, now: str) -> int:
    """Decision 6: EVERY run retires every quotation whose text is no longer displayed, dated,
    at itself, whichever documents it read — a limited run included (Copilot, PR #44: a sweep
    narrowed to the documents read left stale quotations live, against the accepted decision).
    A document a limited run never reached therefore has its stale rows retired at themselves,
    and the run that reads it writes replacements that point back at nothing."""
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


def _live_on_page(con: Connection, sha: str, page_no: int) -> list[tuple]:
    """Every live machine row of this METHOD on one page, whatever its version, text or
    channel (decision 5): (decided_id, ordinal, text_id, method_version, printed_text,
    decided_date)."""
    return con.execute(
        "SELECT decided_id, ordinal, text_id, method_version, printed_text, decided_date"
        " FROM decision_decided_date WHERE document_sha256 = ? AND page_no = ? AND method = ?"
        " AND reading_channel <> ? AND superseded_by IS NULL ORDER BY ordinal, decided_id",
        (sha, page_no, METHOD, methods.HUMAN),
    ).fetchall()


def read_document(
    con: Connection,
    sha: str,
    out: Summary,
    *,
    now: str | None = None,
    machine: set[str] | None = None,
) -> None:
    """One document, every machine channel its display shows. The caller commits."""
    now = now or utcnow()
    machine = machine if machine is not None else methods.machine_channels(con)
    by_channel: dict[str, list[tuple]] = {}
    for row in con.execute(_PAGES, (sha,)).fetchall():
        _, _, channel, role, *_ = row
        if role == "human" or channel not in machine:
            out.human_pages += 1  # decision 3: a person's reading is not a model's to quote
            continue
        by_channel.setdefault(channel, []).append(row)
    for channel, pages in sorted(by_channel.items()):
        # A BLANK PAGE IS READ TOO, and its run recorded (Copilot, PR #44): migration 0018 makes
        # an empty `document_text.text` a completed reading, and decision 8 says a run reads
        # every displayed page. A channel of blank pages is read and found nothing — which is
        # what `extraction_run` exists to say, rather than leaving it looking unread.
        found = 0
        for text_id, page_no, _, _, render, engine, engine_version, _, text in pages:
            page_lines = lines(text or "")
            found += len(page_lines)
            out.pages += 1
            live = _live_on_page(con, sha, page_no)
            # decision 8: unchanged is "these rows already quote THIS text, at this version,
            # line for line", decided by identity and never by a clock
            if [(r[1], r[2], r[3], r[4], r[5]) for r in live] == [
                (ln.ordinal, text_id, VERSION, ln.printed_text, ln.decided_date)
                for ln in page_lines
            ]:
                out.unchanged += 1
                continue
            # decision 5: retire EVERY live machine row of this METHOD on the page first — a
            # map keyed by ordinal kept one of two rows sharing a line (code review)
            for decided_id, *_ in live:
                supersede.retire(con, "decision_decided_date", "decided_id", decided_id, at=now)
            out.retired += len(live)
            # each retired row points at the new row on its line; the first per line is enough
            successor_of: dict[int, list[int]] = {}
            for decided_id, ordinal, *_ in live:
                successor_of.setdefault(ordinal, []).append(decided_id)
            ocr = channel == "ocr"
            for line in page_lines:
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
                        dump_json({"page": page_no, "spans": line.spans}),
                        sha,
                        now,
                    ),
                ).lastrowid
                for old_id in successor_of.get(line.ordinal, ()):
                    con.execute(
                        "UPDATE decision_decided_date SET superseded_by = ? WHERE decided_id = ?",
                        (new_id, old_id),
                    )
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
    machine = methods.machine_channels(con)
    for n, sha in enumerate(_documents(con)):
        # documents, not readings: one document can be read on two channels (Copilot, PR #44)
        if limit is not None and n >= limit:
            break
        read_document(con, sha, out, machine=machine)
        con.commit()
        if n and n % 2000 == 0:
            log(f"  {n:,} documents: {out.lines:,} lines on {out.pages:,} pages")
    # AFTER the documents, not before: a page read above retired its old rows and pointed each
    # at its replacement on the same (page, ordinal) (decision 6). What is still stale now is a
    # page no longer read — its text gone from the display — and retires at itself.
    out.stale = _retire_stale(con, utcnow())
    con.commit()
    return out
