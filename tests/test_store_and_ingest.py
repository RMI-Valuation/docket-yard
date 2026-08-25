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
        request_params=[],
        body=body,
        http_status=200,
        ingest_mode=mode,
    )
    if asserted:
        records.set_verdict(con, cid, filter_asserted=True, row_count=0, reported_total=0)
    return cid


# --- store ---------------------------------------------------------------------------


def test_migration_applies_once(con):
    assert con.execute("PRAGMA user_version").fetchone()[0] == 1
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"capture", "docket", "event"} <= tables
    assert db.migrate(con) == 1  # re-running changes nothing


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
    save(con, tmp_path, b"quarantined bytes", asserted=False)
    cid = save(con, tmp_path, make_body([("FD_5_0", "T")], total=1))
    records.set_verdict(con, cid, filter_asserted=True, row_count=1, reported_total=10_000)
    s = projections.status(con)
    assert s["captures"] == 2
    assert s["captures_quarantined"] == 1
    assert s["captures_capped"] == 1
    assert s["captures_unprocessed"] == 1
    assert projections.pending_capture_ids(con) == [cid]
