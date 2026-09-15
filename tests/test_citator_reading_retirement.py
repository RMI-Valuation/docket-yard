"""A retraction retires the key's readings too (ADR 0018 addendum, Accepted 2026-09-13), and
migration 0029 retires the ones v2026.09.15's re-load left stranded."""

import re
import sqlite3
from importlib import resources
from pathlib import Path

import pytest

from docketyard.citator import keys, load, methods
from docketyard.store import db, dump
from tests.test_citator_pipeline import _scored, _store
from tests.test_citator_retraction import NOW, OLD, _load, _walked
from tests.test_citator_schema import KEY, STAMP, _citation, _extraction_measurement, _key

PRECHECK = Path(__file__).parents[1] / "infra" / "deploy" / "0029-precheck.sql"
ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")  # `db.utcnow()`'s form

DOC = KEY[0]
PARENT = KEY  # retracted to a sub-docket successor, as 768 of production's 903 were
SUCCESSOR = (DOC, 3, "stb", "FD 36873 (1)")
ALONE = (DOC, 3, "stb", "AB 55")  # retracted at itself, as the other 135 were
LIVE = (DOC, 3, "stb", "EP 445")  # a key whose citation is still live
MISFIT = (DOC, 3, "stb", "MC 1")  # a same-key pointer the view and the trigger both refuse


# --- the loader ------------------------------------------------------------------------


def _reading_id(con, key: str) -> int:
    return con.execute(
        "SELECT reading_id FROM citation_reading WHERE target_key = ? ORDER BY reading_id", (key,)
    ).fetchone()[0]


def _retracted_to_its_successor(tmp_path):
    """The parent key a v1 pass read, as an older finder's, then retracted by a pass that keys
    the sub-docket instead — `test_citator_retraction`'s wrapped sub-number, with a reading."""
    con = _store(tmp_path)
    stamps = _scored(con)
    parent = {"page": 4, "target": "FD 36873", "quoted": "See FD 36873, slip op. at 2."}
    _load(con, _walked(parent), stamps)
    con.execute("UPDATE citation SET method_version = ? WHERE target_key = 'FD 36873'", (OLD,))
    return con, stamps, _load(con, _walked(NOW), stamps)


def test_a_retracted_keys_reading_is_retired_with_it_and_points_at_the_successor(tmp_path):
    con, stamps, result = _retracted_to_its_successor(tmp_path)
    assert (result.retracted, result.readings_retired) == (1, 1)
    old, new = _reading_id(con, "FD 36873"), _reading_id(con, "FD 36873 (1)")
    pointer, at = con.execute(
        "SELECT superseded_by, superseded_at FROM citation_reading WHERE reading_id = ?", (old,)
    ).fetchone()
    assert pointer == new, "the successor key's live reading on the same channel"
    assert ISO.match(at)
    retraction = con.execute(
        "SELECT citation_id FROM citation WHERE target_key = 'FD 36873'"
    ).fetchone()[0]
    assert con.execute(
        "SELECT reading_id, citation_id, reason, method, method_version, retired_at"
        " FROM citation_reading_retirement"
    ).fetchall() == [(old, retraction, "retracted-key", methods.EXTRACTOR, "v1", at)]
    assert con.execute("SELECT COUNT(*) FROM citation_reading_residue").fetchone() == (0,)
    # the page's machine readings are now only the live key's, so nothing is left to refuse
    assert con.execute(
        "SELECT target_key FROM citation_reading WHERE superseded_by IS NULL"
    ).fetchall() == [("FD 36873 (1)",)]
    again = _load(con, _walked(NOW), stamps)
    assert (again.retracted, again.readings_retired) == (0, 0), "a restart retires nothing more"


