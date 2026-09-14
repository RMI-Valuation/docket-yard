"""Resolution: a normalised target becomes a docket, a work, or an honest failure.

ADR 0017 D2: **the registry check is the first rule of RESOLUTION, not a filter inside the
finder.** A finder that can only emit dockets the registry holds cannot emit an unresolvable
one — which empties the review queue by construction and makes "cites `EP 445` (not in the
record)" a display that can never be produced. So every docket-shaped hit arrives here, and
this decides.

A row is never discarded for failing. An unresolved target is stored `unresolved` and never
projected; it is a real edge and it goes to a human (ADR 0017 D5).

Three rules, and each is a distinct method with its own confidence:

  rule 1   the normalised key is held. Resolved.
  rule 2   it is not, the printed number has five digits, and exactly one
           trailing-digit-stripped reading IS held. Repaired, at lower confidence, and
           NEVER a rewrite of the raw — the repair is a separate assertion over the same
           key, which is why it needs its own precedence rank (ADR 0018 D4/D7: a flat rank
           makes every repair unreachable, because rule 1 writes a row when it fails and
           outranks the repair that exists because it failed).
  exposed  it IS held, and it is a bare number of four digits or fewer whose
           last-digit-stripped reading is ALSO held. That is the footnote-fusion shape —
           `AB 124` followed by footnote `2` read as `AB 1242` — so it resolves confidently
           to the WRONG proceeding. Measured at 3 of 225 on the sheet (ADR 0017 § The
           exposure test): to review, not to a page.
"""

import re
from dataclasses import dataclass
from datetime import date

from docketyard.citator import find, keys

RESOLVER = "registry-match"
# THE RULES CARRY THE ANCHOR'S VERSION (Codex on PR #32, 2026-09-14; the operator's decision). The
# served-date window changed what a row asserts — the family became a fallback, not a peer — and
# the note below says any later widening of what a row asserts is a version bump, because a
# resolution row carries no finder version: `registry-match@rule-1` written before and after the
# change would be indistinguishable. `load` retires every older-version row onto the new one, and
# the release waits for none to be left on a live key. No separator in the value, as the store's
# other versioned tables refuse one. Until 2026-09-14 these were `rule-1` and `rule-2-repair`.
RULE_1 = "rule-1-2026-09-14"
RULE_2 = "rule-2-repair-2026-09-14"

# The exposure test is a DISTINCT RULE with its own definition and its own history — ADR 0017
# reconsidered its membership between 3, 5 and 14 before settling on 3 — so it carries its own
# method and version rather than borrowing the resolver's. Writing `registry-match@rule-1` on
# an exposure judgement was simply false provenance: that method did not make that judgement,
# and redefining the class would have rewritten every row in place with no visible change.
EXPOSURE_METHOD = "exposure-test"
EXPOSURE_VERSION = "2026-09-01"

# NO FIGURE IS DECLARED IN THIS PACKAGE, and that is the point. ADR 0017 D3: confidence is
# the measured precision of the class on the checked sheet, carried on the row with a
# pointer to the exact measurement it was stamped from. A constant here would be a second
# home for a number `class_measurement` already holds, and the two would drift — which is
# the whole failure this record has repeated. `methods.stamp` reads the measurement; a class
# nobody has scored has no precision and therefore cannot be stamped `measured` at all.


@dataclass(frozen=True)
class Resolution:
    """One resolution attempt. `outcome` is typed because a null docket id would otherwise
    mean three things at once: not tried, tried and failed, and tried and vetoed."""

    outcome: str  # resolved | unresolved | repaired | vetoed
    method: str
    docket_id: int | None = None
    decision_id: str | None = None
    exposed: bool = False  # resolved, but to a proceeding a fused footnote could explain


