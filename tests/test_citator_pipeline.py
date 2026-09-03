"""`docketyard.citator` — the pass that fills migration 0014's shape.

The projection is exercised end to end here on a hand-built store; the sixty-decision
benchmark is exercised by `tools/rmi-ai-machine/citation_dryrun.py`, which imports the same
code. Between them, a change that alters what a reader is shown breaks something.
"""

import argparse
import json
import sqlite3

import pytest

from docketyard import cli
from docketyard.citator import judge, keys, load, methods, project, resolve
from docketyard.store import db

STAMP = "2026-09-01T00:00:00+00:00"
SHA = "d" * 64


def _store(tmp_path):
    """One docket family, one decision on it, one document of its bytes.

    `FD 36873` is the parent, `FD 36873 (1)` its sub-docket, `EP 445` an unrelated
    proceeding — so the family closure has something to include and something to exclude.
    """
    con = db.connect(tmp_path / "s.sqlite")
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence, sub_sequence, suffix,"
        " parent_docket_id) VALUES (1, 'FD_36873', 'FD', 36873, NULL, NULL, NULL)"
    )
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence, sub_sequence, suffix,"
        " parent_docket_id) VALUES (2, 'FD_36873_1', 'FD', 36873, 1, NULL, 1)"
    )
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence, sub_sequence, suffix,"
        " parent_docket_id) VALUES (3, 'EP_445', 'EP', 445, NULL, NULL, NULL)"
    )
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence, sub_sequence, suffix,"
        " parent_docket_id) VALUES (4, 'AB_1296_0_X', 'AB', 1296, NULL, 'X', NULL)"
    )
    con.execute(
        "INSERT INTO capture (capture_id, source_system, endpoint, request_params,"
        " response_sha256, http_status, filter_asserted, ingest_mode, captured_at,"
        " table_action) VALUES (1, 's', 'e', '{}', 'x', 200, 1, 'forward', ?, 't')",
        (STAMP,),
    )
    con.execute(
        "INSERT INTO event (event_id, event_type, docket_id, recorded_at, capture_id,"
        " source_key, payload, payload_version)"
        " VALUES (1, 'decision_observed', 1, ?, 1, 'k', '{}', 1)",
        (STAMP,),
    )
    con.execute(
        "INSERT INTO decision_record (decision_pk, docket_id, stb_decision_id, service_date,"
        " observed_in_event) VALUES (1, 1, '52526', '2021-03-12', 1)"
    )
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'pdf', ?)",
        (SHA, STAMP),
    )
    con.execute(
        "INSERT INTO decision_attachment (decision_pk, source_url, document_sha256)"
        " VALUES (1, 'u', ?)",
        (SHA,),
    )
    con.execute("INSERT INTO decision_work VALUES ('52526')")
    return con


def _scored(
    con,
    precision=0.981,
    channel=methods.CHANNEL_TEXT,
    stages=("citation", "citation_resolution", "projection"),
):
    """Score every stage, because an unscored class projects nothing (ADR 0017 D3) — on ONE
    channel, because a measurement is of the text it was taken on (ADR 0018 D8)."""
    for stage in stages:
        methods.measure(
            con,
            measured_target=stage,
            cls="docket",
            extractor_version="v1",
            score_file="test",
            benchmark_date="2026-09-01",
            reading_channel=channel,
            recall=0.911,
            precision=precision,
        )
    methods.declare(con, "v1")
    return methods.stamp(con, stages=stages, channel=channel)


def _batch(tmp_path, **docs):
    """A findings directory: each keyword is a file, a dict is dumped and a str written raw."""
    batch = tmp_path / "findings"
    batch.mkdir(exist_ok=True)
    for name, doc in docs.items():
        body = doc if isinstance(doc, str) else json.dumps(doc)
        (batch / f"{name}.json").write_text(body, encoding="utf-8")
    return batch


def _load_verb(tmp_path, batch) -> int:
    """`docketyard citator load` against the store `_store` built, as the CLI calls it."""
    return cli._citator(
        argparse.Namespace(db=str(tmp_path / "s.sqlite"), what="load", findings=str(batch))
    )


def _findings(*findings):
    return {
        "document_sha256": SHA,
        "method": methods.EXTRACTOR,
        "method_version": "v1",
        "reading_channel": methods.CHANNEL_TEXT,
        "pages_read": 9,
        "findings": list(findings),
    }


