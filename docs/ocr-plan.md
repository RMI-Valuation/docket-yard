# OCR of the image-only record — plan

**Measured 2026-08-29 — read this first.** The plan below was written on the assumption
that OCR accuracy propagates into everything downstream, so the engine choice mattered and
was worth paying for. Measured against the labelled decisions, it does not. Extraction run
over Textract's OCR of a page recovers **as many citations as extraction over the
publisher's own text layer** — 91.9% of STB edges against 89.2%, and identical on courts,
captions and dated deadlines. A 10.8% character error rate costs approximately zero
citation edges, because a citation is a long, redundant, structured string that survives a
wrong character. Meanwhile the *extractor* choice moves citation recall by nearly
16 points (qwen3:14b 73.5%, Claude Sonnet 5 89.2%) on identical clean text — still five
times the spread between the best and worst OCR engines.

So the money belongs at the extraction stage and the OCR stage should be as cheap as is
adequate. The engine comparison is in `docs/research/ocr-benchmark/runs/`; the two
extraction runs either side of OCR are `claude-textlayer.json` and `claude-ocr.json` in
`docs/research/benchmark/runs/`. Both caveats stand: the sixty labelled decisions are
born-digital, so their renders are cleaner than a real scan and the figure is a lower bound
on OCR damage; and precision cannot be read until the operator has checked the sheet, since
a real citation the drafter missed scores as a false positive.

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
   Ground truth and output pass through one normaliser first — whitespace collapsed, line-end
   hyphens joined, bracket annotations unwrapped — so that no engine is scored for preserving
   or reflowing the printed lines; reading order, the table grid and false text on a graphic
   page are scored on top of it (`research/ocr-benchmark/README.md` § How a transcription is
   scored).
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

## Cost and time (measured 2026-08-29)

Per page, on the benchmark's own pages: **Textract $0.0015**, **Claude Sonnet 5 $0.0171**
(2,684 input and 605 output tokens a page, measured, not estimated), **qwen2.5vl:7b free**
at 8.2 s a page on the box. Over ~175k pages:

| stage | engine | cost |
|---|---|---|
| OCR | Textract | ~$260 |
| Extraction | Claude, batched | ~$1,075 |
| **Backfill total** | | **~$1,335** |

The shape of that table is the finding: OCR is a fifth of the bill and buys nothing more if
you spend on it, while extraction is the rest and buys 16 points of citation recall. A GPU
rental was costed and rejected — it competes only on the OCR line, where the saving is at
most ~$140 against a managed service that needs no instance, no driver and no spot
interruption handling.

**Superseded on the OCR line, 2026-09-01.** The reasoning above holds; the conclusion was
drawn before anything both adequate and free had been measured. **PaddleOCR-VL 1.6 on the
box reads better than Textract and costs nothing** — 8.8% CER against 10.8%, and on the
degraded tier 12.0% against 18.4%, within 1.5 points of Claude. At 1.3 s a page the whole
backfill is about 63 hours of box time, so the ~$260 OCR line goes to ~$0 and buys *more*
accuracy rather than less. Tesseract, the baseline nothing had until that day, sits at 13.3%
and shows Textract's margin over free software was always modest. Two caveats decide the
routing rather than the engine: Textract with TABLES still recovers 87.4% of table cells
against PaddleOCR-VL's 57.5%; and on the graphic tier PaddleOCR-VL has a rare, catastrophic
failure — **one page of nine, on which it invented 20,368 characters**, against Textract's
worst of 1,794 and Tesseract's none. It is silent on the other eight, so this is a tail to
gate behind the confidence layer rather than an inability to be routed around, and **nine
pages cannot establish how often it happens** — the frequency is what would decide between
gating and routing, and it is not measured. The full table, and how PaddleOCR-VL has to be
run to reach that speed, is in `research/ocr-benchmark/README.md` § Step 3.

The box keeps two jobs: it is free, so it is where anything gets tried first, and
qwen2.5vl:7b is a usable bulk reader (9.2% CER, better than Textract's 10.8%) **provided
graphic and tabular pages route elsewhere** — on nine graphic pages it emitted 3,920 false
characters against Claude's 6. It does not read those pages, it invents prose about them.

The operator's time remains the real cost: the ninety-page ground truth (checked
2026-08-29) and the review queue at whatever weekly budget is set.

## Decisions for the operator

1. Choose the plan (or not) — it starts with the sample, nothing is read into the store
   until step 3.
2. ~~The API candidate: measure it or local-only.~~ **Done 2026-08-29:** both measured,
   for about $5. Textract, Claude Sonnet 5 and qwen2.5vl:7b are all in the benchmark.
3. The weekly review budget (pages), which sets how fast the flagged tail clears.
4. Whether a trusted contributor may sit at the queue later (`/contribute` says nothing
   about this today; it would need a sentence).