# ---------------------------------------------------------------------------------------
# The work-level step (ADR 0018 D4): a docket becomes a DOCUMENT when the page says which
# ---------------------------------------------------------------------------------------
# ONE RESOLUTION ROW ASSERTS THE COMPLETE OUTCOME, so this is not a second method with a
# second row. Migration 0014 discharged ADR 0018's owed item 3 in the DDL itself: "the family
# test reads the docket column and query 2 keys on the decision column, and they must come
# off the SAME resolution or the query joins one method's work-level answer to another's
# docket-level one." So `decision_id` rides on the rule that resolved the docket, and
# `method_version` stays `rule-1` / `rule-2-repair`.
#
# A NULL `decision_id` under `rule-1` therefore means ONE thing, "looked, and the page named
# no date or an ambiguous one", never "asserted before this step existed": the operator
# decided 2026-09-10 to keep the version on the measured fact that production held zero
# rows in every citator table that day (the 2026-09-04 chain ran into a copy that is never
# loaded), so every `rule-1` row the record will ever hold postdates the widening. Any LATER
# widening of what a row asserts is a version bump and a re-score of the checked sheet.
#
# The pattern is `judge.SPAN_NAMES_DOCUMENT`'s `served` alternative with the date completed,
# which makes ADR 0018 D4's FIRST condition — "the text names a document" — true BY
# CONSTRUCTION rather than by a second call into `judge`. A resolver that asked `judge` would
# bind its answer to `SPAN_VERSION` without any of its rows saying so; a resolver that is a
# strict narrowing of the span pattern cannot claim a work the span test would then suppress.
# A test pins the containment, because it is the whole argument.
#
# "served ON March 12, 2021" is DELIBERATELY NOT MATCHED. It is 0.96% of pages against this
# form's 5.43% (200,000 production pages, 2026-09-05), and admitting it would break the
# containment above: the span test does not match it either, so those edges are suppressed at
# projection and a work-level answer on them would be a claim nothing publishes. Closing that
# gap is a SPAN_VERSION bump and a re-measurement of every edge stamped by the old one
# (`judge.py`), never a quiet widening here.
SERVED = re.compile(r"served\s+(\w+)\.?\s+(\d{1,2}),?\s+(\d{4})", re.I)
# a sentence boundary the anchor window stops at: period, space, capitalised word, space
SENTENCE = re.compile(r"\.\s+(?=[A-Z][a-z]+\s)")

# Full names and the abbreviations the Board actually prints, counted over the same 200,000
# pages. `sept` is in this map because it was MEASURED at 1,335 occurrences — more than
# `march` — and a three-letter-prefix rule would have dropped every one of them.
MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def served_date(passage: str) -> str | None:
    """The ONE service date the passage prints, as ISO, or None.

    None when there is no readable `served <date>`, when the month word or the day is not a
    date, and — the case worth naming — when the passage prints SEVERAL different service
    dates. ADR 0018 D4 resolves to a work only on an unambiguous match, and a passage that
    names two documents is exactly as ambiguous as a day that holds two decisions; both stay
    at docket level rather than being arbitrated here.
    """
    seen = set()
    for month, day, year in SERVED.findall(passage or ""):
        number = MONTHS.get(month.lower())
        if number is None:
            continue  # a word in the month's place that is not a month
        try:
            seen.add(date(int(year), number, int(day)).isoformat())
        except ValueError:
            continue  # `served April 31, 2021` is not a date, and `date` is the only judge
    return seen.pop() if len(seen) == 1 else None


def _stripped(key: str) -> str | None:
    """The key with the last digit of a bare sequence removed, or None if it has none to
    remove. Only a BARE digit run can swallow a following footnote marker: a match ending in
    a closing paren or a letter suffix cannot (ADR 0017 § The exposure test, three checks)."""
    m = keys.BARE_KEY.match(key)
    if not m or len(m.group(1)) < 2:
        return None
    return key[:-1]


