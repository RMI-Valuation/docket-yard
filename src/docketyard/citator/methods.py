"""The two registries a pass must write before it may write an edge.

`assertion_method` orders the families and declares who owns a class; `class_measurement`
holds every score. Migration 0014 seeds NEITHER, on purpose: ADR 0018 D1 fixes ownership
"at insert time from the owning method's own declaration", and a method version welded into
DDL is a version the code then has to match. So a pass declares itself here, on its first
run, and the declarations are idempotent because a backfill is restartable.
"""

import sqlite3

from docketyard.citator import judge, resolve
from docketyard.store.db import utcnow

EXTRACTOR = "regex-docket-cite"
SPAN_METHOD = "span-names-document"
CHANNEL_TEXT = "text-layer"
RANK_VERSION = "v1"
# A human is a method, a channel and a version like any other — `reading_vocab` carries
# 'human' for exactly this reason (ADR 0018 D3: the channel is in every key, so a human row
# must carry something legal).
#
# HUMAN_VERSION is the QUEUE's convention version: what evidence was shown and under which
# rules the decision was made. It lives here, in ONE place, because the registry row and the
# assertion row must carry the same string — the projection joins them on it, and a mismatch
# would drop every human answer through an INNER join without saying so.
HUMAN = "human"
HUMAN_VERSION = "2026-09-01"

# ADR 0018 D8: this names the things the projection is a PRODUCT of, because a figure may
# only be published with the rule named beside it. D8 lists three — the span test's version,
# the family closure's, and `rank_version`.
#
# THE GATE IS A FOURTH, added when migration 0015 made the exposed class wait for a human
# (ADR 0017 D2). Bumping this string was not optional: without it a measurement taken before
# the gate and one taken after would carry the SAME `projection_rule_version` with different
# numbers and nothing to say why, and `class_measurement_identity` would collide them on one
# benchmark_date. That is the fourth repetition of the error ADR 0017 § Consequences names,
# so it is bumped here before the first edge is stamped rather than after.
PROJECTION_RULE = (
    f"span={judge.SPAN_VERSION};closure=cite.py@2026-09-01;rank={RANK_VERSION}"
    f";gate=exposed@{resolve.EXPOSURE_VERSION}"
)

# The text layer outranks OCR for every method, held as registry data (ADR 0018 D7). Ranks
# are unique per (rank_version, target_table), so "the highest-ranked live row" is singular.
RANKS = {
    (resolve.RESOLVER, resolve.RULE_1, CHANNEL_TEXT): 1,
    (resolve.RESOLVER, resolve.RULE_2, CHANNEL_TEXT): 2,
}


class Conflict(RuntimeError):
    """A declaration that contradicts one already in this `rank_version`. The registry is
    append-only and a re-rank is a NEW version, so this is a refusal, not a retry."""


_COLUMNS = (
    "target_table",
    "method",
    "method_version",
    "reading_channel",
    "role",
    "precedence_rank",
    "target_kind",
    "target_form",
)


def _already_declared(con, row: tuple, rank_version: str) -> bool:
    """True when this exact declaration is already on record — a restart, not a conflict."""
    where = " AND ".join(
        f"{c} IS ?" for c in _COLUMNS
    )  # IS, not =, because five of the eight are nullable
    return (
        con.execute(
            f"SELECT 1 FROM assertion_method WHERE {where} AND rank_version IS ?",
            (*row, rank_version),
        ).fetchone()
        is not None
    )


def owner(con, target_kind: str, target_form: str, *, rank_version: str = RANK_VERSION):
    """The method declared to own a class, or None. ADR 0018 D1: ownership is fixed at
    insert time FROM THE OWNING METHOD'S OWN DECLARATION, and migration 0014 states the
    writer's side of it — "the extractor looks up its own class, finds no owner row and must
    refuse to insert". `load` is that lookup."""
    return con.execute(
        "SELECT method, method_version FROM assertion_method WHERE target_table = 'citation'"
        " AND target_kind = ? AND target_form = ? AND rank_version = ?",
        (target_kind, target_form, rank_version),
    ).fetchone()


