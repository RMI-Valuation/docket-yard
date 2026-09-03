"""Migration 0014 — the citator's five families (ADR 0018), and the checks that hold them.

Every test here pins something a review round found and the schema now enforces, so that
loosening the schema breaks a test rather than a published number. The names say which.
"""

import sqlite3
from pathlib import Path

import pytest

from docketyard.store import db

STAMP = "2026-09-01T00:00:00+00:00"
KEY = ("d" * 64, 3, "stb", "FD 36873")


def _store(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'pdf', ?)",
        (KEY[0], STAMP),
    )
    return con


def _measurement(con, target="citation_resolution", cls="docket", **over):
    cols = {
        "measured_target": target,
        "class": cls,
        "extraction_method": "regex-docket-cite",
        "extraction_method_version": "2026-08-30",
        "resolution_method": "registry-match",
        "resolution_method_version": "rule-1",
        "reading_channel": "text-layer",
        "projection_rule_version": None,
        "benchmark_date": "2026-09-01",
        "score_file": "projection_score.py",
        "recall": 0.893,
        "precision": None,
        "false_veto_rate": None,
        "measured_at": STAMP,
    }
    cols.update(over)
    names = ", ".join(f'"{k}"' for k in cols)
    return con.execute(
        f"INSERT INTO class_measurement ({names}) VALUES ({', '.join('?' * len(cols))})",
        tuple(cols.values()),
    ).lastrowid


def _extraction_measurement(con):
    return _measurement(
        con, "citation", "docket", resolution_method=None, resolution_method_version=None
    )


def _key(con, key=KEY):
    con.execute(
        "INSERT INTO citation_key (citing_document, page, target_kind, target_key,"
        " key_version, first_seen_at) VALUES (?, ?, ?, ?, 'v1', ?)",
        (*key, STAMP),
    )


def _citation(con, score_row_id, key=KEY, version="2026-08-30"):
    con.execute(
        "INSERT INTO citation (citing_document, page, target_kind, target_key, method,"
        " method_version, asserted_at, confidence, confidence_state, measured_target,"
        " score_row_id)"
        " VALUES (?, ?, ?, ?, 'regex-docket-cite', ?, ?, 0.978, 'measured', 'citation', ?)",
        (*key, version, STAMP, score_row_id),
    )
    return con.execute("SELECT MAX(citation_id) FROM citation").fetchone()[0]


def _method(con, **over):
    cols = {
        "target_table": "citation",
        "method": "regex-docket-cite",
        "method_version": "2026-08-30",
        "reading_channel": None,
        "role": None,
        "precedence_rank": None,
        "target_kind": "stb",
        "target_form": "docket",
        "measured_target": None,
        "score_row_id": None,
        "rank_version": "v1",
        "declared_at": STAMP,
    }
    cols.update(over)
    names = ", ".join(cols)
    return con.execute(
        f"INSERT INTO assertion_method ({names}) VALUES ({', '.join('?' * len(cols))})",
        tuple(cols.values()),
    )


def _live(con, table):
    return con.execute(f"SELECT COUNT(*) FROM {table} WHERE superseded_by IS NULL").fetchone()[0]


def test_the_store_migrates_and_query_two_runs_and_returns_nothing(tmp_path):
    """ADR 0017 D7: query 2 filters on a negative polarity, and every edge in the first slice
    is `cites`. An empty result is the correct day-one answer — and an unparseable query is
    not an answer at all, which is why citation_treatment is in migration 0014."""
    con = _store(tmp_path)
    assert con.execute("PRAGMA user_version").fetchone()[0] == db.MIGRATIONS[-1][0]
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    rows = con.execute(
        Path("docs/citator-query-2.sql").read_text(encoding="utf-8"),
        {"rank_version": "v1", "target_work": "52526"},
    ).fetchall()
    assert rows == []


def test_a_confidence_is_measured_only_when_it_points_at_the_measurement(tmp_path):
    """ADR 0018 D8. A human review has a confidence; what it lacks is a benchmark."""
    con = _store(tmp_path)
    _key(con)
    with pytest.raises(sqlite3.IntegrityError):
        _citation(con, None)  # 'measured' with no score_row_id
    _citation(con, _extraction_measurement(con))
    # and the other way, because the CHECK is an equivalence and not an implication: a
    # non-measured row may NOT carry a benchmark it did not come from
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO citation (citing_document, page, target_kind, target_key, method,"
            " method_version, asserted_at, confidence, confidence_state, measured_target,"
            " score_row_id) VALUES (?, 9, 'stb', 'EP 445', 'm', 'v', ?, 1.0, 'human',"
            " 'citation', 1)",
            (KEY[0], STAMP),
        )


def test_a_row_cannot_be_stamped_from_another_stages_measurement(tmp_path):
    """The error ADR 0017 made four times, made impossible in the one table built to stop
    it: an extraction row displaying 98.0%, which is the projection's figure."""
    con = _store(tmp_path)
    _key(con)
    projection = _measurement(
        con,
        "projection",
        "docket",
        recall=0.893,
        precision=0.980,
        projection_rule_version="span=2026-09-01;closure=v1;rank=v1",
    )
    with pytest.raises(sqlite3.IntegrityError):  # the (id, stage) pair does not exist
        _citation(con, projection)
    # and the column cannot simply be relabelled to make the pair fit
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO citation (citing_document, page, target_kind, target_key, method,"
            " method_version, asserted_at, confidence, confidence_state, measured_target,"
            " score_row_id) VALUES (?, ?, ?, ?, 'm', 'v', ?, 0.98, 'measured', 'projection',"
            " ?)",
            (*KEY, STAMP, projection),
        )
    # the span judgement is the one family that legitimately carries a projection figure:
    # 98.0% is a property of the PAIR, extractor plus this rule, and is the span test's own
    _citation(con, _extraction_measurement(con))
    con.execute(
        "INSERT INTO citation_judgement (citing_document, page, target_kind, target_key,"
        " judgement, value_domain, value, method, method_version, reading_channel,"
        " asserted_at, confidence, confidence_state, measured_target, score_row_id)"
        " VALUES (?, ?, ?, ?, 'span_names_document', 'boolean', 'true', 'span', 'v1',"
        " 'text-layer', ?, 0.98, 'measured', 'projection', ?)",
        (*KEY, STAMP, projection),
    )


