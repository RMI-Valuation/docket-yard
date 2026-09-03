"""Retire at itself, insert, repoint: how a live row is replaced under a partial live index.

The idiom is 0006_parties.sql's and every assertion table since carries it. It lived in the
citator's loader until 2026-09-03; `text/paginate.py` is the second caller and
`document_text`'s loader the third, so it lives with the store now. Both helpers are
table-agnostic by requirement: the table, the id column and the SQL are the caller's.
"""


def retire(con, table: str, id_col: str, row_id: int, *, at: str | None = None) -> None:
    """0006_parties.sql's order, forced by the partial live index: retire the old row by
    pointing it at ITSELF so the replacement can take the key, then repoint it once the new
    id exists. Inserting first fails, because for that instant two rows on one key would be
    live. The caller holds the transaction — a crash between the two steps leaves a
    self-pointer that cannot be told apart from a deliberate retirement.

    `at` writes `superseded_at` IN THE SAME STATEMENT, for the tables that carry
    `CHECK ((superseded_by IS NULL) = (superseded_at IS NULL))` — `document_pagination` and
    `document_text` (0018), `decision_decided_date` (0019) — which refuse the pointer alone.
    The citator's families carry no `superseded_at` (deferred.md, 2026-09-01) and pass
    nothing."""
    if at is None:
        con.execute(f"UPDATE {table} SET superseded_by = ? WHERE {id_col} = ?", (row_id, row_id))
    else:
        con.execute(
            f"UPDATE {table} SET superseded_by = ?, superseded_at = ? WHERE {id_col} = ?",
            (row_id, at, row_id),
        )


def if_changed(
    con,
    *,
    table: str,
    id_col: str,
    where: str,
    where_args: tuple,
    compare: str,
    values: tuple,
    insert: str,
    insert_args: tuple,
    retire_at: str | None = None,
) -> bool:
    """Write an assertion only if it says something the live row does not. Returns True when
    a row was written.

    The alternative — `INSERT OR IGNORE` on the live key — keeps the FIRST answer for ever,
    and for a target the registry did not yet hold the first answer is `unresolved`. Waves
    2-3 are still adding dockets, so that would quietly cap what the citator can ever show.
    """
    live = con.execute(
        f"SELECT {id_col}, {compare} FROM {table} WHERE {where} AND superseded_by IS NULL",
        where_args,
    ).fetchone()
    if live is not None and tuple(live[1:]) == tuple(values):
        return False  # the same answer, already asserted at this method and version
    if live is not None:
        retire(con, table, id_col, live[0], at=retire_at)
    cur = con.execute(insert, insert_args)
    if live is not None:
        con.execute(
            f"UPDATE {table} SET superseded_by = ? WHERE {id_col} = ?", (cur.lastrowid, live[0])
        )
    return True
