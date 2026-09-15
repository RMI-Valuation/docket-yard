"""Migration 0030 — the veto's trigger (ADR 0018 D7; its 2026-09-15 addendum, Proposed).

0014 left two cross-row conditions as prose, "owed with the veto": a suppress declaration's
measurement carries a false-veto rate rather than a recall, and a suppress method's rows are
measured. Each refusal here is one the triggers hold, beside the case they allow.
"""

import re
import sqlite3
from importlib import resources
from pathlib import Path

import pytest

from docketyard.citator import methods
from docketyard.store import db

STAMP = "2026-09-15T00:00:00+00:00"
KEY = ("e" * 64, 3, "stb", "FD 36873")
PRECHECK = Path(__file__).parents[1] / "infra" / "deploy" / "0030-precheck.sql"
DECLARATION = "suppress declaration names a false-veto rate"
ROW = "row of a suppress method is measured"
OVER_ROWS = "not declared suppress while any of its rows"
APPEND = "a measurement is append-only"


def _seed(con):
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


def _store(tmp_path):
    return _seed(db.connect(tmp_path / "s.sqlite"))


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


def _recall(con, benchmark_date="2026-09-16"):
    return _measurement(con, recall=0.9, false_veto_rate=None, benchmark_date=benchmark_date)


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


