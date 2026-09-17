"""Cheap, explainable text-quality features for one page of text. Scratch measurement code.

Features (all shares, so page length does not move them):
- words: tokens that look like words once edge punctuation is stripped (letters, with
  internal ' or - between letter runs), 2+ letters.
- lex: share of `words` found in the lexicon (the record's own vocabulary: words appearing in
  at least MIN_DF Board decisions served 2015-2023). A hyphenated word counts if every part does.
- mangled: share of letter-bearing tokens that are NOT word-like (letters fused with digits or
  symbols: "^f.certificate'of", "vEkecutive^Director").
- junk: share of non-space characters outside letters, digits and ordinary punctuation.
- case: share of words with a lower->UPPER flip inside the word ("PreseHation"), ignoring
  Mc/Mac/O' and all-caps.
"""

import re

ORDINARY = set(".,;:'\"()-/$%&§?![]‘’“”–—§#@")
EDGE = ".,;:!?'\"()[]{}*‘’“”•·_-–—<>|`~^"
WORD = re.compile(r"^[A-Za-z]+(?:['’\-][A-Za-z]+)*$")
FLIP = re.compile(r"[a-z][A-Z]")
LEGIT_FLIP = re.compile(r"^(?:Mc|Mac|O'|D'|De|La|Le|Van|Von)[A-Z]")
LETTER = re.compile(r"[A-Za-z]")
SPLIT_WORD = re.compile(r"[A-Za-z]+")


def features(text: str, lexicon: set[str]) -> dict:
    toks = text.split()
    n_tok = len(toks)
    lettered = 0
    words = 0
    hits = 0
    flips = 0
    for t in toks:
        if not LETTER.search(t):
            continue
        lettered += 1
        core = t.strip(EDGE)
        if len(core) < 2 or not WORD.match(core):
            continue
        words += 1
        parts = SPLIT_WORD.findall(core)
        if all(p.lower() in lexicon for p in parts):
            hits += 1
        if not core.isupper() and FLIP.search(core) and not LEGIT_FLIP.match(core):
            flips += 1
    nonspace = 0
    junk = 0
    for ch in text:
        if ch.isspace():
            continue
        nonspace += 1
        if ch.isalnum() and ch.isascii():
            continue
        if ch in ORDINARY:
            continue
        junk += 1
    return {
        "n_tok": n_tok,
        "lettered": lettered,
        "words": words,
        "hits": hits,
        "flips": flips,
        "nonspace": nonspace,
        "junk": junk,
    }


def shares(f: dict) -> dict:
    return {
        "lex": f["hits"] / f["words"] if f["words"] else None,
        "mangled": 1 - f["words"] / f["lettered"] if f["lettered"] else None,
        "junk": f["junk"] / f["nonspace"] if f["nonspace"] else None,
        "case": f["flips"] / f["words"] if f["words"] else None,
    }


# --- the prose screen, for ORDERING a re-read queue and nothing else ------------------------
#
# The re-read is prose first (ocr-plan.md decision 3, the operator 2026-09-17), and the page's
# kind is known only for the pages somebody labelled. These three numbers come from the stored
# text, need no scan and no model, and separate prose from maps, drawings and tables well enough
# to order a queue: on the 166 labelled pages, recall 0.92 and precision 0.92; two-fold with the
# thresholds chosen on one half, recall 0.86-0.94 and precision 0.87-0.94 on the held-out half.
# NOT a published claim about a page, and not a kind assertion — a queue order.
PROSE_TOKENS_PER_LINE = 3.0
PROSE_MEDIAN_LINE = 12
PROSE_MAX_NUMERIC = 0.25


def layout(text: str) -> dict:
    """Line shape: prose runs long lines with several words; a drawing's labels do not."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    toks = text.split()
    bare = (t.strip(".,;:()$%-").replace(",", "").replace(".", "") for t in toks)
    numeric = sum(1 for t in bare if t.isdigit())
    lens = sorted(len(ln) for ln in lines) or [0]
    return {
        "lines": len(lines),
        "median_line": lens[len(lens) // 2],
        "tokens_per_line": len(toks) / len(lines) if lines else 0.0,
        "numeric_share": numeric / len(toks) if toks else 0.0,
    }


def looks_like_prose(lay: dict) -> bool:
    return (
        lay["tokens_per_line"] >= PROSE_TOKENS_PER_LINE
        and lay["median_line"] >= PROSE_MEDIAN_LINE
        and lay["numeric_share"] < PROSE_MAX_NUMERIC
    )


def lexicon_words(text: str):
    """Words for the lexicon: lowercase letter runs of 2+ from word-like tokens."""
    for t in text.split():
        core = t.strip(EDGE)
        if len(core) >= 2 and WORD.match(core):
            for p in SPLIT_WORD.findall(core):
                yield p.lower()
