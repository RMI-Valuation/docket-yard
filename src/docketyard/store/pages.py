"""What a reader is shown of a document's text: the display rows, page by page, each with
the operand of its confidence band (ADR 0021 D7-D9).

`document_text_display` IS the rule — the live human row if one exists, else the live
primary — and this reads it rather than restating it. The band is a separate read against
the page's live `second` row, because the view carries no `agreement_distance` on purpose
(migration 0018): every row of it would be NULL and a consumer would render "no band" always,
which under D8 is itself a claim. Here the operand is carried beside the text or it is absent,
and a text-layer page says it has none because it was read once.
"""

from dataclasses import dataclass
from sqlite3 import Connection


@dataclass(frozen=True)
class Second:
    """The page's second reading and its distance from the primary it was measured against."""

    method: str
    method_version: str
    render_profile: str
    distance: float | None
    distance_method: str | None
    distance_method_version: str | None
    # whether the distance was measured against THE PRIMARY NOW SHOWN. A primary is superseded
    # routinely and the second is not re-measured with it; a distance against an earlier
    # reading is not this page's band (ADR 0021 D8, migration 0018 on `agreement_against`).
    against_shown: bool


@dataclass(frozen=True)
class PageText:
    page_no: int
    text: str
    reading_role: str  # 'primary' | 'human'
    reading_channel: str  # 'text-layer' | 'ocr' | 'human'
    method: str
    method_version: str
    render_profile: str
    route_class: str | None
    asserted_at: str
    second: Second | None


@dataclass(frozen=True)
class Pagination:
    outcome: str
    page_count: int | None
    method: str
    method_version: str


def readings(con: Connection, document_sha256: str) -> list[PageText]:
    """Every page of the document the display shows, in page order, with its band operand."""
    rows = con.execute(
        "SELECT d.page_no, d.text, d.reading_role, d.reading_channel, d.method,"
        " d.method_version, d.render_profile, d.route_class, d.asserted_at,"
        " s.method, s.method_version, s.render_profile, s.agreement_distance,"
        " s.agreement_method, s.agreement_method_version, s.agreement_against = d.text_id"
        " FROM document_text_display d"
        " LEFT JOIN document_text s ON s.document_sha256 = d.document_sha256"
        "   AND s.page_no = d.page_no AND s.reading_role = 'second' AND s.superseded_by IS NULL"
        " WHERE d.document_sha256 = ? ORDER BY d.page_no",
        (document_sha256,),
    ).fetchall()
    return [
        PageText(*r[:9], Second(*r[9:15], bool(r[15])) if r[9] is not None else None) for r in rows
    ]


def pagination(con: Connection, document_sha256: str) -> Pagination | None:
    row = con.execute(
        "SELECT outcome, page_count, method, method_version FROM document_pagination"
        " WHERE document_sha256 = ? AND superseded_by IS NULL",
        (document_sha256,),
    ).fetchone()
    return Pagination(*row) if row else None