# --- the key ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,key",
    [
        ("FD 36873", "FD 36873"),
        ("Docket No. FD-36873", "FD 36873"),
        ("EP 328 (Sub-No. 2)", "EP 328 (2)"),
        ("EP 328 (2)", "EP 328 (2)"),  # idempotent
        ("AB 1296X", "AB 1296 (X)"),
        ("AB 1296 (X)", "AB 1296 (X)"),  # idempotent — the defect this test exists for
        ("AB 55 (Sub-No. 814X)", "AB 55 (814X)"),
        ("EP 328 (STB served Oct. 5, 2017)", "EP 328"),  # a wordy paren is not a sub-docket
        ("the exemption is 30 days after", None),  # `IS 30` is the trap, not a docket
        ("", None),
    ],
)
def test_the_normaliser_reads_a_printed_target(raw, key):
    assert keys.normalise(raw) == key


def test_the_normaliser_is_idempotent_or_a_rendered_key_cannot_be_read_back():
    """`AB 1296X` normalised to `AB 1296 (X)` while `AB 1296 (X)` normalised to `AB 1296`
    until 2026-09-01 — one docket with two normal forms depending on how it was printed. It
    put 2,711 suffixed dockets into the scorer's registry without their suffix, so every
    finding naming one scored as unresolvable and the projected figure was measured low."""
    for raw in ("AB 1296X", "AB 1296 (X)", "EP 328 (Sub-No. 2)", "AB 55 (814X)", "FD 36873"):
        once = keys.normalise(raw)
        assert once is not None and keys.normalise(once) == once


def test_the_registry_key_and_the_scorers_agree(tmp_path):
    """The scorer keeps its own copy on purpose — a scorer that imports the code it scores
    cannot catch that code being wrong — so the two are pinned equal here instead."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path("tools/rmi-ai-machine").resolve()))
    import projection_score as ps

    for row in (
        ("AB", 1296, None, "X"),
        ("EP", 328, 2, None),
        ("FD", 36873, None, None),
        ("AB", 55, 814, "X"),
        ("AB", 33, None, "TA"),
    ):
        assert keys.registry_key(*row) == ps.printed(*row)


def test_the_rendered_key_is_readable_and_never_a_digest():
    assert keys.render(SHA, 3, "stb", "AB 1296 (X)") == f"{SHA}/3/stb/AB 1296 (X)"


# --- resolution ------------------------------------------------------------------------


def test_rule_one_resolves_and_an_unresolved_target_is_kept(tmp_path):
    con = _store(tmp_path)
    held = keys.registry(con)
    assert resolve.resolve("FD 36873", held) == resolve.Resolution(
        outcome="resolved", method=resolve.RULE_1, docket_id=1
    )
    # ADR 0017 D2: a target the registry cannot resolve is a REAL EDGE bound for a human,
    # and a finder that could not emit one would empty that queue by construction
    miss = resolve.resolve("NOR 99999", held)
    assert miss.outcome == "unresolved" and miss.docket_id is None


def test_rule_two_repairs_a_five_digit_number_and_never_rewrites_the_raw(tmp_path):
    con = _store(tmp_path)
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence) VALUES (5, 'FD_3687', "
        "'FD', 3687)"
    )
    held = keys.registry(con)
    repaired = resolve.resolve("FD 36878", held)  # not held; `FD 3687` is
    assert repaired.outcome == "repaired" and repaired.docket_id == 5
    assert repaired.method == resolve.RULE_2  # a DISTINCT method, so it can be ranked below
    # four digits is not the repair's shape: `\d{1,5}` caps the finder, so only a five-digit
    # number can have absorbed a sixth character
    assert resolve.resolve("FD 3688", held).outcome == "unresolved"


def test_the_exposure_test_flags_a_fused_footnote_marker(tmp_path):
    """ADR 0017 § The exposure test: a bare number of four digits or fewer whose
    last-digit-stripped reading is ALSO held resolves CONFIDENTLY TO THE WRONG proceeding."""
    con = _store(tmp_path)
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence) VALUES (6, 'AB_124', "
        "'AB', 124)"
    )
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence) VALUES (7, 'AB_1242', "
        "'AB', 1242)"
    )
    held = keys.registry(con)
    assert resolve.resolve("AB 1242", held).exposed is True  # `AB 124` + footnote `2`
    assert resolve.resolve("FD 36873", held).exposed is False  # five digits: capped
    assert resolve.resolve("AB 1296 (X)", held).exposed is False  # not a bare digit run


# --- the measurement a row is stamped from ----------------------------------------------


def test_an_unscored_class_cannot_stamp_a_row(tmp_path):
    """ADR 0017 D3: a class nobody has scored is unmeasured and projects nothing."""
    con = _store(tmp_path)
    with pytest.raises(methods.Unscored):
        methods.stamp(con)
    methods.measure(
        con,
        measured_target="citation",
        cls="docket",
        extractor_version="v1",
        score_file="t",
        benchmark_date="2026-09-01",
        recall=0.9,
    )
    # measured, but with a recall and no precision — and a row is stamped with a PRECISION
    with pytest.raises(methods.Unscored, match="no precision"):
        methods.stamp(con, stages=("citation",))


def test_a_measurement_of_another_channel_cannot_stamp_a_row(tmp_path):
    """`stamp` selected on (measured_target, class) alone until 2026-09-03, so the first
    OCR-channel load would have stamped every row with the TEXT-LAYER precision, marked it
    `measured` and published it — the ADR 0017 D3 violation `docs/ocr-migration.md` held as
    live. A channel nobody has scored is unscored, whatever another channel measured."""
    con = _store(tmp_path)
    _scored(con)  # every stage, on the text layer
    assert methods.stamp(con)  # the default channel is the text layer
    with pytest.raises(methods.Unscored, match="'ocr'"):
        methods.stamp(con, channel="ocr")
    # score the OCR channel and the OCR stamp is that row, not the text layer's
    ocr = _scored(con, precision=0.5, channel="ocr", stages=("citation",))
    assert ocr["citation"][1] == 0.5
    assert methods.stamp(con, stages=("citation",))["citation"][1] == 0.981


def test_the_loader_refuses_stamps_measured_on_another_channel(tmp_path):
    """The CLI stamps once per batch; the loader checks the stamps it is handed against the
    measurement rows themselves, so a caller that stamped the wrong channel — or a batch
    the CLI's own refusal did not see — writes nothing rather than a borrowed figure."""
    con = _store(tmp_path)
    stamps = _scored(con)  # text-layer stamps
    doc = _findings({"page": 4, "target": "EP 445", "quoted": "EP 445, slip op. at 3."})
    doc["reading_channel"] = "ocr"
    with pytest.raises(load.WrongChannel, match="'ocr'"):
        load.load_document(con, doc, keys.registry(con), stamps)
    for table in ("citation", "citation_reading", "citation_resolution", "citation_judgement"):
        assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