def test_an_unmeasured_row_may_carry_zero_which_the_party_idiom_would_have_rejected(tmp_path):
    """ADR 0018 D8 says so explicitly: these tables cannot reuse 0006_parties.sql's
    `CHECK (confidence > 0)`, because the state is the predicate and the number is inert."""
    con = _store(tmp_path)
    _key(con)
    con.execute(
        "INSERT INTO citation (citing_document, page, target_kind, target_key, method,"
        " method_version, asserted_at, confidence, confidence_state)"
        " VALUES (?, ?, ?, ?, 'm', 'v', ?, 0, 'unmeasured')",
        (*KEY, STAMP),
    )
    assert con.execute("SELECT confidence FROM citation").fetchone()[0] == 0


def test_one_method_owns_a_class_and_a_second_owner_is_refused(tmp_path):
    """ADR 0018 D1, owed item 6. The citation key has no method in it, so two extractors
    emitting the same target on the same page would collide."""
    con = _store(tmp_path)
    _method(con)
    with pytest.raises(sqlite3.IntegrityError):
        _method(con, method="model:claude-sonnet-5", method_version="v1")
    # a new ranking version may re-declare ownership; that is what versioning it is for
    _method(con, method="model:claude-sonnet-5", method_version="v1", rank_version="v2")


def test_one_method_may_own_several_classes(tmp_path):
    """ADR 0017 D1 buys the API model for four classes — reporter cites, date-named
    decisions, court citations and dated obligations. The identity index paid owed item 6
    and, in the first draft of this migration, forbade the thing owed item 6 exists for."""
    con = _store(tmp_path)
    model = {"method": "model:claude-sonnet-5", "method_version": "v1"}
    _method(con, target_form="reporter", **model)
    _method(con, target_form="date-named", **model)
    _method(con, target_kind="court", target_form="docket", **model)
    got = con.execute(
        "SELECT COUNT(*) FROM assertion_method WHERE method = ?", (model["method"],)
    ).fetchone()[0]
    assert got == 3


def test_two_methods_may_not_share_a_rank_so_the_highest_ranked_row_is_singular(tmp_path):
    """The projection orders by precedence_rank alone. Two methods at one rank make the
    projected edge non-deterministic across runs and across SQLite releases."""
    con = _store(tmp_path)
    ranked = {
        "target_table": "citation_resolution",
        "reading_channel": "text-layer",
        "role": "resolve",
        "target_kind": None,
        "target_form": None,
    }
    _method(con, method="rule-1", precedence_rank=1, **ranked)
    with pytest.raises(sqlite3.IntegrityError):
        _method(con, method="rule-2", precedence_rank=1, **ranked)
    _method(con, method="rule-2", precedence_rank=2, **ranked)


def test_an_ownership_row_carries_no_rank_and_a_judgement_row_carries_no_role(tmp_path):
    """A rank on an ownership row would be a fake ordering inside the registry that orders.
    A role on a judgement row means nothing — that family's projection has no role term —
    and 'suppress' there would then demand a false-veto rate for a rule that vetoes nothing.
    """
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):  # ownership row given a rank
        _method(con, reading_channel="text-layer", role="resolve", precedence_rank=1)
    with pytest.raises(sqlite3.IntegrityError):  # resolution row with no rank
        _method(
            con,
            target_table="citation_resolution",
            reading_channel="text-layer",
            target_kind=None,
            target_form=None,
        )
    with pytest.raises(sqlite3.IntegrityError):  # judgement row given a role
        _method(
            con,
            target_table="citation_judgement",
            reading_channel="text-layer",
            role="resolve",
            precedence_rank=1,
            target_kind=None,
            target_form=None,
        )
    _method(
        con,
        target_table="citation_judgement",
        reading_channel="text-layer",
        precedence_rank=1,
        target_kind=None,
        target_form=None,
    )


def test_a_veto_may_not_exist_before_its_false_veto_rate_does(tmp_path):
    """ADR 0018 D7, owed item 7. Absence of the registry row is how the record says
    'not yet trusted'; the veto ships inert because nobody has measured it on OCR."""
    con = _store(tmp_path)
    veto = {
        "target_table": "citation_resolution",
        "method": "on-page-veto",
        "method_version": "v1",
        "reading_channel": "text-layer",
        "role": "suppress",
        "precedence_rank": 2,
        "target_kind": None,
        "target_form": None,
    }
    with pytest.raises(sqlite3.IntegrityError):
        _method(con, **veto)
    # and it may not point at some other stage's number to satisfy the rule
    extraction = _extraction_measurement(con)
    with pytest.raises(sqlite3.IntegrityError):
        _method(con, measured_target="citation", score_row_id=extraction, **veto)
    rate = _measurement(
        con, "citation_resolution", "on-page-veto", recall=None, false_veto_rate=0.015
    )
    _method(con, measured_target="citation_resolution", score_row_id=rate, **veto)
    got = con.execute("SELECT COUNT(*) FROM assertion_method WHERE role = 'suppress'").fetchone()[0]
    assert got == 1


