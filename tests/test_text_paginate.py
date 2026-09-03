"""`docketyard text paginate` — the pass that fills `document_pagination` (migration 0018).

The table is published and `page_count` is the coverage denominator, so every test here is
about a row that must or must not be written, and what the pass says when it is not.
"""

import argparse
import json
import sqlite3

import pytest

from docketyard import cli
from docketyard.store import db
from docketyard.text import paginate

STAMP = "2026-09-03T00:00:00+00:00"
SHA_A = "a" * 64
SHA_B = "b" * 64
ALLOWED = frozenset({"paginated", "not-paginable", "failed"})


def _store(tmp_path, *shas):
    con = db.connect(tmp_path / "s.sqlite")
    for sha in shas or (SHA_A, SHA_B):
        con.execute(
            "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
            " VALUES (?, 1, 'pdf', ?)",
            (sha, STAMP),
        )
    con.commit()
    return con


def _record(sha, pages=9, image_only=False, tool="pymupdf", tool_version="1.24.10", **over):
    """What `extract_text.py` writes: the header fields first, `page_text` LAST."""
    rec = {
        "document_sha256": sha,
        "size_bytes": 1234,
        "method": "text-layer",
        "method_version": "1",
        "tool": tool,
        "tool_version": tool_version,
        "extracted_at": STAMP,
        "pages": pages,
        "chars": 1598 * pages,
        "image_only": image_only,
        "text_sha256": "c" * 64,
        "page_text": ["page text"] * pages,
    }
    rec.update(over)
    return rec


def _row(rec):
    return paginate.from_record(rec, ALLOWED)


def _write(root, rec, *, name=None, tail=None):
    """A record under `<root>/<xx>/<sha>.json`. `tail` replaces the serialised `page_text`
    with raw bytes, to prove the pass never reads that far."""
    sha = name or rec["document_sha256"]
    shard = root / sha[:2]
    shard.mkdir(parents=True, exist_ok=True)
    body = json.dumps(rec, ensure_ascii=False)
    if tail is not None:
        body = body[: body.index('"page_text"')] + '"page_text": ' + tail
    (shard / f"{sha}.json").write_text(body, encoding="utf-8")
    return shard / f"{sha}.json"


def _live(con, sha):
    return con.execute(
        "SELECT outcome, page_count, had_text_layer, method, method_version, confidence,"
        " confidence_state FROM document_pagination"
        " WHERE document_sha256 = ? AND superseded_by IS NULL",
        (sha,),
    ).fetchall()


# --- the record, read from its head ---------------------------------------------------------


def test_only_the_head_of_a_record_is_read(tmp_path):
    """`page_text` holds the whole document and is written last; the pass reads the fields
    before it and never parses the text. Here the tail is not even JSON."""
    root = tmp_path / "text"
    path = _write(root, _record(SHA_A, pages=12), tail="[" + "x" * 200_000)
    with pytest.raises(ValueError):
        json.loads(path.read_text(encoding="utf-8"))  # the file as a whole is unparseable
    row = _row(paginate.read_head(path))
    assert row == paginate.Pagination(SHA_A, "paginated", 12, 1, "pymupdf", "1.24.10")


def test_the_method_is_the_tool_and_the_text_layer_answer_is_the_tools():
    """`method` is the tool that counted (migration 0018's weld: both values under ONE
    method), not the extraction's channel name. `image_only` negates to `had_text_layer`."""
    assert _row(_record(SHA_A, image_only=True)).had_text_layer == 0
    assert _row(_record(SHA_A, image_only=False)).had_text_layer == 1
    row = _row(_record(SHA_A, tool="pdftotext", tool_version="24.02.0"))
    assert (row.method, row.method_version) == ("pdftotext", "24.02.0")


