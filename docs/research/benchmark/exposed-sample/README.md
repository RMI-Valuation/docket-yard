# The exposed-class sample (2026-09-11)

**Why it exists.** ADR 0017 sends an *exposed* citation to a person rather than publishing it:
a bare docket number of four digits or fewer whose last-digit-stripped reading is also a held
docket, because a footnote marker fused onto the number (`AB 124` + footnote `2` read as
`AB 1242`) resolves confidently to the wrong proceeding. The citator's rehearsal load of
2026-09-04 held **1,946** such keys, which at the runbook's thirty seconds a key is about
sixteen hours of reading. Measured 2026-09-11 on that load: they are 178 distinct targets from
984 citing documents, and **for 1,360 of them the citing document is filed in the very docket
the number names**; for none is it filed in the stripped number's docket.

**The operator's decision, 2026-09-11** (`docs/runbook.md` § Blocker 2): a rule clearing an
exposed key whose citing document is filed in the named docket, measured first on a random
fifty of those 1,360 that he judges. If they hold, the rule reaches him as an ADR 0017
addendum, because it narrows what decision 5 leaves to a person; the other 586 stay held.

## How it was drawn

- Store: `citator-dryrun.sqlite` on the instance, the 2026-09-04 rehearsal load (read-only).
- Population: the rows `citator.review.QUEUES["citation_exposed"]` returns, kept where any
  record carrying the citing document is filed in a docket with the target's prefix and
  sequence — **1,360** of 1,946.
- Sample: the population sorted by (citing document, page, target), then
  `random.Random(20260911).sample(population, 50)`. All fifty are decisions.
- `sample.json` holds the fifty with the passage the extractor quoted, the printed form, the
  record and page. The page is `tools/exposed_check_page.py --sample sample.json`.

## What the labels mean, and what fifty can show

Each key is judged `right` (the number is the docket it names), `fused` (a shorter number with
a footnote marker run on), or `unsure`. The answers land in `labels.csv` beside this file.

- **No `fused` answer** puts the class's fused rate under about 6% at 95% confidence — three
  in fifty, the rule of three — not at zero. Whether that is enough to publish the class by
  rule is the operator's decision, in the addendum.
- **One `fused` answer** rejects the rule as drafted: it would have published a wrong edge,
  and the shape of that case says what a narrower rule must exclude.
- **`unsure`** answers are counted apart and are neither.

The population will be recomputed by the rule at the real load; this sample measures the
rule's premise, not the load's count.