def test_the_loader_refuses_a_channel_a_model_pass_cannot_read_on(tmp_path):
    """A null channel passed the store check — `reading_channel <> NULL` matches nothing —
    and then died on `citation_reading`'s NOT NULL with the identity row already written.
    And 'human' is legal in `reading_vocab` but is never what a model pass read from: a
    model row carrying it is what `review._human_reading` finds and reuses as evidence."""
    con = _store(tmp_path)
    stamps = _scored(con)
    doc = _findings({"page": 4, "target": "EP 445", "quoted": "EP 445, slip op. at 3."})
    for channel in (None, "human", "text_layer"):
        with pytest.raises(load.WrongChannel, match=repr(channel)):
            load.load_document(con, dict(doc, reading_channel=channel), keys.registry(con), stamps)
    assert con.execute("SELECT COUNT(*) FROM citation").fetchone()[0] == 0


def test_the_load_verb_refuses_a_batch_that_mixes_channels(tmp_path, capsys):
    """One channel per load, as one pass per load: the stamps are taken once for the batch
    and a measurement is of one channel (ADR 0018 D8). A null channel is refused, not
    sorted against a string (which raised TypeError inside the refusal message)."""
    con = _store(tmp_path)
    _scored(con)
    con.commit()
    con.close()
    text_doc = _findings({"page": 4, "target": "EP 445", "quoted": "EP 445, slip op. at 3."})
    batch = _batch(tmp_path, a=text_doc, b=dict(text_doc, reading_channel="ocr"))
    assert _load_verb(tmp_path, batch) == 1  # mixed: refused before any stamp is taken
    assert "mixes" in capsys.readouterr().out
    batch = _batch(tmp_path, a=text_doc, b=dict(text_doc, reading_channel=None))
    assert _load_verb(tmp_path, batch) == 1
    assert "mixes" in capsys.readouterr().out
    batch = _batch(
        tmp_path, a=dict(text_doc, reading_channel=None), b=dict(text_doc, reading_channel=None)
    )
    assert _load_verb(tmp_path, batch) == 1
    assert "not one of" in capsys.readouterr().out
    con = db.connect(tmp_path / "s.sqlite")
    assert con.execute("SELECT COUNT(*) FROM citation_reading").fetchone()[0] == 0


