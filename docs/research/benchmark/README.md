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

## Provenance of the labels (2026-08-26)

`labels.csv` was **drafted by a model** (Claude Fable 5, four passes over the Board's PDFs,
one per tier and half-tier, under the rules below) and is **awaiting the operator's check**.
It becomes ground truth for step 2 only after that check; rows the operator strikes or adds
are the ones worth keeping notes on. Two things to hold in view when reading it:

- The drafter is a Claude model and one of step 2's candidates is a Claude API model, so a
  label the operator did not check is a Claude-flavoured target. The check is what removes
  that.
- The drafting passes were told to be exhaustive on the heavy tier and to label every
  short-form and repeated citation on its page; they also labelled ordering-paragraph
  "effective on its service date" sentences as deadlines with a blank `target`, and the
  Board's stamp text on granted letters. Whether those conventions stand is the operator's
  call; the notes column says which rows they are.

Assembled 2026-08-26: 977 rows over the sixty decisions — 813 citations, 164 deadlines;
every row passed the page-range check. Court cases carry `court`; self-references `self`.

## How to label

One row per thing found. Copy the decision's first five columns down for each row.

| Column | Put |
|---|---|
| `kind` | `citation`, `deadline`, or `none` (one row, when a decision contains neither) |
| `page` | The 1-based page of the Board's PDF where it appears |
| `quoted` | **citation:** the citation exactly as printed (`Docket No. FD 36500`, `Union Pacific—Control—Southern Pacific, 1 S.T.B. 233 (1996)`, `Ex Parte No. 711 (Sub-No. 1)`). **deadline:** the whole sentence that sets it, as printed |
| `target` | **citation:** the docket or decision cited, as printed (the part a citator would resolve). **deadline:** the date as printed (`October 15, 2024`), never computed — a deadline expressed only as "30 days after service" is still labelled, with `target` left blank and a note |
| `note` | Anything a checker would need: a citation to a court case rather than the Board (label it, note `court`), a date that is a past event not a deadline (do not label), a self-citation to the same docket (label it, note `self`) |

What counts as a **citation**: any reference to a Board (or ICC) decision or docket other
than the caption of the decision itself — including "this proceeding" references by number,
prior decisions in the same docket, and Ex Parte rulemakings relied on. Court cases are
labelled with note `court` so the citator can decide later. What counts as a **deadline**:
a date, or a period, that the decision itself sets for someone to act by — replies due,
effective dates, comment periods, filing windows. A date recited as history is not one.

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
