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

A row is **right** only when both hold. The verdicts are `right`, `wrong` (the key is not the
proceeding printed), `caption` (the operator's addition, 2026-09-13: the document's own
proceeding named as itself) and `unclear`. `caption` counts against precision, since the finder
called it a citation, but is reported apart so the two errors can be told apart; `unclear` is
set aside. The quote is the line the number sat on, so a case name it cuts short is not an
error: the check is of the key and the kind, never the quote's completeness.

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
aside, `wrong` and `caption` both counting against — is at least 87.5%, the card's citation-stage precision (225 of 257).** A hundred
judgements read that figure to about six points either way, so a result close to the line is
reported with its interval and brought to the operator rather than decided by the point
estimate. Below the line, the branch does not merge; what the wrong rows share decides whether
the grammar is fixed or the long forms are withdrawn.

## Result, 2026-09-13: the gate FAILS

The operator judged all 100 (`verdicts.tsv`, matching `sample.json` row for row): **54 right, 45
caption, 0 wrong, 1 unclear. Precision 54 of 99 = 54.5%** (95% Wilson interval about 45–64%),
against the gate's 87.5%. Every key was the proceeding printed; every miss is the finder calling
the document's own proceeding a citation. Two readings beside the gate, stated as diagnostics and
not as a restated gate, because they were computed after the verdicts were seen:

- **What reaches a reader.** 42 of the 45 captions never publish: 36 are the document's own
  family with the span test false (suppressed at projection) and 6 do not resolve (four of them
  footnote digits fused on, `FD 343531`, `FD 347381`, `FD 336091`, and `FD 321` for FD 32162).
  Over the 50 rows that would project, **47 are right, 94.0%** (about 84–98%), against the card's
  projection figure of 98.2%. Of the 3 that publish, one (`FD 32760`, "This proceeding is related
  to Finance Docket No. 32760") reads as a citation by the rule this check applied to FD 33819,
  one (`FD 35081`, "Decision No. 2 in STB Finance Docket No. 35081") is a notice naming itself,
  and one (`FD 34177`) is a joint decision's running header in a document the record files only
  under FD 33407.
- **Why the finder erred.** For all 36 suppressed captions a word in the finder's ±160-character
  window fired — `served` (15), `order` (9), both (7), `Decision No.`, `slip op.`, `v.` — the
  headers and captions of older decisions. Treating the own family as a caption unless the span
  test names a document would, on these 100, correct 36 of the 45 and flip 2 of the 54 right rows,
  both already suppressed at projection. Chosen after seeing the verdicts, so it can only be gated
  on a fresh sample. The other 8 captions name dockets the record does not link to the document
  (a joint decision filed under one docket only); no finder rule can see those.

**Corrected by the operator the same day:** `FD 32760` on `57f33729a6dc` p1 ("This proceeding is
related to Finance Docket No. 32760") from caption to right, by the rule applied to FD 33819 (a
related proceeding is a citation). The first gate then reads **55 right, 44 caption, 1 unclear:
55 of 99 = 55.6%** — still a failure.

## Decided 2026-09-13 (the operator), after the failed gate

- **The finder's kind rule changes, for every docket form, not only the long ones**: the
  document's own family is a caption unless the span test (`judge.names_document`) names a
  document — the projection's own rule, so what publishes cannot change by construction, and
  the gap `walk.py` recorded on 2026-09-12 closes for the abbreviated forms too.
- **It is gated on a FRESH hundred**, drawn the same way with a new seed from documents none of
  these 100 came from, judged with the same verdicts against the same 87.5%. These 100 have been
  seen and gate nothing further.

## The second draw, 2026-09-13

`sample-2.json`, by `long_form_check_sheet.py --seed 2026091302 --exclude sample.json --name
sample-2` with finder **2026-09-13b** on the same mirror: the kind rule leaves **6,994**
long-form citations (4,251 and 427 unresolved from 1996–2005, 2,087 and 127 from 2006–2019, 91
and 11 from 2020 on). 100 drawn by the same strata, **none from a document the first sample
drew**, one per document; a second draw is identical byte for byte. On the sixty the new rule's
card reads citation 223 of 230, resolution 217 of 221, projection 217 of 221 (unchanged), work 140
of 140. Its verdicts go in `verdicts-2.tsv`.

## Result of the second gate, 2026-09-13

The operator judged all 100 (`verdicts-2.tsv`, matching `sample-2.json` row for row): **94 right,
5 wrong, 1 caption, 0 unclear — 94 of 100 = 94.0%, 95% Wilson interval 87.5–97.2%**, against
the 87.5% gate: a pass on the point estimate, with the interval's lower end on the line.

- **Every `wrong` is a digit error, and none publishes.** Four are footnote markers fused onto the
  number (`FD 342491`, `FD 340192`, `FD 351471`, `FD 339961`) and one a digit split off by a space
  (`FD 3482` for FD 34821); all five are unresolved (the 176-case pattern in `../../deferred.md`).
  The one `caption` (`FD 36472`) would be shown.
- **Over the 80 rows that would reach a reader, 79 are right: 98.8%**, against the card's
  projection figure of 98.2% — a diagnostic beside the gate, not the gate.
- **One row reads as a fusion the verdict calls right:** `FD 345614` on `1e029c50a184` p4, "STB
  Finance Docket Nos. 345614 and 345625" — FD 34561 and FD 34562 with footnotes 4 and 5 fused on
  (FD 34561 is held, FD 345614 is not). As `wrong` the gate reads 93 of 100 = 93.0%, interval
  about 86–96%. Put to the operator with the result, as a result this close to the line is.

**Decided 2026-09-13 (the operator):** `FD 345614` is `wrong` (a fused footnote marker), so the
second gate reads **93 of 100 = 93.0%** (95% interval about 86–96%), and **he accepts it as a
pass**: every miss but one is a digit fusion that never resolves or publishes, and 79 of the 80
rows that would reach a reader are right. Finder 2026-09-13b merges by pull request, then the
production re-load follows `docs/runbook.md` § The long-form re-load.