def test_the_load_verb_refuses_a_channel_nobody_scored_or_ranked(tmp_path, capsys):
    """Unscored: refused as before. Scored but UNRANKED: `declare` ranks the text layer
    only, and the projection INNER-joins each resolution to its rank row on the channel, so
    an OCR load would have stored `measured` rows no page can ever show, and exited 0."""
    con = _store(tmp_path)
    _scored(con)
    con.commit()
    con.close()
    doc = _findings({"page": 4, "target": "EP 445", "quoted": "EP 445, slip op. at 3."})
    batch = _batch(tmp_path, a=dict(doc, reading_channel="ocr"))
    assert _load_verb(tmp_path, batch) == 1
    assert "no class_measurement" in capsys.readouterr().out
    con = db.connect(tmp_path / "s.sqlite")
    _scored(con, precision=0.5, channel="ocr")
    con.commit()
    con.close()
    assert _load_verb(tmp_path, batch) == 1
    assert "ranked on channel 'ocr'" in capsys.readouterr().out
    con = db.connect(tmp_path / "s.sqlite")
    assert con.execute("SELECT COUNT(*) FROM citation_reading").fetchone()[0] == 0


def test_the_confidence_on_a_row_is_the_one_the_measurement_holds(tmp_path):
    """No figure lives in the package. A constant would be a second home for a number
    `class_measurement` already holds, and the two would drift — which is the failure this
    record has repeated four times."""
    con = _store(tmp_path)
    stamps = _scored(con, precision=0.777)
    load.load_document(
        con, _findings({"page": 4, "target": "EP 445", "quoted": "q"}), keys.registry(con), stamps
    )
    got = con.execute("SELECT DISTINCT confidence FROM citation_resolution").fetchone()
    assert got[0] == 0.777


# --- loading ----------------------------------------------------------------------------


def test_a_findings_document_becomes_four_families_and_a_run(tmp_path):
    con = _store(tmp_path)
    stamps = _scored(con)
    result = load.load_document(
        con,
        _findings(
            {"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."},
            {"page": 9, "target": "NOR 99999", "quoted": "a proceeding we do not hold"},
            {"page": 9, "target": "3 I.C.C.2d 196", "quoted": "a reporter cite"},
        ),
        keys.registry(con),
        stamps,
    )
    assert (result.emitted, result.resolved, result.unresolved) == (2, 1, 1)
    assert result.out_of_class == 1  # the reporter cite: COUNTED, never silently dropped
    for table in ("citation_key", "citation", "citation_reading", "citation_resolution"):
        assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 2
    # ADR 0018 D10: absence is not a measurement, and "not kept" must be a number
    run = con.execute(
        "SELECT pages_read, targets_emitted, targets_out_of_class FROM extraction_run"
    ).fetchone()
    assert run == (9, 2, 1)


def test_a_re_run_replaces_the_pass_row_and_supersedes_nothing_else(tmp_path):
    con = _store(tmp_path)
    stamps = _scored(con)
    doc = _findings({"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."})
    load.load_document(con, doc, keys.registry(con), stamps)
    # the same version again: the pass row is a RECORD OF A PASS, not an assertion
    load.load_document(con, doc, keys.registry(con), stamps)
    assert con.execute("SELECT COUNT(*) FROM extraction_run").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM citation_key").fetchone()[0] == 1


def test_an_unresolved_target_reaches_no_page_but_is_stored(tmp_path):
    con = _store(tmp_path)
    stamps = _scored(con)
    load.load_document(
        con,
        _findings({"page": 4, "target": "NOR 99999", "quoted": "slip op. at 3"}),
        keys.registry(con),
        stamps,
    )
    assert con.execute("SELECT outcome FROM citation_resolution").fetchone()[0] == "unresolved"
    assert project.projected(con) == []


# --- the projection ---------------------------------------------------------------------


def test_an_edge_outside_the_family_projects(tmp_path):
    con = _store(tmp_path)
    stamps = _scored(con)
    load.load_document(
        con,
        _findings({"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."}),
        keys.registry(con),
        stamps,
    )
    rows = project.projected(con)
    assert len(rows) == 1
    assert rows[0][0] == "52526" and rows[0][2] == "EP 445"  # folded to the WORK
    assert project.cited_by(con, docket_id=3) == rows
    assert project.cited_by(con, work_id="52526") == []  # nothing resolves to a work yet


