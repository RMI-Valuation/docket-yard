"""The citator: citation edges, from a page of text to a "cited by" list.

Migration 0014 holds the shape (ADR 0018); this holds the pass that fills it, under ADR
0017's shipping decision. The chain and where each stage lives:

    text -> findings       `find` is NOT here yet, deliberately - see the note below
    findings -> families   `load`, writing citation_key + the four live families
    key -> docket/work     `resolve`, whose FIRST RULE is the registry (ADR 0017 D2)
    passage -> judgement   `judge`, the span test, a stored assertion and never a view
    families -> a page     `project`, the one home for the projection SQL

Nothing here reads a PDF. Text extraction runs on the enrichment box and comes back over
the internal API (`docs/architecture.md`), so this package takes text and findings, and the
shipped dependency list is unchanged.

**The finder is not in this package, and that is a decision waiting rather than an
oversight.** `tools/rmi-ai-machine/benchmark_regex.py` is the measured extractor, and two
things about it are unsettled:

  * It filters on the registry inside the finder. ADR 0017 D2 moved that check into
    resolution, so the shipped finder must drop it - that part is settled and easy.
  * It also classifies each hit `citation` or `caption` from a document-word window, and
    emits ONLY the citations. That is the `kind` judgement of ADR 0018 D5 - and its value
    domain in `judgement_value_vocab` is deliberately EMPTY, because the typing pass has
    not decided its values. Until it does, a finder that drops captions discards rows
    ("a row is never discarded"), and one that keeps them cannot say what they are.

So the finder ships when `kind` has a vocabulary. Everything downstream of it is here,
measured, and exercised against the sixty-decision benchmark by
`tools/rmi-ai-machine/citation_dryrun.py`, which imports this package rather than
reimplementing it.

**AND THIS PACKAGE MUST NOT WRITE TO PRODUCTION YET.** Two things are missing, and the
second is a promise this project has already made in an accepted record:

  1. There is no finder, per the note above, so nothing produces the findings a load
     consumes except a replay of the benchmark.
  2. **There is no review queue.** ADR 0017 D5 routes the exposed class and every rule-2
     repair to a human BEFORE publication — that is the whole reason the exposure test was
     defined, since it decides what gets published without a person looking. `load` computes
     those keys and `citator load` prints them, but `review_action` (ADR 0016) is in no
     migration, so nothing stores them and nothing gates on them. An exposed edge — `AB 124`
     with a footnote `2` fused on, resolving confidently to `AB 1242` — projects today
     indistinguishably from a clean one.

Neither is hard. Both are blocking, and they are in TODO.md as such rather than left for
whoever runs the first load to discover.
"""
