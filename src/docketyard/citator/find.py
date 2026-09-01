"""The finder: a page of text becomes docket-shaped findings.

ADR 0017 D1 buys this class from a regular expression and nothing else — it emits 97.8% of
docket-shaped targets, above Claude's 95.6% and every local candidate, at no per-page cost.
The API model ships for reporter cites, date-named decisions, court citations and dated
obligations, which are not in this slice.

Nothing here reads a PDF. Text extraction runs on the enrichment box and comes back over the
internal API (`docs/architecture.md`); this takes the text, so the shipped dependency list is
unchanged and the same grammar runs either side of the seam.

**IT DOES NOT FILTER ON THE REGISTRY** (ADR 0017 D2). A finder that can only emit dockets the
registry holds cannot emit an unresolvable one — which empties the review queue by
construction, makes "cites `EP 445` (not in the record)" a display that can never be
produced, and caps recall by arithmetic. Resolution decides what the registry holds; this
decides what the page says.

**IT DOES DECIDE `kind`**, and that is not the same thing. ADR 0017 D1 keeps the own-docket
rule with the extractor: a caption only when the number is the citing decision's OWN
proceeding and no document word is near; any other docket is a citation. The record already
knows which docket a decision sits in, so that is the one judgement no extractor has to
guess at — and it is why the model is not bought for it. Measured 95.1% recall at 88.1%
precision on the sixty-decision sheet, which is the `kind` judgement's own figure and not the
span test's.

**BOTH KINDS ARE EMITTED** (the operator's decision, 2026-09-01). A finder that keeps only
the citations discards rows, and "a row is never discarded" is the discipline the whole
store is built on. A caption is a finding with `kind = 'caption'`; it is stored, judged, and
suppressed at projection by the family closure — not dropped on the floor and counted in a
total nobody can check.
"""

import re

from docketyard.citator.keys import DOCKET, SUBNO, normalise

FINDER_VERSION = "2026-09-01"

# Words that mean a DOCUMENT rather than a proceeding, within a window round the number.
# `\bv\.\s` catches a case name; `S.T.B.` and `I.C.C.` catch a reporter cite beside the
# docket. This is the finder's own test and it is NOT the span test — `judge.py` runs a
# narrower one at projection, and the two are measured separately on purpose.
DOC_WORDS = re.compile(
    r"slip op|Decision No|served|NPRM|\border\b|\bv\.\s|Notice of Interim|\bS\.T\.B\.|I\.C\.C\.",
    re.I,
)
WINDOW = 160
PAGE_RE = re.compile(r"^===== page (\d+) =====$", re.M)


def printed(page_text: str, m: re.Match) -> str:
    """The target EXACTLY as the page prints it — `EP 542 (Sub-No. 32)`, `AB 1296X`.

    Sliced from the source rather than rebuilt from the match groups, because `keys.DOCKET`
    has no group for the parenthetical: rebuilding gives `EP 542` where the page says
    `EP 542 (Sub-No. 32)`, and `citation_reading.cited_raw` is defined as "the string as THIS
    reading printed it". `keys.normalise` is the only thing allowed to turn it into a key.
    """
    end = m.end()
    tail = SUBNO.match(page_text[end:])
    if tail:
        end += tail.end()
    else:
        # THE HYPHENATED SUB-DOCKET, which `keys.DOCKET` stops short of: the Board prints
        # `WB25-33` for `WB 25 (Sub-No. 33)`, and decision 52676 in the benchmark is
        # docketed that way and cites `WB-20-50`. Absorbed here so `cited_raw` is honest —
        # migration 0014 defines it as "the string as THIS reading printed it". Whether the
        # KEY should carry the sub-docket too is a `keys.py` and ADR question, and it is in
        # docs/deferred.md rather than answered in passing.
        hyphenated = re.match(r"-\d{1,4}[A-Z]?\b", page_text[end:])
        if hyphenated:
            end += hyphenated.end()
    return " ".join(page_text[m.start() : end].split())