def test_a_record_is_validated_and_never_coerced():
    """`bool("false")` is True and `int(9.7)` is 9: a coerced record would publish an
    inverted text-layer answer or a truncated count. Each of these is refused instead."""
    for broken in (
        {k: v for k, v in _record(SHA_A).items() if k != "pages"},
        _record(SHA_A, tool=""),
        _record(SHA_A, tool_version=None),
        _record(SHA_A, pages=-1),
        _record(SHA_A) | {"pages": 9.7},
        _record(SHA_A) | {"pages": "9"},
        _record(SHA_A) | {"pages": True},
        _record(SHA_A, image_only="false"),
        _record(SHA_A, image_only=0),
        _record(SHA_A, outcome="unknown"),
        _record("short"),
        ["not", "an", "object"],
    ):
        with pytest.raises(paginate.Unreadable):
            _row(broken)


def test_the_outcome_vocabulary_is_the_stores(tmp_path):
    """A record may say the file did not paginate, in the store's own words: the vocabulary
    is read from `pagination_outcome_vocab`, not copied into Python, so widening it is the
    INSERT migration 0018 made it a table for."""
    con = _store(tmp_path)
    assert paginate.outcomes(con) == ALLOWED
    row = _row(_record(SHA_A, outcome="failed"))
    assert (row.outcome, row.page_count, row.had_text_layer) == ("failed", None, None)
    con.execute("INSERT INTO pagination_outcome_vocab VALUES ('encrypted', 'test')")
    row = paginate.from_record(_record(SHA_A, outcome="encrypted"), paginate.outcomes(con))
    assert row.outcome == "encrypted"


# --- the row, and what supersedes it --------------------------------------------------------


def test_a_pass_writes_one_unmeasured_row_per_document_with_its_provenance(tmp_path):
    con = _store(tmp_path)
    assert paginate.paginate_document(con, _row(_record(SHA_A, pages=9))) == "asserted"
    assert paginate.paginate_document(con, _row(_record(SHA_B, pages=3, image_only=True))) == (
        "asserted"
    )
    assert _live(con, SHA_A) == [("paginated", 9, 1, "pymupdf", "1.24.10", 0, "unmeasured")]
    assert _live(con, SHA_B) == [("paginated", 3, 0, "pymupdf", "1.24.10", 0, "unmeasured")]


def test_a_restart_asserts_nothing_twice(tmp_path):
    """Resumable: the same answer again is `unchanged`, at any version of the same tool —
    the live row already says what the record's pages are and who first found it."""
    con = _store(tmp_path)
    paginate.paginate_document(con, _row(_record(SHA_A)))
    assert paginate.paginate_document(con, _row(_record(SHA_A))) == "unchanged"
    newer = _row(_record(SHA_A, tool_version="1.26.0"))
    assert paginate.paginate_document(con, newer) == "unchanged"
    assert con.execute("SELECT COUNT(*) FROM document_pagination").fetchone()[0] == 1


def test_a_changed_answer_supersedes_rather_than_updating(tmp_path):
    """`page_count` is a published denominator: a re-pagination that disagrees is a new row
    pointing back at the old one, with `superseded_at` — never an UPDATE in place."""
    con = _store(tmp_path)
    paginate.paginate_document(con, _row(_record(SHA_A, pages=12)))
    newer = _row(_record(SHA_A, pages=13, tool_version="1.26.0"))
    assert paginate.paginate_document(con, newer, now=STAMP) == "superseded"
    rows = con.execute(
        "SELECT pagination_id, page_count, method_version, superseded_by, superseded_at"
        " FROM document_pagination ORDER BY pagination_id"
    ).fetchall()
    assert rows == [(1, 12, "1.24.10", 2, STAMP), (2, 13, "1.26.0", None, None)]
    assert _live(con, SHA_A)[0][1] == 13


def test_a_different_tool_supersedes_even_when_it_agrees(tmp_path):
    """`had_text_layer` is the TOOL's judgement (the weld in migration 0018) and `method` is
    what a correction traces it to, so an agreeing answer from another tool is a new row."""
    con = _store(tmp_path)
    paginate.paginate_document(con, _row(_record(SHA_A, pages=12)))
    other = _row(_record(SHA_A, pages=12, tool="pdftotext", tool_version="24.02.0"))
    assert paginate.paginate_document(con, other) == "superseded"
    assert _live(con, SHA_A)[0][3:5] == ("pdftotext", "24.02.0")


