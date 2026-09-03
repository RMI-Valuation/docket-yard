"""`page_fts` kept in step with `document_text_display` (migration 0018, ADR 0022 D4).

External-content FTS5 never syncs itself, and the view it indexes is a RULE, not a table: a
row enters it when it becomes the page's live primary with no live human row, and leaves it
when it is superseded OR when a human row lands on the page — the second with no write to
the row itself, so no trigger on the row could fire. Every writer to `document_text` owes
these three calls, and there is one definition of them so that the review layer's human
writer (Migration B) and the loader agree on what "as indexed" meant.

`leave` deletes WITH THE TEXT AS INDEXED, which FTS5 requires: a 'delete' carrying different
text does not error, it leaves stale tokens behind. `document_text` is append-only and its
`text` immutable, so the row itself supplies it.

WHAT THIS CANNOT KNOW: whether a row is in the index is inferred from the view's rule as it
stands NOW, not recorded. A human row inserted without `leave(primary)` leaves the index
holding text the view no longer shows; the loader then sees the page as not visible and
neither deletes nor inserts. Until the review layer's half exists, the human writer is by
hand and owes the calls by hand. `search_meta.page_built` is not bumped here — that is the
search wiring (`docs/ocr-migration.md` item 11), owed.
"""


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
    con.execute("INSERT INTO page_fts (rowid, text) VALUES (?, ?)", (text_id, text))


def leave(con, text_id: int) -> None:
    row = con.execute("SELECT text FROM document_text WHERE text_id = ?", (text_id,)).fetchone()
    if row is None:
        raise LookupError(f"document_text {text_id} does not exist; nothing to leave the index")
    con.execute(
        "INSERT INTO page_fts (page_fts, rowid, text) VALUES ('delete', ?, ?)", (text_id, row[0])
    )
