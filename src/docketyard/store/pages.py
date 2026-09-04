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


# THE ONE SELECT over the display view and the page's live second reading. `readings` and
# `by_text_ids` both use it, so the display rule and the band's join condition — a distance
# measured against a superseded primary is not this page's band (migration 0018) — have one
# home; the two leading columns are the row's identity, the rest build a `PageText`.
_SELECT = (
    "SELECT d.text_id, d.document_sha256,"
    " d.page_no, d.text, d.reading_role, d.reading_channel, d.method,"
    " d.method_version, d.render_profile, d.route_class, d.asserted_at,"
    " s.method, s.method_version, s.render_profile, s.agreement_distance,"
    " s.agreement_method, s.agreement_method_version, s.agreement_against = d.text_id"
    " FROM document_text_display d"
    " LEFT JOIN document_text s ON s.document_sha256 = d.document_sha256"
    "   AND s.page_no = d.page_no AND s.reading_role = 'second' AND s.superseded_by IS NULL"
)


def _page(r) -> PageText:
    return PageText(*r[2:11], Second(*r[11:17], bool(r[17])) if r[11] is not None else None)


def readings(con: Connection, document_sha256: str) -> list[PageText]:
    """Every page of the document the display shows, in page order, with its band operand."""
    rows = con.execute(
        _SELECT + " WHERE d.document_sha256 = ? ORDER BY d.page_no", (document_sha256,)
    ).fetchall()
    return [_page(r) for r in rows]


def by_text_ids(con: Connection, text_ids: list[int]) -> dict[int, tuple[str, PageText]]:
    """The display rows whose ids these are — a search's hits — in one query:
    text_id -> (document_sha256, the page). An id the view no longer shows is absent."""
    if not text_ids:
        return {}
    marks = ",".join("?" for _ in text_ids)
    rows = con.execute(_SELECT + f" WHERE d.text_id IN ({marks})", list(text_ids)).fetchall()
    return {r[0]: (r[1], _page(r)) for r in rows}


def label(p: PageText) -> str:
    """Who read the page: the sentence the text page prints and a search hit carries (ADR
    0021 D7). One home, so the two surfaces cannot describe one reading differently."""
    if p.reading_role == "human":
        return f"Corrected by a person ({p.asserted_at[:10]})."
    if p.reading_channel == "text-layer":
        return f"The publisher's own text layer, read by {p.method} {p.method_version}."
    routed = f", routed as {p.route_class}" if p.route_class else ""
    return f"Machine-read by {p.method} {p.method_version} at render {p.render_profile}{routed}."


def band(p: PageText) -> str:
    """The band's operand, or why there is none — never a threshold or a confidence word
    (ADR 0021 D8). A human row has no band and says nothing."""
    if p.reading_role == "human":
        return ""
    s = p.second
    if s is None:
        if p.reading_channel == "text-layer":
            return "Read once; no second reading to compare it with, so no band."
        return "No second reading yet, so no band."
    if s.distance is not None and s.against_shown:
        return (
            f"Distance from the second reading ({s.method} {s.method_version}):"
            f" {s.distance:.3f} by {s.distance_method} {s.distance_method_version}"
            " — 0 is agreement."
        )
    if s.distance is not None:
        return (
            f"A second reading exists ({s.method} {s.method_version}); its distance was"
            " measured against an earlier reading of this page, so no band."
        )
    return (
        f"A second reading exists ({s.method} {s.method_version}); its distance from this"
        " one has not been computed, so no band."
    )


def pagination(con: Connection, document_sha256: str) -> Pagination | None:
    row = con.execute(
        "SELECT outcome, page_count, method, method_version FROM document_pagination"
        " WHERE document_sha256 = ? AND superseded_by IS NULL",
        (document_sha256,),
    ).fetchone()
    return Pagination(*row) if row else None
