"""A key an older version of the finder asserted, which its current version no longer emits,
is retracted when the document is re-loaded (2026-09-11: the wrapped sub-docket moved 628 keys
from the parent to the sub-docket they name, and the stale parent key must stop counting) —
and what a retraction must leave alone (schema-critic, 2026-09-11)."""

import pytest

from docketyard.citator import find, keys, load, methods, restamp, review
from tests.test_citator_pipeline import (
    SHA,
    STAMP,
    _batch,
    _findings,
    _load_verb,
    _scored,
    _store,
)
from tests.test_citator_review import EXPOSED
from tests.test_citator_review import _reviewer as _grant
from tests.test_citator_review import _scored as _review_scored
from tests.test_citator_review import _store as _review_store

OLD = "2026-09-01"  # the finder version that keyed the wrapped sub-docket as its parent
NOW = {
    "page": 4,
    "target": "FD 36873 (Sub-No. 1)",
    "quoted": "See FD 36873 (Sub-No. 1), slip op. 6.",
}


def _older(con, page: int, key: str) -> None:
    """A citation identity row as the OLDER finder wrote it."""
    con.execute(
        "INSERT OR IGNORE INTO citation_key (citing_document, page, target_kind, target_key,"
        " key_version, first_seen_at) VALUES (?, ?, 'stb', ?, ?, ?)",
        (SHA, page, key, keys.KEY_VERSION, STAMP),
    )
    con.execute(
        "INSERT INTO citation (citing_document, page, target_kind, target_key,"
        " asserted_from_document, method, method_version, asserted_at, confidence,"
        " confidence_state) VALUES (?, ?, 'stb', ?, ?, ?, ?, ?, 0, 'unmeasured')",
        (SHA, page, key, SHA, methods.EXTRACTOR, OLD, STAMP),
    )


def _reading(con, page: int, key: str, channel: str, version: str) -> None:
    """A live reading of the key on another channel, at a given finder version."""
    con.execute(
        "INSERT INTO citation_reading (citing_document, page, target_kind, target_key,"
        " reading_channel, text_ref, reading_method, reading_method_version, cited_raw,"
        " quoted_passage, source_location, asserted_from_document, method, method_version,"
        " asserted_at, confidence, confidence_state)"
        " VALUES (?, ?, 'stb', ?, ?, 'benchmark', 'dots.mocr', '1.5', ?, 'q', '{}', ?, ?, ?,"
        " ?, 0, 'unmeasured')",
        (SHA, page, key, channel, key, SHA, methods.EXTRACTOR, version, STAMP),
    )


def _walked(*findings, pages=(4,)):
    """A findings document naming the pages it read, as `find.findings_document` writes it."""
    return _findings(*findings) | {"pages_walked": list(pages)}


def _load(con, doc, stamps):
    return load.load_document(con, doc, keys.registry(con), keys.works(con), stamps)


def _live(con) -> set[str]:
    return {
        k for (k,) in con.execute("SELECT target_key FROM citation WHERE superseded_by IS NULL")
    }


def test_a_key_the_current_finder_no_longer_emits_points_at_its_successor(tmp_path):
    con = _store(tmp_path)
    stamps = _scored(con)
    _older(con, 4, "FD 36873")  # what the wrapped sub-number used to key as
    result = _load(con, _walked(NOW), stamps)
    assert (result.retracted, result.retraction_held) == (1, 0)
    assert _live(con) == {"FD 36873 (1)"}
    # ADR 0018 D2's shape: the mis-keyed row points at its replacement, which names the pass
    # and dates the retraction; the row itself stays, attributed to the version that wrote it
    successor = con.execute(
        "SELECT citation_id FROM citation WHERE target_key = 'FD 36873 (1)'"
    ).fetchone()[0]
    assert con.execute(
        "SELECT superseded_by, method_version FROM citation WHERE target_key = 'FD 36873'"
    ).fetchone() == (successor, OLD)
    # and a re-load at the same version retracts nothing more: a restart, not a second pass
    again = _load(con, _walked(NOW), stamps)
    assert (again.retracted, again.unchanged) == (0, 1)


def test_with_no_single_successor_it_is_retired_at_itself(tmp_path):
    con = _store(tmp_path)
    stamps = _scored(con)
    _older(con, 5, "EP 445")
    other = {"page": 5, "target": "FD 36873", "quoted": "See FD 36873, slip op. at 2."}
    assert _load(con, _walked(other, pages=(5,)), stamps).retracted == 1
    assert con.execute(
        "SELECT 1 FROM citation WHERE target_key = 'EP 445' AND superseded_by = citation_id"
    ).fetchone()


