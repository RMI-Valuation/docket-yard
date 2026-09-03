"""`store.batches` — the loop the passes share, and the transaction it claims to hold."""

import sqlite3

from docketyard.store import batches, db


def _store(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, n INTEGER UNIQUE)")
    con.commit()
    return con


def _count(tmp_path):
    other = sqlite3.connect(tmp_path / "s.sqlite")
    try:
        return other.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        other.close()


def test_the_commit_is_per_batch_and_the_transaction_is_real(tmp_path):
    """A SAVEPOINT issued outside a transaction is the outermost one, and releasing it is a
    COMMIT — so the first version committed per document while saying it batched. The
    loop begins a transaction first, and another connection sees nothing until the batch."""
    con = _store(tmp_path)
    seen_by_other = []

    def one(n):
        con.execute("INSERT INTO t (n) VALUES (?)", (n,))
        assert con.in_transaction
        seen_by_other.append(_count(tmp_path))
        return "ok"

    totals = batches.run(
        con, ((str(n), n) for n in range(7)), one, log=lambda s: None, commit_every=3
    )
    assert totals == {"ok": 7}
    # inside the loop the other connection saw 0, 0, 0, 3, 3, 3, 6: batches of three
    assert seen_by_other == [0, 0, 0, 3, 3, 3, 6]
    assert _count(tmp_path) == 7 and not con.in_transaction


def test_a_document_the_writer_refuses_is_rolled_back_alone(tmp_path):
    """Any exception but the store's own is the document's: rolled back to its savepoint,
    counted `failed`, and the pass goes on. The first version caught IntegrityError only,
    so a loader's own refusal escaped through RELEASE with the partial document kept."""
    con = _store(tmp_path)
    lines = []

    def one(n):
        con.execute("INSERT INTO t (n) VALUES (?)", (n,))
        if n == 2:
            con.execute("INSERT INTO t (n) VALUES (?)", (n * 100,))
            raise ValueError("the writer found something wrong")
        if n == 4:
            con.execute("INSERT INTO t (n) VALUES (?)", (1,))  # the store refuses: UNIQUE
        return "ok"

    totals = batches.run(con, ((str(n), n) for n in range(6)), one, log=lines.append)
    assert totals == {"ok": 4, "failed": 2}
    assert [r[0] for r in con.execute("SELECT n FROM t ORDER BY n")] == [0, 1, 3, 5]
    assert "failed 2: ValueError" in lines[0] and "failed 4: IntegrityError" in lines[1]


def test_the_store_failing_aborts_the_pass_and_rolls_the_batch_back(tmp_path):
    con = _store(tmp_path)
    holder = sqlite3.connect(tmp_path / "s.sqlite", timeout=0)
    holder.execute("BEGIN IMMEDIATE")
    con.execute("PRAGMA busy_timeout = 50")
    lines = []
    totals = batches.run(
        con,
        ((str(n), n) for n in range(3)),
        lambda n: (con.execute("INSERT INTO t (n) VALUES (?)", (n,)), "ok")[1],
        log=lines.append,
    )
    assert totals == {"aborted": 1}
    assert "aborted at 0" in lines[0] and "locked" in lines[0]
    holder.rollback()
    assert _count(tmp_path) == 0 and not con.in_transaction


def test_an_item_that_is_an_error_is_counted_not_raised(tmp_path):
    con = _store(tmp_path)
    items = [("a", 1), ("b", ValueError("bad")), ("c", 2)]
    lines = []
    totals = batches.run(
        con,
        items,
        lambda n: (con.execute("INSERT INTO t (n) VALUES (?)", (n,)), "ok")[1],
        log=lines.append,
    )
    assert totals == {"ok": 2, "unreadable": 1}
    assert lines == ["  unreadable b: bad"]


def test_walk_visits_the_shards_in_order_and_yields_a_readers_error(tmp_path):
    root = tmp_path / "root"
    for shard, name in (("ab", "ab1"), ("ab", "ab0"), ("00", "zz")):
        (root / shard).mkdir(parents=True, exist_ok=True)
        (root / shard / f"{name}.json").write_text("{}", encoding="utf-8")
    (root / "_manifest.json").write_text("{}", encoding="utf-8")  # the root's own file

    def read(path):
        if path.stem == "ab0":
            raise ValueError("no")
        return path.stem

    labels = [label for label, _ in batches.walk(root, read)]
    assert labels == ["00/zz.json", "ab/ab0.json", "ab/ab1.json"]
    things = [thing for _, thing in batches.walk(root, read)]
    assert things[0] == "zz" and isinstance(things[1], ValueError) and things[2] == "ab1"
