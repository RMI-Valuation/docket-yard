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

FINDER_VERSION = "2026-09-11"  # the wrapped `(Sub-No. …)`, and the quote's continuation line

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

# THE WRAPPED SUB-DOCKET (2026-09-11). `keys.SUBNO` refuses a newline before its parenthesis
# on purpose — `EP 445` ending a line above a list marker `(a)` must not key as `EP 445 (A)` —
# so a sub-number the Board's line breaking pushed onto the next line was lost: 628 citations
# in the first load, `Docket No. AB-12 ↵ (Sub-No. 162X)` keyed as the parent AB 12, 626 of
# them naming a sub-docket the registry holds. ACROSS A LINE BREAK THE WORDS ARE REQUIRED:
# `(Sub-No. 162X)` is a sub-docket wherever it sits, while a bare `(3)` on the next line is a
# list item — both bare cases the first load held were. The contents are `keys.SUBNO`'s, year
# exclusion included, so one grammar reads both; `keys.normalise` then keys the whitespace-
# collapsed target exactly as it keys a one-line one, and KEY_VERSION does not move.
WRAPPED_SUBNO = re.compile(
    r"[^\S\n]*\n[^\S\n]*\(\s*Sub[-\s]*No\.?\s*"
    r"(?!(?:19|20)\d\d\s*\))(\d{1,4}[A-Z]?|[A-Z]{1,2})\s*\)",
    re.I,
)
# THE CONTINUATION LINE (2026-09-11). `find` quotes the line a target sat on, and the resolver
# reads a served date only from the quote (`resolve._anchored`), so a date the line breaking
# pushed onto the next line was unreachable: 3,438 citations in the first load printed their
# served date only there, 3,293 of them left with no document. The next line is quoted when
# the citation PLAINLY runs onto it, and only then: the rest of the target's line opens a
# parenthesis it does not close (`AB-379X (ICC ↵ served Nov. 4, 1992)`), or holds nothing but
# a comma or `et al.` and the next line opens a served parenthetical (`AB 6 (Sub-No. 430X),
# et al. ↵ (STB served June 5, 2008)`). A caption line followed by prose, or a list item, is
# quoted alone as before — the continuation feeds the span test too, and a line that is not
# the citation's would hand it words the citation never printed.
TRAILING = re.compile(r"^[\s,]*(?:et\s+al\.?)?[\s,]*$", re.I)
OPENS_SERVED = re.compile(r"^\s*\(\s*(?:[A-Z][A-Za-z.]*\s+){0,2}served\b", re.I)


def _target_end(page_text: str, m: re.Match) -> int:
    """Where the target ends: the number, then a same-line or wrapped sub-docket
    parenthetical, or a hyphenated sub-docket."""
    end = m.end()
    tail = SUBNO.match(page_text[end:])
    if tail:
        return end + tail.end()
    if wrapped := WRAPPED_SUBNO.match(page_text, end):
        return wrapped.end()
    # THE HYPHENATED SUB-DOCKET, which `keys.DOCKET` stops short of: the Board prints
    # `WB25-33` for `WB 25 (Sub-No. 33)`, and decision 52676 in the benchmark is docketed
    # that way and cites `WB-20-50`. Absorbed here so `cited_raw` is honest — migration 0014
    # defines it as "the string as THIS reading printed it". Whether the KEY should carry the
    # sub-docket too is a `keys.py` and ADR question, and it is in docs/deferred.md rather
    # than answered in passing.
    hyphenated = re.match(r"-\d{1,4}[A-Z]?\b", page_text[end:])
    return end + hyphenated.end() if hyphenated else end


def printed(page_text: str, m: re.Match) -> str:
    """The target EXACTLY as the page prints it — `EP 542 (Sub-No. 32)`, `AB 1296X` — with
    whitespace collapsed, so a sub-docket wrapped onto the next line reads as one target.

    Sliced from the source rather than rebuilt from the match groups, because `keys.DOCKET`
    has no group for the parenthetical: rebuilding gives `EP 542` where the page says
    `EP 542 (Sub-No. 32)`, and `citation_reading.cited_raw` is defined as "the string as THIS
    reading printed it". `keys.normalise` is the only thing allowed to turn it into a key.
    """
    return " ".join(page_text[m.start() : _target_end(page_text, m)].split())


