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
# The work class, when a card carries one. OPTIONAL AND SEPARATE FROM `stages`, for two
# reasons. It is not a stage — it is a second class of `citation_resolution`, and putting it
# in `stages` would let `figures` divide it by the sheet's docket truth, which counts a
# different population. And it comes from a different instrument: the three stages are the
# scorer comparing sets, while this is the operator judging claims one at a time
# (`tools/rmi-ai-machine/work_check_sheet.py`), so a card may honestly carry three
# measurements and not the fourth. A card without it declares the work class not at all,
# which leaves the grain shut — the state every card written before 2026-09-10 is in.
WORK = "work"
WORK_FIELDS = ("right", "judged", "score_file")


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
    work = card.get(WORK)
    if work is not None:
        # CHECKED AS HARD AS THE STAGES ARE. This block opens a grain no figure has ever
        # stood behind, so a malformed one must refuse here rather than stamp 16,051 rows
        # from `0/0` or from a precision somebody typed.
        if not isinstance(work, dict) or any(work.get(f) is None for f in WORK_FIELDS):
            raise Unusable(f"{path}: the work block does not carry {list(WORK_FIELDS)}")
        # TYPES, because JSON has none the reader can rely on: `"98"` passes every test
        # below by comparing as a string and then divides into a TypeError at the moment
        # `declare` is writing a measurement, half way through a card.
        counts = [work["right"], work["judged"], work.get("truth")]
        if any(
            not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in counts if n is not None
        ):
            raise Unusable(f"{path}: the work block's counts are not whole numbers: {counts}")
        if not work["judged"]:
            raise Unusable(
                f"{path}: the work block judged {work['judged']!r} claims;"
                f" {work['right']}/{work['judged']} is not a precision"
            )
        if work["right"] > work["judged"]:
            raise Unusable(
                f"{path}: the work block says {work['right']} right of {work['judged']} judged"
            )
        if work.get("truth") is not None and work["right"] > work["truth"]:
            raise Unusable(
                f"{path}: the work block says {work['right']} right of {work['truth']} true"
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


def work_figures(card: dict) -> tuple[float | None, float] | None:
    """(recall, precision) for the work class, or None when the card carries no work block.

    Its own function rather than a fourth entry in `figures`, because its denominators are
    not a stage's: precision is over the claims the operator JUDGED, and the recall is None
    unless the docket-level stops were judged too. Folding it into `figures` would have let
    the caller's loop hand `measured_target='work'` to `methods.measure`, which is not a
    stage and never was.
    """
    work = card.get(WORK)
    if work is None:
        return None
    truth = work.get("truth")
    return (work["right"] / truth if truth else None, work["right"] / work["judged"])


def declare(con, card: dict) -> dict:
    """Declare the methods and write the measurements — three stages, and the work class when
    the card carries one. Returns the stamps.

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
    # THE WORK CLASS, WHEN THE CARD CARRIES ONE. Its numbers are the operator's judgements,
    # not the scorer's, so it takes its own score file and its own denominators: precision
    # over the claims that were JUDGED (an unclear is excluded from both, and counted in the
    # queue rather than folded in as a wrong), and a recall only when the docket-level stops
    # were judged too — a work truth is otherwise unknown, and `class_measurement.recall` is
    # nullable exactly so an unknown one is not invented.
    # A CARD WITHOUT A WORK BLOCK DOES NOT RETIRE THE WORK FIGURE, and silence about that is
    # how a stale one keeps stamping. `_work_measurement` picks the newest by benchmark date
    # with no tie to the card's stages, so a re-score that skips the operator's judging sitting
    # moves the docket figure and leaves the work figure exactly where it was. That may be
    # intended; it must not be invisible (schema-critic, 2026-09-10).
    work, figured = card.get(WORK), work_figures(card)
    if work is None and methods._work_measurement(con, channel) is not None:
        print(
            f"  NOTE: this card carries no work block, and a work measurement is already live"
            f" on {channel}. It stays live, and rows naming a document keep being stamped from"
            " it — re-score the work class too if this card supersedes it."
        )
    if work is not None and figured is not None:
        recall, precision = figured
        methods.measure(
            con,
            measured_target="citation_resolution",
            cls=methods.WORK_CLASS,
            extractor_version=version,
            score_file=work["score_file"],
            benchmark_date=work.get("benchmark_date", card["benchmark_date"]),
            reading_channel=channel,
            precision=precision,
            recall=recall,
            truth_count=work.get("truth"),
            # `shown_count`, not `found_count`. The stage rows use `found_count` for what the
            # FINDER found, and the work class has no such number — what it has is the count
            # of claims the rule answered, which is what a reader would be SHOWN at that
            # grain. One published column must not carry two meanings (schema-critic).
            shown_count=work["judged"],
        )
    con.commit()
    return methods.stamp(con, channel=channel)