def test_a_human_page_count_is_held_against_the_routine_pass(tmp_path):
    """ADR 0007 § Validation: a human assertion is never overwritten by a model re-run. The
    trigger would refuse the write; refusing here makes it a counted outcome."""
    con = _store(tmp_path)
    paginate.paginate_document(con, _row(_record(SHA_A, pages=12)))
    con.execute(
        "UPDATE document_pagination SET superseded_by = 1, superseded_at = ?"
        " WHERE pagination_id = 1",
        (STAMP,),
    )
    con.execute(
        "INSERT INTO document_pagination (document_sha256, outcome, page_count,"
        " had_text_layer, method, method_version, asserted_at, confidence, confidence_state)"
        " VALUES (?, 'paginated', 9, 1, 'human', 'unversioned', ?, 1, 'human')",
        (SHA_A, STAMP),
    )
    con.execute("UPDATE document_pagination SET superseded_by = 2 WHERE pagination_id = 1")
    again = _row(_record(SHA_A, pages=12, tool_version="1.26.0"))
    assert paginate.paginate_document(con, again) == "human_held"
    assert _live(con, SHA_A) == [("paginated", 9, 1, "human", "unversioned", 1, "human")]


def test_a_record_for_bytes_the_store_does_not_hold_writes_nothing(tmp_path):
    con = _store(tmp_path, SHA_A)
    assert paginate.paginate_document(con, _row(_record(SHA_B))) == "unknown_document"
    assert con.execute("SELECT COUNT(*) FROM document_pagination").fetchone()[0] == 0


def test_a_failed_open_is_a_row_with_no_count(tmp_path):
    con = _store(tmp_path)
    paginate.paginate_document(con, _row(_record(SHA_A, outcome="failed")))
    assert _live(con, SHA_A) == [("failed", None, None, "pymupdf", "1.24.10", 0, "unmeasured")]
    with pytest.raises(sqlite3.IntegrityError):  # and the weld holds: no count without opening
        con.execute(
            "INSERT INTO document_pagination (document_sha256, outcome, page_count,"
            " had_text_layer, method, method_version, asserted_at, confidence,"
            " confidence_state) VALUES (?, 'failed', 4, 1, 'pymupdf', '1', ?, 0, 'unmeasured')",
            (SHA_B, STAMP),
        )


# --- the pass over a directory --------------------------------------------------------------


def test_the_pass_walks_the_shards_and_counts_what_it_could_not(tmp_path):
    con = _store(tmp_path)
    root = tmp_path / "text"
    _write(root, _record(SHA_A, pages=9), tail="[" + "y" * 50_000)  # the text is never read
    _write(root, _record(SHA_B, pages=2, image_only=True))
    _write(root, _record("e" * 64))  # bytes the store does not hold
    _write(root, _record("f" * 64), name="9" * 64)  # filed under another name: refused
    (root / "cd").mkdir()
    (root / "cd" / ("c" * 64 + ".json")).write_text("{not json", encoding="utf-8")
    (root / "_manifest.json").write_text("{}", encoding="utf-8")  # the root's own file
    lines = []
    totals = paginate.run(con, root, log=lines.append)
    assert totals == {"asserted": 2, "unknown_document": 1, "unreadable": 2}
    assert len(lines) == 2 and all("unreadable" in line for line in lines)
    assert _live(con, SHA_A)[0][1] == 9 and _live(con, SHA_B)[0][2] == 0
    other = db.connect(tmp_path / "s.sqlite")  # committed: another connection sees it
    assert other.execute("SELECT COUNT(*) FROM document_pagination").fetchone()[0] == 2
    # and a restart over the same directory asserts nothing new
    assert paginate.run(con, root, log=lines.append)["unchanged"] == 2