def test_an_own_family_mention_is_suppressed_unless_its_span_names_a_document(tmp_path):
    """ADR 0017 D4, and the reason the span test is a stored assertion: it decides what
    every published edge IS. The sub-docket is inside the citing decision's family."""
    con = _store(tmp_path)
    stamps = _scored(con)
    load.load_document(
        con,
        _findings({"page": 4, "target": "FD 36873 (Sub-No. 1)", "quoted": "Docket No. FD 36873"}),
        keys.registry(con),
        stamps,
    )
    assert judge.names_document("Docket No. FD 36873") is False
    assert project.projected(con) == []  # the default is SUPPRESS, not project

    con2 = _store(tmp_path / "b")
    stamps2 = _scored(con2)
    load.load_document(
        con2,
        _findings(
            {
                "page": 4,
                "target": "FD 36873 (Sub-No. 1)",
                "quoted": "FD 36873 (Sub-No. 1), slip op. at 6 (STB served Mar. 12, 2021)",
            }
        ),
        keys.registry(con2),
        stamps2,
    )
    # inside the family, but the span names a DOCUMENT — the reconsideration edge Q2 exists
    # to find, and the abbreviated month is the case the pattern was fixed for
    assert len(project.projected(con2)) == 1


def test_a_retraction_bites_because_the_projection_joins_live_citation(tmp_path):
    """ADR 0018 D2. A retraction supersedes ONLY the citation row; the resolution and the
    judgement anchored on the retracted key still read superseded_by IS NULL."""
    con = _store(tmp_path)
    stamps = _scored(con)
    load.load_document(
        con,
        _findings({"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."}),
        keys.registry(con),
        stamps,
    )
    assert len(project.projected(con)) == 1
    cid = con.execute("SELECT citation_id FROM citation").fetchone()[0]
    con.execute("UPDATE citation SET superseded_by = ? WHERE citation_id = ?", (cid, cid))
    assert (
        con.execute(
            "SELECT COUNT(*) FROM citation_resolution WHERE superseded_by IS NULL"
        ).fetchone()[0]
        == 1
    )  # the child is untouched, and harmless...
    assert project.projected(con) == []  # ...because the parent must be live


def test_an_unmeasured_extraction_reaches_no_page(tmp_path):
    """The confidence predicate is stated for EVERY family, and the `citation` join carried
    liveness but not the predicate until the second schema-critic pass."""
    con = _store(tmp_path)
    stamps = _scored(con)
    load.load_document(
        con,
        _findings({"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."}),
        keys.registry(con),
        stamps,
    )
    con.execute(
        "UPDATE citation SET confidence_state = 'unmeasured', score_row_id = NULL,"
        " measured_target = NULL, confidence = 0"
    )
    assert project.projected(con) == []


def test_cited_by_takes_exactly_one_grain(tmp_path):
    """A public 'cited by' count may not silently mix two grains (ADR 0018 D9)."""
    con = _store(tmp_path)
    with pytest.raises(ValueError):
        project.cited_by(con)
    with pytest.raises(ValueError):
        project.cited_by(con, docket_id=1, work_id="52526")


def test_the_veto_ships_inert_and_suppresses_only_what_it_vetoed(tmp_path):
    """ADR 0018 D7: a suppress row exists only once its false-veto rate is measured, and a
    veto pass that records what it CHECKED AND CLEARED must not suppress that."""
    con = _store(tmp_path)
    stamps = _scored(con)
    load.load_document(
        con,
        _findings({"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."}),
        keys.registry(con),
        stamps,
    )
    rate = methods.measure(
        con,
        measured_target="citation_resolution",
        cls="on-page-veto",
        extractor_version="v1",
        score_file="t",
        benchmark_date="2026-09-02",
        false_veto_rate=0.015,
    )
    con.execute(
        "INSERT INTO assertion_method (target_table, method, method_version, reading_channel,"
        " role, precedence_rank, measured_target, score_row_id, rank_version, declared_at)"
        " VALUES ('citation_resolution', 'on-page-veto', 'v1', 'text-layer', 'suppress', 9,"
        " 'citation_resolution', ?, ?, ?)",
        (rate, methods.RANK_VERSION, STAMP),
    )
    row = con.execute(
        "SELECT citing_document, page, target_kind, target_key FROM citation_resolution"
    ).fetchone()
    veto = (
        "INSERT INTO citation_resolution (citing_document, page, target_kind, target_key,"
        " method, method_version, reading_channel, outcome, cited_docket_id, asserted_at,"
        " confidence, confidence_state, measured_target, score_row_id)"
        " VALUES (?, ?, ?, ?, 'on-page-veto', 'v1', 'text-layer', ?, ?, ?, 0.985, 'measured',"
        " 'citation_resolution', ?)"
    )
    # checked AND CLEARED: the auditable way to write a veto pass, and it must not suppress
    con.execute(veto, (*row, "resolved", 3, STAMP, rate))
    assert len(project.projected(con)) == 1
    con.execute(
        "UPDATE citation_resolution SET outcome = 'vetoed', cited_docket_id = NULL"
        " WHERE method = 'on-page-veto'"
    )
    assert project.projected(con) == []


