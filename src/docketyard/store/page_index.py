"""`page_fts` kept in step with `document_text_display` (migration 0018, ADR 0022 D4).

External-content FTS5 never syncs itself, and the view it indexes is a RULE, not a table: a
row enters it when it becomes the page's live primary with no live human row, and leaves it
when it is superseded OR when a human row lands on the page — the second with no write to
the row itself, so no trigger on the row could fire. Every writer to `document_text` owes
these three calls, and there is one definition of them so that the review layer's human
writer (Migration B) and the loader agree on what "as indexed" meant.

`leave` deletes WITH THE TEXT AS INDEXED, which FTS5 requires: a 'delete' carrying different
text does not error, it leaves stale tokens behind. `document_text` is append-only and its
`text` immutable, so the row itself supplies it — through `dy_display_text`, as the view and
`enter` do (migration 0020, `store/display.py`): the indexed bytes are the displayed bytes,
with contact details already omitted, so no MATCH can find what no page shows.

WHAT THIS CANNOT KNOW: whether a row is in the index is inferred from the view's rule as it
stands NOW, not recorded. A human row inserted without `leave(primary)` leaves the index
holding text the view no longer shows; the loader then sees the page as not visible and
neither deletes nor inserts. Until the review layer's half exists, the human writer is by
hand and owes the calls by hand. `search_meta.page_built` is not bumped here — that is the
search wiring (`docs/ocr-migration.md` item 11), owed.
"""

# The signature `search.rebuild_pages` writes while it owns the index. Spelled here rather
# than imported so this module keeps its one import of nothing; `test_page_search` asserts
# the two strings are the same, which is the only way they can drift.
REBUILDING = "rebuilding"


class Rebuilding(RuntimeError):
    """A rebuild owns the index. A writer that went ahead anyway would index a row the
    rebuild's scan is about to index again — external-content FTS5 takes the duplicate
    rowid in silence, and a later `leave` clears one copy and leaves the other's tokens
    behind, which is the corruption `search_pages` reports as a malformed disk image
    (code review, 2026-09-04)."""


def owned_by_rebuild(con) -> bool:
    """Whether `search rebuild-pages` is in flight (or died in flight). Read ONCE at the
    top of a pass, never per row: it is a one-row lookup, but a pass writes a million."""
    row = con.execute("SELECT signature FROM search_meta WHERE key = 'page_built'").fetchone()
    return bool(row) and row[0] == REBUILDING


def visible(con, document_sha256: str, page_no: int) -> bool:
    """Whether a primary on this page is in the display view: no live human row holds it."""
    return (
        con.execute(
            "SELECT 1 FROM document_text WHERE document_sha256 = ? AND page_no = ?"
            " AND reading_role = 'human' AND superseded_by IS NULL",
            (document_sha256, page_no),
        ).fetchone()
        is None
    )


def enter(con, text_id: int, text: str) -> None:
    """`text` is the STORED reading; the index takes it as the view shows it."""
    con.execute(
        "INSERT INTO page_fts (rowid, text) VALUES (?, dy_display_text(?))", (text_id, text)
    )


def leave(con, text_id: int) -> None:
    row = con.execute(
        "SELECT dy_display_text(text) FROM document_text WHERE text_id = ?", (text_id,)
    ).fetchone()
    if row is None:
        raise LookupError(f"document_text {text_id} does not exist; nothing to leave the index")
    con.execute(
        "INSERT INTO page_fts (page_fts, rowid, text) VALUES ('delete', ?, ?)", (text_id, row[0])
    )