def test_a_judgement_value_outside_its_declared_domain_is_refused(tmp_path):
    """ADR 0018 D5. One `value` column otherwise holds a boolean and two enumerations
    untyped — and the projection compares that boolean as a string."""
    con = _store(tmp_path)
    _key(con)
    _citation(con, _extraction_measurement(con))
    sql = (
        "INSERT INTO citation_judgement (citing_document, page, target_kind, target_key,"
        " judgement, value_domain, value, method, method_version, reading_channel,"
        " asserted_at, confidence, confidence_state)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'span-test', 'v1', 'text-layer', ?, 0.98,"
        " 'unmeasured')"
    )
    with pytest.raises(sqlite3.IntegrityError):  # 'yes' is not a boolean
        con.execute(sql, (*KEY, "span_names_document", "boolean", "yes", STAMP))
    with pytest.raises(sqlite3.IntegrityError):  # the domain is not this judgement's
        con.execute(sql, (*KEY, "span_names_document", "target_form", "docket", STAMP))
    with pytest.raises(sqlite3.IntegrityError):  # 'kind' has no members yet, by design
        con.execute(sql, (*KEY, "kind", "kind", "authority", STAMP))
    con.execute(sql, (*KEY, "span_names_document", "boolean", "true", STAMP))


def test_a_resolve_row_asserts_the_complete_outcome_and_the_columns_must_agree(tmp_path):
    """Owed item 3. The family test reads the docket column and query 2 keys on the decision
    column; both come off ONE row, so `outcome` cannot disagree with what is set."""
    con = _store(tmp_path)
    _key(con)
    _citation(con, _extraction_measurement(con))
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence)"
        " VALUES (1, 'FD 36873', 'FD', 36873)"
    )
    con.execute("INSERT INTO decision_work VALUES ('52526')")
    sql = (
        "INSERT INTO citation_resolution (citing_document, page, target_kind, target_key,"
        " method, method_version, reading_channel, outcome, cited_docket_id,"
        " cited_decision_id, asserted_at, confidence, confidence_state)"
        " VALUES (?, ?, ?, ?, 'registry-match', ?, 'text-layer', ?, ?, ?, ?, 0.93,"
        " 'unmeasured')"
    )
    with pytest.raises(sqlite3.IntegrityError):  # resolved, but to nothing
        con.execute(sql, (*KEY, "rule-1", "resolved", None, None, STAMP))
    with pytest.raises(sqlite3.IntegrityError):  # unresolved, yet naming a docket
        con.execute(sql, (*KEY, "rule-1", "unresolved", 1, None, STAMP))
    with pytest.raises(sqlite3.IntegrityError):  # a work with no docket around it
        con.execute(sql, (*KEY, "rule-1", "resolved", None, "52526", STAMP))
    con.execute(sql, (*KEY, "rule-1", "resolved", 1, "52526", STAMP))
    # and an unresolved target is KEPT, never discarded (ADR 0017 D2)
    con.execute(sql, (*KEY, "rule-2", "unresolved", None, None, STAMP))
    assert con.execute("SELECT COUNT(*) FROM citation_resolution").fetchone()[0] == 2


def test_a_target_kind_is_retracted_and_never_superseded_in_place(tmp_path):
    """ADR 0018 D2. target_kind is IN the key, so a corrected row mints a DIFFERENT key and
    the mis-keyed row's superseded_by points at it. The projection's obligation is the other
    half: it must join `citation` and require it live, or the retraction changes nothing."""
    con = _store(tmp_path)
    mid = _extraction_measurement(con)
    right_key = (KEY[0], KEY[1], "court", KEY[3])
    _key(con, KEY)
    _key(con, right_key)
    wrong = _citation(con, mid, KEY)
    right = _citation(con, mid, right_key)
    con.execute("UPDATE citation SET superseded_by = ? WHERE citation_id = ?", (right, wrong))
    assert _live(con, "citation") == 1


def test_an_extraction_may_be_superseded_at_a_higher_version_and_retracted_with_no_successor(
    tmp_path,
):
    """The three paths the first draft's non-partial UNIQUE forbade, which is why
    `citation_key` is a table: ADR 0017's "a better extractor supersedes rather than
    rewrites", an ownership handover, and 0009's retire-with-no-successor self-pointer for a
    docket-shaped string that is not a citation at all (the WB25-53 trap)."""
    con = _store(tmp_path)
    mid = _extraction_measurement(con)
    _key(con)
    v1 = _citation(con, mid, version="2026-08-30")
    # two LIVE rows on one key is what the partial index forbids, so the order is the one
    # 0006's re-split already uses: retire the old row at itself, insert, then repoint
    with pytest.raises(sqlite3.IntegrityError):
        _citation(con, mid, version="2026-09-15")
    con.execute("UPDATE citation SET superseded_by = ? WHERE citation_id = ?", (v1, v1))
    v2 = _citation(con, mid, version="2026-09-15")
    con.execute("UPDATE citation SET superseded_by = ? WHERE citation_id = ?", (v2, v1))
    assert _live(con, "citation") == 1
    # retirement with no successor: 0009_party_ids_permanent.sql's idiom, a self-pointer
    con.execute("UPDATE citation SET superseded_by = ? WHERE citation_id = ?", (v2, v2))
    assert _live(con, "citation") == 0
    # the key survives its assertions; it is a registry row, not a claim
    assert con.execute("SELECT COUNT(*) FROM citation_key").fetchone()[0] == 1


