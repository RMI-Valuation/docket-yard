"""Store migration, capture persistence, and ingest idempotence."""

import sqlite3

import pytest

from docketyard.capture import records
from docketyard.ingest import dockets
from docketyard.store import db, events, projections
from tests.test_dockets_parse import make_body


@pytest.fixture
def con():
    return db.connect(":memory:")


def save(con, data_dir, body, *, asserted=True, mode="forward"):
    cid = records.save_capture(
        con,
        data_dir,
        source_system="stb-ajax",
        endpoint="test",
        table_action="stb_hook_table_dockets",
        request_params=[],
        body=body,
        http_status=200,
        ingest_mode=mode,
    )
    if asserted:
        records.set_verdict(con, cid, filter_asserted=True, row_count=0, reported_total=0)
    return cid


# --- store ---------------------------------------------------------------------------


def test_migrations_apply_once(con):
    head = db.MIGRATIONS[-1][0]
    assert con.execute("PRAGMA user_version").fetchone()[0] == head
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"capture", "docket", "event", "document", "filing", "walk_slice"} <= tables
    assert db.migrate(con) == head  # re-running changes nothing


def test_migrations_are_numbered_one_to_n_and_a_gap_refuses_before_anything_applies(monkeypatch):
    """`migrate` skips every version at or below the stamp, so a migration registered past a gap
    (a branch's 0032 merged before 0030 and 0031) would leave the gap unapplied for ever."""
    assert [v for v, _ in db.MIGRATIONS] == list(range(1, len(db.MIGRATIONS) + 1))
    monkeypatch.setattr(db, "MIGRATIONS", [m for m in db.MIGRATIONS if m[0] != 2])
    raw = sqlite3.connect(":memory:")
    with pytest.raises(RuntimeError, match="contiguously"):
        db.migrate(raw)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 0
    assert raw.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0


def test_a_script_that_fails_partway_leaves_nothing_a_commit_could_keep(con, monkeypatch):
    """A statement that fails to PARSE partway raises with the script's `BEGIN` still open;
    a caller that kept the connection and committed kept what ran before it (the schema
    critic, 2026-09-13). `migrate` rolls back before re-raising."""
    head = db.MIGRATIONS[-1][0]
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, (head + 1, "broken.sql")])
    real = db._script
    monkeypatch.setattr(
        db,
        "_script",
        lambda name: (
            "BEGIN TRANSACTION; CREATE TABLE half_applied (x); SELEC broken; COMMIT;"
            if name == "broken.sql"
            else real(name)
        ),
    )
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(con)
    con.commit()  # what a caller that kept the connection would do
    assert con.execute("PRAGMA user_version").fetchone()[0] == head
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "half_applied" not in tables


def test_versionless_tables_are_refused():
    raw = sqlite3.connect(":memory:")
    raw.execute("CREATE TABLE capture (x)")  # tables exist, no version stamp
    with pytest.raises(RuntimeError, match="disposable"):
        db.migrate(raw)


def test_blob_roundtrip(tmp_path):
    sha = records.save_blob(tmp_path, b"hello")
    assert records.load_blob(tmp_path, sha) == b"hello"
    assert records.save_blob(tmp_path, b"hello") == sha  # content-addressed: same bytes, no-op


def test_capture_starts_quarantined_until_verdict(con, tmp_path):
    cid = save(con, tmp_path, b"raw bytes, never parsed", asserted=False)
    asserted, sha = con.execute(
        "SELECT filter_asserted, response_sha256 FROM capture WHERE capture_id=?", (cid,)
    ).fetchone()
    assert asserted == 0
    assert records.load_blob(tmp_path, sha) == b"raw bytes, never parsed"  # raw survives


def test_duplicate_docket_identity_is_impossible(con):
    con.execute("INSERT INTO docket (raw_docket, prefix, sequence) VALUES ('FD_1_0', 'FD', 1)")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        con.execute("INSERT INTO docket (raw_docket, prefix, sequence) VALUES ('FD_1_0', 'FD', 1)")


# --- ingest --------------------------------------------------------------------------


def test_ingest_counts_and_skips_reprocessing(con, tmp_path):
    body = make_body([("FD_36873_0", "UP/NS MERGER"), ("FD_36873_1", "SUB ONE")], total=2)
    cid = save(con, tmp_path, body)
    first = dockets.ingest_capture(con, tmp_path, cid)
    assert first["new_dockets"] == 2 and first["events"] == 2 and first["suppressed"] == 0
    assert dockets.ingest_capture(con, tmp_path, cid) == {"already_processed": True}
    # identical content in a NEW capture is a true idempotence check
    second = dockets.ingest_capture(con, tmp_path, save(con, tmp_path, body))
    assert second["new_dockets"] == 0 and second["events"] == 0
    assert projections.docket_count(con) == 2


def test_new_dockets_counts_minted_parents(con, tmp_path):
    stats = dockets.ingest_capture(
        con, tmp_path, save(con, tmp_path, make_body([("AB_55_785_X", "DISC.")], total=1))
    )
    assert stats["new_dockets"] == 2  # the sub AND its inferred parent
    assert projections.docket_count(con) == 2