def test_with_no_successor_the_reading_is_retired_at_itself(tmp_path):
    con = _store(tmp_path)
    stamps = _scored(con)
    gone = {"page": 5, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."}
    _load(con, _walked(gone, pages=(5,)), stamps)
    con.execute("UPDATE citation SET method_version = ? WHERE target_key = 'EP 445'", (OLD,))
    other = {"page": 5, "target": "FD 36873", "quoted": "See FD 36873, slip op. at 2."}
    assert _load(con, _walked(other, pages=(5,)), stamps).readings_retired == 1
    rid = _reading_id(con, "EP 445")
    assert con.execute(
        "SELECT superseded_by FROM citation_reading WHERE reading_id = ?", (rid,)
    ).fetchone() == (rid,)


def test_a_retirement_row_is_held_to_its_reading_its_date_and_its_retraction(tmp_path):
    con, _, _ = _retracted_to_its_successor(tmp_path)
    old, new = _reading_id(con, "FD 36873"), _reading_id(con, "FD 36873 (1)")
    retraction, successor = (
        con.execute("SELECT citation_id FROM citation WHERE target_key = ?", (k,)).fetchone()[0]
        for k in ("FD 36873", "FD 36873 (1)")
    )
    at = con.execute(
        "SELECT superseded_at FROM citation_reading WHERE reading_id = ?", (old,)
    ).fetchone()[0]
    insert = (
        "INSERT INTO citation_reading_retirement (reading_id, citation_id, reason, method,"
        " method_version, retired_at) VALUES (?, ?, 'retracted-key', 'm', 'v', ?)"
    )
    # a LIVE reading breaks both rules (its key's citation is live too), and SQLite does not
    # promise which BEFORE INSERT trigger fires first
    with pytest.raises(sqlite3.IntegrityError, match="names a retired reading|names its key's"):
        con.execute(insert, (new, successor, at))
    with pytest.raises(sqlite3.IntegrityError, match="names a retired reading"):
        con.execute(insert, (old, retraction, "2020-01-01T00:00:00+00:00"))  # another date
    with pytest.raises(sqlite3.IntegrityError, match="names its key's retraction"):
        con.execute(insert, (old, successor, at))  # a citation of another, live key
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("UPDATE citation_reading_retirement SET method = 'x'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("DELETE FROM citation_reading_retirement")


# --- stores as production holds them -----------------------------------------------------


def _document(con) -> None:
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'pdf', ?)",
        (DOC, STAMP),
    )


def _reading(con, key) -> int:
    """A live text-layer reading as the migration-0028 copy left it: `pre-0026`."""
    return con.execute(
        "INSERT INTO citation_reading (citing_document, page, target_kind, target_key,"
        " reading_channel, text_ref, cited_raw, quoted_passage, method, method_version,"
        " asserted_at, confidence, confidence_state)"
        " VALUES (?, ?, ?, ?, 'text-layer', 'pre-0026', ?, 'q', 'regex-docket-cite',"
        " '2026-09-01', ?, 0, 'unmeasured')",
        (*key, key[3], STAMP),
    ).lastrowid


def _alone(con, m: int) -> int:
    """A key retracted at itself, its reading left live. Returns the retraction's id."""
    _key(con, ALONE)
    cid = _citation(con, m, key=ALONE)
    con.execute("UPDATE citation SET superseded_by = citation_id WHERE citation_id = ?", (cid,))
    _reading(con, ALONE)
    return cid


def _to_a_successor(con, m: int) -> tuple[int, int]:
    """The production majority: the parent retracted to the sub-docket row that pass wrote, and
    THAT row since replaced on its own key by a later load. The pointer must follow the key.
    Returns (the retraction's id, the successor key's live reading)."""
    _key(con, PARENT)
    _key(con, SUCCESSOR)
    parent = _citation(con, m, key=PARENT)
    first = _citation(con, m, key=SUCCESSOR)
    con.execute("UPDATE citation SET superseded_by = ? WHERE citation_id = ?", (first, parent))
    con.execute("UPDATE citation SET superseded_by = citation_id WHERE citation_id = ?", (first,))
    later = _citation(con, m, key=SUCCESSOR)
    con.execute("UPDATE citation SET superseded_by = ? WHERE citation_id = ?", (later, first))
    _reading(con, PARENT)
    return parent, _reading(con, SUCCESSOR)


def _live(con, m: int) -> int:
    _key(con, LIVE)
    _citation(con, m, key=LIVE)
    return _reading(con, LIVE)


def _misfit(con, m: int) -> None:
    """A key whose newest citation row points BACK at an older row of its own key — no shipped
    writer makes one, and both the view and the retirement trigger must refuse it."""
    _key(con, MISFIT)
    older = _citation(con, m, key=MISFIT)
    con.execute("UPDATE citation SET superseded_by = citation_id WHERE citation_id = ?", (older,))
    newer = _citation(con, m, key=MISFIT)
    con.execute("UPDATE citation SET superseded_by = ? WHERE citation_id = ?", (older, newer))
    _reading(con, MISFIT)