def declare(
    con,
    extractor_version: str,
    *,
    extractor: str = EXTRACTOR,
    human_version: str = HUMAN_VERSION,
    rank_version: str = RANK_VERSION,
) -> None:
    """Ownership, then the ranks. Idempotent: a re-run declares nothing new, and a
    declaration that CONTRADICTS one already on record raises `Conflict` rather than being
    swallowed. The extractor is a parameter because a findings document names its own
    method, and declaring one method while loading another is how the one-owner rule
    quietly stops being true.

    NO SUPPRESS ROW IS WRITTEN. The on-page veto exists only once its false-veto rate is
    measured (ADR 0018 D7), and it is unmeasured for OCR — absence of the registry row is
    how the record says "not yet trusted", so the mechanism ships inert rather than
    ships wrong.
    """
    now = utcnow()
    rows = [
        # the ownership row: WHO MAY WRITE the docket-shaped class. No channel, because the
        # citation key carries none — one page read twice is one key, so ownership of a
        # class cannot be per-channel either.
        ("citation", extractor, extractor_version, None, None, None, "stb", "docket"),
        # the ranking rows: WHO WINS. `role` only where the projection reads one.
        *[
            ("citation_resolution", method, version, channel, "resolve", rank, None, None)
            for (method, version, channel), rank in RANKS.items()
        ],
        # THE HUMAN RESOLVER, at rank 0: it outranks every machine rule, because ADR 0017 D5
        # says a review writes a `human` row which a model pass may never supersede — and a
        # row that cannot be superseded but does not win is a review that changed nothing.
        # Without this declaration the projection's candidate join is INNER and drops it, so
        # an accepted review silently turns a published edge into no edge at all.
        ("citation_resolution", HUMAN, human_version, HUMAN, "resolve", 0, None, None),
        # the span test ranks and carries no role: its family's projection has no role term
        ("citation_judgement", SPAN_METHOD, judge.SPAN_VERSION, CHANNEL_TEXT, None, 1, None, None),
        # `kind` at rank 2, AT THE EXTRACTOR'S OWN METHOD AND VERSION — `load` writes those
        # from the findings document, so a constant here would register a version nothing
        # wrote and leave every kind row unregistered. Nothing reads it yet (the projection
        # reads `span_names_document` and `exposed`), but it is declared so a later ranked
        # read cannot drop them all through an INNER join, which is how a bumped
        # SPAN_VERSION suppressed every in-family edge before `declare` learned to refuse.
        ("citation_judgement", extractor, extractor_version, CHANNEL_TEXT, None, 2, None, None),
    ]
    for row in rows:
        try:
            con.execute(
                "INSERT INTO assertion_method (target_table, method, method_version,"
                " reading_channel, role, precedence_rank, target_kind, target_form,"
                " rank_version, declared_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*row, rank_version, now),
            )
        except sqlite3.IntegrityError:
            # NOT `INSERT OR IGNORE`, which would swallow exactly the collisions this
            # registry exists to raise. Two of its indexes are meant to refuse:
            # `assertion_method_one_owner` (one method per class per rank_version) and
            # `assertion_method_rank` (one method per rank). Under OR IGNORE a bumped
            # SPAN_VERSION collided with the old rank-1 row, was dropped, and every span
            # judgement it then wrote had NO registry row — the projection's INNER JOIN
            # dropped them and every in-family edge silently suppressed.
            if _already_declared(con, row, rank_version):
                continue  # a restart: the identical declaration is already there
            raise Conflict(
                f"{row[0]} {row[1]}@{row[2]} collides with a declaration already in"
                f" rank_version {rank_version!r}. A change of owner or of rank is a NEW"
                f" rank_version — this registry is append-only."
            ) from None


def machine_channels(con) -> set[str]:
    """The channels a MODEL pass may say it read on: `reading_vocab` less 'human'. The
    third value exists so a review row has a legal key (ADR 0018 D3); it is never what a
    findings document was read from, and a model row carrying it would be found by
    `review._human_reading` and reused as a reviewer's evidence."""
    return {
        c
        for (c,) in con.execute(
            "SELECT reading_channel FROM reading_vocab WHERE reading_channel <> ?", (HUMAN,)
        )
    }


def ranked(con, channel: str, *, rank_version: str = RANK_VERSION) -> bool:
    """Whether the projection could show an edge read on this channel: a resolver ranked
    on it AND the span test ranked on it, because `project._TERMS` INNER-joins BOTH
    `citation_resolution` and `citation_judgement` to their rank rows on the channel, and
    an in-family edge whose span judgement has no rank row is suppressed by default. A
    channel with neither, or with one, stores rows no page can show — silently, with the
    load exiting 0. `declare` ranks the text layer only (RANKS and the span row); ranking
    OCR is a new `rank_version`, not a default."""
    return (
        con.execute(
            "SELECT EXISTS (SELECT 1 FROM assertion_method"
            "   WHERE target_table = 'citation_resolution' AND role = 'resolve'"
            "     AND reading_channel = ? AND rank_version = ?)"
            " AND EXISTS (SELECT 1 FROM assertion_method"
            "   WHERE target_table = 'citation_judgement' AND method = ?"
            "     AND reading_channel = ? AND rank_version = ?)",
            (channel, rank_version, SPAN_METHOD, channel, rank_version),
        ).fetchone()[0]
        == 1
    )


