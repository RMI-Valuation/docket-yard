"""The score card: a measurement, written by the tool that measured it, read by the verb
that stamps rows with it.

WHY A FILE AND NOT ARGUMENTS OR A CONSTANT. `citator load` stamps every row it writes with a
class's measured precision (ADR 0017 D3), so declaring that measurement is the moment a
published claim is made about 73,101 rows. Three ways to make it were weighed on 2026-09-04
and the operator chose this one: the figures are re-typed by nobody, so they cannot drift
from the tool that measured them. It is the same reasoning migration 0016 recorded when the
figures were last re-derived — "re-run it and keep the run reproducible" — carried one step
further, to the moment the number reaches the store.

The alternatives and what they cost, so a later reader knows they were considered: figures
as command arguments make the operator state the claim, which is the most explicit reading
of "every derived assertion carries provenance", and put a typo one keystroke from a stamped
precision. Figures hardcoded in this file would make the CODE the claimant, and would put
the same numbers in three places — here, migration 0016's header, and ADR 0017 — which is
the drift this record keeps finding.

WHAT THE CARD IS NOT. It is not a measurement in itself and nothing reads it twice: `declare`
writes `class_measurement` rows and those are what a `citation` row points at. Losing the
card afterwards costs nothing; changing it changes nothing already stamped.
"""

import json
from pathlib import Path

from docketyard.citator import methods

CARD_VERSION = 1
# What a card must say before anything is stamped from it. `reading_channel` is here because
# a measurement is OF one channel (ADR 0018 D8): a text-layer figure written onto OCR rows is
# the borrowed precision `load.WrongChannel` exists to refuse.
REQUIRED = (
    "card_version",
    "extractor",
    "extractor_version",
    "reading_channel",
    "score_file",
    "benchmark_date",
    "truth_count",
    "stages",
)
# Per stage: what `methods.measure` needs, and nothing it does not.
# Per stage: (numerator, denominator). The denominator is named because a precision is the
# whole point and a zero one is not a small number — it is no measurement at all.
STAGE_FIELDS = {
    "citation": ("found", "emitted"),
    "citation_resolution": ("resolved", "resolved_shown"),
    "projection": ("projected", "shown"),
}


class Unusable(ValueError):
    """A card that cannot be stamped from. Raised rather than defaulted: a missing number
    here becomes a precision on every row a load writes."""


def build(
    scores: dict,
    *,
    extractor_version: str,
    score_file: str,
    benchmark_date: str,
    extractor: str = methods.EXTRACTOR,
    reading_channel: str = methods.CHANNEL_TEXT,
) -> dict:
    """A card from a scorer's own counts. `scores` is what `citation_dryrun.py` produces."""
    missing = [
        k
        for k in ("truth", "emitted", "found", "resolved", "resolved_shown", "projected", "shown")
        if scores.get(k) is None
    ]
    if missing:
        raise Unusable(f"the run reported no {missing}; there is no measurement to write")
    # EVERY DENOMINATOR, not just the first. A run that emitted nothing, resolved nothing, or
    # had everything held for review yields no precision — and `0/0` reached `declare` as an
    # uncaught ZeroDivisionError while `max(shown, 1)` turned it into a precision of 0.0 that
    # `stamp` would accept and every row would carry (code review, 2026-09-04).
    for stage, (num, denom) in (
        ("citation", ("found", "emitted")),
        ("citation_resolution", ("resolved", "resolved_shown")),
        ("projection", ("projected", "shown")),
    ):
        if not scores[denom]:
            raise Unusable(
                f"the run shows {denom} = {scores[denom]!r} for {stage}:"
                f" {scores[num]}/{scores[denom]} is not a precision"
            )
    return {
        "card_version": CARD_VERSION,
        "extractor": extractor,
        "extractor_version": extractor_version,
        "reading_channel": reading_channel,
        "score_file": score_file,
        "benchmark_date": benchmark_date,
        "truth_count": scores["truth"],
        "stages": {
            "citation": {"found": scores["found"], "emitted": scores["emitted"]},
            "citation_resolution": {
                "resolved": scores["resolved"],
                "resolved_shown": scores["resolved_shown"],
            },
            "projection": {"projected": scores["projected"], "shown": scores["shown"]},
        },
    }