def _decided_by_review(con, key) -> None:
    """An open review question on the key — `load._decided`'s second test, keyed by
    `keys.render`. Foreign keys off, as a fixture needs no reviewer row — after a commit,
    because the pragma is a no-op inside a transaction (`db.migrate` says the same)."""
    con.commit()
    con.execute("PRAGMA foreign_keys = OFF")
    con.execute(
        "INSERT INTO review_action (reviewer_id, queue, target_table, target_keyed, target_key,"
        " target_key_version, method_version, decision, asserted_at)"
        " VALUES (1, 'citation_exposed', 'citation_resolution', 'natural', ?, 'v1', 'v1',"
        " 'escalated', ?)",
        (keys.render(*key), STAMP),
    )
    con.commit()
    con.execute("PRAGMA foreign_keys = ON")


def _decided_by_resolution(con, key) -> None:
    """A live `human` resolution on the key — `load._decided`'s first test."""
    con.execute(
        "INSERT INTO citation_resolution (citing_document, page, target_kind, target_key, method,"
        " method_version, reading_channel, outcome, asserted_at, confidence, confidence_state)"
        " VALUES (?, ?, ?, ?, 'human', 'v1', 'human', 'unresolved', ?, 1.0, 'human')",
        (*key, STAMP),
    )


# --- migration 0029 ----------------------------------------------------------------------


def test_migration_0029_retires_the_stranded_readings_at_one_instant_and_leaves_nothing(tmp_path):
    path = tmp_path / "s.sqlite"
    con = db.connect(path, upto=28)
    _document(con)
    m = _extraction_measurement(con)
    alone = _alone(con, m)
    parent, successor_reading = _to_a_successor(con, m)
    live_reading = _live(con, m)
    con.commit()
    con.close()

    con = db.connect(path, upto=29)  # the migration production will run
    assert con.execute("PRAGMA user_version").fetchone()[0] == 29
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert con.execute("SELECT name FROM sqlite_temp_master").fetchall() == [], "nothing left"
    assert con.execute("SELECT COUNT(*) FROM citation_reading_residue").fetchone() == (0,)

    retired = {
        key: (rid, pointer, at, cid)
        for key, rid, pointer, at, cid in con.execute(
            "SELECT g.target_key, g.reading_id, g.superseded_by, g.superseded_at, x.citation_id"
            " FROM citation_reading_retirement x JOIN citation_reading g USING (reading_id)"
        )
    }
    assert set(retired) == {ALONE[3], PARENT[3]}
    rid, pointer, _, cid = retired[ALONE[3]]
    assert (pointer, cid) == (rid, alone), "retired at itself"
    _, pointer, _, cid = retired[PARENT[3]]
    assert (pointer, cid) == (successor_reading, parent), "followed the successor's KEY"
    (at,) = {at for _, _, at, _ in retired.values()}
    assert ISO.match(at), "one instant, in the loader's date form"
    assert con.execute(
        "SELECT DISTINCT reason, method, method_version, retired_at"
        " FROM citation_reading_retirement"
    ).fetchall() == [("retracted-key", "migration", "0029_retire_retracted_readings", at)]
    assert con.execute(
        "SELECT reading_id FROM citation_reading WHERE superseded_by IS NULL ORDER BY 1"
    ).fetchall() == [(successor_reading,), (live_reading,)]


def test_migration_0029_aborts_whole_when_a_person_decided_a_key_it_would_retire(tmp_path):
    path = tmp_path / "s.sqlite"
    con = db.connect(path, upto=28)
    _document(con)
    _alone(con, _extraction_measurement(con))
    _decided_by_review(con, ALONE)
    con.close()

    with pytest.raises(sqlite3.IntegrityError, match="migration 0029"):
        db.connect(path)
    # and a caller that COMMITS after the failure keeps nothing either: RAISE(ROLLBACK) ended the
    # transaction, where a RAISE(ABORT) would have left the earlier statements open to a commit
    raw = sqlite3.connect(path)
    script = resources.files("docketyard.store").joinpath("0029_retire_retracted_readings.sql")
    with pytest.raises(sqlite3.IntegrityError, match="migration 0029"):
        raw.executescript(script.read_text(encoding="utf-8"))
    raw.commit()
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 28
    assert (
        raw.execute(
            "SELECT name FROM sqlite_master WHERE name IN ('citation_reading_residue',"
            " 'citation_reading_retirement', 'retirement_reason_vocab')"
        ).fetchall()
        == []
    ), "the view and tables created before the guard are rolled back with everything else"
    assert raw.execute("SELECT superseded_by FROM citation_reading").fetchall() == [(None,)]
    raw.close()


