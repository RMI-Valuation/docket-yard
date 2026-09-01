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

**AND THE SURFACE IS BUILT.** `/review` (migration 0017, `signin`, `web/review_routes.py`)
is the one signed-in page on the site: magic-link sign-in, a session cookie scoped to
`/review` so no read page can become identity-linked, and no page view counted, because
ADR 0016 says the review surfaces log the decision "and nothing else". A grant can now be
used by the person it was granted to.

What is left is not a gap in the code. Nobody has run the first real load: the finder needs
text from the enrichment box, and the box's side of the seam — the work batch out, the
findings back — is the next piece.
"""