def find(page_text: str, own: set[str]) -> list[dict]:
    """Every docket-shaped hit on one page, with its kind and the line it sat on.

    `own` is the normalised keys of the dockets the citing work is entered in — record data,
    passed in, never guessed. An EMPTY set calls every caption a citation, which is why
    `findings_document` refuses one rather than degrading quietly;
    `tools/rmi-ai-machine/citation_dryrun.py` is the reference caller.

    One finding per (page, key), carrying EVERY occurrence's line joined with " | " — the
    separator `load` uses when it joins across findings, so the two agree.
    """
    found: dict[str, dict] = {}
    for m in DOCKET.finditer(page_text):
        raw = printed(page_text, m)
        # THE KEY IS NORMALISED FROM THE RAW, never from a window past the match. A window
        # made `find` judge `own` and de-duplicate under one key while `load` stored another
        # — `load` normalises `target`, which is this raw — so the `kind` written against a
        # key could be the call made for a different target.
        key = normalise(raw)
        if key is None:
            continue
        context = page_text[max(0, m.start() - WINDOW) : m.end() + WINDOW]
        names_document = bool(DOC_WORDS.search(context)) or key not in own
        start = page_text.rfind("\n", 0, m.start()) + 1
        end = page_text.find("\n", m.end())
        line = page_text[start : end if end > 0 else len(page_text)].strip()

        if key not in found:
            found[key] = {
                "kind": "citation" if names_document else "caption",
                "target": raw,
                "quoted": line,
            }
            continue
        # EVERY OCCURRENCE, not just the first. ADR 0017 D4 settled the span test as
        # disjunctive over occurrences BECAUSE "the extractor quotes the FIRST match's line,
        # which is usually the running caption" — and keeping only the first left that
        # defect alive WITHIN a page: a caption at the top and a real citation lower down
        # stored the caption's line, read span-false and suppressed a real edge unless some
        # other page happened to rescue it. The fold across pages was never enough.
        if line not in found[key]["quoted"].split(" | "):
            found[key]["quoted"] += f" | {line}"
        # and one occurrence naming a document makes the target a citation, for the same
        # reason: the question is whether the page cites it, and one place saying so answers
        if names_document:
            found[key]["kind"] = "citation"
    return list(found.values())


def pages(text: str) -> list[tuple[int, str]]:
    """Split a marked-up document into (page number, text).

    THE MARKERS ARE THE BENCHMARK CORPUS'S, not the enrichment box's:
    `benchmark_sample.py` and `benchmark_ocr_text.py` write `===== page N =====`, while
    `extract_text.py` — the box's own pass — emits JSON with a per-page list and no markers
    at all. So this is the benchmark's reader, and a caller wiring the internal API in should
    pass its pages to `findings_document` directly rather than round-tripping through text.

    Unmarked text is ONE page, which is right for a one-page document and wrong for a
    forty-page one: every citation would key at page 1, every `source_location` would say
    page 1, and the fold that implements ADR 0017 D4's disjunction across pages would have
    nothing to fold. `findings_document` refuses the shape that would hide it.
    """
    marks = list(PAGE_RE.finditer(text))
    if not marks:
        return [(1, text)]
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((int(m.group(1)), text[m.end() : end]))
    return out


class Unmarked(ValueError):
    """Text long enough to be several pages, arriving with no page markers. Accepting it
    would key every citation at page 1 and quietly defeat the span test's disjunction."""


def findings_document(
    text: str | list[tuple[int, str]],
    *,
    document_sha256: str,
    own: set[str],
    reading_channel: str = "text-layer",
) -> dict:
    """One document, in the interchange shape `load.load_document` consumes.

    Takes either marked-up text (the benchmark corpus) or an explicit page list, which is
    what the enrichment box has and what a caller should pass.
    """
    if not own:
        raise ValueError(
            f"{document_sha256}: no `own` dockets. Every caption would read as a citation"
            " — ADR 0017 D1 keeps that judgement with the extractor precisely because the"
            " record already knows, so a missing answer is a refusal and not a default."
        )
    found = []
    page_list = list(text) if not isinstance(text, str) else pages(text)
    if isinstance(text, str) and len(page_list) == 1 and len(text) > 6000:
        raise Unmarked(
            f"{document_sha256}: {len(text)} characters with no `===== page N =====` marker."
            " Pass the pages explicitly; one page here would be a false location on every row."
        )
    for page, body in page_list:
        for f in find(body, own):
            found.append({"page": page, **f})
    return {
        "document_sha256": document_sha256,
        "method": "regex-docket-cite",
        "method_version": FINDER_VERSION,
        "reading_channel": reading_channel,
        "pages_read": len(page_list),
        "findings": found,
    }
