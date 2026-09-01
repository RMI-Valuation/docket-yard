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

from dataclasses import dataclass

from docketyard.citator import keys

RESOLVER = "registry-match"
RULE_1 = "rule-1"
RULE_2 = "rule-2-repair"

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


def _stripped(key: str) -> str | None:
    """The key with the last digit of a bare sequence removed, or None if it has none to
    remove. Only a BARE digit run can swallow a following footnote marker: a match ending in
    a closing paren or a letter suffix cannot (ADR 0017 § The exposure test, three checks)."""
    m = keys.BARE_KEY.match(key)
    if not m or len(m.group(1)) < 2:
        return None
    return key[:-1]


def resolve(key: str, held: dict[str, int]) -> Resolution:
    """Rule 1, then rule 2, and the exposure flag on what rule 1 resolved.

    `held` is `keys.registry(con)`. It is passed rather than queried per target because a
    backfill resolves tens of thousands of targets against one registry snapshot, and
    because the caller then knows exactly which registry a run was measured against — the
    bias `docs/citator-schema.md` records inverts with registry size.
    """
    bare = keys.BARE_KEY.match(key)
    digits = len(bare.group(1)) if bare else 0
    docket_id = held.get(key)
    if docket_id is not None:
        stripped = _stripped(key)
        return Resolution(
            outcome="resolved",
            method=RULE_1,
            docket_id=docket_id,
            # four digits or fewer: `\d{1,5}` caps the finder, so a five-digit docket cannot
            # absorb a sixth and only the shorter numbers are at risk
            exposed=bool(stripped and digits <= 4 and stripped in held),
        )
    # rule 2: five printed digits, and the stripped reading resolves. The five-digit
    # condition is ADR 0018 D4's; `\d{1,5}` caps the finder's sequence, so five digits is
    # the longest a number can be and still have absorbed a marker.
    if digits == 5 and (repaired := held.get(key[:-1])) is not None:
        return Resolution(outcome="repaired", method=RULE_2, docket_id=repaired)
    return Resolution(outcome="unresolved", method=RULE_1)
