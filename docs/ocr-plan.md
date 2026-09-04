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

## Decided by the operator, 2026-09-02

Four answers that shape everything below, taken after the census, the agreement measurement
(`research/ocr-benchmark/README.md` § Step 6) and a four-lens review of the draft records.

1. **The text is a finding aid, always shown.** Every read page displays its text, labelled
   machine-read, with the engine and version, a confidence band and a link to the agency's
   scan; search covers all of it. Nothing is withheld for being imperfect. **But no derived
   assertion is published from it until its class is measured** — ADR 0017 D3 unchanged. The
   scan being one click away is what makes the first half honest, and the split between
   showing and asserting is what keeps the second half safe. ADR 0021 D7.
2. **A second reading is bought, and escalation is not automatic.** The second reader is the
   cheapest non-family engine — about +23% on the backfill, not the doubling assumed here
   earlier — which buys the per-page confidence signal § Step 6 measures at AUC 0.93–0.97.
   Claude Sonnet 5 sits above it as a third reader on disagreement, **run by the operator as
   a batch, never as a standing stage**: roughly $210 at a wide bar, $840 at a narrow one. It
   is a CLI verb on the box, recorded as a pass with its own method and version — no standing
   spend and no authenticated surface added to the reader-facing process.
3. **Maps are read last; tables are not in this pass, and not abandoned either.** The order
   is clean, then degraded, then maps — **prose before pictures**, so the 86% of pages that
   carry the record's words land first and the tier with the least certain payoff waits until
   the pipeline has been proven on the easy 53%. Maps are worth reading at all because
   PP-OCRv6 gets 47% of their labels while inventing nothing on all nine graphic pages: a
   detector-plus-recogniser cannot write a sentence that is not on the page, so its worst
   case is silence.

   **Tables wait for their own pass**, not for the end of this one. Five pages decide
   nothing, no free engine detects an unruled columnar list, and the one that closes the gap
   carries a licence the CC0 dump cannot absorb — so deferring the tier defers that decision
   with it. Until then a tabular page is marked *scanned; contains a table we have not read*,
   with its image linked, which is an honest statement rather than an absence.
4. **The grain ships before the review layer.** ADR 0021 decides what a stored reading is;
   Migration B redesigns ranking and the queue against the flag rate § Step 6 measured. See
   `ocr-migration.md`.

**Decided 2026-09-04, and the wave started the same day** (`tools/rmi-ai-machine/ocr_wave.py`,
whose docstring is the runbook):

5. **200 DPI for the degraded tier** — dots.mocr's measured optimum, 0.6pp on the tier that
   hurts for about 40 more hours of box time. The clean tier stays at 150.
6. **HunyuanOCR-1.5 reads the tabular tier, and tabular is read last**, its own pass after
   this wave. The licence question is answered by ADR 0022 D3: `document_text` is held from
   the CC0 dump, so nothing it reads is published under the dedication.
7. **The clean/degraded split is provisional and says so.** The router's fixed rule folds
   them; the one free signal that splits them (region count, AUC 0.843 on the 90 pages)
   cannot be confirmed without the unseen sample the top-up would provide. Rather than read
   every text page with dots.mocr (three weeks) or wait, the wave routes a text page with
   more than 13 regions — the midpoint of the two measured medians, 8.5 and 18.0 — to
   degraded, and every row records the router as `pp-doclayoutv3+regions` at
   `provisional-1`, so a confirmed rule supersedes it by re-reading (ADR 0021 D4). The
   region count is written to every route file for the day the sample exists.
8. **What each class gets.** Clean: PP-OCRv6 primary, read once, no band. Degraded:
   dots.mocr primary at 200 DPI and PP-OCRv6 second at 150 with the distance, so the band
   is bought where the errors are. Graphic: PP-OCRv6 primary, in the last pass. Unrouted (the
   router found nothing): PP-OCRv6, because the blank call is unsafe. Tabular: not in this
   wave; the page shows "not yet read" until the HunyuanOCR pass.

## What is to be read

Measured 2026-08-27 on RMI-AI-MACHINE over the whole held record (80,271 files): 60,360 PDFs
carry a text layer; **13,604 (22.5%) are image-only** and ~330 are not PDFs.

**Superseded by a census of the extraction output, 2026-09-02** —
`tools/rmi-ai-machine/text_layer_census.py` over `/data/docketyard/text`, which reads the
header of every extraction JSON. The three figures above are one *run's* manifest, and that
run skipped 13,936 files as already extracted, so its counts are a subset:

| | documents | pages | characters | per page |
| --- | --- | --- | --- | --- |
| image-only | **15,085** (plus one 0-page PDF) | **247,923** | ~0 | — |
| text layer | **59,210** | **857,012** | 1,369,267,089 | **1,598** |

- **The image-only page count is 247,923, not ~175,000** — 42% higher, and it is the number
  every cost in this document is multiplied by. At the routed 2.71 s a page the backfill is
  about **187 hours**, not 132; `research/ocr-benchmark/README.md` § Step 5's "132 to 172
  hours over 175,000 pages" scales the same way, to about 187–244.
- **15,085 image-only documents**, which is exactly what the benchmark README recorded on
  2026-08-28 and which the 13,604 above never contradicted — it counted one run.
