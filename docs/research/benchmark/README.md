# Benchmark step 1 — the labelled sample

Drawn 2026-08-26 by `tools/rmi-ai-machine/benchmark_sample.py` (seed 20260826) from the 885
decisions of the wave-1 window (served 2024-08-01 onward) whose text layer step 0 produced.
Three tiers of twenty, per `docs/extraction-benchmark.md` § Step 1: **heavy** (the twenty
drawn from the sixty decisions with the most citation-like strings), **routine** (notices of
exemption and notices), **short** (one- or two-page decisions). None is image-only.

`sample.json` records what was drawn and why; `labels.csv` is the sheet to fill in. The
per-page text of each decision is on RMI-AI-MACHINE at `/data/docketyard/benchmark/text/`
and mirrored to `data/benchmark/text/` on the working machine (disposable, not committed)
— but **label from the Board's PDF**, linked below; the text layer is what is being tested.

## How to check the labels (2026-08-29)

A queue, as the OCR ground truth has, built by
`tools/rmi-ai-machine/labels_check_page.py` and published privately to the operator (the
address is not recorded here — the page is regenerable from the script and the sheet). One decision at a
time: its **text on the left with every labelled passage highlighted in place**, its labels
on the right, each marked right or wrong, with a sweep for a whole decision. Judgements stay
in the browser; **Copy findings** hands them back in one block.

The highlighting is the point, and it is why this queue differs from the OCR one. An OCR
transcription is judged on what it says; a label set is also judged on **what it missed**,
and an unhighlighted citation sitting in the running text is the only way to see one. Each
decision therefore carries a box for what the drafter passed over.

**The four conventions were settled 2026-08-29** and are now applied in `labels.csv`,
so the queue no longer asks them — 287 of the 977 rows changed. They are recorded here
because they are the shape of the citation edge itself, and the citator's schema gate will
have to answer them again:

| Question | Settled | Why |
|---|---|---|
| Is a decision's own docket a citation? | **No, where the text names only the proceeding** — those rows are `kind: caption` | The record already knows which docket a decision belongs to; an edge there is a self-loop. They are kept, not deleted, because telling a caption from a citation is the skill being tested, and they are the only negative examples the sheet has. But a *prior decision* in that same docket is a different document, and citing it is a real edge — see below. |
| Is a repeated short-form its own citation? | **Neither required nor penalised** | A repeat adds no edge. Scoring compares *sets* of `(decision, target)` pairs, so an engine is neither rewarded for thoroughness nor punished for it. |
| Are court citations in scope? | **Yes, typed `court`, scored apart** | They cannot be validated against the docket registry, so they stay out of the citator's first slice — but a court vacating a Board decision is the strongest negative-treatment signal there is, and re-labelling them later would be expensive. |
| Is "effective on its service date" a deadline? | **Yes, with the target named, never blank** | The Board stated both the rule and the service date; joining two published facts is quotation, not computation. A blank target read as missing data, which was the actual defect. |

Two things surfaced while applying them that the binary questions had not anticipated:

- **"self" did not mean "caption", and a first pass got this wrong.** The note marks *the
  target docket is this decision's own*, wherever it appears and whatever it points at — so
  reclassifying every self-noted row as a caption swept in 90 rows that cite a **prior
  decision** (`Decision No. 1, FD 36732 et al., slip op. at 6`, `NPRM, EP 787, slip op. at
  4`, `By decision served March 12, 2024, the Board vacated the NITU`). Those are genuine
  edges: a prior decision is a different document, whatever docket it sits in. The test that
  separates them is whether the text names a **document** or only the **proceeding** —
  `slip op.`, `Decision No.`, `served`, `NPRM`, `order` mean a document. Twelve more are
  **record cites** (`IANR Reply 2, Aug. 14, 2024, FD 36798`), which cite a *filing* and
  carry the docket only as an address. Of the 188 self-noted rows: 90 are citations to prior
  decisions, 12 are record cites, and **86 are true captions**.
- **Blank deadline targets were three different things**, not one. Twenty are the service-date
  reference; nineteen quote only a period ("15 days after the draft EA is available"), where
  the quoted sentence is the whole answer and there is no separate date to hold; six are
  indefinite (until further order, or every deadline tolled by a lapse in appropriations).
  Naming all three was the same decision applied consistently — leaving twenty of them blank
  would have recreated the defect.

**Fourteen labels quote a passage that runs over a page break**, and the queue now says so
rather than calling them missing — a filter shows only those. They cannot be located in the
extracted text at any effort: extraction emits each page's body first and its footnotes
after, so the two halves of the passage are not adjacent, and what sits between them is not
whitespace. Only the Board's PDF settles them, which is what the queue links to. The
drafter noted every one while reading the PDF (`citation begins at the foot of p10 and
completes on p11`), so the notes are the guide.