STAGES = ("citation", "citation_resolution", "projection")  # every row is stamped from one


class Unscored(RuntimeError):
    """A class nobody has scored, asked to stamp a row. ADR 0017 D3: such a class is
    `unmeasured` and PROJECTS NOTHING, so refusing here is the rule, not an inconvenience."""


def stamp(
    con,
    stages=STAGES,
    cls="docket",
    *,
    channel: str = CHANNEL_TEXT,
):
    """The measurement each stage's rows are stamped from: {stage: (id, precision)}.

    THE CHANNEL IS A TERM OF THE LOOKUP. A measurement is of one reading channel (ADR 0018
    D8 keys `class_measurement` on it), and a figure measured on the text layer says
    nothing about what the same method finds in OCR text at 10.8% CER. Until 2026-09-03
    this selected on `(measured_target, class)` alone, so the first OCR-channel load would
    have stamped every row with the text-layer precision, marked it `measured` and
    published it — the ADR 0017 D3 violation `docs/ocr-migration.md` recorded. A channel
    nobody has scored is `Unscored` exactly as a class nobody has scored is.

    THE VALUE IS A PRECISION, never a recall. ADR 0017 D3 is explicit — "confidence is the
    measured precision of the resolution's class on the checked sheet" — and a recall
    answers a different question (how much was found), which no reader is shown beside an
    edge. A measurement with no precision cannot stamp anything, which is what stops a
    figure being borrowed from the nearest column.

    The newest measurement wins, by benchmark_date. `class_measurement` is append-only, so
    a re-score adds a row and every edge already stamped keeps the historical pointer —
    which is the snapshot validation query 3 wants.
    """
    out: dict[str, tuple[int, float]] = {}
    for stage in stages:
        row = con.execute(
            "SELECT measurement_id, precision FROM class_measurement"
            " WHERE measured_target = ? AND class = ? AND reading_channel = ?"
            " ORDER BY benchmark_date DESC, measurement_id DESC LIMIT 1",
            (stage, cls, channel),
        ).fetchone()
        if row is None:
            raise Unscored(f"no class_measurement for ({stage}, {cls}) on channel {channel!r}")
        if row[1] is None:
            raise Unscored(
                f"({stage}, {cls}) on channel {channel!r} has been measured but carries no"
                " precision"
            )
        out[stage] = (row[0], row[1])
    return out


def measure(
    con,
    *,
    measured_target: str,
    cls: str,
    extractor_version: str,
    score_file: str,
    benchmark_date: str,
    reading_channel: str = CHANNEL_TEXT,
    recall: float | None = None,
    precision: float | None = None,
    false_veto_rate: float | None = None,
    truth_count: int | None = None,
    found_count: int | None = None,
    shown_count: int | None = None,
) -> int:
    """One score, in the one home for scores, and return its id so a row can point at it.

    `measured_target` says WHICH STAGE the figure is true of, and the assertion tables
    foreign-key the (id, stage) pair — so a row cannot be stamped from another stage's
    number. That is the error ADR 0017 made four times, and it is why this function will
    not let a caller pass a figure without saying what it measures.

    `reading_channel` says WHICH TEXT the figure was measured on, and `stamp` selects on it:
    a score recorded here for 'ocr' is the only thing that lets an OCR row be `measured`.
    """
    is_projection = measured_target == "projection"
    return con.execute(
        "INSERT INTO class_measurement (measured_target, class, extraction_method,"
        " extraction_method_version, resolution_method, resolution_method_version,"
        " reading_channel, projection_rule_version, benchmark_date, score_file, truth_count,"
        " found_count, shown_count, recall, precision, false_veto_rate, measured_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            measured_target,
            cls,
            EXTRACTOR,
            extractor_version,
            None if measured_target == "citation" else resolve.RESOLVER,
            None if measured_target == "citation" else resolve.RULE_1,
            reading_channel,
            PROJECTION_RULE if is_projection else None,
            benchmark_date,
            score_file,
            truth_count,
            found_count,
            shown_count,
            recall,
            precision,
            false_veto_rate,
            utcnow(),
        ),
    ).lastrowid