def _row(con, score_row_id=None, method="on-page-veto", version="v1", channel="text-layer"):
    """A veto row; measured from `score_row_id` when one is given, unmeasured otherwise."""
    measured = score_row_id is not None
    return con.execute(
        "INSERT INTO citation_resolution (citing_document, page, target_kind, target_key,"
        " method, method_version, reading_channel, outcome, asserted_at, confidence,"
        " confidence_state, measured_target, measured_class, score_row_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'vetoed', ?, ?, ?, ?, ?, ?)",
        (
            *KEY,
            method,
            version,
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
    with pytest.raises(sqlite3.IntegrityError, match=DECLARATION):
        _declare(con, _recall(con))


def test_a_declaration_on_another_channels_rate_is_refused(tmp_path):
    con = _store(tmp_path)
    ocr = _measurement(con, channel="ocr")
    with pytest.raises(sqlite3.IntegrityError, match=DECLARATION):
        _declare(con, ocr)
    _declare(con, ocr, reading_channel="ocr")  # on its own channel it stands


def test_a_declaration_may_not_be_updated_onto_a_recall_or_another_channel(tmp_path):
    con = _store(tmp_path)
    method_row = _declare(con, _measurement(con))
    recall = _recall(con)
    with pytest.raises(sqlite3.IntegrityError, match=DECLARATION):
        con.execute(
            "UPDATE assertion_method SET score_row_id = ? WHERE method_row_id = ?",
            (recall, method_row),
        )
    with pytest.raises(sqlite3.IntegrityError, match=DECLARATION):
        con.execute(
            "UPDATE assertion_method SET reading_channel = 'ocr' WHERE method_row_id = ?",
            (method_row,),
        )


# --- the measurement (rule 4) -------------------------------------------------------------


def test_a_measurement_is_never_changed_removed_or_replaced(tmp_path):
    """ADR 0018 D8: a re-score is a new row. A veto's rate could otherwise be withdrawn or
    re-pointed after the declaration and the rows it binds were checked against it."""
    con = _store(tmp_path)
    rate = _measurement(con)
    _declare(con, rate)
    with pytest.raises(sqlite3.IntegrityError, match=APPEND):
        con.execute(
            "UPDATE class_measurement SET false_veto_rate = NULL, recall = 0.9"
            " WHERE measurement_id = ?",
            (rate,),
        )
    with pytest.raises(sqlite3.IntegrityError, match=APPEND):
        con.execute(
            "UPDATE class_measurement SET measurement_id = 999 WHERE measurement_id = ?", (rate,)
        )
    spare = _recall(con)  # named by nothing, and append-only all the same
    with pytest.raises(sqlite3.IntegrityError, match=APPEND):
        con.execute(
            "UPDATE class_measurement SET score_file = 'u' WHERE measurement_id = ?", (spare,)
        )
    with pytest.raises(sqlite3.IntegrityError, match=APPEND):
        con.execute("DELETE FROM class_measurement WHERE measurement_id = ?", (spare,))
    with pytest.raises(sqlite3.IntegrityError, match=APPEND):
        con.execute(
            "INSERT OR REPLACE INTO class_measurement SELECT * FROM class_measurement"
            " WHERE measurement_id = ?",
            (rate,),
        )
    # and through the identity key, with no id: REPLACE would delete the card firing no trigger
    with pytest.raises(sqlite3.IntegrityError, match=APPEND):
        con.execute(
            "INSERT OR REPLACE INTO class_measurement (measured_target, class,"
            " extraction_method, extraction_method_version, resolution_method,"
            " resolution_method_version, reading_channel, projection_rule_version,"
            " benchmark_date, score_file, recall, precision, false_veto_rate, measured_at)"
            " SELECT measured_target, class, extraction_method, extraction_method_version,"
            " resolution_method, resolution_method_version, reading_channel,"
            " projection_rule_version, benchmark_date, 'other', recall, precision,"
            " false_veto_rate, measured_at FROM class_measurement WHERE measurement_id = ?",
            (spare,),
        )
    assert con.execute("SELECT COUNT(*) FROM class_measurement").fetchone() == (2,)
    assert con.execute(
        "SELECT score_file FROM class_measurement WHERE measurement_id = ?", (spare,)
    ).fetchone() == ("t",)


def test_a_card_differing_only_in_its_projection_rule_is_a_new_card(tmp_path):
    con = _store(tmp_path)
    assert _measurement(con) != _measurement(con, projection_rule_version="rule-p2")


def test_a_card_differing_only_in_its_resolution_version_is_a_new_card(tmp_path):
    con = _store(tmp_path)
    assert _measurement(con) != _measurement(con, resolution_method_version="rule-2")


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
    with pytest.raises(sqlite3.IntegrityError, match=ROW):
        _row(con, _recall(con, "2026-09-17"))
    _row(con, rate)


def test_a_veto_row_may_not_be_re_pointed_at_a_recall_or_unmeasured(tmp_path):
    con = _store(tmp_path)
    rate = _measurement(con)
    _declare(con, rate)
    row = _row(con, rate)
    recall = _recall(con)
    with pytest.raises(sqlite3.IntegrityError, match=ROW):
        con.execute(
            "UPDATE citation_resolution SET score_row_id = ? WHERE resolution_id = ?",
            (recall, row),
        )
    with pytest.raises(sqlite3.IntegrityError, match=ROW):
        con.execute(
            "UPDATE citation_resolution SET confidence_state = 'unmeasured', confidence = 0,"
            " score_row_id = NULL, measured_target = NULL, measured_class = NULL"
            " WHERE resolution_id = ?",
            (row,),
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


def test_moving_a_declaration_onto_a_version_with_unmeasured_rows_is_refused(tmp_path):
    con = _store(tmp_path)
    method_row = _declare(con, _measurement(con))
    _row(con, version="v2")  # the v2 triple is declared nowhere, so this row is legal
    with pytest.raises(sqlite3.IntegrityError, match=OVER_ROWS):
        con.execute(
            "UPDATE assertion_method SET method_version = 'v2' WHERE method_row_id = ?",
            (method_row,),
        )


def test_declaring_suppress_over_rows_measured_on_a_rate_is_allowed(tmp_path):
    con = _store(tmp_path)
    rate = _measurement(con)
    _row(con, rate)
    _declare(con, rate)


# --- the migration's guard and the runbook's pre-check ------------------------------------


def test_the_guard_names_both_kinds_of_violation_and_refuses_the_migration_whole(tmp_path):
    path = tmp_path / "s.sqlite"
    con = _seed(db.connect(path, upto=29))
    declaration = _declare(con, _recall(con))  # at schema 29 nothing refuses either
    row = _row(con)
    con.commit()

    expected = [("declaration", declaration), ("row", row)]
    assert con.execute(PRECHECK.read_text(encoding="utf-8")).fetchall() == expected
    migration = resources.files("docketyard.store").joinpath("0030_veto_trigger.sql")
    guards = re.findall(
        r"INSERT INTO m0030_violation\s*\n(SELECT .*?);",
        migration.read_text(encoding="utf-8"),
        re.S,
    )
    assert len(guards) == 2
    assert sorted(r for sql in guards for r in con.execute(sql).fetchall()) == expected
    # and the TEXT agrees, so a clause changed in one copy fails here even on a store it misses

    def norm(sql):
        return " ".join(sql.split())

    body = "\n".join(
        line
        for line in PRECHECK.read_text(encoding="utf-8").splitlines()
        if not line.startswith("--")
    )
    declared = guards[0].replace(
        "SELECT 'declaration', a.method_row_id",
        "SELECT 'declaration' AS what, a.method_row_id AS id",
    )
    composed = f"SELECT what, id FROM ( {declared} UNION ALL {guards[1]} ) ORDER BY what, id"
    assert norm(body) == norm(composed)
    con.close()

    with pytest.raises(sqlite3.IntegrityError, match="migration 0030"):
        db.connect(path)
    raw = sqlite3.connect(path)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 29
    assert (
        raw.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            " AND (name LIKE '%veto%' OR tbl_name = 'class_measurement')"
        ).fetchall()
        == []
    )
    raw.close()


def test_the_guard_skips_what_the_trigger_skips_and_neither_shape_is_writable(tmp_path):
    """The guard gates on `score_row_id` and the stage exactly as
    `assertion_method_veto_is_measured_on_its_own_channel` does (code review, 2026-09-15), or it
    would abort the migration over a declaration the migration then permits. Neither shape can be
    in a store anyway: 0014's CHECKs refuse a `suppress` row without a resolution measurement."""
    con = _seed(db.connect(tmp_path / "s.sqlite", upto=29))
    with pytest.raises(sqlite3.IntegrityError, match="constraint failed"):
        _declare(con, None)  # a suppress row naming no measurement
    with pytest.raises(sqlite3.IntegrityError, match="constraint failed"):
        _declare(con, _recall(con), measured_target="citation")  # or another stage's
    assert con.execute(PRECHECK.read_text(encoding="utf-8")).fetchall() == []


def test_the_precheck_is_empty_on_a_store_that_breaks_nothing(tmp_path):
    con = _store(tmp_path)
    rate = _measurement(con)
    _declare(con, rate)
    _row(con, rate)
    assert con.execute(PRECHECK.read_text(encoding="utf-8")).fetchall() == []


# --- the verb that declares --------------------------------------------------------------


def test_declare_passes_a_veto_refusal_through_rather_than_calling_it_a_collision(tmp_path):
    """`methods.declare` reads every IntegrityError as a collision. A D7 refusal is not one, and
    reported as "collides with a declaration" it would send the operator after the wrong fault.
    No declaration `declare` writes today can trip a D7 trigger, so a stand-in raises one."""
    con = db.connect(tmp_path / "s.sqlite")
    con.execute(
        "CREATE TEMP TRIGGER stand_in BEFORE INSERT ON assertion_method"
        " BEGIN SELECT RAISE(ABORT, 'ADR 0018 D7: a stand-in refusal'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="ADR 0018 D7: a stand-in refusal"):
        methods.declare(con, "v1")
