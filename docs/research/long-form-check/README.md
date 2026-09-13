# Long-form check — the gate for finder 2026-09-13

Finder 2026-09-13 reads the Board's long docket forms, `Finance Docket No. N` and `Ex Parte No.
N` (branch `finder-long-forms`, `keys.LONG_DOCKET`). Its card is still measured on the sixty
decisions, which print one long-form citation between them (decision 53072, page 3), so the card
cannot vouch for the long forms. This check is what does.

## Decided 2026-09-13 (the operator)

**About a hundred long-form citations, judged one at a time, as a gate before the branch
merges.** The card stays the sixty's; this figure is recorded here and in the runbook, and it
stamps no row.

## The question, fixed before anything is drawn

For each drawn long-form citation — a finding whose `target` matches `keys.LONG_DOCKET` and
whose `kind` is `citation` — two things, judged on the page:

1. **Does the key name the proceeding the page prints?** `STB Finance Docket No. 32760 (Sub-No.
   46)` keyed `FD 32760 (46)` is right; a sub-number dropped, a digit wrong, or a number that
   belongs to something else is wrong.
2. **Is it a citation, not the document's own proceeding named as itself?** The sixty's
   convention (`../benchmark/README.md`): a document cited in the own docket (`Decision No. 5`,
   `served …`) is a citation; the own caption or a bare mention of the own proceeding is not.

A row is **right** only when both hold. `unclear` is allowed and is reported apart, never folded
into either side.

## The population

The branch finder through the shipped walk, over the text layer of a production mirror
(`data/rehearse-family.sqlite`, 2026-09-12): **11,231 long-form citations** — 10,666 resolved,
565 unresolved — beside 17,615 long-form captions.

| Era of the carrying decision | Resolved | Unresolved |
|---|---|---|
| 1996–2005 | 7,071 | 427 |
| 2006–2019 | 3,391 | 127 |
| 2020 on | 204 | 11 |

## The draw

Stratified by era and by resolution, a fixed seed, one citation per document at most so no
long volume dominates: 40 from 1996–2005, 35 from 2006–2019, 15 from 2020 on, and 10 more drawn
from the unresolved of any era, which the proportional strata would barely reach. 100 in all.

## The gate, fixed before judging

**The long-form citations pass if their judged precision — right over judged, `unclear` set
aside — is at least 87.5%, the card's citation-stage precision (225 of 257).** A hundred
judgements read that figure to about six points either way, so a result close to the line is
reported with its interval and brought to the operator rather than decided by the point
estimate. Below the line, the branch does not merge; what the wrong rows share decides whether
the grammar is fixed or the long forms are withdrawn.