def test_a_child_cannot_hang_on_a_key_that_was_never_minted(tmp_path):
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO citation_reading (citing_document, page, target_kind, target_key,"
            " reading_channel, cited_raw, quoted_passage, method, method_version, asserted_at,"
            " confidence, confidence_state)"
            " VALUES (?, ?, ?, ?, 'text-layer', 'FD 36873', 'q', 'm', 'v', ?, 0.9,"
            " 'unmeasured')",
            (*KEY, STAMP),
        )


def test_a_measurement_of_one_stage_does_not_collide_with_another_stage(tmp_path):
    """Owed item 1. Without `measured_target` in the COALESCE index, the extraction figure
    and the projection figure for one class on one day are the same row — which is the
    'quoting one stage for another' error, made structural."""
    con = _store(tmp_path)
    _extraction_measurement(con)
    _measurement(
        con,
        "projection",
        "docket",
        recall=0.893,
        precision=0.980,
        projection_rule_version="span=2026-09-01;closure=v1;rank=v1",
    )
    with pytest.raises(sqlite3.IntegrityError):  # the same stage, class and day twice
        _extraction_measurement(con)
    assert con.execute("SELECT COUNT(*) FROM class_measurement").fetchone()[0] == 2
    # a NULL resolution method must not read as "distinct" — that is what COALESCE buys,
    # and the empty string may not sneak past it either
    with pytest.raises(sqlite3.IntegrityError):
        _measurement(con, "citation", "docket", resolution_method="", resolution_method_version="")


def test_a_projection_figure_must_name_the_rule_it_is_a_property_of(tmp_path):
    """ADR 0017: every published figure is a property of a PAIR — extractor plus projection
    rule — and may only be published with the rule named beside it."""
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        _measurement(
            con,
            "projection",
            "docket",
            recall=0.893,
            precision=0.980,
            projection_rule_version=None,
        )


def test_a_class_belongs_to_the_stage_that_measured_it(tmp_path):
    """Owed item 1's second half: the class vocabulary is SCOPED."""
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):  # 'on-page-veto' is a resolution class
        _measurement(
            con,
            "citation",
            "on-page-veto",
            resolution_method=None,
            resolution_method_version=None,
        )


def test_a_correction_can_now_address_a_natural_keyed_row(tmp_path):
    """ADR 0018 § Cost of reversing — the one live table this migration touches."""
    con = _store(tmp_path)
    con.execute(
        "INSERT INTO correction (target_table, target_key, note, asserted_at)"
        " VALUES ('citation', ?, 'wrong kind', ?)",
        (f"{KEY[0]}/{KEY[1]}/{KEY[2]}/{KEY[3]}", STAMP),
    )
    for table in ("citation_resolution", "citation_key", "decision_decided_date"):
        with pytest.raises(sqlite3.IntegrityError):  # a bare pk cannot name a keyed row
            con.execute(
                "INSERT INTO correction (target_table, target_key, note, asserted_at)"
                " VALUES (?, '7', 'n', ?)",
                (table, STAMP),
            )
    # a table with integer pks is unaffected; the digits are the rendering
    con.execute(
        "INSERT INTO correction (target_table, target_key, note, asserted_at)"
        " VALUES ('party_relationship', '7', 'n', ?)",
        (STAMP,),
    )


def test_a_reading_supersedes_within_its_channel_and_the_engine_is_not_in_the_key(tmp_path):
    """ADR 0018 D3. With the OCR engine in the key a re-OCR mints a row that supersedes
    nothing and doubles the live readings, over 1,480 of 9,663 image-only files."""
    con = _store(tmp_path)
    _key(con)
    _citation(con, _extraction_measurement(con))
    sql = (
        "INSERT INTO citation_reading (citing_document, page, target_kind, target_key,"
        " reading_channel, reading_method, reading_method_version, cited_raw,"
        " quoted_passage, method, method_version, asserted_at, confidence,"
        " confidence_state) VALUES (?, ?, ?, ?, 'ocr', ?, ?, 'FD 36873', 'q', 'm', 'v',"
        " ?, 0.9, 'unmeasured')"
    )
    con.execute(sql, (*KEY, "tesseract", "5.3", STAMP))
    with pytest.raises(sqlite3.IntegrityError):  # a better engine must MATCH and supersede
        con.execute(sql, (*KEY, "tesseract", "5.4", STAMP))
    rid = con.execute("SELECT reading_id FROM citation_reading").fetchone()[0]
    con.execute("UPDATE citation_reading SET superseded_by = ? WHERE reading_id = ?", (rid, rid))
    con.execute(sql, (*KEY, "tesseract", "5.4", STAMP))
    assert _live(con, "citation_reading") == 1


