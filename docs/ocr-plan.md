# OCR of the image-only record — plan

**Status:** chosen by the operator 2026-08-28 (decisions: measure the API candidate on the 90 sample pages; a review budget of about 50 pages a week; the contributor path designed in from the start — reviewer identity and a `/contribute` sentence ship with the queue). Step 1 (the sample) begins; nothing reads into the store before step 3. The operator's requirement, stated the same day:
*whatever engine is used, make it as accurate as possible, with a review layer.* This
document is the plan that meets it; the decision points at the end are the operator's.

## What is to be read

Measured 2026-08-27 on RMI-AI-MACHINE over the whole held record (80,271 files): 60,360 PDFs
carry a text layer; **13,604 (22.5%) are image-only** and ~330 are not PDFs. The image-only
set is almost entirely the older record (pre-2005 scans; wave 1 had 2 of 4,273). It is what
capability M3 ("OCR the pre-2000 record") names: the boundary at which search, the citation
graph and the registers all degrade. Until it is read, a 1998 decision can be viewed but not
searched, cited by text, or mined for citations.

## The discipline (the same as extraction's)

The extraction benchmark (`docs/extraction-benchmark.md`) set the rule: **nothing commits to
a model's output until it has been measured against ground truth the operator checked.** OCR
follows it step for step, and adds the review layer the operator asked for.

1. **Ground truth.** Draw a sample of image-only pages (not documents — pages are the unit
   OCR is scored on): three tiers of thirty — *clean typescript*, *degraded* (skew, faint
   toner, stamps, handwriting in margins), and *tabular* (rate tables, appendices). The
   sample is drawn by seed, recorded with why each page was drawn. The transcription is
   drafted by a model and **checked by the operator against the page image**, as
   `labels.csv` was; a page's transcription is ground truth only after that check.
2. **Candidates, measured.** Every candidate runs over the ninety pages and is scored by
   character error rate (CER) and word error rate (WER) per tier, plus the two errors that
   matter most to this record and are scored separately: **docket numbers** and **dates**
   read wrongly (a transposed digit in "FD 32760" is worse than a hundred misread commas).
   Candidates the box can run: Tesseract 5 (the baseline every study reports against);
   a document-OCR model (docTR or PaddleOCR-class); a vision-language model that fits 12 GB
   (a 7B-class VLM, quantised). An API candidate (a frontier model with vision) is measured
   on the same pages **only on the operator's go — it spends money.**
3. **Choose by the numbers**, per tier if the winner differs by tier.

## The review layer

Accuracy is not one number; it is knowing which pages are wrong. The review layer is three
things, each cheap, each recorded:

- **Agreement as confidence.** Two engines read every page. Where they agree (normalised
  text within a small edit distance), the page is *high confidence*. Where they disagree,
  a third reading breaks the tie or the page is *flagged*. The per-page confidence is
  stored with the text (ADR 0007: method, method version, timestamp, confidence).
- **The record's own checks.** A docket number read from a page must parse against the
  registry's grammar and, where the page is in a known docket, match it; a date must be a
  date the docket's timeline makes possible. A page that fails these is flagged whatever
  the engines agreed on. This is the citator's validation step, applied early.
- **The operator's queue.** Flagged pages go to a review page — image beside text, the
  disagreement highlighted — where the operator (or later a trusted contributor) accepts one
  reading or types the correction. A human correction is stored as its own method
  (`human`, with who and when), supersedes the engines' readings, and is never overwritten
  by a re-run. The queue is bounded by budget: the plan states how many flagged pages a
  week the operator will take, and the rest wait rather than publish.

What reaches a reader: only text at or above a confidence threshold the benchmark sets,
and every published passage carries its confidence and links the page image. Below the
threshold, the page is searchable by nothing and the sheet says *"scanned; not yet read"*
rather than showing text that may be wrong. The coverage page counts the three states —
read, flagged, unread — from the store.

## Shape in the store

A `document_text` table: one row per (document, page, method, method_version) with the
text, the confidence, the timestamp and, for a human row, the reviewer; a view selecting
the best row per page by the rule above. It is a derived assertion in ADR 0007's sense and
touches nothing in the event ledger. **Schema-critic reviews it before it exists.** The
search index reads the view; the citation extractor reads the view; the viewer page shows
the text beside the image with its confidence and a "report a misreading" link that lands
in the queue.

## Cost and time

The box: RTX 4070 (12 GB), 64 GB, 1.6 TB free. Tesseract over 13.6k documents (~150k pages
at ~11 pages each) is hours; a VLM at a page every few seconds is days. Two engines plus a
tie-breaker over the whole set is under a week of unattended GPU time. The operator's time
is the real cost: the ninety-page ground truth (a few hours of checking) and the review
queue at whatever weekly budget is set.

## Decisions for the operator

1. Choose the plan (or not) — it starts with the sample, nothing is read into the store
   until step 3.
2. The API candidate: measure it (spends money) or local-only.
3. The weekly review budget (pages), which sets how fast the flagged tail clears.
4. Whether a trusted contributor may sit at the queue later (`/contribute` says nothing
   about this today; it would need a sentence).