def write(path, card: dict) -> Path:
    path = Path(path)
    path.write_text(json.dumps(card, indent=1) + "\n", encoding="utf-8")
    return path


def read(path) -> dict:
    """A card off disk, checked before anything is stamped from it."""
    try:
        card = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Unusable(f"{path}: {type(e).__name__} {e}") from e
    if not isinstance(card, dict):
        raise Unusable(f"{path}: not an object")
    absent = [k for k in REQUIRED if not card.get(k)]
    if absent:
        raise Unusable(f"{path}: says no {absent}")
    if card["card_version"] != CARD_VERSION:
        raise Unusable(
            f"{path}: card version {card['card_version']}, this build writes {CARD_VERSION}"
        )
    # ONE EXTRACTOR. `methods.measure` writes `extraction_method` as `methods.EXTRACTOR` and
    # takes no argument for it, so a card naming another method would declare that method as
    # the class's owner while attributing every measurement to this one — a borrowed
    # precision with nothing to catch it, since `load` checks the owner pair and the channel
    # and never the measurement's method (code review, 2026-09-04). This package ships one
    # class (ADR 0017 D1); a second extractor is a bigger decision than a card.
    if card["extractor"] != methods.EXTRACTOR:
        raise Unusable(
            f"{path}: measures {card['extractor']!r}; this build measures"
            f" {methods.EXTRACTOR!r} and cannot record another method's figures"
        )
    if not isinstance(card["stages"], dict):
        raise Unusable(f"{path}: `stages` is not an object")
    for stage, (num, denom) in STAGE_FIELDS.items():
        got = card["stages"].get(stage)
        if not isinstance(got, dict) or got.get(num) is None or got.get(denom) is None:
            raise Unusable(f"{path}: stage {stage!r} does not carry {[num, denom]}")
        if not got[denom]:
            raise Unusable(
                f"{path}: stage {stage!r} has {denom} = {got[denom]!r};"
                f" {got[num]}/{got[denom]} is not a precision"
            )
    return card


def figures(card: dict) -> dict[str, tuple[float, float]]:
    """stage -> (recall, precision), from the card's counts. ONE definition, so what the verb
    prints and what `declare` writes are the same arithmetic rather than two readings of it.

    Each stage's denominator is its own and they differ on purpose: extraction's is what the
    finder emitted, resolution's is what it resolved, and the projection's is what a reader
    would be SHOWN — `resolved / emitted` is neither a precision nor a recall, and this record
    has published enough of those (`citation_dryrun.register`, whose reasoning this keeps).
    """
    truth, s = card["truth_count"], card["stages"]
    return {
        stage: (s[stage][num] / truth, s[stage][num] / s[stage][denom])
        for stage, (num, denom) in STAGE_FIELDS.items()
    }


def declare(con, card: dict) -> dict:
    """Declare the methods and write the three measurements. Returns the stamps.

    THE PRECISIONS ARE THE SCORER'S, computed here from the counts the card carries rather
    than copied from it, so a card cannot claim a precision its own numbers do not support.
    Each stage's denominator is its own and they differ on purpose: extraction's is what the
    finder emitted, resolution's is what it resolved, and the projection's is what a reader
    would be SHOWN — `resolved / emitted` is neither a precision nor a recall, and this
    record has published enough of those (`citation_dryrun.register`, whose reasoning this
    keeps).
    """
    s, version, channel = card["stages"], card["extractor_version"], card["reading_channel"]
    scored = figures(card)
    common = {
        "cls": "docket",
        "extractor_version": version,
        "score_file": card["score_file"],
        "benchmark_date": card["benchmark_date"],
        "reading_channel": channel,
        "truth_count": card["truth_count"],
        "found_count": s["citation"]["found"],
    }
    methods.declare(con, version, extractor=card["extractor"])
    for stage, (recall, precision) in scored.items():
        extra = {"shown_count": s["projection"]["shown"]} if stage == "projection" else {}
        methods.measure(
            con, measured_target=stage, recall=recall, precision=precision, **common, **extra
        )
    con.commit()
    return methods.stamp(con, channel=channel)