def test_a_decided_date_is_quoted_and_its_ordinal_is_in_the_key(tmp_path):
    """Owed item 5, and ADR 0017 D7's two fences: never a decision_record column, never a
    ledger event. Dates are quoted, never computed."""
    con = _store(tmp_path)
    sql = (
        "INSERT INTO decision_decided_date (document_sha256, date_kind, ordinal,"
        " reading_channel, method, method_version, render_profile, printed_text,"
        " decided_date, asserted_at, confidence, confidence_state) VALUES (?, 'decided', ?,"
        " 'text-layer', 'layout', 'v1', 'native', ?, ?, ?, 0.9, 'unmeasured')"
    )
    con.execute(sql, (KEY[0], 0, "Decided: October 5, 2017", "2017-10-05", STAMP))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(sql, (KEY[0], 0, "Decided: October 6, 2017", "2017-10-06", STAMP))
    con.execute(sql, (KEY[0], 1, "Decided: October 6, 2017", "2017-10-06", STAMP))
    with pytest.raises(sqlite3.IntegrityError):  # a row with no printed form is a computation
        con.execute(
            "INSERT INTO decision_decided_date (document_sha256, date_kind, reading_channel,"
            " method, method_version, render_profile, decided_date, asserted_at, confidence,"
            " confidence_state) VALUES (?, 'decided', 'text-layer', 'layout', 'v2', 'native',"
            " '2017-10-05', ?, 0.9, 'x')",
            (KEY[0], STAMP),
        )
    assert "decided_date" not in {r[1] for r in con.execute("PRAGMA table_info(decision_record)")}
    # nobody has scored this stage, so no row of it may claim to be measured: the stage is
    # in the vocabulary and has no class, exactly as the 'kind' domain has no members
    got = con.execute(
        "SELECT COUNT(*) FROM class_vocab WHERE measured_target = 'decision_decided_date'"
    ).fetchone()[0]
    assert got == 0


def test_a_re_read_at_a_better_render_sits_beside_the_earlier_quotation(tmp_path):
    """Migration 0019 — ADR 0021 D2's argument reaching the table ADR 0021 § Consequences
    said it did not reach. Two renders of one page through one engine at one version are
    DIFFERENT TEXT, so the dates read off them are different QUOTATIONS; without the render
    in the live key the second write supersedes the first and destroys a `printed_text` that
    is NOT NULL precisely because dates are quoted and never computed.

    `method`/`method_version` are the DATE EXTRACTOR's and the OCR engine stays payload in
    `reading_method`/`reading_method_version`, where 0014 had BOTH as payload. 0019 moves the
    engine's NAME into the key and leaves its VERSION out (ADR 0023 D6), so this test pins the
    RENDER axis alone: one engine at one version, read twice at different DPI."""
    con = _store(tmp_path)
    sql = (
        "INSERT INTO decision_decided_date (document_sha256, date_kind, ordinal,"
        " reading_channel, method, method_version, render_profile, reading_method,"
        " reading_method_version, printed_text, decided_date, asserted_at, confidence,"
        " confidence_state) VALUES (?, 'decided', 0, 'ocr', 'layout', 'v1', ?, 'dots.mocr',"
        " '1.5', ?, ?, ?, 0.9, 'unmeasured')"
    )
    con.execute(sql, (KEY[0], "150", "Decided: October 5, 2Ol7", None, STAMP))
    con.execute(sql, (KEY[0], "200", "Decided: October 5, 2017", "2017-10-05", STAMP))
    live = con.execute(
        "SELECT render_profile, printed_text FROM decision_decided_date"
        " WHERE superseded_by IS NULL ORDER BY render_profile"
    ).fetchall()
    assert live == [("150", "Decided: October 5, 2Ol7"), ("200", "Decided: October 5, 2017")]
    with pytest.raises(sqlite3.IntegrityError):  # the SAME render still supersedes, or collides
        con.execute(sql, (KEY[0], "200", "Decided: October 6, 2017", "2017-10-06", STAMP))


def _decided(con, **over):
    row = {
        "document_sha256": KEY[0],
        "date_kind": "decided",
        "ordinal": 0,
        "reading_channel": "ocr",
        "method": "layout",
        "method_version": "v1",
        "render_profile": "200",
        "reading_method": "dots.mocr",
        "reading_method_version": "1.5",
        "printed_text": "Decided: October 5, 2017",
        "decided_date": "2017-10-05",
        "asserted_at": STAMP,
        "confidence": 0.9,
        "confidence_state": "unmeasured",
    }
    row.update(over)
    # the engine and the channel are a biconditional: only an `ocr` row was read by one, and
    # only an `ocr` row may name one. The default row is `ocr`, so a caller switching the
    # channel clears the engine unless it says otherwise — mirroring the schema rather than
    # making every non-OCR call pass two explicit Nones.
    if row["reading_channel"] != "ocr" and "reading_method" not in over:
        row["reading_method"] = row["reading_method_version"] = None
    cols = ", ".join(row)
    con.execute(
        f"INSERT INTO decision_decided_date ({cols}) VALUES ({', '.join('?' * len(row))})",
        list(row.values()),
    )
    return con.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_a_decided_date_written_without_a_render_is_refused(tmp_path):
    """Why 0019 is a REBUILD and not an `ADD COLUMN`: under `NOT NULL`, `ADD COLUMN` requires
    a non-NULL default, so the render would have had one — and an `ocr` writer that omitted
    the column would take 'native' silently, stamping a false render on a quoted date.
    `document_text` gives the same column no default (migration 0018); this now matches it,
    and SQLite has no `ALTER COLUMN`, so getting here later was this same rebuild."""
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO decision_decided_date (document_sha256, date_kind, ordinal,"
            " reading_channel, method, method_version, printed_text, decided_date,"
            " asserted_at, confidence, confidence_state) VALUES (?, 'decided', 0, 'ocr',"
            " 'layout', 'v1', 'Decided: October 5, 2017', '2017-10-05', ?, 0.9, 'unmeasured')",
            (KEY[0], STAMP),
        )