def test_a_human_resolution_needs_a_human_reading_or_it_projects_nothing(tmp_path):
    """The reading join is INNER and channel-matched, which is an invariant on the writer
    rather than an accident — migration 0014's header states it, and this pins it."""
    con = _store(tmp_path)
    stamps = _scored(con)
    load.load_document(
        con,
        _findings({"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."}),
        keys.registry(con),
        stamps,
    )
    row = con.execute(
        "SELECT citing_document, page, target_kind, target_key FROM citation_resolution"
    ).fetchone()
    con.execute(
        "INSERT INTO citation_resolution (citing_document, page, target_kind, target_key,"
        " method, method_version, reading_channel, outcome, cited_docket_id, asserted_at,"
        " confidence, confidence_state) VALUES (?, ?, ?, ?, 'human', ?, 'human',"
        " 'resolved', 3, ?, 1.0, 'human')",
        (*row, methods.HUMAN_VERSION, STAMP),
    )
    # `declare` registered the human resolver at rank 0, so it outranks the machine and now
    # owns the edge — but it brought no reading, and the reading join is INNER
    assert project.projected(con) == []
    con.execute(
        "INSERT INTO citation_reading (citing_document, page, target_kind, target_key,"
        " reading_channel, cited_raw, quoted_passage, method, method_version, asserted_at,"
        " confidence, confidence_state) VALUES (?, ?, ?, ?, 'human', 'EP 445', 'as read',"
        " 'human', 'v1', ?, 1.0, 'human')",
        (*row, STAMP),
    )
    assert len(project.projected(con)) == 1
    # A human answer at a version the registry does not know is DROPPED from the candidate
    # set, and the machine's answer publishes again — the edge REAPPEARS rather than
    # vanishing. Pinned because it is not obvious and it is not fail-closed: an unregistered
    # reviewer method silently un-does the review instead of blocking the edge.
    con.execute(
        "UPDATE citation_resolution SET method_version = 'not-declared'"
        " WHERE confidence_state = 'human'"
    )
    back = project.projected(con)
    assert len(back) == 1 and back[0][6] == "measured"  # the machine's row, not the human's


def test_the_projection_and_query_two_share_their_terms(tmp_path):
    """`docs/citator-query-2.sql` is validation query 2 written out and `project.py` is the
    shipping projection; they are different jobs over the SAME terms, and they drifted
    within a day of being written. Both must still run, and agree where they overlap."""
    con = _store(tmp_path)
    stamps = _scored(con)
    load.load_document(
        con,
        _findings({"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."}),
        keys.registry(con),
        stamps,
    )
    from pathlib import Path

    q2 = Path("docs/citator-query-2.sql").read_text(encoding="utf-8")
    for term in (
        "role = 'suppress' AND outcome = 'vetoed'",
        "AND c.confidence_state IN ('measured', 'human')",
        "rc.role = 'resolve' AND rc.outcome IN ('resolved', 'repaired')",
        "COALESCE(sp.value, 'false') <> 'true'",
    ):
        assert term in q2 and term in project.PROJECTION, term
    rows = con.execute(
        q2, {"rank_version": methods.RANK_VERSION, "target_work": "52526"}
    ).fetchall()
    assert rows == []  # no treatment row exists; ADR 0017 D7's day-one answer
    assert len(project.projected(con)) == 1


def test_the_store_and_the_dry_run_agree_on_the_shipped_projection():
    """A guard against the projection being edited in one place. `citation_dryrun.py` no
    longer carries its own copy — it imports this one — and this asserts that stays true."""
    from pathlib import Path

    dry = Path("tools/rmi-ai-machine/citation_dryrun.py").read_text(encoding="utf-8")
    assert "WITH rank_res AS" not in dry, "the dry run has grown a second projection"
    assert "project.projected(con)" in dry


def test_sqlite_will_not_silently_accept_a_bad_stage_pointer(tmp_path):
    """The stage-scoped pointer is a foreign key, not a convention: a projection figure
    cannot be stamped on an extraction row."""
    con = _store(tmp_path)
    _scored(con)
    projection = con.execute(
        "SELECT measurement_id FROM class_measurement WHERE measured_target = 'projection'"
    ).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO citation_key (citing_document, page, target_kind, target_key,"
            " key_version, first_seen_at) VALUES (?, 1, 'stb', 'EP 445', 'v1', ?)",
            (SHA, STAMP),
        )
        con.execute(
            "INSERT INTO citation (citing_document, page, target_kind, target_key, method,"
            " method_version, asserted_at, confidence, confidence_state, measured_target,"
            " score_row_id) VALUES (?, 1, 'stb', 'EP 445', 'm', 'v', ?, 0.98, 'measured',"
            " 'citation', ?)",
            (SHA, STAMP, projection),
        )