Two classes were mechanical and are fixed (2026-08-30), taking an original 58 down to 14:

- **whitespace** — a PDF wraps where it likes and extraction turns a wrap inside a caption
  into a space, so the text holds `Inc.— Discontinuance` where the label quotes
  `Inc.—Discontinuance`. Matching ignores whitespace entirely. That accounted for 38.
- **the Board's running header and its footnote markers** — a citation crossing a page
  break has `Docket No. EP 788` and a page number wedged into the middle of it, and a
  sentence carries the marker of the footnote it annotates (`received,1 the exemption`
  where the page prints `received, the exemption`). Both are skipped when matching. The
  footnote rule fires only on a digit or two between a lower-case word's punctuation and
  the next lower-case word, which leaves `Sub-No. 5X` and `1 I.C.C.2d at 825` untouched.

A caution recorded because it was learned the hard way: **the text layer cannot be used to
judge a page-spanning label.** Searching it for one half of such a citation finds a
different citation elsewhere in the decision and makes the label look like a wrong pin
cite. Two rows were wrongly called wrong pin cites that way before the PDF was consulted.

## Provenance of the labels (2026-08-26)

`labels.csv` was **drafted by a model** (Claude Fable 5, four passes over the Board's PDFs,
one per tier and half-tier, under the rules below) and was **checked by the operator on
2026-08-30**: all 884 cards judged, one row marked wrong, none missing. It is ground truth
for step 2, and precision may now be read — before the check it could not be, since a real
citation the drafter passed over scored as a false positive.

The one correction was a class, not a row. `Decision No. 1, FD 36744 et al., slip op. at 6`
recorded its target as `FD 36744 et al.`, and 68 rows over 16 distinct targets did the same.
**Decided 2026-08-30 (operator): `target` holds what a citator resolves; `quoted` holds
what the page printed.** The 68 rows now read `FD 36744`; `et al.` survives in `quoted`.
Scoring did not move (`norm_target` already reduced both forms to the same key; the truth
sets were compared before and after and are identical), and the column is now consistent
with the caption rows, which already wrote a consolidated proceeding as resolved keys
(`NOR 42144; NOR 42150; …`).

One report of a missing highlight (`NOR 42060 (Sub-No. 1)` on page 20 of 51532) was the
queue's own defect, not a gap in the sheet: the label existed and the matcher was binding
quotes to the wrong occurrence. Fixed the same day; the label renders.

Two things to hold in view when reading it:

- The drafter is a Claude model and one of step 2's candidates is a Claude API model, so a
  label the operator did not check is a Claude-flavoured target. The check is what removes
  that.
- The drafting passes were told to be exhaustive on the heavy tier and to label every
  short-form and repeated citation on its page; they also labelled ordering-paragraph
  "effective on its service date" sentences as deadlines with a blank `target`, and the
  Board's stamp text on granted letters. Those conventions were settled on 2026-08-29
  (above) and `target_kind` now carries the answer on every row.

Assembled 2026-08-26, conventions applied 2026-08-29: 977 rows over the sixty decisions —
**727 citations** (599 `stb`, 116 `court`, 12 `record`), **86 captions**, **164 deadlines**
(119 `date`, 21 `reference`, 18 `period`, 6 `indefinite`). Every row passed the page-range
check, and no row is left without a `target_kind` or an unexplained empty `target`.
Deduplicated to the pairs a citator would consume, the citation set is **360 STB edges**,
86 court and 7 record.

## How to label

One row per thing found. Copy the decision's first five columns down for each row.

| Column | Put |
|---|---|
| `kind` | `citation`, `caption`, or `deadline` |
| `page` | The 1-based page of the Board's PDF where it appears |
| `quoted` | **citation / caption:** the reference exactly as printed (`Docket No. FD 36500`, `Union Pacific—Control—Southern Pacific, 1 S.T.B. 233 (1996)`, `Ex Parte No. 711 (Sub-No. 1)`). **deadline:** the whole sentence that sets it, as printed |
| `target` | What a citator would resolve, or the date a deadline sets — always as printed, never computed. Left empty only where `target_kind` says the quoted text is the whole answer (`period`, `indefinite`) |
| `target_kind` | **citation:** `stb`, `court`, or `record`. **caption:** `self`. **deadline:** `date`, `reference`, `period`, or `indefinite`. Never blank |
| `note` | Anything a checker would need: where on the page it sits, an ambiguity, why a nearby string was passed over |

What counts as a **citation**: a reference to a Board or ICC decision or docket other than
this decision's own — including prior decisions in another docket given by date alone, Ex
Parte rulemakings relied on, and short forms. A court case is a citation too, typed `court`.
A **record cite** — a filing in this proceeding, given as party, document and date — is a
citation typed `record`; the docket number in it is an address, not the target. Statutes and
CFR sections are not citations.

