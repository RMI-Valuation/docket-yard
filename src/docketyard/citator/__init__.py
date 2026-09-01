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

**THE REVIEW GATE IS BUILT** (migration 0015, `review`). ADR 0017 D2 sends the exposed class
to a human before publication — the whole reason the exposure test was defined, since it
decides what gets published without a person looking — and until 0015 there was no queue, so
it published itself. Now `load` stores an `exposed` judgement, `review` computes the queue,
and `project` holds such an edge until a live `human` resolution exists for it. Measured on
the benchmark: 3 edges held, exactly the three ADR 0017 § The exposure test names.

**WHAT IS STILL MISSING BEFORE THIS WRITES TO PRODUCTION:**

  1. **The finder**, per the note above, so nothing produces the findings a load consumes
     except a replay of the benchmark.
  2. **`/review` and sign-in.** The queue and the decision are here and reachable through
     `docketyard citator review` / `decide`, which is enough for the operator — reviewer
     zero, ADR 0016 — and not enough for anyone else. Magic-link sign-in exists in ADR 0011's
     decision and not yet in code, and until it does, a grant cannot be used by the person it
     was granted to.

Both are in TODO.md rather than left for whoever runs the first load to discover.
"""