- **~5,975 files are not PDFs, not ~330.** 74,296 of the 80,271 held files have extraction
  output; the remainder were seen and skipped as non-PDF.
- The 22.5% is 13,604 over 60,360, which is that run's image-only share of the PDFs it
  extracted. Against the corpus the share is **20.3%** (15,085 of 74,296 PDFs).
- Both page counts are lower bounds for what needs OCR: `image_only` is a *document*-level
  flag, so image pages inside an otherwise text-layer document are counted on the text-layer
  side and read as blank.

The image-only set is almost entirely the older record (pre-2005 scans; wave 1 had 2 of
4,273). It is what capability M3 ("OCR the pre-2000 record") names: the boundary at which
search, the citation graph and the registers all degrade. Until it is read, a 1998 decision
can be viewed but not searched, cited by text, or mined for citations.

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
  (`human`, with who and when), and is never overwritten by a re-run.
  **The last sentence of this paragraph is superseded, 2026-09-02.** It read: *"The queue is
  bounded by budget: the plan states how many flagged pages a week the operator will take,
  and the rest wait rather than publish."* § Step 6 measured the flag rate at 20–60%, which
  is 19 to 58 years of a fifty-page week, so a queue that waits is a queue that never ends
  and a record that never publishes. **The queue ranks rather than clears**: the worst pages
  are reviewed for as long as it is worth doing, and everything else publishes labelled under
  decision 1 above.

What reaches a reader — **revised 2026-09-02 by decision 1 above**, which replaces the
threshold this paragraph originally described. Every read page shows its text with its
confidence band and a link to the scan; there is no display bar, because a bar would need a
threshold no measurement supports and would hide the pre-2005 record from search, which is
the boundary this work exists to cross. What the threshold still governs is *assertion*: an
unmeasured reading feeds no published edge, no party attribution and no alert. The coverage
page counts read, flagged and unread from the store, in words that distinguish machine-read
from published.

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
drawn before anything both adequate and free had been measured. Thirteen runs later, **three
free local engines beat Textract outright and the ~$260 OCR line goes to ~$0 while buying
MORE accuracy**. Tesseract, the baseline nothing had until that day, sits at 13.3% and shows
Textract's margin over free software was always modest.

**dots.mocr is the engine to build on**: 8.2% CER against Textract's 10.8%, 12.7% on the
degraded tier against 18.4%, MIT-licensed, no invented text on any graphic page, and **every
docket number on all 90 pages at 100% recall and precision** — which only Claude also
manages, at $0.0171 a page. PaddleOCR-VL 1.6 is faster (1.3 s) at 8.8%, so a 175k-page
backfill is about 63 hours of box time.

**No single engine wins, and that is the finding.** PP-OCRv6 medium reads 47.2% of map
labels while inventing nothing, where every VL model is blind to a map; on tables only
HunyuanOCR-1.5 (86.2%) and Textract (87.4%) detect all five, because the VL layout models
will not call an unruled columnar list a table and agency filings are full of them. So the
plan's OCR step becomes a routed one. **The router was measured 2026-09-02** and is cheap
enough to be free — PP-DocLayoutV3 at 0.05 s a page, an eighth of the read it chooses — but it
is not settled: it is safe on the graphic call, unsafe on the blank one, and the split that
carries 86% of the pages is one it was assumed unable to make and partly can (AUC 0.843,
unconfirmed). See `research/ocr-benchmark/README.md` § What the measurements route to and
§ Step 4, which also record why a column-count rule fitted to this sample was refused.

**Preprocessing was measured 2026-09-02 and the plan should not add a stage for it**
(§ Step 5). Greyscale is a no-op because 86 of the 90 pages are already monochrome; 300 DPI
is a wash for PP-OCRv6 at twice the time and OOMs dots.mocr on the 12 GB card; binarise and
denoise lose outright, and deskew is a small loss once it is measured with an estimator that
actually deskews. Crop-to-content improves CER — dots.mocr 8.2% to 7.9% — and is **not**
carried forward, because it is also the only variant that raises both invention measures: it
finishes `[cut]` lines and asserts text on a graphic page, since cropping removes the margin
that tells a model where the scan ends. Masking the non-prose regions in place has the same
motive without that cost and gives dots its best clean tier (2.6%), but it loses five dates to
whited-out stamps; it is a re-ask for the second sample, not a decision.

**Resolution is the one live choice, and it is per engine.** PP-OCRv6 is flat from 150 to 300,
so the clean tier stays at the cheapest render. dots.mocr peaks at **200 DPI** — degraded
12.7% to 12.1%, all 34 dockets held, nothing invented — where 250 overshoots and 300 exhausts
the 12 GB card. Through the router's tier shares that takes the pipeline from 2.71 s to 3.54 s
a page, about 132 hours to 172 hours over 175,000 pages of box time nobody pays for. **The
operator's call, not a measurement.**

**One engine carries a licence the record cannot absorb.** HunyuanOCR-1.5 is the only free
engine that closes the table gap, but the Tencent Hunyuan Community License excludes the EU,
UK and South Korea from its grant and forbids using outputs to improve any AI model — which
cannot be reconciled with publishing them in a CC0 dump. Measured, not adopted; the decision
is the operator's.

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