What counts as a **caption**: this decision's own proceeding named as *itself*, naming no
document — the caption, a section heading, a table header, a bare `Docket No. X`, the "All
pleadings, referring to Docket No. X, should be filed" paragraph. Label it, typed `self`.
It is not an edge in the citation graph; it is here so that an engine which cannot tell it
from a citation is caught. **The test is document versus proceeding**: `Docket No. EP 787`
is a caption, `NPRM, EP 787, slip op. at 4` is a citation, because it points at a specific
decision — and that holds even though both name the decision's own docket.

What counts as a **deadline**: a date, or a period, that the decision itself sets for someone
to act by — replies due, effective dates, comment periods, filing windows. A date recited as
history is not one. Where the sentence gives only a period, or fixes no end at all, the
`target` stays empty and `target_kind` says which; where the effective date is another known
date ("effective on its service date"), `target` names that reference rather than a date.

Time: the routine and short tiers are a minute or two each; the heavy tier is where the
hour goes. Labels are the truth for step 2 — a model that finds more than the labels is
checked against the PDF, not trusted.

## The sixty

| # | Tier | Docket | Served | Type | Pages | Board's file |
|---|---|---|---|---|---|---|
| 1 | heavy | AB 284/5/X | 2024-08-23 | Decision | 5 | [52238](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1724427819738/52238.pdf) |
| 2 | heavy | EP 542/32 | 2024-09-18 | Decision | 23 | [52260](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1726669804956/52260.pdf) |
| 3 | heavy | AB 55/814/X | 2024-10-17 | Decision | 27 | [52211](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1729175404332/52211.pdf) |
| 4 | heavy | FD 36744/1 | 2025-01-14 | Decision | 38 | [52295](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1736868708942/52295.pdf) |
| 5 | heavy | EP 328/2 | 2025-01-15 | Decision | 33 | [51532](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1736955004819/51532.pdf) |
| 6 | heavy | FD 32760/50 | 2025-04-28 | Decision | 7 | [52330](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1745865626975/52330.pdf) |
| 7 | heavy | NOR 42183 | 2025-05-29 | Decision | 10 | [52616](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1748547583718/52616.pdf) |
| 8 | heavy | EP 665/2 | 2025-05-30 | Decision | 10 | [52526](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1748620478627/52526.pdf) |
| 9 | heavy | FD 32760/49 | 2025-06-30 | Decision | 9 | [52332](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1751297598299/52332.pdf) |
| 10 | heavy | FD 32760/48 | 2025-08-15 | Decision | 9 | [52701](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1755272313346/52701.pdf) |
| 11 | heavy | EP 542/33 | 2025-09-05 | Decision | 23 | [52267](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1757082605245/52267.pdf) |
| 12 | heavy | EP 782 | 2025-09-11 | Decision | 4 | [52699](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1757601004420/52699.pdf) |
| 13 | heavy | EP 788 | 2026-01-07 | Decision | 18 | [52748](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1767799805582/52748.pdf) |
| 14 | heavy | AB 1305/1 | 2026-02-19 | Decision | 15 | [52835](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1771536817487/52835.pdf) |
| 15 | heavy | FD 36501 | 2026-03-13 | Decision | 21 | [52822](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1773415845345/52822.pdf) |
| 16 | heavy | EP 787 | 2026-05-08 | Decision | 32 | [52988](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1778251158324/52988.pdf) |
| 17 | heavy | EP 767 | 2026-05-08 | Decision | 4 | [52991](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1778250603985/52991.pdf) |
| 18 | heavy | FD 36849/1 | 2026-05-26 | Decision | 11 | [53072](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1779831726491/53072.pdf) |
| 19 | heavy | FD 36873/1 | 2026-05-28 | Decision | 42 | [53052](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1779972242620/53052.pdf) |
| 20 | heavy | FD 32760/48 | 2026-07-21 | Decision | 7 | [53046](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1784658047556/53046.pdf) |
| 21 | routine | FD 36781 | 2024-09-06 | Notice of Exemption | 3 | [52268](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1725633046981/52268.pdf) |
| 22 | routine | FD 36803 | 2024-09-19 | Notice of Exemption | 3 | [52280](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1726756255897/52280.pdf) |
| 23 | routine | FD 36813 | 2024-10-24 | Notice of Exemption | 3 | [52326](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1729780205030/52326.pdf) |
| 24 | routine | AB 290/414/X | 2024-11-20 | Notice of Exemption | 3 | [52347](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1732116680892/52347.pdf) |
| 25 | routine | AB 290/415/X | 2024-11-20 | Notice of Exemption | 4 | [52361](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1732116604983/52361.pdf) |
| 26 | routine | FD 36819 | 2024-12-13 | Notice of Exemption | 3 | [52395](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1734103805149/52395.pdf) |
| 27 | routine | FD 36845 | 2025-03-28 | Notice of Exemption | 3 | [52522](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1743172336880/52522.pdf) |
| 28 | routine | FD 36486/8 | 2025-04-17 | Notice of Exemption | 3 | [52537](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1744900345302/52537.pdf) |
| 29 | routine | FD 36841 | 2025-05-01 | Notice of Exemption | 3 | [52573](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1746109803436/52573.pdf) |
| 30 | routine | EP 670/1 | 2025-09-30 | Notice | 2 | [52757](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1759242738839/52757.pdf) |
| 31 | routine | FD 36901 | 2026-01-08 | Notice of Exemption | 3 | [52860](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1767886305513/52860.pdf) |
| 32 | routine | AB 511/8/X | 2026-01-23 | Notice of Exemption | 4 | [52887](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1769182204119/52887.pdf) |
| 33 | routine | EP 670/1 | 2026-01-30 | Notice | 2 | [52908](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1769802728996/52908.pdf) |
| 34 | routine | FD 35217/1 | 2026-04-03 | Notice of Exemption | 3 | [52971](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1775226811459/52971.pdf) |
| 35 | routine | EP 774/2 | 2026-04-08 | Notice | 2 | [52978](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1775658604020/52978.pdf) |
| 36 | routine | FD 36920 | 2026-05-01 | Notice of Exemption | 2 | [53021](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1777645804171/53021.pdf) |
| 37 | routine | FD 36929 | 2026-05-29 | Notice of Exemption | 3 | [53059](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1780065003174/53059.pdf) |
| 38 | routine | FD 36939 | 2026-06-12 | Notice of Exemption | 3 | [53089](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1781274602485/53089.pdf) |
| 39 | routine | AB 400/8/X | 2026-06-26 | Notice of Exemption | 4 | [53125](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1782484299282/53125.pdf) |
| 40 | routine | FD 36896 | 2026-07-22 | Notice of Exemption | 3 | [52851](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1784730640186/52851.pdf) |
| 41 | short | AB 290/417/X | 2025-01-23 | Decision | 2 | [52441](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1737664174603/52441.pdf) |
| 42 | short | EP 777 | 2025-01-31 | Decision | 2 | [52457](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1738353633899/52457.pdf) |
| 43 | short | FD 36629 | 2025-02-21 | Decision | 2 | [52454](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1740151804180/52454.pdf) |
| 44 | short | FD 31340/0 | 2025-03-14 | Decision | 2 | [52448](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1741962687769/52448.pdf) |
| 45 | short | AB 290/415/X | 2025-03-14 | Decision | 2 | [52498](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1741962654466/52498.pdf) |
| 46 | short | AB 167/445/N | 2025-03-19 | Decision | 2 | [52519](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1742394605231/52519.pdf) |
| 47 | short | AB 534/4/X | 2025-06-06 | Decision | 2 | [52602](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1749234219168/52602.pdf) |
| 48 | short | EP 682/16 | 2025-06-09 | Decision | 2 | [52621](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1749479404901/52621.pdf) |
| 49 | short | FD 36439 | 2025-07-14 | Decision | 2 | [52665](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1752516781472/52665.pdf) |
| 50 | short | WB 25/33 | 2025-07-22 | Decision | 2 | [52676](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1753208734200/52676.pdf) |
| 51 | short | AB 1344/0/X | 2025-10-01 | Decision | 1 | [52763](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1759329005137/52763.pdf) |
| 52 | short | FD 36849 | 2025-11-14 | Decision | 2 | [52773](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1763155477258/52773.pdf) |
| 53 | short | FD 36836 | 2025-12-18 | Decision | 1 | [52846](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1766093339182/52846.pdf) |
| 54 | short | AB 312/6/X | 2025-12-31 | Decision | 2 | [52826](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1767203424871/52826.pdf) |
| 55 | short | AB 55/819/X | 2026-01-26 | Decision | 2 | [52807](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1769459722883/52807.pdf) |
| 56 | short | AB 511/8/X | 2026-02-02 | Decision | 1 | [52910](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1770046300459/52910.pdf) |
| 57 | short | EP 751/0 | 2026-02-02 | Decision | 1 | [52915](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1770046203599/52915.pdf) |
| 58 | short | EP 290/5 | 2026-02-06 | Decision | 2 | [52918](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1770405831095/52918.pdf) |
| 59 | short | AB 1324/0/X | 2026-04-13 | Decision | 2 | [52996](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1776110733951/52996.pdf) |
| 60 | short | FD 36932 | 2026-06-10 | Decision | 2 | [53076](https://dcms-external.s3.amazonaws.com/DCMS_External_PROD/1781101904075/53076.pdf) |