def quoted(page_text: str, start: int, end: int) -> str:
    """The line or lines a target sat on: from the start of its first line to the end of the
    line it ends on — two lines when its sub-docket wrapped — plus the next line when the
    citation plainly continues there (`TRAILING`, `OPENS_SERVED`). ONE LINE COMES BACK EXACTLY
    AS BEFORE, stripped and nothing else, so a re-load does not rewrite every unchanged quote;
    several are joined with one space."""
    first = page_text.rfind("\n", 0, start) + 1
    last = page_text.find("\n", end)
    last = len(page_text) if last < 0 else last
    # THIS TARGET'S rest of line, up to the next docket number: a parenthesis opened after a
    # later target is that target's (ingest specialist, 2026-09-11 — `See EP 445 and FD 36873
    # (STB ↵ served Mar. 12, 2021)` gave EP 445 FD 36873's date line, and flipped its span test)
    following_target = DOCKET.search(page_text, end, last)
    boundary = following_target.start() if following_target else last
    lines = page_text[first:last]
    if last < len(page_text):
        following = page_text.find("\n", last + 1)
        following = len(page_text) if following < 0 else following
        nxt = page_text[last + 1 : following]
        depth = _left_open(page_text, end, last, boundary)
        if depth > 0 or (TRAILING.match(page_text[end:boundary]) and OPENS_SERVED.match(nxt)):
            lines += "\n" + _to_close(nxt, depth)
    return " ".join(line.strip() for line in lines.split("\n") if line.strip())


def _left_open(page_text: str, end: int, last: int, boundary: int) -> int:
    """How many closes the next line owes before THIS target's parenthesis is shut: 0 when it
    left none open. The rest of the line is scanned IN ORDER (code review, 2026-09-11 — two
    counts could not tell `(see FD 1 (Sub-No. 2) ↵` from a closed pair, nor `) (STB ↵` from
    nothing open): a `(` opened before `boundary`, the next docket number, is this target's
    and one opened after it is that target's; a `)` shuts the innermost open one, and a stray
    `)` shuts nothing opened here. What is owed runs from the outermost of ours to the top."""
    stack: list[bool] = []
    for i, ch in enumerate(page_text[end:last], start=end):
        if ch == "(":
            stack.append(i < boundary)
        elif ch == ")" and stack:
            stack.pop()
    return len(stack) - stack.index(True) if True in stack else 0


def _to_close(line: str, depth: int) -> str:
    """The continuation line up to the parenthesis that closes what is open — `depth` left
    open on the line before, or the one this line opens itself — or the whole line if nothing
    closes. Never a paragraph a text layer happened to print on one line: everything quoted
    reaches the span test (ingest specialist, 2026-09-11)."""
    opened = depth > 0
    for i, ch in enumerate(line):
        if ch == "(":
            depth += 1
            opened = True
        elif ch == ")":
            depth -= 1
            if opened and depth <= 0:
                return line[: i + 1]
    return line


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
        end = _target_end(page_text, m)
        raw = " ".join(page_text[m.start() : end].split())  # `printed`, without a second scan
        # THE KEY IS NORMALISED FROM THE RAW, never from a window past the match. A window
        # made `find` judge `own` and de-duplicate under one key while `load` stored another
        # — `load` normalises `target`, which is this raw — so the `kind` written against a
        # key could be the call made for a different target.
        key = normalise(raw)
        if key is None:
            continue
        context = page_text[max(0, m.start() - WINDOW) : m.end() + WINDOW]
        names_document = bool(DOC_WORDS.search(context)) or key not in own
        line = quoted(page_text, m.start(), end)

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
        # WHICH pages, not only how many: the loader retracts an older finder's key only on a
        # page this pass read, because a page it did not read found nothing (ADR 0018 D10)
        "pages_walked": [page for page, _ in page_list],
        "findings": found,
    }
