"""Migration 0030 — the veto's trigger (ADR 0018 D7; its 2026-09-15 addendum, Proposed).

0014 left two cross-row conditions as prose, "owed with the veto": a suppress declaration's
measurement carries a false-veto rate rather than a recall, and a suppress method's rows are
measured. Each refusal here is one the triggers hold, beside the case they allow.
"""

import sqlite3

import pytest

from docketyard.store import db

STAMP = "2026-09-15T00:00:00+00:00"
KEY = ("e" * 64, 3, "stb", "FD 36873")
DECLARATION = "suppress declaration names a false-veto rate"
ROW = "row of a suppress method is measured"
OVER_ROWS = "not declared suppress while any of its rows"
KEPT = "is not withdrawn or re-pointed"


def _store(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'pdf', ?)",
        (KEY[0], STAMP),
    )
    con.execute(
        "INSERT INTO citation_key (citing_document, page, target_kind, target_key,"
        " key_version, first_seen_at) VALUES (?, ?, ?, ?, 'v1', ?)",
        (*KEY, STAMP),
    )
    return con


def _measurement(con, channel="text-layer", cls="on-page-veto", **over):
    cols = {
        "measured_target": "citation_resolution",
        "class": cls,
        "extraction_method": "regex-docket-cite",
        "extraction_method_version": "2026-08-30",
        "resolution_method": "registry-match",
        "resolution_method_version": "rule-1",
        "reading_channel": channel,
        "benchmark_date": "2026-09-15",
        "score_file": "t",
        "recall": None,
        "false_veto_rate": 0.015,
        "measured_at": STAMP,
    }
    cols.update(over)
    names = ", ".join(f'"{k}"' for k in cols)
    return con.execute(
        f"INSERT INTO class_measurement ({names}) VALUES ({', '.join('?' * len(cols))})",
        tuple(cols.values()),
    ).lastrowid


def _declare(con, score_row_id, role="suppress", rank_version="v1", rank=9, **over):
    cols = {
        "target_table": "citation_resolution",
        "method": "on-page-veto",
        "method_version": "v1",
        "reading_channel": "text-layer",
        "role": role,
        "precedence_rank": rank,
        "measured_target": None if score_row_id is None else "citation_resolution",
        "score_row_id": score_row_id,
        "rank_version": rank_version,
        "declared_at": STAMP,
    }
    cols.update(over)
    names = ", ".join(cols)
    return con.execute(
        f"INSERT INTO assertion_method ({names}) VALUES ({', '.join('?' * len(cols))})",
        tuple(cols.values()),
    ).lastrowid


def _row(con, score_row_id=None, method="on-page-veto", channel="text-layer"):
    """A veto row; measured from `score_row_id` when one is given, unmeasured otherwise."""
    measured = score_row_id is not None
    return con.execute(
        "INSERT INTO citation_resolution (citing_document, page, target_kind, target_key,"
        " method, method_version, reading_channel, outcome, asserted_at, confidence,"
        " confidence_state, measured_target, measured_class, score_row_id)"
        " VALUES (?, ?, ?, ?, ?, 'v1', ?, 'vetoed', ?, ?, ?, ?, ?, ?)",
        (
            *KEY,
            method,
            channel,
            STAMP,
            0.985 if measured else 0.0,
            "measured" if measured else "unmeasured",
            "citation_resolution" if measured else None,
            "on-page-veto" if measured else None,
            score_row_id,
        ),
    ).lastrowid


# --- the declaration (rule 3) -------------------------------------------------------------


def test_a_declaration_on_a_recall_alone_is_refused(tmp_path):
    con = _store(tmp_path)
    recall = _measurement(con, recall=0.9, false_veto_rate=None)
    with pytest.raises(sqlite3.IntegrityError, match=DECLARATION):
        _declare(con, recall)


def test_a_declaration_on_another_channels_rate_is_refused(tmp_path):
    con = _store(tmp_path)
    ocr = _measurement(con, channel="ocr")
    with pytest.raises(sqlite3.IntegrityError, match=DECLARATION):
        _declare(con, ocr)
    _declare(con, ocr, reading_channel="ocr")  # on its own channel it stands


def test_a_declaration_may_not_be_updated_onto_a_recall(tmp_path):
    con = _store(tmp_path)
    method_row = _declare(con, _measurement(con))
    recall = _measurement(con, recall=0.9, false_veto_rate=None, benchmark_date="2026-09-16")
    with pytest.raises(sqlite3.IntegrityError, match=DECLARATION):
        con.execute(
            "UPDATE assertion_method SET score_row_id = ? WHERE method_row_id = ?",
            (recall, method_row),
        )


# --- the measurement (rule 4) -------------------------------------------------------------


def test_withdrawing_a_declared_rate_is_refused_and_an_unreferenced_one_is_not(tmp_path):
    con = _store(tmp_path)
    rate = _measurement(con)
    _declare(con, rate)
    with pytest.raises(sqlite3.IntegrityError, match=KEPT):
        con.execute(
            "UPDATE class_measurement SET false_veto_rate = NULL, recall = 0.9"
            " WHERE measurement_id = ?",
            (rate,),
        )
    with pytest.raises(sqlite3.IntegrityError, match=KEPT):
        con.execute(
            "UPDATE class_measurement SET reading_channel = 'ocr' WHERE measurement_id = ?",
            (rate,),
        )
    with pytest.raises(sqlite3.IntegrityError, match=KEPT):
        con.execute(
            "UPDATE class_measurement SET measurement_id = 999 WHERE measurement_id = ?", (rate,)
        )
    spare = _measurement(con, recall=0.9, benchmark_date="2026-09-16")
    con.execute(
        "UPDATE class_measurement SET false_veto_rate = NULL WHERE measurement_id = ?", (spare,)
    )


