"""Re-assert live resolutions under a newly declared measurement, without changing an answer.

WHY A VERB AND NOT A MIGRATION. ADR 0017 § Consequences promises that "re-measurement is a
scorer run, not a migration", and until now that was aspiration: `supersede.if_changed`
writes only when the ANSWER changes — `(outcome, cited_docket_id, cited_decision_id)` — and a
new measurement changes no answer, so a card declared after a load never reached the rows
that preceded it. They kept the class and the figure they were stamped with, for ever, and
the only path from a re-scored class to its rows was hand-written SQL over every one: the
migration-touching-every-row shape the five validation queries exist to catch (schema-critic,
2026-09-10; the operator chose to build this rather than defer it).

WHAT IT DOES NOT DO, and this is the whole discipline. It never edits a row. Every re-stamp
is an append: the live row is retired and an identical assertion is inserted beside it under
the new `(measured_class, score_row_id)`, so what a reader saw before the re-stamp is still
in the table and validation query 3's snapshot still reconstructs. It never changes an
answer, a method, a version or a channel — a row whose answer should change is the loader's
work, not this one's. And it never invents a class: a row is re-stamped from the measurement
its OWN shape calls for, which is the same rule `load` applies (`methods.WORK_CLASS` where
the row names a document, `methods.DOCKET_CLASS` where it stops at the proceeding).

WHAT IT COSTS. A re-stamped row is a second row on a key that already had one, so the table
grows by what is re-stamped. That is the price of an append-only assertion table and it is
the same price every supersession pays.
"""

from docketyard.citator import methods
from docketyard.store import supersede
from docketyard.store.db import utcnow

# Everything an assertion carries that is NOT the stamp. Named rather than `SELECT *` so a
# column added to the table fails here loudly instead of being silently dropped from every
# re-stamped row — which would be an edit disguised as an append.
_CARRIED = (
    "citing_document",
    "page",
    "target_kind",
    "target_key",
    "method",
    "method_version",
    "reading_channel",
    "outcome",
    "cited_docket_id",
    "cited_decision_id",
    "asserted_from_document",
    "asserted_from_capture",
    "source_location",
)


# The classes THIS verb owns. `class_vocab` also holds ('citation_resolution',
# 'on-page-veto') — the suppressor's own class, whose figure is a false-veto RATE and not a
# resolver's precision (ADR 0018 D7) — and a veto row must be left exactly alone. Reading
# "every measured resolution" instead re-stamped one from the docket precision, which is the
# borrowed-precision error this package exists to refuse (code review, 2026-09-10). A class
# this verb does not own is not stale; it is somebody else's.
_OURS = (methods.DOCKET_CLASS, methods.WORK_CLASS)


def stale(con, stamps: dict) -> list[tuple]:
    """Live measured resolutions whose class or measurement is not what `stamps` now says.

    A row is stale when the class its shape calls for is not the class it carries, or when it
    carries the right class from an older measurement of it. A `human` row is never stale:
    it is stamped from no measurement (`score_row_id IS NULL`) and a re-score does not touch
    a judgement a person made. Nor is a row of a class this verb does not own — see `_OURS`.
    """
    work = stamps.get(methods.WORK_KEY)
    docket = stamps["citation_resolution"]
    # ONLY KEYS THE MEASURED FINDER WROTE (code review, 2026-09-11). A key can stay live at an
    # older finder version — held from retraction, on a page the new walk skipped, in a
    # document it did not yield — and re-stamping its resolution with the new card's figures
    # is the borrowed precision `load_document` refuses (ADR 0017 D3).
    # Both stamps must measure ONE finder, or the filter below would admit keys for one card's
    # figures on the other's say-so — refused, as `load_document` refuses it (code review).
    ids = sorted({s[0] for s in (docket, work) if s is not None})
    rows = con.execute(
        f"SELECT extraction_method_version FROM class_measurement"
        f" WHERE measurement_id IN ({', '.join('?' * len(ids))})",
        ids,
    ).fetchall()
    finders = {v for (v,) in rows}
    if len(rows) != len(ids) or len(finders) != 1:  # a stamp naming no measurement, too
        raise methods.Unscored(
            f"the stamps name finder version(s) {sorted(finders)} across measurements {ids};"
            " a re-stamp needs every class measured on one finder"
        )
    (finder,) = finders
    out = []
    for row in con.execute(
        f"SELECT resolution_id, measured_class, score_row_id, cited_decision_id,"
        f" {', '.join(_CARRIED)}"
        " FROM citation_resolution"
        " WHERE superseded_by IS NULL AND confidence_state = 'measured'"
        f"   AND measured_class IN ({', '.join('?' * len(_OURS))})"
        # on a LIVE key: a retracted key's resolution is left live beside a retired identity
        # row (load.py, 2026-09-11), and re-stamping it would write a fresh `measured` row on a
        # key the record no longer asserts (schema-critic, 2026-09-11). Names qualified: an
        # unqualified column binds to the inner scope, the trap `project.py` records.
        "   AND EXISTS (SELECT 1 FROM citation c"
        "                WHERE c.citing_document = citation_resolution.citing_document"
        "                  AND c.page = citation_resolution.page"
        "                  AND c.target_kind = citation_resolution.target_kind"
        "                  AND c.target_key = citation_resolution.target_key"
        "                  AND c.superseded_by IS NULL AND c.method_version = ?)",
        (*_OURS, finder),
    ):
        wanted = work if (row[3] is not None and work is not None) else docket
        want_class = (
            methods.WORK_CLASS
            if (row[3] is not None and work is not None)
            else methods.DOCKET_CLASS
        )
        if (row[1], row[2]) != (want_class, wanted[0]):
            out.append((row, want_class, wanted))
    return out


def run(con, stamps: dict, *, channel: str = methods.CHANNEL_TEXT) -> dict:
    """Re-stamp every stale row. Returns the counts; the caller holds the transaction.

    THE CHANNEL IS A FILTER, not a rewrite: a measurement is of one reading channel (ADR 0018
    D8), so a text-layer card re-stamps text-layer rows and leaves an OCR reading alone. The
    stamps are looked up per channel by `methods.stamp`, and re-stamping across channels would
    be the borrowed precision every other guard in this package exists to refuse.
    """
    now = utcnow()
    counts = {"restamped": 0, "to_work": 0, "to_docket": 0}
    for row, want_class, wanted in stale(con, stamps):
        resolution_id, _, _, _, *carried = row
        if carried[6] != channel:  # reading_channel, in _CARRIED's order
            continue
        supersede.retire(con, "citation_resolution", "resolution_id", resolution_id)
        cur = con.execute(
            f"INSERT INTO citation_resolution ({', '.join(_CARRIED)}, asserted_at, confidence,"
            " confidence_state, measured_target, measured_class, score_row_id)"
            f" VALUES ({', '.join('?' for _ in _CARRIED)}, ?, ?, 'measured',"
            " 'citation_resolution', ?, ?)",
            (*carried, now, wanted[1], want_class, wanted[0]),
        )
        con.execute(
            "UPDATE citation_resolution SET superseded_by = ? WHERE resolution_id = ?",
            (cur.lastrowid, resolution_id),
        )
        counts["restamped"] += 1
        counts["to_work" if want_class == methods.WORK_CLASS else "to_docket"] += 1
    return counts