def test_inferred_parent_gets_provenance_and_correction(con, tmp_path):
    cid = save(con, tmp_path, make_body([("AB_55_785_X", "DISCONTINUANCE")], total=1))
    dockets.ingest_capture(con, tmp_path, cid)
    by_raw = dict(con.execute("SELECT raw_docket, parent_docket_id FROM docket").fetchall())
    parent_row = con.execute(
        "SELECT docket_id FROM docket WHERE sub_sequence IS NULL AND suffix IS NULL"
    ).fetchone()
    assert parent_row is not None
    parent_id = parent_row[0]
    assert by_raw["AB_55_785_X"] == parent_id  # sub links to the parent, not to itself
    assert by_raw["AB_55_0"] is None  # parent does not self-link
    # the minted parent is recorded as inferred (with the implying capture), never observed
    assert events.latest_payload(con, "docket_inferred", parent_id) == {
        "inferred_from": "AB_55_785_X"
    }
    assert events.latest_payload(con, "docket_observed", parent_id) is None
    # first direct observation corrects the synthesised spelling
    dockets.ingest_capture(
        con, tmp_path, save(con, tmp_path, make_body([("AB_55", "THE PARENT")], total=1))
    )
    raw = con.execute("SELECT raw_docket FROM docket WHERE docket_id=?", (parent_id,))
    assert raw.fetchone()[0] == "AB_55"
    assert events.latest_payload(con, "docket_observed", parent_id) == {"title": "THE PARENT"}


def test_reobservation_without_change_appends_nothing(con, tmp_path):
    body = make_body([("EP_749_0", "PETITION FOR RULEMAKING")], total=1)
    dockets.ingest_capture(con, tmp_path, save(con, tmp_path, body))
    dockets.ingest_capture(con, tmp_path, save(con, tmp_path, body))
    assert projections.status(con)["events"] == 1


def test_title_change_appends_event(con, tmp_path):
    dockets.ingest_capture(
        con, tmp_path, save(con, tmp_path, make_body([("EP_749_0", "OLD TITLE")], total=1))
    )
    dockets.ingest_capture(
        con, tmp_path, save(con, tmp_path, make_body([("EP_749_0", "NEW TITLE")], total=1))
    )
    assert projections.status(con)["events"] == 2


def test_same_row_twice_in_one_capture_is_surfaced_not_silent(con, tmp_path):
    body = make_body([("EP_749_0", "TITLE A"), ("EP_749_0", "TITLE B")], total=2)
    stats = dockets.ingest_capture(con, tmp_path, save(con, tmp_path, body))
    # within-capture dedup suppressed the second, differing write — and said so
    assert stats["events"] == 1 and stats["suppressed"] == 1


def test_quarantined_capture_refuses_ingest(con, tmp_path):
    cid = save(con, tmp_path, make_body([("EP_749_0", "T")], total=1), asserted=False)
    with pytest.raises(ValueError, match="quarantined"):
        dockets.ingest_capture(con, tmp_path, cid)


# --- projections ---------------------------------------------------------------------


def test_view_and_ledger_agree_on_latest(con, tmp_path):
    # docket_current's subquery and events.latest_payload are two spellings of one
    # definition of "latest"; this pins them together so they cannot drift
    for title in ("FIRST", "SECOND"):
        dockets.ingest_capture(
            con, tmp_path, save(con, tmp_path, make_body([("FD_99_0", title)], total=1))
        )
    docket_id, payload = con.execute(
        "SELECT docket_id, latest_payload FROM docket_current WHERE raw_docket='FD_99_0'"
    ).fetchone()
    assert db.load_json(payload) == events.latest_payload(con, "docket_observed", docket_id)
    assert projections.docket_titles(con)[0] == ("FD_99_0", "SECOND")


def test_status_counts(con, tmp_path):
    bad = save(con, tmp_path, b"quarantined bytes", asserted=False)
    records.set_verdict(con, bad, filter_asserted=False, row_count=0, reported_total=0)
    save(con, tmp_path, b"saved then crashed before any verdict", asserted=False)
    cid = save(con, tmp_path, make_body([("FD_5_0", "T")], total=1))
    records.set_verdict(con, cid, filter_asserted=True, row_count=1, reported_total=10_000)
    s = projections.status(con)
    assert s["captures"] == 3
    assert s["captures_quarantined"] == 1  # judged and failed
    assert s["captures_unjudged"] == 1  # never judged: not a criteria failure
    assert s["captures_capped"] == 1
    assert s["captures_unprocessed"] == 1
    assert projections.pending_capture_ids(con) == [cid]


# --- the foreign-key check after a script, scoped (deferred.md, release review 2026-09-10) ---

FK_BASE = """
CREATE TABLE parent (id INTEGER PRIMARY KEY);
CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent (id));
CREATE TABLE audit (child_id INTEGER REFERENCES child (id));
CREATE TABLE elsewhere_parent (id INTEGER PRIMARY KEY);
CREATE TABLE elsewhere (p INTEGER REFERENCES elsewhere_parent (id));
CREATE TABLE log (n INTEGER);
CREATE TRIGGER log_writes AFTER INSERT ON log BEGIN DELETE FROM parent; END;
INSERT INTO parent VALUES (1);
INSERT INTO child VALUES (1, 1);
PRAGMA user_version = 1;
"""


