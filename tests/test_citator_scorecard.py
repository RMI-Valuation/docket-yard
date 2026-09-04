"""`citator.scorecard` and the `declare` verb — how a measured precision reaches the store.

`citator load` stamps every row it writes with a class's measured precision (ADR 0017 D3),
so declaring the measurement is the moment a published claim is made about every edge a load
produces. Until 2026-09-04 no verb did it and a real load was impossible with the shipped
CLI; the rehearsal used a hand-written script. These tests are about the three things that
must hold: a card cannot be believed without saying what it measured, the precisions are
computed from the counts rather than copied, and a load stamps rows from what was declared.
"""

import argparse
import json

import pytest

from docketyard import cli
from docketyard.citator import methods, scorecard
from docketyard.store import db
from tests.test_citator_pipeline import _store

# migration 0016 § The figures, measured 2026-09-01 over sixty decisions
SCORES = {
    "truth": 225,
    "emitted": 231,
    "found": 222,
    "resolved": 216,
    "resolved_shown": 221,
    "projected": 213,
    "shown": 218,
}


def _card(**over):
    card = scorecard.build(
        SCORES,
        extractor_version="2026-09-01",
        score_file="migration 0016 The figures",
        benchmark_date="2026-09-01",
    )
    return card | over


def test_a_card_carries_the_counts_and_the_precisions_are_derived_from_them(tmp_path):
    """The card holds COUNTS, never a precision: a card that carried its own precision could
    claim one its numbers do not support, and the number is what every row is stamped with."""
    card = _card()
    assert "precision" not in json.dumps(card), "a card must not carry a precision"
    assert card["truth_count"] == 225
    assert card["stages"]["projection"] == {"projected": 213, "shown": 218}

    con = _store(tmp_path)
    stamps = scorecard.declare(con, card)
    assert set(stamps) == set(methods.STAGES)
    # each stage's denominator is its own, and they differ on purpose
    assert stamps["citation"][1] == pytest.approx(222 / 231)
    assert stamps["citation_resolution"][1] == pytest.approx(216 / 221)
    assert stamps["projection"][1] == pytest.approx(213 / 218)  # migration 0016's 97.7%
    con.close()