def _anchored(passage: str, printed: str, *, family: bool = True) -> str:
    """The parts of the passage that belong to THIS target: from the end of each of its
    printed occurrences to the next docket-shaped number, or the end of that line.

    THE DATE IS ANCHORED TO THE NUMBER, never searched over the whole passage — the discipline
    `keys.SUBNO` already carries. `find` quotes the WHOLE LINE a target sat on, and one line
    commonly cites several proceedings: "See EP 445, slip op. at 3 (STB served Mar. 12, 2021);
    see also FD 36873." handed FD 36873 the document EP 445 named, an edge asserting something
    the page never said (reproduced 2026-09-05, code review).

    THREE THINGS THE FIRST VERSION GOT WRONG (code review, 2026-09-10), each reproduced:

    - `printed` is the finder's target, whitespace-COLLAPSED (`find.printed`), while the
      quoted line keeps the page's own spacing; `FD  36873` with two spaces, common in OCR,
      never matched and its served date was dropped uncounted. The line is collapsed the
      same way before the search.
    - A bare `str.find` matched INSIDE a longer, different-family number: `FD 3687` found
      itself in `FD 36873` and took that citation's served date.
    - The window ran to the next docket-shaped token or the end of the line, so a later
      citation on the same line that names its proceeding by TITLE handed its served date
      to the numbered docket before it. The window now also ends at a sentence boundary —
      a period, space, and a capitalised word followed by a space (`. Compare `, `. See `)
      — which leaves abbreviations inside a caption (`Ry. Co.—`, `Inc. (`) alone.

    AND AN OCCURRENCE IS FOUND BY ITS KEY, NOT ITS SPELLING (ingest specialist, 2026-09-13,
    F1). `printed` is the first occurrence's spelling only, and since finder 2026-09-13 one
    finding folds `Finance Docket No. 34002` and `FD 34002` together: searching for the first
    spelling never reached `See FD 34002, slip op. at 3 (STB served May 1, 2002)`, and a
    re-load would have dropped a correct document to its docket. So every docket number on
    the line is keyed the way the finder keys it (`find.printed`, `keys.normalise`) and each
    one whose key is the target's anchors a window. A `printed` that keys as nothing keeps the
    spelling search, since the spelling is all there is to anchor on.

    THE FAMILY IS A FALLBACK, NOT A PEER (the operator's decision, 2026-09-13; `resolve` makes
    it). `family=False` anchors on occurrences keyed exactly as the target; `family=True` also
    lets one of its own sub-docket or suffixed forms (`FD 36873 (1)` for `FD 36873`) anchor the
    parent, the limit the 2026-09-10 review pinned. Held as a peer, it handed a parent every
    date its sub-dockets printed: decision 41393 cites `FD 34554 (STB served Oct. 7, 2004) …
    FD 34554 (Sub-No. 2) (STB served February 11, 2005)`, the parent saw two dates and named
    nothing, where notice 35093 is right. As a fallback it still carries `EP 575 and EP 575
    (Sub-No. 1) (STB served Oct. 30, 2007)` to decision 36758, filed in both dockets.

    THIS WINDOW IS VERSIONED BY THE RULES (`RULE_1`, `RULE_2`). An earlier note here said the
    finder and the rank versioned it; neither is written on a resolution row, so a changed answer
    and an unchanged one read alike (Codex on PR #32, 2026-09-14). Any change to what the window
    hands a row is a rule version, a re-scored card and a re-load that leaves no older row live.
    """
    out = []
    if not printed:
        return ""
    key = keys.normalise(printed)
    for raw in passage.split(" | "):
        line = " ".join(raw.split())
        for end in _occurrence_ends(line, printed, key, family):
            stops = [len(line)]
            if following := keys.docket_search(line, end):
                stops.append(following.start())
            if sentence := SENTENCE.search(line, end):
                stops.append(sentence.start())
            out.append(line[end : min(stops)])
    return " | ".join(out)