# --- what the two reviews of 2026-09-01 found ------------------------------------------


def test_a_parenthetical_is_never_grafted_from_further_down_the_sentence():
    """The first draft of the idempotence fix searched a 30-character window, so a trailing
    year or a LATER docket's sub-number was welded onto this key — a resolvable citation
    stored unresolved, or one pointing at the wrong proceeding."""
    assert keys.normalise("Docket No. FD 35873, slip op. at 4 (2015)") == "FD 35873"
    assert keys.normalise("EP 445 and FD 36873 (Sub-No. 1)") == "EP 445"
    assert keys.normalise("EP 328 (STB served Oct. 5, 2017)") == "EP 328"
    # and the line break the window was actually there for still works
    assert keys.normalise("EP 711 (Sub-\nNo. 2)") == "EP 711 (2)"


def test_the_scorer_and_the_shipped_normaliser_read_printed_text_the_same_way():
    """`projection_score.printed` was fixed on the registry side, and `norm_target` — which
    keys BOTH sides of the truth and run sets — still had the defect. The dry run then
    compared keys from two normalisers and reported agreement."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path("tools/rmi-ai-machine").resolve()))
    import benchmark_score as bs

    for raw in (
        "AB 1296X",
        "AB 1296 (X)",
        "EP 328 (Sub-No. 2)",
        "EP 328 (2)",
        "FD 36873",
        "AB 55 (Sub-No. 814X)",
        "Docket No. FD 35873, slip op. at 4 (2015)",
    ):
        assert bs.norm_target(raw) == keys.normalise(raw), raw


def test_an_unresolved_target_resolves_when_the_registry_catches_up(tmp_path):
    """The registry grows through waves 2-3. `citation_resolution`'s key carries the
    RESOLVER's version, not the run's, so an INSERT OR IGNORE kept the first answer for ever
    — and for a target the registry did not yet hold, the first answer is `unresolved`. ADR
    0017 D2's "store it unresolved, resolve it later" would have had no later."""
    con = _store(tmp_path)
    stamps = _scored(con)
    doc = _findings({"page": 4, "target": "NOR 42150", "quoted": "See NOR 42150, slip op. at 3."})
    load.load_document(con, doc, keys.registry(con), stamps)
    assert con.execute("SELECT outcome FROM citation_resolution").fetchone()[0] == "unresolved"
    assert project.projected(con) == []

    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence)"
        " VALUES (9, 'NOR_42150', 'NOR', 42150)"
    )
    load.load_document(con, doc, keys.registry(con), stamps)  # same pass, bigger registry
    live = con.execute(
        "SELECT outcome, cited_docket_id FROM citation_resolution WHERE superseded_by IS NULL"
    ).fetchall()
    assert live == [("resolved", 9)]
    assert len(project.projected(con)) == 1
    # the old answer is superseded, never deleted
    assert con.execute("SELECT COUNT(*) FROM citation_resolution").fetchone()[0] == 2


def test_a_second_reading_channel_is_written_even_though_the_key_is_unchanged(tmp_path):
    """The citation key carries no channel, so an OCR pass over a document already read from
    its text layer matches on the key — and must still write its own reading, resolution and
    judgement. ADR 0018 D3 designs `citation_reading` around exactly that second row."""
    con = _store(tmp_path)
    stamps = _scored(con)
    finding = {"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."}
    load.load_document(con, _findings(finding), keys.registry(con), stamps)
    ocr = _findings(finding) | {
        "reading_channel": "ocr",
        "reading_method": "tesseract",
        "reading_method_version": "5.3",
    }
    # stamped from the OCR channel's OWN measurement: the text-layer stamps are refused
    ocr_stamps = _scored(con, precision=0.5, channel="ocr")
    result = load.load_document(con, ocr, keys.registry(con), ocr_stamps)
    assert result.unchanged == 1  # the identity was already asserted...
    channels = {r[0] for r in con.execute("SELECT reading_channel FROM citation_reading")}
    assert channels == {"text-layer", "ocr"}  # ...and the reading still landed
    assert con.execute("SELECT COUNT(*) FROM citation").fetchone()[0] == 1
    # and each reading carries the precision of the channel it was read on, not the other's
    by_channel = dict(
        con.execute(
            "SELECT r.reading_channel, m.reading_channel FROM citation_reading r"
            " JOIN class_measurement m ON m.measurement_id = r.score_row_id"
        )
    )
    assert by_channel == {"text-layer": "text-layer", "ocr": "ocr"}
    # THE OCR ROWS DO NOT PROJECT: nothing ranks a resolver on that channel, so the
    # projection's channel-matched rank join drops them. `citator load` refuses an unranked
    # channel for this reason; a direct caller stores rows no page shows.
    assert not methods.ranked(con, "ocr")
    assert {r[10] for r in project.cited_by(con, docket_id=3)} == {"text-layer"}