def test_a_key_column_that_would_not_parse_back_out_of_the_rendered_key_is_refused(tmp_path):
    """`review_action.target_key` and `correction.target_key` render this row as its key
    columns joined by '/'. A HuggingFace-style engine id (`rednote-hilab/dots.ocr`) in any of
    them renders a key that cannot be parsed back into columns and can collide with a
    different split — the defect migration 0018 pins for `document_text`. `ADD COLUMN` could
    have reached `render_profile` and never `method`/`method_version`, which is the second
    reason this is a rebuild."""
    con = _store(tmp_path)
    for col in ("method", "method_version", "render_profile", "reading_method"):
        with pytest.raises(sqlite3.IntegrityError):
            _decided(con, **{col: "rmi/date-layout"})
        with pytest.raises(sqlite3.IntegrityError):
            _decided(con, **{col: ""})
    # `reading_method` joined the key at 0019, so the HuggingFace case is live HERE too: the
    # engine's published id carries a slash, and the short name is what may be stored
    with pytest.raises(sqlite3.IntegrityError):
        _decided(con, reading_method="rednote-hilab/dots.ocr")
    # the VERSION stays payload and is unconstrained, because it is not in the key
    _decided(con, reading_method_version="1.5/rc2")


def test_an_ocr_reading_must_name_the_engine_that_read_it(tmp_path):
    """ADR 0007, which CLAUDE.md lists as non-negotiable: every derived assertion carries its
    method. The pairing biconditional alone let an `ocr` row store a quotation as 'read by
    OCR' with the engine unrecorded — the hole migration 0018 closes for `document_text`."""
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        _decided(con, reading_method=None, reading_method_version=None)
    _decided(
        con,
        reading_channel="text-layer",
        render_profile="native",
        reading_method=None,
        reading_method_version=None,
    )  # the text layer has no engine to name
    # AND THE OTHER WAY, which is load-bearing now that `reading_method` is IN the key: a
    # text-layer row naming an engine and one naming none differ in a key column, so both
    # would be LIVE and the key would enforce nothing for them (code review, 2026-09-02)
    with pytest.raises(sqlite3.IntegrityError):
        _decided(
            con,
            ordinal=1,
            reading_channel="text-layer",
            render_profile="native",
            reading_method="dots.mocr",
            reading_method_version="1.5",
        )


def test_the_text_layer_and_a_human_reading_are_pinned_to_their_own_renders(tmp_path):
    """ADR 0021 D3 ties the text layer to 'native', and migration 0018 says an unenforced
    decision is a comment. A human row is pinned separately: a person read a page, not a DPI,
    and without the pin a human quotation records that it was read off the publisher's text
    layer at native render — a claim nobody made."""
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        _decided(con, reading_channel="text-layer", render_profile="300")
    _decided(con, reading_channel="text-layer", render_profile="native")
    with pytest.raises(sqlite3.IntegrityError):  # 'human' is three columns, bound together
        _decided(con, reading_channel="human", render_profile="human")
    with pytest.raises(sqlite3.IntegrityError):
        _decided(con, reading_channel="human", method="human", render_profile="native")
    _decided(
        con,
        reading_channel="human",
        method="human",
        render_profile="human",
        confidence=1.0,
        confidence_state="human",
    )


def test_two_engines_disagreeing_about_a_date_both_survive(tmp_path):
    """ADR 0023 D6, and the operator's question that forced it: an engine can read a page
    BETTER overall and get the DATE wrong. No page-level score orders those two readings — a
    decided date is one line — so an engine disagreement is a finding for a person, not a tie
    to break, and it is only a finding if both rows are still there."""
    con = _store(tmp_path)
    _decided(
        con, reading_method="dots.mocr", printed_text="Decided: October 5, 2Ol7", decided_date=None
    )
    _decided(con, reading_method="pp-ocrv6", printed_text="Decided: October 5, 2017")
    assert _live(con, "decision_decided_date") == 2
    # a VERSION bump of ONE engine is the case 0014 protected: one reader improving, so the
    # readings are ordered and the newer must MATCH and supersede rather than sitting beside
    with pytest.raises(sqlite3.IntegrityError):
        _decided(con, reading_method="dots.mocr", reading_method_version="1.6")


def test_the_live_key_is_enforced_for_readings_that_name_no_engine(tmp_path):
    """SQLite holds NULLs DISTINCT in a unique index, so the bare column would have left every
    text-layer and human row — which have no engine — unconstrained by the key it is part of,
    silently. The index coalesces to '' for exactly this reason."""
    con = _store(tmp_path)
    layer = {
        "reading_channel": "text-layer",
        "render_profile": "native",
        "reading_method": None,
        "reading_method_version": None,
    }
    _decided(con, **layer)
    with pytest.raises(sqlite3.IntegrityError):
        _decided(con, **layer)  # two live text-layer readings of one date, on one key
    assert _live(con, "decision_decided_date") == 1


def test_only_one_human_reading_of_a_date_is_live_at_a_time(tmp_path):
    """ADR 0023 D4. The live key cannot enforce this: `citator.methods.HUMAN_VERSION` is a
    DATED string sitting in `method_version`, so the day it changes a second human correction
    of one date is a second LIVE row and the display has two human answers. `document_text`
    pins human rows to 'unversioned' instead; this table cannot, because the same convention
    sits in four shipped citator keys. The index does that work and leaves them alone."""
    con = _store(tmp_path)
    human = {
        "reading_channel": "human",
        "method": "human",
        "render_profile": "human",
        "confidence": 1.0,
        "confidence_state": "human",
        "reading_method": None,
        "reading_method_version": None,
    }
    first = _decided(con, method_version="2026-09-01", **human)
    with pytest.raises(sqlite3.IntegrityError):  # the day HUMAN_VERSION is bumped
        _decided(con, method_version="2026-10-01", **human)
    con.execute(
        "UPDATE decision_decided_date SET superseded_by = ?, superseded_at = ?"
        " WHERE decided_id = ?",
        (first, STAMP, first),
    )
    _decided(con, method_version="2026-10-01", **human)  # once the first is retired
    # a different ordinal is a different date instance and is unaffected
    _decided(con, ordinal=1, method_version="2026-10-01", **human)