def _occurrence_ends(line: str, printed: str, key: str | None, family: bool) -> list[int]:
    """Where each occurrence of the target ends on the line: every docket number keying as
    `key`, and with `family` also as one of its own sub-docket or suffixed forms (above), to the
    end the finder gives it, or, when `printed` keys as nothing, every place the spelling
    itself stands alone."""
    if key is None:
        target = re.compile(r"(?<![A-Za-z0-9])" + re.escape(printed) + r"(?!\d)")
        return [m.end() for m in target.finditer(line)]
    ends = []
    for m in keys.docket_matches(line):
        found = keys.normalise(find.printed(line, m)) or ""
        if found == key or (family and found.startswith(key + " (")):
            ends.append(find._target_end(line, m))
    return ends


def _work(docket_id: int, works: dict[tuple[int, str], str], segment: str) -> str | None:
    """The decision the passage names inside an already-resolved docket, or None.

    Both halves of ADR 0018 D4's "exactly one" are enforced, and neither is arbitrated: the
    passage must print ONE service date (`served_date`), and that day must hold ONE decision
    in this docket (`keys.works` omits the days that hold more). Either way out is docket
    level, which is the outcome the record already publishes for 23,713 of 23,713 decisions
    whose `decision_number` is unfilled.
    """
    served = served_date(segment)
    return None if served is None else works.get((docket_id, served))


def resolve(
    key: str,
    held: dict[str, int],
    works: dict[tuple[int, str], str],
    passage: str,
    printed: str,
) -> Resolution:
    """Rule 1, then rule 2, the exposure flag on what rule 1 resolved, and the work.

    `held` is `keys.registry(con)` and `works` is `keys.works(con)`. Both are passed rather
    than queried per target because a backfill resolves tens of thousands of targets against
    one registry snapshot, and because the caller then knows exactly which registry a run was
    measured against — the bias `docs/citator-schema.md` records inverts with registry size.

    `passage` is the reading's `quoted_passage`, the same string the span test is given, and
    `printed` is `cited_raw` — the target exactly as the page prints it, which is what the
    served date is anchored to. Both are REQUIRED rather than defaulted: a default would
    silently resolve every target to the docket, and `cited_decision_id` being NULL on every
    row is the state these arguments exist to end.
    """
    # the target's own occurrences first; its family's only when they print no service date
    segment = _anchored(passage, printed, family=False)
    if served_date(segment) is None:
        segment = _anchored(passage, printed)
    bare = keys.BARE_KEY.match(key)
    digits = len(bare.group(1)) if bare else 0
    docket_id = held.get(key)
    if docket_id is not None:
        stripped = _stripped(key)
        return Resolution(
            outcome="resolved",
            method=RULE_1,
            docket_id=docket_id,
            decision_id=_work(docket_id, works, segment),
            # four digits or fewer: `\d{1,5}` caps the finder, so a five-digit docket cannot
            # absorb a sixth and only the shorter numbers are at risk
            exposed=bool(stripped and digits <= 4 and stripped in held),
        )
    # rule 2: five printed digits, and the stripped reading resolves. The five-digit
    # condition is ADR 0018 D4's; `\d{1,5}` caps the finder's sequence, so five digits is
    # the longest a number can be and still have absorbed a marker.
    if digits == 5 and (repaired := held.get(key[:-1])) is not None:
        # A REPAIR REACHES THE WORK TOO. Nothing in ADR 0018 D4 excludes it, and the two
        # judgements are independent: the repair says which proceeding the printed number
        # meant, the served date says which document inside it. A wrong repair carries the
        # decision id down with it, which is the ordinary consequence of a wrong docket and
        # is what rule 2's lower rank and the review queue are for — not a reason to publish
        # half an answer on a row the schema requires to be complete.
        return Resolution(
            outcome="repaired",
            method=RULE_2,
            docket_id=repaired,
            decision_id=_work(repaired, works, segment),
        )
    return Resolution(outcome="unresolved", method=RULE_1)