def test_declare_refuses_a_declaration_that_contradicts_the_registry(tmp_path):
    """`INSERT OR IGNORE` swallowed exactly the collisions this registry exists to raise: a
    bumped SPAN_VERSION collided with the old rank-1 row, was dropped, and every judgement it
    then wrote had no registry row — so the projection's INNER JOIN silently suppressed every
    in-family edge."""
    con = _store(tmp_path)
    methods.declare(con, "v1")
    methods.declare(con, "v1")  # idempotent: an identical declaration is a restart
    with pytest.raises(methods.Conflict):
        methods.declare(con, "v2")  # a different owner version at the same rank_version
    # a re-rank is a NEW rank_version, which is what the append-only registry already says
    methods.declare(con, "v2", rank_version="v2")


def test_a_document_whose_method_does_not_own_the_class_is_refused(tmp_path):
    """ADR 0018 D1's one-owner rule. The index constrains DECLARATIONS; only this lookup
    constrains ROWS, and migration 0014 states it as the writer's obligation."""
    con = _store(tmp_path)
    stamps = _scored(con)  # declares regex-docket-cite@v1 as the owner
    doc = _findings({"page": 4, "target": "EP 445", "quoted": "q"}) | {
        "method": "model:claude-sonnet-5"
    }
    with pytest.raises(load.NotTheOwner):
        load.load_document(con, doc, keys.registry(con), stamps)
    assert con.execute("SELECT COUNT(*) FROM citation").fetchone()[0] == 0


def test_a_false_span_judgement_is_not_stamped_with_the_projections_precision(tmp_path):
    """Migration 0014 states the limit: the projection precision speaks for what the pair
    SHOWS, so it stands behind a `true`. Stamping a suppression with it quotes the pair for a
    decision the pair does not make."""
    con = _store(tmp_path)
    stamps = _scored(con)
    load.load_document(
        con,
        _findings(
            {"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."},
            {"page": 5, "target": "FD 36873 (Sub-No. 1)", "quoted": "Docket No. FD 36873"},
        ),
        keys.registry(con),
        stamps,
    )
    rows = dict(
        con.execute(
            "SELECT value, confidence_state FROM citation_judgement"
            " WHERE judgement = 'span_names_document'"
        ).fetchall()
    )
    assert rows == {"true": "measured", "false": "unmeasured"}
    # the exposure judgement is `unmeasured` for the same reason the span test's `false` rows
    # are: ADR 0017 measures how often it FIRES, which is a rate and not a precision, so
    # nothing has scored it — and it carries its OWN method, never the resolver's
    assert {
        r
        for r in con.execute(
            "SELECT DISTINCT confidence_state, method, method_version FROM citation_judgement"
            " WHERE judgement = 'exposed'"
        )
    } == {("unmeasured", resolve.EXPOSURE_METHOD, resolve.EXPOSURE_VERSION)}
    # and the outcome is unchanged: an unmeasured judgement is filtered out of the candidate
    # set, so COALESCE defaults to suppress exactly as before
    assert len(project.projected(con)) == 1


def test_a_cited_by_count_is_pairs_and_not_passages(tmp_path):
    """ADR 0018 D9: short-form density must not inflate a count a reader is shown."""
    con = _store(tmp_path)
    stamps = _scored(con)
    load.load_document(
        con,
        _findings(
            {"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."},
            {"page": 9, "target": "EP 445", "quoted": "EP 445, slip op. at 11."},
        ),
        keys.registry(con),
        stamps,
    )
    rows = project.cited_by(con, docket_id=3)
    assert len(rows) == 2  # two passages...
    assert len({(r[0], r[2]) for r in rows}) == 1  # ...one edge


def test_the_load_verb_runs_end_to_end(tmp_path):
    """`citator load` passed bare measurement ids where the loader wanted (id, precision), so
    the verb raised TypeError on its first finding and no test covered the path."""
    con = _store(tmp_path)
    _scored(con)
    con.commit()
    con.close()
    batch = _batch(
        tmp_path,
        a=_findings({"page": 4, "target": "EP 445", "quoted": "EP 445, slip op. at 3."}),
        b_broken="{not json",
    )
    assert _load_verb(tmp_path, batch) == 0  # the malformed file is skipped, not fatal
    con = db.connect(tmp_path / "s.sqlite")
    assert len(project.projected(con)) == 1