def test_the_runbook_precheck_gives_the_views_answer_on_every_column(tmp_path):
    """The pre-check is a SECOND COPY of the view's rule (the view does not exist on production
    until the migration runs), so the two are run over one store and must agree on every column —
    and a decided key is found by either of `load._decided`'s tests only if the SQL renders the
    review key exactly as `keys.render` does."""
    con = db.connect(tmp_path / "s.sqlite")
    _document(con)
    m = _extraction_measurement(con)
    alone = _alone(con, m)
    parent, successor_reading = _to_a_successor(con, m)
    _live(con, m)
    _misfit(con, m)
    _decided_by_resolution(con, ALONE)
    _decided_by_review(con, PARENT)
    parent_reading = _reading_id(con, PARENT[3])
    alone_reading = _reading_id(con, ALONE[3])

    view = con.execute(
        "SELECT citing_document || '/' || page || '/' || target_kind || '/' || target_key,"
        " reading_channel, citation_id, pointer, decided FROM citation_reading_residue"
        " ORDER BY 1, 2"
    ).fetchall()
    assert view == sorted(
        [
            (keys.render(*ALONE), "text-layer", alone, alone_reading, 1),
            (keys.render(*PARENT), "text-layer", parent, successor_reading, 1),
        ]
    ), "the misfit and the live key are not residue"
    assert parent_reading != successor_reading
    assert con.execute(PRECHECK.read_text(encoding="utf-8")).fetchall() == view


def test_the_loader_refuses_to_retire_a_reading_a_person_decided(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    _document(con)
    _alone(con, _extraction_measurement(con))
    _decided_by_resolution(con, ALONE)
    with pytest.raises(load.DecidedResidue):
        load._retire_readings(con, DOC, methods.EXTRACTOR, "v1", STAMP)
    assert con.execute("SELECT COUNT(*) FROM citation_reading_retirement").fetchone() == (0,)


def test_a_rebuild_of_citation_reading_must_drop_the_objects_that_name_it(tmp_path):
    """0028's procedure — create, copy, DROP, RENAME — fails with the residue view in place
    (SQLite re-parses every view at the RENAME). The migration's header says to drop the view and
    the retirement triggers first and recreate them after; this runs both ways."""
    con = db.connect(tmp_path / "s.sqlite")
    con.commit()
    naming = ("citation_reading_residue",) + tuple(
        name
        for (name,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            " AND tbl_name = 'citation_reading_retirement' AND sql LIKE '%citation_reading r%'"
        )
    )
    ddl = [
        con.execute("SELECT sql FROM sqlite_master WHERE name = ?", (n,)).fetchone()[0]
        for n in naming
    ]
    rebuild = (
        "CREATE TABLE citation_reading_rebuilt AS SELECT * FROM citation_reading;"
        " DROP TABLE citation_reading;"
        " ALTER TABLE citation_reading_rebuilt RENAME TO citation_reading;"
    )
    con.execute("PRAGMA foreign_keys = OFF")
    with pytest.raises(sqlite3.OperationalError, match="citation_reading"):
        con.executescript(f"BEGIN; {rebuild} COMMIT;")
    con.rollback()

    drops = " ".join(
        f"DROP {'VIEW' if n == 'citation_reading_residue' else 'TRIGGER'} {n};" for n in naming
    )
    con.executescript(f"BEGIN; {drops} {rebuild} {'; '.join(ddl)}; COMMIT;")
    assert con.execute("SELECT COUNT(*) FROM citation_reading_residue").fetchone() == (0,)


# --- the dump ----------------------------------------------------------------------------


def test_the_retirement_layer_is_held_back_children_first():
    order = list(dump.HELD_TABLES)
    child = order.index("citation_reading_retirement")
    assert child < order.index("citation_reading") and child < order.index("citation")
    assert child < order.index("retirement_reason_vocab")
    assert "citation_reading_residue" in dump.HELD_VIEWS