def test_one_refused_document_is_rolled_back_alone_and_the_batch_lands(tmp_path):
    """The commit is per batch, the rollback per document: a record the store refuses (here
    a tool named 'human', which the CHECK binding the two encodings of human rejects) is
    undone inside its savepoint, and both its neighbours are committed with it."""
    con = _store(tmp_path, SHA_A, SHA_B, "c" * 64)
    root = tmp_path / "text"
    _write(root, _record(SHA_A, pages=9))
    _write(root, _record(SHA_B, pages=4, tool="human", tool_version="unversioned"))
    _write(root, _record("c" * 64, pages=2))
    lines = []
    totals = paginate.run(con, root, log=lines.append, commit_every=1000)
    assert totals == {"asserted": 2, "failed": 1}
    assert "failed" in lines[0] and "IntegrityError" in lines[0]
    other = db.connect(tmp_path / "s.sqlite")
    assert other.execute(
        "SELECT document_sha256 FROM document_pagination ORDER BY 1"
    ).fetchall() == [(SHA_A,), ("c" * 64,)]
    # the refused document's live row, had it had one, is not left retired at itself
    paginate.paginate_document(con, _row(_record(SHA_B, pages=4)))
    con.commit()
    _write(root, _record(SHA_B, pages=5, tool="human", tool_version="unversioned"))
    assert paginate.run(con, root, log=lines.append)["failed"] == 1
    assert _live(con, SHA_B)[0][1] == 4


def test_a_store_that_cannot_be_written_aborts_the_pass_rather_than_counting(tmp_path):
    """With the 30 s busy timeout, a held write lock would turn every remaining document
    into a wait, a `failed` line and an exit of 0. The pass stops at the first one."""
    con = _store(tmp_path)
    root = tmp_path / "text"
    _write(root, _record(SHA_A, pages=9))
    _write(root, _record(SHA_B, pages=4))
    holder = sqlite3.connect(tmp_path / "s.sqlite", timeout=0)
    holder.execute("BEGIN IMMEDIATE")  # the write lock, held for the whole test
    con.execute("PRAGMA busy_timeout = 50")
    lines = []
    totals = paginate.run(con, root, log=lines.append)
    assert totals == {"aborted": 1}
    assert "aborted" in lines[0] and "locked" in lines[0]
    holder.rollback()
    assert paginate.run(con, root, log=lines.append)["asserted"] == 2


def test_the_verb_says_when_nothing_was_attached(tmp_path, capsys):
    """Exit status is for the operator's cron: 1 when the pass attached nothing (a wrong
    `--db`, an empty root), when the store refused a document, or when it aborted."""
    con = _store(tmp_path, SHA_A)
    con.close()
    root = tmp_path / "text"
    _write(root, _record(SHA_A, pages=9))
    ns = argparse.Namespace(db=str(tmp_path / "s.sqlite"), what="paginate", root=str(root))
    assert cli._text(ns) == 0
    assert "'asserted': 1" in capsys.readouterr().out
    con = db.connect(tmp_path / "s.sqlite")
    assert _live(con, SHA_A)[0][1] == 9
    con.close()
    # every record names bytes another store holds: a wrong --db, and not a success
    _write(root, _record("e" * 64))
    (root / SHA_A[:2] / f"{SHA_A}.json").unlink()
    assert cli._text(ns) == 1
    assert "names a document this store holds" in capsys.readouterr().out
    # a document the store refused: the count is printed and the status says look
    _write(root, _record(SHA_A, pages=9, tool="human", tool_version="unversioned"))
    assert cli._text(ns) == 1
    assert "refused 1" in capsys.readouterr().out
    ns.root = str(tmp_path / "nowhere")
    assert cli._text(ns) == 1  # no directory is a refusal, not an empty pass
    ns.root = str(tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    assert cli._text(ns) == 1
    assert "no extraction record" in capsys.readouterr().out
    (tmp_path / "empty" / "ab").mkdir()
    (tmp_path / "empty" / "ab" / "x.json").write_text("{not json", encoding="utf-8")
    assert cli._text(ns) == 1
    assert "none readable" in capsys.readouterr().out