def test_withdrawing_a_rate_a_bound_row_names_is_refused(tmp_path):
    con = _store(tmp_path)
    _declare(con, _measurement(con))
    stamped = _measurement(con, recall=0.9, benchmark_date="2026-09-16")
    _row(con, stamped)  # stamped from a second rate the declaration does not name
    with pytest.raises(sqlite3.IntegrityError, match=KEPT):
        con.execute(
            "UPDATE class_measurement SET false_veto_rate = NULL WHERE measurement_id = ?",
            (stamped,),
        )


# --- the rows (rules 1 and 2) -------------------------------------------------------------


def test_an_unmeasured_or_human_veto_row_is_refused_and_a_measured_one_on_a_rate_is_not(
    tmp_path,
):
    con = _store(tmp_path)
    rate = _measurement(con)
    _declare(con, rate)
    with pytest.raises(sqlite3.IntegrityError, match=ROW):
        _row(con)
    _declare(
        con,
        _measurement(con, channel="human", benchmark_date="2026-09-16"),
        rank=1,
        method="human",
        reading_channel="human",
    )
    with pytest.raises(sqlite3.IntegrityError, match=ROW):
        con.execute(
            "INSERT INTO citation_resolution (citing_document, page, target_kind, target_key,"
            " method, method_version, reading_channel, outcome, asserted_at, confidence,"
            " confidence_state) VALUES (?, ?, ?, ?, 'human', 'v1', 'human', 'vetoed', ?, 1.0,"
            " 'human')",
            (*KEY, STAMP),
        )
    recall = _measurement(con, recall=0.9, false_veto_rate=None, benchmark_date="2026-09-17")
    with pytest.raises(sqlite3.IntegrityError, match=ROW):
        _row(con, recall)
    _row(con, rate)


def test_re_pointing_a_veto_rows_score_at_a_recall_is_refused(tmp_path):
    con = _store(tmp_path)
    rate = _measurement(con)
    _declare(con, rate)
    row = _row(con, rate)
    recall = _measurement(con, recall=0.9, false_veto_rate=None, benchmark_date="2026-09-16")
    with pytest.raises(sqlite3.IntegrityError, match=ROW):
        con.execute(
            "UPDATE citation_resolution SET score_row_id = ? WHERE resolution_id = ?",
            (recall, row),
        )


def test_renaming_a_row_onto_the_suppress_triple_is_refused(tmp_path):
    con = _store(tmp_path)
    _declare(con, _measurement(con))
    row = _row(con, method="registry-match")  # an unmeasured row of an undeclared triple
    with pytest.raises(sqlite3.IntegrityError, match=ROW):
        con.execute(
            "UPDATE citation_resolution SET method = 'on-page-veto' WHERE resolution_id = ?",
            (row,),
        )


def test_a_suppress_declaration_in_any_ranking_binds_the_triple(tmp_path):
    """A resolution carries no `rank_version`, so a triple declared `resolve` in a later ranking
    is still bound by the ranking that declared it `suppress`."""
    con = _store(tmp_path)
    _declare(con, _measurement(con), rank_version="v1")
    _declare(con, None, role="resolve", rank_version="v2", rank=3)
    with pytest.raises(sqlite3.IntegrityError, match=ROW):
        _row(con)


# --- the order (rule 5) -------------------------------------------------------------------


def test_declaring_suppress_over_an_unmeasured_row_is_refused(tmp_path):
    con = _store(tmp_path)
    rate = _measurement(con)
    _row(con)  # nothing binds the triple yet, so the unmeasured row is legal
    with pytest.raises(sqlite3.IntegrityError, match=OVER_ROWS):
        _declare(con, rate)
    resolve = _declare(con, None, role="resolve", rank=3)
    with pytest.raises(sqlite3.IntegrityError, match=OVER_ROWS):
        con.execute(
            "UPDATE assertion_method SET role = 'suppress', measured_target ="
            " 'citation_resolution', score_row_id = ? WHERE method_row_id = ?",
            (rate, resolve),
        )


def test_declaring_suppress_over_rows_measured_on_a_rate_is_allowed(tmp_path):
    con = _store(tmp_path)
    rate = _measurement(con)
    _row(con, rate)
    _declare(con, rate)


def test_a_store_already_breaking_the_rule_refuses_the_migration_whole(tmp_path):
    path = tmp_path / "s.sqlite"
    con = db.connect(path, upto=29)
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'pdf', ?)",
        (KEY[0], STAMP),
    )
    con.execute(
        "INSERT INTO citation_key (citing_document, page, target_kind, target_key,"
        " key_version, first_seen_at) VALUES (?, ?, ?, ?, 'v1', ?)",
        (*KEY, STAMP),
    )
    _declare(con, _measurement(con))
    _row(con)
    con.commit()
    con.close()
    with pytest.raises(sqlite3.IntegrityError, match="migration 0030"):
        db.connect(path)
    raw = sqlite3.connect(path)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 29
    assert (
        raw.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE '%veto%'"
        ).fetchall()
        == []
    )
    raw.close()