def _fk_store(monkeypatch, *scripts):
    """A store at FK_BASE, built by `migrate` itself, with `scripts` registered after it."""
    texts = {"1.sql": FK_BASE} | {f"{n}.sql": s for n, s in enumerate(scripts, 2)}
    monkeypatch.setattr(db, "_script", texts.__getitem__)
    monkeypatch.setattr(db, "MIGRATIONS", [(1, "1.sql")])
    raw = sqlite3.connect(":memory:")
    db.migrate(raw)
    monkeypatch.setattr(db, "MIGRATIONS", [(n, f"{n}.sql") for n in range(1, len(texts) + 1)])
    return raw


def _stamped(body: str) -> str:
    return f"BEGIN; {body} PRAGMA user_version = 2; COMMIT;"


@pytest.mark.parametrize(
    "body",
    [
        "DELETE FROM parent;",  # strands a child the script never names
        "INSERT INTO log VALUES (1);",  # the same, through a trigger on a table it names
        "INSERT INTO log VALUES (1); DROP TRIGGER log_writes;",  # fired, then dropped: it wrote
        "INSERT INTO child VALUES (2, 99);",  # a reference written to nothing
        # SQLite's rebuild procedure, done carelessly: the rows are not copied across
        "DROP TRIGGER log_writes; CREATE TABLE parent_new (id INTEGER PRIMARY KEY);"
        " DROP TABLE parent; ALTER TABLE parent_new RENAME TO parent;",
    ],
)
def test_a_scoped_check_still_finds_what_the_script_broke(monkeypatch, body):
    """The scope is an over-approximation of what a script with enforcement OFF can break:
    the tables it names, what their triggers write, what its DDL changed, and the children of
    all of those. Each case here breaks a reference the script does not name."""
    raw = _fk_store(monkeypatch, _stamped(body))
    with pytest.raises(RuntimeError, match="dangling foreign keys"):
        db.migrate(raw)


def test_the_check_is_scoped_to_what_a_script_could_reach(monkeypatch):
    """The point: unscoped it was 280 s a script on the production copy, the whole store checked
    after scripts that touched a table or two. A table the script cannot reach is not checked."""
    raw = _fk_store(monkeypatch, _stamped("INSERT INTO log VALUES (0);"))
    before = db._schema(raw)
    # the child, not the grandchild: `audit` references `child`, which this did not write
    assert db._fk_scope(raw, "UPDATE parent SET id = id", before) == ["child", "parent"]
    assert db._fk_scope(raw, "INSERT INTO log VALUES (1)", before) == ["child", "log", "parent"]
    assert db._fk_scope(raw, "-- touches nothing", before) == []
    raw.execute("CREATE TABLE fresh (p INTEGER REFERENCES elsewhere_parent (id))")
    assert db._fk_scope(raw, "", before) == ["fresh"], "its DDL changed, so it is in scope"
    raw.execute("DROP TABLE fresh")
    # a dangling row out of the script's reach is not this script's to report
    raw.execute("DROP TRIGGER log_writes")
    raw.execute("PRAGMA foreign_keys = OFF")  # `migrate` leaves enforcement on
    raw.execute("INSERT INTO elsewhere VALUES (42)")
    raw.commit()
    assert db.migrate(raw) == 2


def test_a_temp_trigger_an_earlier_script_left_is_inside_the_next_scripts_scope(monkeypatch):
    """Every pending migration runs on one connection, and a TEMP trigger lives in
    `sqlite_temp_master`: left by script 2 on a table script 3 writes, it fires into a table
    script 3 never names. The scope reads the temp schema too (schema-critic, 2026-10-03)."""
    raw = _fk_store(
        monkeypatch,
        "BEGIN; DROP TRIGGER log_writes; CREATE TEMP TRIGGER sneaky AFTER INSERT ON main.log"
        " BEGIN DELETE FROM parent; END; PRAGMA user_version = 2; COMMIT;",
        "BEGIN; INSERT INTO log VALUES (1); PRAGMA user_version = 3; COMMIT;",
    )
    with pytest.raises(RuntimeError, match="dangling foreign keys"):
        db.migrate(raw)


def test_what_the_word_match_cannot_see_gets_the_full_check():
    """`writable_schema` moves contents with no name and no DDL diff; a name that is not a
    plain word escapes the word match. Both fall back to the store-wide check."""
    plain = {("table", "parent"): ("parent", "CREATE TABLE parent (id)")}
    assert not db._needs_full_check("DELETE FROM parent", plain, plain)
    assert db._needs_full_check("PRAGMA writable_schema = ON", plain, plain)
    odd = plain | {("table", "doc ument"): ("doc ument", 'CREATE TABLE "doc ument" (id)')}
    assert db._needs_full_check("DELETE FROM parent", odd, odd)
