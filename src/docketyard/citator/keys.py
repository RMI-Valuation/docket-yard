"""The citation natural key: how a printed target becomes one, and how it is written down.

ADR 0018 D1 keys a citation on `(citing_document, page, target_kind, target_key)`, where
`target_key` is the NORMALISED target and never the string as printed. This module is the
only place that normalisation happens, because `key_version` names it: the normaliser has
already changed once (the scorer's docket-suffix fix moved the docket-shaped truth from 220
targets to 225 on 2026-08-30), and under a digest that class of change rewrites every key
silently. A change here is a change to KEY_VERSION and a migration somebody can see.

The registry side of the same coin is here too. `docket` stores a proceeding in four
columns; `normalise` reads it out of printed text. Both have to arrive at one string or the
resolver compares two spellings of one docket - which is why they are two functions in one
file rather than one function in each of three tools, as they were before this shipped.
"""

import re
import unicodedata

# Bump with any change to `normalise`. It is stored on every `citation_key` row, so a change
# is visible in the store rather than inferred from a commit date.
KEY_VERSION = "norm-docket@2026-09-01"  # SUBNO changed on this date; see below

# THE PREFIX IS MATCHED CASE-SENSITIVELY, and that is a scar rather than a style: `IS` and
# `SO` are English words, so a deadline sentence ("the exemption is 30 days after ...")
# would otherwise normalise to the docket key `IS 30`. Found in code review 2026-08-30, in
# the scorer, and it is the same trap either side of the seam.
#
# The suffix letter may be glued to the number (`AB 1296X`, an abandonment exemption) or sit
# inside the sub-docket parenthetical (`AB 55 (Sub-No. 814X)`); both key the same way.
#
# The prefix list is the UNION of the scorer's and the finder's: `benchmark_score.py` lists
# `IS` and `SUB` but not `FSB`/`PCA`, `benchmark_regex.py` the reverse, and a target the
# owning finder emits must not fall out of class here by an accident of which file was
# edited last.
#
# `\d{1,6}`, not the finder's `\d{1,5}`: 104 held dockets carry a six-digit sequence (the
# largest is 253517), and under a five-digit cap `NOR 253517` keys as NOTHING — the trailing
# `\b` refuses the partial match, which is right, but the citation is then lost. THE COST IS
# NAMED IN `resolve.py`: ADR 0017's exposure argument rests on the finder's own cap, so a
# SIX-digit fusion falls outside both the repair and the exposure test by the accepted
# definitions, and neither rule is widened here to cover it.
DOCKET = re.compile(
    r"\b(FD|AB|EP|NOR|MCF|MCC|NOM|ISM|IS|SDM|WB|SO|DOP|STA|WCC|SUB|FSB|PCA)"
    r"\s*[-\s]?\s*(\d{1,6})([A-Z])?\b"
)
# The parenthetical after the number, with or without the words "Sub-No.". THE WORDS ARE
# OPTIONAL, and that is the fix for a defect the scorer still carried on 2026-09-01: with
# `Sub[-\s]?No\.` REQUIRED, `AB 1296X` normalised to `AB 1296 (X)` while `AB 1296 (X)`
# normalised to `AB 1296` — the same docket with two normal forms depending on how it was
# printed, which is the exact defect `citator-schema.md` cites for `EP 328 (2)` versus
# `EP 328 (Sub-No. 2)`. A key that is not idempotent cannot be rendered, corrected by a
# human, or read back.
#
# IT IS ANCHORED TO THE NUMBER, never searched over a window. A window is how the first
# draft of this fix read `Docket No. FD 35873, slip op. at 4 (2015)` as `FD 35873 (2015)`
# and `EP 445 and FD 36873 (Sub-No. 1)` as `EP 445 (1)` — a resolvable citation silently
# stored unresolved, or a key pointing at the wrong proceeding. The leading `\s*` still
# crosses the line break in `EP 711 (Sub-\nNo. 2)`, which is what the window was there for.
#
# The contents are a sub-docket number of at most four digits with an optional suffix letter
# (the largest held sub-docket is 1195), or a bare suffix of one or two letters (2,711 held
# dockets carry one: `X`, `TA`). A year or a pin cite — `(2015)`, `(STB served Oct. 5,
# 2017)` — matches nothing, and the key stays the bare docket.
SUBNO = re.compile(r"\s*\(\s*(?:Sub[-\s]*No\.?\s*)?(\d{1,4}[A-Z]?|[A-Z]{1,2})\s*\)", re.I)
# what `normalise` emits for a docket, and therefore what the docket-shaped class IS
DOCKET_KEY = re.compile(r"^[A-Z]{2,4} \d+")
# a key with no sub-docket and no suffix: `EP 445`, not `EP 445 (1)` or `AB 1296 (X)`. The
# exposure test in `resolve` needs this, because only a bare digit run can swallow a
# following footnote marker.
BARE_KEY = re.compile(r"^[A-Z]{2,4} (\d+)$")


def normalise(raw: str) -> str | None:
    """A printed target reduced to the comparable key, or None if it is not docket-shaped.

    `Docket No. FD 36500`, `FD 36500` and `FD-36500` are one edge and one key. Returning
    None rather than a fallback string is deliberate: this package ships ONE class, the
    docket-shaped one (ADR 0017 D1), and a caller that cannot tell "not a docket" from
    "some other normalisation of a docket" would write the model's classes into the class
    regex owns. Out of class is counted on `extraction_run`, never silently kept.
    """
    if not raw:
        return None
    text = unicodedata.normalize("NFKC", raw).replace("—", " ").replace("–", " ")
    m = DOCKET.search(text)
    if not m:
        return None
    key = f"{m.group(1).upper()} {int(m.group(2))}"
    # ANCHORED at the end of the number, so a parenthetical belonging to a later docket in
    # the same sentence — or a year at the end of a citation — cannot be grafted onto it
    sub = SUBNO.match(text[m.end() :])
    if sub:
        return f"{key} ({sub.group(1).upper()})"
    return f"{key} ({m.group(3).upper()})" if m.group(3) else key


def registry_key(prefix: str, sequence: int, sub_sequence: int | None, suffix: str | None) -> str:
    """A `docket` row in the same spelling `normalise` produces from printed text."""
    key = f"{prefix.upper()} {int(sequence)}"
    if sub_sequence is not None:
        return f"{key} ({int(sub_sequence)}{(suffix or '').upper()})"
    return f"{key} ({suffix.upper()})" if suffix else key


def registry(con) -> dict[str, int]:
    """Every held proceeding, keyed the way a citation is. This is the registry ADR 0017 D2
    checks against in RESOLUTION - never inside the finder, which would make an unresolvable
    target impossible to emit and empty the review queue by construction."""
    return {
        registry_key(p, s, sub, suf): did
        for did, p, s, sub, suf in con.execute(
            "SELECT docket_id, prefix, sequence, sub_sequence, suffix FROM docket"
        )
    }


def render(citing_document: str, page: int, target_kind: str, target_key: str) -> str:
    """The canonical rendering of the key as ONE string, for `review_action.target_key` and
    `correction.target_key` (ADR 0018 D1; migration 0014 documents the same shape). Never a
    digest: a normaliser change must strand no human row, and must be readable on a review
    page."""
    return f"{citing_document}/{page}/{target_kind}/{target_key}"
