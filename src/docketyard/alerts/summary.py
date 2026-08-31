"""One description of a record event, from which every channel renders: the email text,
the Atom entry, the webhook JSON. Nothing here decides who receives it. Every field is
quoted from the event's own payload — the Board's dates, captions and summaries as
printed — and every entry links to the Board's file.
"""

from dataclasses import asdict, dataclass, field
from sqlite3 import Connection

from docketyard.ingest.dockets import parse_docket_id
from docketyard.store.db import load_json
from docketyard.web import labels, urls


@dataclass(frozen=True)
class EventSummary:
    event_id: int
    kind: str  # filing | decision | file_replaced
    docket: str  # printed, e.g. FD 36873 (Sub-No. 1)
    docket_url: str
    first: bool  # a new record, as opposed to a re-observation with changes
    record_id: str | None  # the Board's filing or decision id
    date: str | None  # the Board's date, as printed
    url: str | None  # the record's permanent address here
    record_kind: str | None = None  # filing | decision — for a replaced file, whose it was
    board_files: list[str] = field(default_factory=list)
    filing_type: str | None = None
    filed_for: str | None = None
    deciding_body: str | None = None
    decision_type: str | None = None
    summary: str | None = None
    observed_at: str = ""  # when this record observed it

    def title(self) -> str:
        if self.kind == "file_replaced":
            on = (
                f"{self.record_kind} {self.record_id}"
                if self.record_id
                else "a record it holds (not identified)"
            )
            return f"{self.docket} — the Board replaced a file on {on}"
        what = "new" if self.first else "updated"
        return f"{self.docket} — {what} {self.kind} {self.record_id}, {self.date or 'undated'}"

    def lines(self) -> list[str]:
        """The email's rendering: a head line and indented detail."""
        out = [self.title()]
        if self.kind == "decision":
            out.append(
                f"  {self.deciding_body or labels.kind_label('decision', self.decision_type)}"
            )
            if self.summary:
                out.append(f"  {self.summary}")
        elif self.kind == "filing":
            out.append(f"  {self.filing_type or 'Filing'}")
            if self.filed_for:
                out.append(f"  Filed for: {self.filed_for}")
        if self.url:
            out.append(f"  {self.url}")
        for f in self.board_files:
            out.append(f"  The Board's file: {f}")
        return out

    def as_dict(self) -> dict:
        return asdict(self)


def event_summary(con: Connection, event_id: int, site: str) -> EventSummary:
    etype, docket_id, payload, source_key, capture_id = con.execute(
        "SELECT event_type, docket_id, payload, source_key, capture_id FROM event"
        " WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    p = load_json(payload)
    raw = con.execute("SELECT raw_docket FROM docket WHERE docket_id = ?", (docket_id,)).fetchone()
    ident = parse_docket_id(raw[0]) if raw else None
    printed = urls.printed_docket(ident) if ident else "?"
    docket_url = f"https://{site}{urls.docket_path(ident)}" if ident else f"https://{site}/"
    observed = con.execute(
        "SELECT captured_at FROM capture WHERE capture_id = ?", (capture_id,)
    ).fetchone()
    observed_at = observed[0] if observed else ""
    if etype == "document_replaced":
        # Ordered, not `LIMIT 1` on an arbitrary row: one URL can be owned by records in
        # more than one table, and an unowned row (or a comment, whose owner lives in a
        # third column) would otherwise win and report a NAMED filing as "not identified".
        owner = con.execute(
            "SELECT stb_filing_id, stb_decision_id, comment_source_key FROM document_source"
            " WHERE document_sha256 = ? AND source_url = ?"
            " ORDER BY (stb_filing_id IS NULL AND stb_decision_id IS NULL"
            "           AND comment_source_key IS NULL) LIMIT 1",
            (p.get("new"), p.get("source_url")),
        ).fetchone()
        filing_id, decision_id, comment_key = owner or (None, None, None)
        # a comment is addressed by its number; the docket half of the key is already the
        # docket this alert names
        comment_number = comment_key.split("|")[-1] if comment_key else None
        path = (
            urls.decision_path(decision_id)
            if decision_id
            else urls.filing_path(filing_id)
            if filing_id
            else urls.comment_path(comment_number)
            if comment_number
            else None
        )
        return EventSummary(
            event_id=event_id,
            kind="file_replaced",
            docket=printed,
            docket_url=docket_url,
            first=False,
            record_id=decision_id or filing_id or comment_number,
            record_kind=(
                "decision"
                if decision_id
                else "filing"
                if filing_id
                else "environmental comment"
                if comment_number
                else None
            ),
            date=None,
            url=f"https://{site}{path}" if path else None,
            board_files=[p["source_url"]] if p.get("source_url") else [],
            observed_at=observed_at,
        )
    record_id = source_key.split("|")[-1]
    kind = "decision" if etype == "decision_observed" else "filing"
    first = (
        con.execute(
            "SELECT COUNT(*) FROM event WHERE source_key = ? AND event_type = ? AND event_id < ?",
            (source_key, etype, event_id),
        ).fetchone()[0]
        == 0
    )
    path = urls.decision_path(record_id) if kind == "decision" else urls.filing_path(record_id)
    return EventSummary(
        event_id=event_id,
        kind=kind,
        docket=printed,
        docket_url=docket_url,
        first=first,
        record_id=record_id,
        record_kind=kind,
        date=p.get("date_printed") or p.get("date"),
        url=f"https://{site}{path}",
        board_files=list(p.get("attachments") or []),
        filing_type=p.get("filing_type") if kind == "filing" else None,
        filed_for=labels.display_filed_for(p["filed_for"])
        if kind == "filing" and p.get("filed_for")
        else None,
        deciding_body=p.get("deciding_body") if kind == "decision" else None,
        decision_type=p.get("decision_type") if kind == "decision" else None,
        summary=p.get("summary") if kind == "decision" else None,
        observed_at=observed_at,
    )