def test_a_page_is_recorded_where_source_location_held_it_in_json(tmp_path):
    """ADR 0023 D2. Typed, nullable and OUTSIDE the key: a re-read that paginates differently
    would otherwise mint a row that supersedes nothing — the defect `source_location` was
    taken out of the key for. ADR 0021 D4 is what makes it channel-independent: the sha fixes
    the byte stream, so page order is a property of the bytes."""
    con = _store(tmp_path)
    _decided(con, page_no=4)
    _decided(con, ordinal=1, page_no=None)  # no writer exists to be held to it yet
    for bad in (0, -1):
        with pytest.raises(sqlite3.IntegrityError):
            _decided(con, ordinal=2, page_no=bad)
    # not in the key: two renders of ONE page are two rows, and repaginating is not a new one
    assert _live(con, "decision_decided_date") == 2


def test_a_model_pass_may_not_supersede_a_human_decided_date(tmp_path):
    """The rule `citation` carries at 0014 and `document_text` at 0018, in the same idiom and
    for a sharper reason: what this table holds is a quotation. `superseded_at` travels in the
    same statement or the biconditional refuses it — which is why `store.supersede.retire`
    takes `at`, and this table's writer must pass it."""
    con = _store(tmp_path)
    human = _decided(
        con,
        reading_channel="human",
        method="human",
        render_profile="human",
        confidence=1.0,
        confidence_state="human",
    )
    model = _decided(con, ordinal=1)
    with pytest.raises(sqlite3.IntegrityError):  # superseded_by without superseded_at
        con.execute(
            "UPDATE decision_decided_date SET superseded_by = ? WHERE decided_id = ?",
            (model, model),
        )
    con.execute(  # a row retired at ITSELF passes the trigger's guard, human or not
        "UPDATE decision_decided_date SET superseded_by = ?, superseded_at = ?"
        " WHERE decided_id = ?",
        (human, STAMP, human),
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "UPDATE decision_decided_date SET superseded_by = ?, superseded_at = ?"
            " WHERE decided_id = ?",
            (model, STAMP, human),
        )


def test_an_extraction_run_separates_read_and_found_nothing_from_not_yet_read(tmp_path):
    """ADR 0018 D10. Absence is not a measurement, and 'not kept' must be a number."""
    con = _store(tmp_path)
    con.execute(
        "INSERT INTO extraction_run (document_sha256, method, method_version, reading_channel,"
        " outcome, pages_read, targets_emitted, targets_out_of_class, ran_at)"
        " VALUES (?, 'regex-docket-cite', 'v1', 'text-layer', 'read', 33, 0, 4, ?)",
        (KEY[0], STAMP),
    )
    row = con.execute("SELECT targets_emitted, targets_out_of_class FROM extraction_run").fetchone()
    assert row == (0, 4)
    with pytest.raises(sqlite3.IntegrityError):  # one row per document, method, version, channel
        con.execute(
            "INSERT INTO extraction_run (document_sha256, method, method_version,"
            " reading_channel, outcome, ran_at)"
            " VALUES (?, 'regex-docket-cite', 'v1', 'text-layer', 'read', ?)",
            (KEY[0], STAMP),
        )


def test_the_citator_is_held_back_from_the_public_dump(tmp_path):
    """dump.py's own docstring promised the enriched layer would be held — 'the party module
    today; the citator later'. It ships empty, and the licence question is answered before an
    edge is published rather than after."""
    from docketyard.store import dump

    assert "citation" in dump.HELD_TABLES and "citation_key" in dump.HELD_TABLES
    assert not dump.PUBLIC_TABLES & set(dump.HELD_TABLES)
    # a reviewer row holds an address, so it is PRIVATE and not merely held; `review_action`
    # is one row per decision, and publishing it would give a per-reviewer count nobody
    # opted into (ADR 0016)
    assert {"reviewer", "reviewer_token"} <= set(dump.PRIVATE_TABLES)
    assert "review_action" in dump.HELD_TABLES
    order = list(dump.HELD_TABLES)
    assert order.index("citation_treatment") < order.index("citation")
    assert order.index("citation") < order.index("citation_key")
    assert order.index("assertion_method") < order.index("class_measurement")

    # a correction NAMES the row it amends, and since 0014 it names it by the row's own key.
    # Dropping the held parent is not enough; the pointer has to go with it.
    con = _store(tmp_path)
    con.execute(
        "INSERT INTO correction (target_table, target_key, note, asserted_at)"
        " VALUES ('citation', ?, 'held-layer identity', ?)",
        (f"{KEY[0]}/{KEY[1]}/{KEY[2]}/{KEY[3]}", STAMP),
    )
    con.execute(
        "INSERT INTO correction (target_table, target_key, note, asserted_at)"
        " VALUES ('filing', '7', 'public', ?)",
        (STAMP,),
    )
    con.commit()
    con.close()
    out = tmp_path / "public.sqlite"
    dump.scrub(tmp_path / "s.sqlite", out)
    pub = sqlite3.connect(out)
    assert pub.execute("SELECT target_table FROM correction").fetchall() == [("filing",)]
    pub.close()