def test_a_card_that_does_not_say_what_it_measured_is_refused(tmp_path):
    """Every one of these would otherwise become a precision on every row a load writes, so
    each is a refusal and none is a default."""
    good = _card()
    for missing in ("extractor_version", "reading_channel", "score_file", "truth_count"):
        path = scorecard.write(tmp_path / "c.json", {k: v for k, v in good.items() if k != missing})
        with pytest.raises(scorecard.Unusable, match=missing):
            scorecard.read(path)

    # a stage that does not carry its counts
    bad = _card()
    bad["stages"]["projection"] = {"projected": 213}
    path = scorecard.write(tmp_path / "c.json", bad)
    with pytest.raises(scorecard.Unusable, match="projection"):
        scorecard.read(path)

    # a card from another build of this code
    path = scorecard.write(tmp_path / "c.json", _card(card_version=99))
    with pytest.raises(scorecard.Unusable, match="card version"):
        scorecard.read(path)

    # and something that is not a card at all
    (tmp_path / "junk.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(scorecard.Unusable):
        scorecard.read(tmp_path / "junk.json")


def test_a_run_that_emitted_nothing_has_no_precision_to_record():
    """`0/0` is not a precision. The scorer refuses to write the card rather than the store
    refusing to read it, so the failure lands where somebody can see the run that caused it."""
    # every denominator, not just the first: a run that emitted nothing, resolved nothing, or
    # had everything held for review yields no precision for that stage
    for denom in ("emitted", "resolved_shown", "shown"):
        with pytest.raises(scorecard.Unusable, match=f"{denom} = 0"):
            scorecard.build(
                SCORES | {denom: 0},
                extractor_version="v",
                score_file="f",
                benchmark_date="2026-09-01",
            )
    with pytest.raises(scorecard.Unusable, match="resolved"):
        scorecard.build(
            {k: v for k, v in SCORES.items() if k != "resolved"},
            extractor_version="v",
            score_file="f",
            benchmark_date="2026-09-01",
        )


def test_the_measurement_is_of_one_channel(tmp_path):
    """ADR 0018 D8: a text-layer figure says nothing about what the same method finds in OCR
    text at 10.8% CER, so `stamp` looks measurements up BY CHANNEL and a channel nobody
    scored is `Unscored`. The card names its channel for that reason."""
    con = _store(tmp_path)
    scorecard.declare(con, _card())
    assert methods.stamp(con, channel="text-layer")
    with pytest.raises(methods.Unscored):
        methods.stamp(con, channel="ocr")
    con.close()


def test_the_declare_verb_reports_what_it_declared_and_refuses_a_bad_card(tmp_path, capsys):
    con = _store(tmp_path)
    con.commit()
    con.close()
    path = scorecard.write(tmp_path / "card.json", _card())
    args = argparse.Namespace(db=str(tmp_path / "s.sqlite"), what="declare", scores=str(path))
    assert cli._citator(args) == 0
    out = capsys.readouterr().out
    # it says what claim it just made, and on which channel, and where the figures came from
    assert "regex-docket-cite@2026-09-01" in out and "text-layer" in out
    assert "migration 0016 The figures" in out and "225 truth targets" in out
    assert "0.977" in out, "the projection's precision is what a shown edge carries"

    # a card it cannot believe is a refusal with a non-zero exit, not a half-declaration
    bad = scorecard.write(tmp_path / "bad.json", {"card_version": 1})
    args = argparse.Namespace(db=str(tmp_path / "s.sqlite"), what="declare", scores=str(bad))
    assert cli._citator(args) == 1
    assert "refused" in capsys.readouterr().out


def test_a_load_stamps_its_rows_from_the_card_that_was_declared(tmp_path):
    """The whole point: `load` refuses a batch it cannot stamp, and what it stamps is what
    `declare` wrote. Before 2026-09-04 nothing in the shipped CLI could satisfy it."""
    from docketyard.citator import project
    from tests.test_citator_pipeline import _batch, _findings, _load_verb

    con = _store(tmp_path)
    # THE CARD'S VERSION IS THE FINDINGS' VERSION. `load` declares the batch's own
    # `method_version` and ADR 0018 D1 allows one owner per class per rank_version, so a card
    # naming a different version is refused by the registry rather than quietly stamping
    # rows from a measurement of another pass. In production both are `find.FINDER_VERSION`.
    scorecard.declare(con, _card(extractor_version="v1"))
    con.commit()
    con.close()
    batch = _batch(
        tmp_path, a=_findings({"page": 4, "target": "EP 445", "quoted": "EP 445, slip op. at 3."})
    )
    assert _load_verb(tmp_path, batch) == 0
    con = db.connect(tmp_path / "s.sqlite")
    rows = project.projected(con)
    assert len(rows) == 1
    # THE EDGE CARRIES THE RESOLUTION CLASS'S PRECISION, not the projection's and never a
    # recall. ADR 0017 D3: "confidence is the measured precision of the RESOLUTION's class on
    # the checked sheet" — the question an edge's confidence answers is whether the target was
    # resolved rightly. `citation_dryrun.py` checks the same thing at the end of its run and
    # calls a mismatch WRONG STAGE STAMPED.
    assert rows[0][5] == pytest.approx(216 / 221), "a projected row took the wrong stage"
    assert rows[0][5] != pytest.approx(213 / 218), "the projection's own precision is not it"
    assert rows[0][6] == "measured"
    con.close()


def test_a_card_measuring_another_pass_cannot_stamp_this_ones_rows(tmp_path, capsys):
    """ADR 0018 D1's one-owner rule, reached from the card end: a card naming a different
    extractor version than the findings carry is refused by the registry rather than
    stamping rows from a measurement of a pass that did not produce them. Found while
    writing the verb's tests, 2026-09-04 — the numbers would have looked perfectly ordinary.
    """
    from tests.test_citator_pipeline import _batch, _findings, _load_verb

    con = _store(tmp_path)
    scorecard.declare(con, _card(extractor_version="2026-09-01"))  # the findings say v1
    con.commit()
    con.close()
    batch = _batch(
        tmp_path, a=_findings({"page": 4, "target": "EP 445", "quoted": "EP 445, slip op. at 3."})
    )
    assert _load_verb(tmp_path, batch) == 1
    assert "collides" in capsys.readouterr().out


def test_a_card_this_build_cannot_honour_is_refused(tmp_path):
    """`methods.measure` writes `extraction_method` as `methods.EXTRACTOR` and takes no
    argument for it, so a card naming another method would declare that method as the class's
    owner while attributing every measurement to this one — a borrowed precision with nothing
    to catch it, since `load` checks the owner pair and the channel and never the
    measurement's method (code review, 2026-09-04)."""
    path = scorecard.write(tmp_path / "c.json", _card(extractor="some-other-finder"))
    with pytest.raises(scorecard.Unusable, match="cannot record another method"):
        scorecard.read(path)

    # `stages` of the wrong shape must be a refusal, not an AttributeError past the guard
    path = scorecard.write(tmp_path / "c.json", _card(stages=["citation"]))
    with pytest.raises(scorecard.Unusable, match="not an object"):
        scorecard.read(path)

    # and a zero denominator in a card nobody built with `build`
    hand_made = _card()
    hand_made["stages"]["projection"] = {"projected": 213, "shown": 0}
    path = scorecard.write(tmp_path / "c.json", hand_made)
    with pytest.raises(scorecard.Unusable, match="not a precision"):
        scorecard.read(path)


def test_declaring_the_same_card_twice_is_a_refusal_and_not_a_traceback(tmp_path, capsys):
    """`class_measurement` is unique on its identity, so a second declaration is an
    IntegrityError rather than a `Conflict` — and it reached the operator as a traceback while
    the verb promised a refusal (code review, 2026-09-04)."""
    con = _store(tmp_path)
    con.commit()
    con.close()
    path = scorecard.write(tmp_path / "card.json", _card())
    args = argparse.Namespace(db=str(tmp_path / "s.sqlite"), what="declare", scores=str(path))
    assert cli._citator(args) == 0
    capsys.readouterr()
    assert cli._citator(args) == 1
    out = capsys.readouterr().out
    assert "refused" in out and "nothing was changed" in out


def test_the_verb_prints_the_card_it_declared_and_not_the_newest_measurement(tmp_path, capsys):
    """`methods.stamp` returns the NEWEST measurement by benchmark date. Printing from it made
    the verb show this card's identity beside another measurement's figures, under a sentence
    claiming a row would carry them — reproduced at 0.452 against the card's 0.977."""
    con = _store(tmp_path)
    # a newer measurement already in the store, of the same extractor version
    scorecard.declare(
        con,
        _card(benchmark_date="2026-09-30")
        | {
            "stages": {
                "citation": {"found": 1, "emitted": 2},
                "citation_resolution": {"resolved": 1, "resolved_shown": 2},
                "projection": {"projected": 1, "shown": 2},
            }
        },
    )
    con.commit()
    con.close()
    path = scorecard.write(tmp_path / "card.json", _card())
    args = argparse.Namespace(db=str(tmp_path / "s.sqlite"), what="declare", scores=str(path))
    assert cli._citator(args) == 0
    out = capsys.readouterr().out
    assert "0.977" in out, "it printed another measurement's figures"
    assert "0.500" not in out, "it printed the newest measurement instead of this card"