def test_a_key_the_same_version_asserted_is_never_retracted(tmp_path):
    """Retraction corrects an OLDER finder. A pass never retracts what its own version wrote on
    another run — a findings file that happens to miss a key is not evidence the key is wrong."""
    con = _store(tmp_path)
    stamps = _scored(con)
    other = {"page": 4, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."}
    _load(con, _walked(other), stamps)
    assert _load(con, _walked(NOW), stamps).retracted == 0
    assert _live(con) == {"EP 445", "FD 36873 (1)"}


def test_a_key_on_a_page_the_pass_did_not_read_is_left(tmp_path):
    """ADR 0018 D10: absence is not a measurement. `walk` skips a page a person corrected and
    files each page under its live primary's channel, so a page this pass did not read found
    nothing, and its keys stay."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _older(con, 7, "EP 445")
    assert _load(con, _walked(NOW, pages=(4,)), stamps).retracted == 0
    assert "EP 445" in _live(con)


def test_a_findings_document_that_names_no_pages_retracts_nothing(tmp_path):
    con = _store(tmp_path)
    stamps = _scored(con)
    _older(con, 4, "FD 36873")
    assert _load(con, _findings(NOW), stamps).retracted == 0
    assert "FD 36873" in _live(con)


def test_a_stale_reading_on_another_channel_does_not_hold_the_key(tmp_path):
    """Deferring to another channel's OLD reading would let two channels hold each other's
    stale keys for ever; only a current reading, or a person's, holds one."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _older(con, 4, "FD 36873")
    _reading(con, 4, "FD 36873", "ocr", OLD)
    assert _load(con, _walked(NOW), stamps).retracted == 1


def test_a_current_reading_on_another_channel_holds_the_key(tmp_path):
    con = _store(tmp_path)
    stamps = _scored(con)
    _older(con, 4, "FD 36873")
    _reading(con, 4, "FD 36873", "ocr", "v1")  # the current finder read it on OCR
    result = _load(con, _walked(NOW), stamps)
    assert (result.retracted, result.retraction_held) == (0, 1)


def _reviewed(tmp_path, decision: str):
    """The review store's exposed key, answered `decision`, then as though an older finder had
    asserted it and the current one no longer emits it."""
    con = _review_store(tmp_path)
    stamps = _review_scored(con)
    doc = {
        "document_sha256": SHA,
        "method": methods.EXTRACTOR,
        "method_version": "v1",
        "reading_channel": methods.CHANNEL_TEXT,
        "text_ref": "benchmark",
        "pages_read": 9,
        "pages_walked": [EXPOSED["page"]],
        "findings": [EXPOSED],
    }
    _load(con, doc, stamps)
    item = review.pending(con, "citation_exposed")[0]
    review.decide(
        con,
        reviewer_id=_grant(con),
        queue="citation_exposed",
        item=item,
        decision=decision,
        note="checked the page",
    )
    con.execute("UPDATE citation SET method_version = ? WHERE target_key = 'AB 1242'", (OLD,))
    return con, _load(con, dict(doc, findings=[]), stamps)


def test_a_key_a_person_decided_is_left_for_a_person(tmp_path):
    """ADR 0017 D5: a model pass may never override a human answer."""
    con, result = _reviewed(tmp_path, "accepted")
    assert (result.retracted, result.retraction_held) == (0, 1)
    assert "AB 1242" in _live(con)


def test_a_question_still_open_before_a_person_holds_the_key(tmp_path):
    """An escalation writes no human row, so only the action shows the question is open —
    retracting its key would drop the item from the queue with nobody told."""
    con, result = _reviewed(tmp_path, "escalated")
    assert (result.retracted, result.retraction_held) == (0, 1)
    assert "AB 1242" in _live(con)


def test_a_batch_from_another_version_of_this_builds_finder_is_refused(tmp_path):
    """`citator load` declares the batch's version the owner of this build's rank_version, and
    the registry is append-only: an old findings directory loaded by mistake after a finder
    bump would take the new rank for the old finder. Refused before anything is declared."""
    assert find.FINDER_VERSION != "v1"  # the real build's finder, not the pipeline tests' patch
    con = _store(tmp_path)
    _scored(con)
    con.commit()
    con.close()
    assert _load_verb(tmp_path, _batch(tmp_path, one=_findings(NOW))) == 1


def test_a_card_from_another_version_of_this_builds_finder_is_refused(tmp_path, capsys):
    """`declare` makes the card's finder the owner of this build's rank_version, append-only —
    so a card measured on a machine still running the old finder would lock this build's own
    findings out for ever. Refused before anything is declared (code review, 2026-09-11)."""
    import argparse

    from docketyard import cli
    from docketyard.citator import scorecard
    from tests.test_citator_scorecard import SCORES

    con = _store(tmp_path)
    con.commit()
    con.close()
    card = scorecard.build(
        SCORES, extractor_version=OLD, score_file="f", benchmark_date="2026-09-02"
    )
    args = argparse.Namespace(
        db=str(tmp_path / "s.sqlite"),
        what="declare",
        scores=str(scorecard.write(tmp_path / "card.json", card)),
    )
    assert cli._citator(args) == 1
    assert "this build's finder is" in capsys.readouterr().out
    from docketyard.store import db

    con = db.connect(tmp_path / "s.sqlite")  # and nothing was declared
    assert con.execute("SELECT COUNT(*) FROM class_measurement").fetchone() == (0,)
    con.close()


def test_a_restamp_needs_every_stamp_measured_on_one_finder(tmp_path):
    """`stale` admits keys by the finder the stamps measured; a work stamp from another finder
    than the docket stamp would put its figures on keys it never measured, and a stamp naming
    no measurement is no finder at all. Both refused (code review, 2026-09-11)."""
    con = _store(tmp_path)
    _scored(con)  # the docket class, measured on finder v1
    methods.measure(
        con,
        measured_target="citation_resolution",
        cls=methods.WORK_CLASS,
        extractor_version="v2",
        score_file="test",
        benchmark_date="2026-09-10",
        reading_channel=methods.CHANNEL_TEXT,
        precision=0.93,
    )
    (work_id,) = con.execute("SELECT MAX(measurement_id) FROM class_measurement").fetchone()
    stamps = methods.stamp(con)
    with pytest.raises(methods.Unscored, match="one finder"):
        restamp.stale(con, stamps | {methods.WORK_KEY: (work_id, 0.93)})
    with pytest.raises(methods.Unscored, match="one finder"):
        restamp.stale(con, {"citation_resolution": (work_id + 99, 0.9), methods.WORK_KEY: None})


def test_a_stamp_measured_on_another_finder_version_is_refused(tmp_path):
    """The new finder's findings, loaded before its card is declared, would be stamped from the
    OLD finder's figures — borrowed precision (ADR 0017 D3). Refused before a row is written."""
    con = _store(tmp_path)
    stamps = _scored(con)  # measured on finder version v1
    with pytest.raises(methods.Unscored, match="measured on finder"):
        _load(con, _walked(NOW) | {"method_version": "2026-09-11"}, stamps)
    assert _live(con) == set()


def test_a_retracted_key_is_not_restamped(tmp_path):
    """`restamp` writes fresh `measured` rows; on a retracted key that would be an assertion
    the record no longer makes."""
    con = _store(tmp_path)
    stamps = _scored(con)
    parent = {"page": 4, "target": "FD 36873", "quoted": "See FD 36873, slip op. at 2."}
    _load(con, _walked(parent), stamps)
    con.execute("UPDATE citation SET method_version = ? WHERE target_key = 'FD 36873'", (OLD,))
    _load(con, _walked(NOW), stamps)
    methods.measure(
        con,
        measured_target="citation_resolution",
        cls="docket",
        extractor_version="v1",
        score_file="test",
        benchmark_date="2026-09-02",  # a re-score: every live measured row is now stale
        recall=0.9,
        precision=0.99,
    )
    stale = {row[0][0] for row in restamp.stale(con, methods.stamp(con))}
    by_key = dict(
        con.execute(
            "SELECT target_key, resolution_id FROM citation_resolution WHERE superseded_by IS NULL"
        ).fetchall()
    )
    assert by_key["FD 36873 (1)"] in stale and by_key["FD 36873"] not in stale


def test_a_key_still_live_at_an_older_finder_version_is_not_restamped(tmp_path):
    """Held from retraction, or on a page the new walk skipped: its resolution was written from
    the old finder's reading, and the new card's figures do not describe it (code review,
    2026-09-11)."""
    con = _store(tmp_path)
    stamps = _scored(con)
    kept = {"page": 5, "target": "EP 445", "quoted": "See EP 445, slip op. at 3."}
    _load(con, _walked(kept, pages=(5,)), stamps)
    # an older finder wrote it, and no pass since has read page 5
    con.execute("UPDATE citation SET method_version = ? WHERE target_key = 'EP 445'", (OLD,))
    methods.measure(
        con,
        measured_target="citation_resolution",
        cls="docket",
        extractor_version="v1",
        score_file="test",
        benchmark_date="2026-09-02",
        recall=0.9,
        precision=0.99,
    )
    assert restamp.stale(con, methods.stamp(con)) == []