def test_a_model_pass_may_not_supersede_a_human_citation_row(tmp_path):
    """ADR 0017 D5. `citation` is the only family whose live key carries no method, so the
    supersession order does not merely permit a re-extraction to displace a human row — it
    requires it. The rule needed teeth here, and RAISE(ABORT) is 0009's idiom."""
    con = _store(tmp_path)
    mid = _extraction_measurement(con)
    _key(con)
    human = (
        con.execute(
            "INSERT INTO citation (citing_document, page, target_kind, target_key, method,"
            " method_version, asserted_at, confidence, confidence_state)"
            " VALUES (?, ?, ?, ?, 'human', 'v1', ?, 1.0, 'human')",
            (*KEY, STAMP),
        )
        and con.execute("SELECT MAX(citation_id) FROM citation").fetchone()[0]
    )
    # a human row may retire itself with no successor: it points at its own, human, row
    con.execute("UPDATE citation SET superseded_by = ? WHERE citation_id = ?", (human, human))
    con.execute("UPDATE citation SET superseded_by = NULL WHERE citation_id = ?", (human,))
    # but a model row may not take its place
    con.execute("UPDATE citation SET superseded_by = ? WHERE citation_id = ?", (human, human))
    model = _citation(con, mid)
    con.execute("UPDATE citation SET superseded_by = NULL WHERE citation_id = ?", (model,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE citation SET superseded_by = ? WHERE citation_id = ?", (model, human))


def test_a_veto_suppresses_only_what_it_actually_vetoed(tmp_path):
    """A veto pass that records every target it checked AND CLEARED is the auditable way to
    write one. On `role` alone it would suppress everything it looked at, so the projection
    reads the outcome too — and `vetoed` was in the vocabulary and read by nothing."""
    from docketyard.citator import project

    sql = Path("docs/citator-query-2.sql").read_text(encoding="utf-8")
    # validation query 2 and the shipping projection are different jobs over the SAME terms
    for text in (sql, project.PROJECTION):
        assert "role = 'suppress' AND outcome = 'vetoed'" in text
        # the confidence predicate reaches the parent, which it did not until the second
        # schema-critic pass, and the reading, which it did not until the third
        assert text.count("c.confidence_state IN ('measured', 'human')") == 1
        assert text.count("rg.confidence_state IN ('measured', 'human')") == 1
        # and the exposure gate, which query 2 lacked while the shipping projection had it —
        # so Q2 returned a SUPERSET of what a reader sees, silently
        for term in (
            "judgement = 'exposed' AND value = 'true'",
            "outcome NOT IN ('resolved', 'repaired')",
        ):
            assert term in text, term


def test_the_reading_stage_can_be_measured_once_somebody_measures_ocr(tmp_path):
    """ADR 0017 D3 names the day: OCR ships stored and unprojected UNTIL SOMEBODY MEASURES
    IT. SQLite cannot alter a CHECK, and citation_reading is the largest table here, so the
    stage is declared now and its class vocabulary left empty."""
    con = _store(tmp_path)
    stages = {r[0] for r in con.execute("SELECT measured_target FROM measured_target_vocab")}
    assert "citation_reading" in stages
    got = con.execute(
        "SELECT COUNT(*) FROM class_vocab WHERE measured_target = 'citation_reading'"
    ).fetchone()[0]
    assert got == 0  # nothing scored yet, so no reading row can claim to be measured
    # a resolution, by contrast, may NOT carry the projection's figure: that is the one path
    # by which a row could display 98.0% beside a resolution
    _key(con)
    _citation(con, _extraction_measurement(con))
    projection = _measurement(
        con,
        "projection",
        "docket",
        recall=0.893,
        precision=0.980,
        projection_rule_version="span=2026-09-01;closure=v1;rank=v1",
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO citation_resolution (citing_document, page, target_kind, target_key,"
            " method, method_version, reading_channel, outcome, asserted_at, confidence,"
            " confidence_state, measured_target, score_row_id)"
            " VALUES (?, ?, ?, ?, 'm', 'v', 'text-layer', 'unresolved', ?, 0.98, 'measured',"
            " 'projection', ?)",
            (*KEY, STAMP, projection),
        )


def test_a_resolution_whose_method_is_unregistered_projects_nothing(tmp_path):
    """The candidate set joins assertion_method INNER. A human review whose method was never
    registered fails closed and silently — worth pinning, so the reviewer path is not
    discovered empirically on the day somebody uses it."""
    con = _store(tmp_path)
    _key(con)
    _citation(con, _extraction_measurement(con))
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence)"
        " VALUES (1, 'FD 36873', 'FD', 36873)"
    )
    con.execute(
        "INSERT INTO citation_resolution (citing_document, page, target_kind, target_key,"
        " method, method_version, reading_channel, outcome, cited_docket_id, asserted_at,"
        " confidence, confidence_state)"
        " VALUES (?, ?, ?, ?, 'human', 'v1', 'human', 'resolved', 1, ?, 1.0, 'human')",
        (*KEY, STAMP),
    )
    rows = con.execute(
        Path("docs/citator-query-2.sql").read_text(encoding="utf-8"),
        {"rank_version": "v1", "target_work": "52526"},
    ).fetchall()
    assert rows == []  # no assertion_method row ranks it, so it is not a candidate
