# Text-layer quality — the signal, and what it measures

**The question, written before anything ran:** of the pages the site shows as *the publisher's
own text layer*, how many carry text as garbled as `/filing/18005` — and can a cheap signal
find them? The unit is a **live primary reading of one page**, which is what the display shows:
production holds no `human` rows, so `document_text_display`'s rule reduces to the live primary
(`store/display.py`). What would falsify the signal: clean pages scoring as suspect, or garbled
pages scoring clean.

Measured 2026-09-17 against production (read-only, `?mode=ro`, `nice -n 15`): 1,413,300 live
readings scored in 37 minutes; `/health` and a record page answered throughout.

## What the router does today, and what it never does

`tools/rmi-ai-machine/extract_text.py` and `infra/extract/extract.py` (ADR 0024) call a
document **image-only** when EVERY page carries under 20 stripped characters. A document that
fails that test is read from its text layer, page by page, and **nothing ever reads it again**:
the OCR wave, ADR 0024 D7's queue and the `second` readings all take image-only or blank pages.
A publisher's text layer that is old OCR over a scan — 18005's is Acrobat Paper Capture, 2007,
over a 1996 fax-grade scan — is copied through unjudged, and its page says it has no band
because it was read once (ADR 0021 D8, `store/pages.py:band`). That is the failure mode this
directory measures; it sits BEFORE the OCR pipeline, not inside it.

## The signal

`tools/rmi-ai-machine/text_quality.py`. Per page, over tokens that contain a letter:

- **`good` = `lexicon_hits / letter-bearing tokens`** — THE signal, and the only definition
  used anywhere here. The module also exposes `shares()["lex"]`, which divides by *word-shaped*
  tokens instead; that is a diagnostic, it is not `good`, and mixing the two put 0.56 beside
  0.22 for one page in an earlier draft of this document (schema-critic, 2026-09-17). The
  denominators differ by exactly the mangled share, which is largest on the worst pages.
- `mangled` — the share that are not word-shaped (letters fused with digits or symbols).
- `junk` — the share of non-space characters outside letters, digits and ordinary punctuation.
- `case` — the share of words with a lower→UPPER flip inside them (`PreseHation`).

**The lexicon is the record's own vocabulary**, not a dictionary: 23,524 words that appear in at
least 3 of the 4,192 Board decisions served 2015–2023 that carry a text layer. Built from the
store in the same pass. A general word list would miss rail and docket terms and would need a
dependency; this is reproducible from the record.

**A floor of 15 letter-bearing tokens**, and blank pages counted separately. An earlier floor of
20 *word-shaped* tokens was wrong and would have hidden the very pages it was meant to find:
18005 has 9 word-shaped tokens because nearly everything on it is fused junk.

## What it separates, on text somebody checked

`good` over the labelled sets (pages with ≥15 letter-bearing tokens):

| Set | Pages | p5 | median | <0.5 | <0.7 |
| --- | ---: | ---: | ---: | ---: | ---: |
| ground truth, clean tier | 37 | 0.86 | 0.93 | 0 | 0 |
| ground truth, degraded tier | 37 | 0.82 | 0.93 | 0 | 0 |
| ground truth, graphic tier | 9 | 0.64 | 0.78 | 0 | 3 |
| ground truth, tabular tier | 5 | 0.61 | 0.91 | 0 | 1 |
| born-digital decisions (60 decisions, 440 pages) | 440 | 0.84 | 0.94 | 1 | 10 |
| engine output, CER < 10% | 930 | 0.81 | 0.93 | 0 | 14 |
| engine output, CER 10–30% | 386 | 0.78 | 0.91 | 4 | 16 |
| engine output, CER ≥ 30% | 239 | 0.26 | 0.76 | 38 | 94 |
| **18005 page 1** | 1 | — | **0.22** | — | — |

Ground truth is `../ocr-benchmark/ground-truth` (90 pages, operator-checked 2026-08-29; no
absolute accuracy figure may be published from it). Born-digital is the extraction benchmark's
60 decisions, served 2025. Engine output is `data/ocr/runs/*` scored by the shipped
`ocr_score.py` against the same ground truth.

**CER is a blurry label for this purpose** and was not used as one: the scorer counts reordered
text as error, so engine readings at CER ≥ 30% still have a median `good` of 0.76.

## What it finds in production

Live primary readings, by channel and era (the era is the earliest year any record carrying the
document is dated). `judged` excludes blank pages and pages under the floor.

| channel | era | pages | blank | short | judged | <0.3 | <0.5 | <0.7 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| text-layer | 1996–99 | 15,811 | 764 | 478 | 14,569 | 13 | 40 | 106 |
| text-layer | 2000–04 | 34,950 | 14,894 | 536 | 19,520 | 16 | 78 | 219 |
| text-layer | 2005–09 | 186,747 | 15,211 | 14,022 | 157,514 | 3,329 | 7,235 | 14,270 |
| text-layer | 2010–14 | 215,555 | 21,909 | 14,086 | 179,560 | 4,294 | 8,109 | 16,809 |
| text-layer | 2015–19 | 298,775 | 22,095 | 15,446 | 261,234 | 2,821 | 4,957 | 10,464 |
| text-layer | 2020–26 | 333,454 | 10,351 | 24,108 | 298,995 | 5,509 | 11,379 | 23,027 |
| ocr | 1996–99 | 2,391 | 72 | 340 | 1,979 | 60 | 120 | 289 |
| ocr | 2000–04 | 141,571 | 1,132 | 8,970 | 131,469 | 771 | 2,876 | 6,022 |
| ocr | 2005–09 | 95,908 | 439 | 5,793 | 89,676 | 679 | 2,315 | 4,830 |
| ocr | 2010–14 | 13,753 | 139 | 905 | 12,709 | 84 | 278 | 530 |
| ocr | 2015–19 | 18,309 | 73 | 961 | 17,275 | 307 | 957 | 2,091 |
| ocr | 2020–26 | 697 | 3 | 40 | 654 | 1 | 10 | 27 |

**~31,800 text-layer pages score below 0.5**, and the low scores are NOT concentrated in the
scanned era: 2020–26 holds the most of them, which is the reason the sample below exists.

## The labelled sample — precision and recall

`sample.json`: 64 text-layer pages, 8 per (band × era) cell, seed 20260917, bands
`<0.3 / 0.3–0.5 / 0.5–0.7 / ≥0.7` crossed with `≤2014 / ≥2015`. Each page was labelled from the
page image beside the stored text, by four agents that were **not shown the score**.

**Three axes, not one** (the operator, 2026-09-17). The first rubric's `nontext` label meant
"not prose AND faithfully carried", which files a broken grid as a success and a garbled map as
a text failure. Split:

- **kind** — prose, table, map, drawing, form, mixed: what the page *is*.
- **quality** — clean, noisy, garbage, partial, mismatch: how well its words came through.
- **structure**, tables only — grid, ordered, scrambled, absent: whether a cell's column still
  says what the cell is. The benchmark already scores tables this way (`ocr_score.py`: CER for
  the words, cell recall for the grid), and the two come apart — qwen3-vl:32b reads the tabular
  tier at 5.6% CER with 0% cell recall.

**Checked by the operator, 2026-09-17**, every page against its scan: `labels-checked.json` is
the reference; `labels-draft.json` and `kinds-draft.json` are what the model drafted.
The drafts held up unevenly — **quality 46 of 53** (the 11 `nontext` pages had no drafted
quality to compare), **kind 59 of 64**, **structure 11 of 15**. Four of the seven quality
corrections were the draft calling a page *partial* or *noisy* where it is **garbage**
(L09, L56, L62, L63): the drafting pass was systematically kinder than the check, so the draft
figures understated the damage.

### What the record holds, by band

| band | population | n | at least noisy | garbage | garbage rate, 95% CI | pages that implies |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| <0.3 | 15,982 | 16 | 16 | 14 | 0.64–0.97 | 10,200–15,400 |
| 0.3–0.5 | 15,816 | 16 | 16 | 9 | 0.33–0.77 | 5,200–12,200 |
| 0.5–0.7 | 33,097 | 16 | 10 | 1 | 0.01–0.28 | 400–9,400 |
| ≥0.7 | 866,497 | 16 | 4 | 0 | 0.00–0.19 | 0–167,800 |

**Read the intervals, not the point estimates.** Eight pages a cell is enough to establish that
the bands differ and nowhere near enough to size the record: garbage lands somewhere between
16,000 and 205,000 pages, and *at least noisy* between 127,000 and 488,000. The ≥0.7 band's
866k pages dominate both, and 16 labelled pages cannot pin a rate there. **The ~100-page top-up
of that band is what would.**

### The signal, scored against the checked labels

| cut | flagged | precision | in the sample | recall |
| --- | ---: | ---: | ---: | ---: |
| **as a garbage detector, <0.5** | ~31,800 | **0.72** | 23/32 | **0.68** |
| as a garbage detector, <0.7 | ~64,900 | 0.38 | 24/48 | 0.75 |
| as an any-fault detector, <0.5 | ~31,800 | **1.00** | 32/32 | 0.29 |
| as an any-fault detector, <0.7 | ~64,900 | 0.80 | 42/48 | 0.47 |

**The precision column is population-weighted and the count beside it is not.** The sample takes
8 pages per cell from bands that hold 15,982 / 15,816 / 33,097 / 866,497 pages, so a raw
proportion over it is not a proportion over the record; precision here weights each band's
sampled rate by that band's size. The two agree at <0.5 (0.720 against 23/32 = 0.719) because the
two bands below it are nearly equal in size, and part company at <0.7, where the raw counts give
0.50 and 0.875 against the weighted 0.38 and 0.80. The earlier table printed the counts inside
the precision cell, which invited exactly the division that does not hold.

Every recall here is against the record-wide totals this document arrives at below — **110,539
faulty pages and 33,444 garbage pages**. An earlier draft divided by a pre-correction estimate
of ~245,000 and understated all of them (code review, 2026-09-17).

**The garbage recall was 0.92 in this document until 2026-09-17 and it was wrong**
(schema-critic). It was computed from the 64-page sample alone, whose ≥0.7 cell held 16 pages
and 0 garbage — so the cut appeared to miss nothing above it. The 102-page top-up found
**1 garbage page in 102** up there, which stands for roughly 8,500 pages, and recall falls to
0.68. The lesson is the sample's, not the signal's: a rate for a band of 866,497 pages may not
be read off 16 of them, in either direction.

**This is the result that matters: below 0.5 the signal is a fair detector of the 18005 failure
and a poor detector of everything else.** Roughly two garbage pages in three fall below 0.5, and
every one of the 32 pages it flagged there has something wrong with it — but *noisy* text sits
at every score, so **71% of faulty pages are not flagged at all**. The signal is a re-read queue, never
a coverage statement.

### What the flagged pages are

Of the 32 labelled pages below 0.5: **11 maps, 7 mixed, 5 prose, 5 tables, 2 forms,
2 drawings.** Two thirds are pages whose text is mostly labels on a picture, where OCR recovers
little (the benchmark's PP-OCRv6 gets 47% of map labels while inventing nothing). Quality by
kind, over all 64:

| kind | n | clean | noisy | partial | garbage |
| --- | ---: | ---: | ---: | ---: | ---: |
| prose | 19 | 9 | 7 | 0 | 3 |
| table | 15 | 7 | 4 | 0 | 4 |
| map | 16 | 1 | 3 | 5 | 7 |
| mixed | 9 | 1 | 1 | 0 | 7 |
| form | 3 | 0 | 1 | 1 | 1 |
| drawing | 2 | 0 | 0 | 0 | 2 |

**A prose page's text layer is usually adequate; a map's almost never is.** That is the
argument for reading prose first, and it is now measured rather than assumed.

### The top-up: what the pages ABOVE 0.7 hold

The band the first sample could not size — 866,497 pages, 16 labelled — was sampled again on
2026-09-17: **102 pages** (`topup-sample.json`), allocated roughly in proportion to the
sub-bands `0.7-0.8 / 0.8-0.9 / 0.9+` crossed with era, floor of 10 a cell, seed 20260917917.
Each page was labelled **twice, by independent blind agents** (`topup-labels-blind.json`);
the two passes agreed on 97 of 102 pages, 95 of them exactly.

**Then the operator checked 31 of them** (`topup-labels-checked.json`): all 7 pages the two
passes labelled differently, plus 24 they agreed on, drawn at random across the bands. That
check is the reason the figures below are not the blind passes' own:

| what the two blind passes said | pages he checked | he called faulty | his rate |
| --- | ---: | ---: | ---: |
| both clean | 13 | 0 | 0.00 (0.00-0.23) |
| both faulty | 13 | 5 | **0.38** (0.18-0.64) |
| they split | 5 | 0 | 0.00 (0.00-0.43) |

**The blind readers over-call faults by about two and a half times, and miss none.** He
overruled *both* passes on eight pages — T017, T028, T053, T055, T059, T061, T083, T095 — all
of them `noisy` to the readers and `clean` to him: a handful of substitutions in a long page,
a signature name lost, a party name misread, a table whose values are all present. Nothing the
readers called clean turned out faulty, so the drafting bias runs one way only. This is the
second time in this work a model pass has been miscalibrated against the operator, in the
opposite direction to the first (the 64-page pass was too kind; these two are too harsh), and
it is the reason no rate here is published from model labels alone.

Correcting each band by the class rates above (a two-phase estimate: class shares from all 102
pages, his faulty rate within each class):

| sub-band | population | classes (clean / faulty / split) | faulty rate | faulty pages |
| --- | ---: | --- | ---: | --- |
| 0.7-0.8 | 47,599 | 5 / 15 / 0 | 0.29 | 13,700 (6,300-25,700) |
| 0.8-0.9 | 185,465 | 14 / 6 / 1 | 0.11 | 20,400 (9,400-66,200) |
| 0.9+ | 633,433 | 51 / 6 / 4 | 0.04 | 24,000 (11,000-179,000) |
| **whole band** | **866,497** | | **0.07** | **58,000 (27,000-271,000)** |

Uncorrected, the blind passes alone would have said 201,000. **The check removed three
quarters of that.**

### The record-wide figure

Combining the operator's own labels below 0.7 with the corrected estimate above:

| band | population | faulty rate | faulty pages (95% CI) |
| --- | ---: | ---: | --- |
| <0.3 | 15,982 | 1.00 | 15,982 (12,888-15,982) |
| 0.3-0.5 | 15,816 | 1.00 | 15,816 (12,754-15,816) |
| 0.5-0.7 | 33,097 | 0.62 | 20,686 (12,789-26,980) |
| >=0.7 | 866,497 | 0.07 | 58,055 (26,861-271,214) |
| **all judged text-layer pages** | **931,392** | **0.12** | **110,500 (65,300-330,000)** |

**About one text-layer page in eight is faulty, and 29% of those are in the 3.4% of pages the
signal flags below 0.5.** Garbage specifically is ~33,400 pages, of which ~22,900 are below 0.5
and ~8,500 sit above 0.7, where the top-up found one garbage page in 102 — that band is so large
that one labelled page stands for thousands. The interval is
still wide, and its width now comes from the 0.9+ band's size, not from the signal.

### Two findings the score could not have produced

**No table page keeps its grid — not one.** Of 20 table and mixed pages carrying a structure
verdict: 5 `ordered`, 9 `scrambled`, 7 `absent`, **0 `grid`**. Seven of those pages have
*clean* words. So a table's text layer is reliably usable for search and quotation and
reliably useless for reading a row, whatever its score — which is an argument about the tabular
pass, not about the re-read.

**Nine of the 64 pages must be rotated before anything reads them**, six of them in the <0.3
band. `ocr_wave.py` constructs PP-OCRv6 with `use_doc_orientation_classify=False` and
`use_textline_orientation=False` (lines 466–468), so the wave reads a sideways page sideways.
The benchmark's `ppocr-pre` run measured those toggles as *worse* overall (12.3% CER against
11.8%) — but it measured them on the 90 image-only pages, where rotation is rarer than in this
text-layer sample. **Re-reading a rotated page without fixing orientation first spends the
machine time and gets garbage twice.**

## What the signal cannot do

- **It does not see invention.** On 18005 a local `deepseek-ocr` reading wrote fluent sentences
  that are not on the page ("walking trails along the same road", "Department of
  Transportation", ZIP `20243`) and scored `good` 0.96 — beside `qwen3-vl`'s honest reading at
  0.97. Only a second reading and a distance catch that (ADR 0021 D8).
- **It is weak on engine readings** generally: against the wave's measured `agreement_distance`
  on 55,356 degraded-tier primaries, AUC is 0.59. It is a text-layer instrument.
- **`noisy` is invisible to it**, per the recall finding above.

## 18005, read four ways

Local runs 2026-09-17 (RTX 5080 workstation; `qwen3-vl` also on the 3090 at `home-ws-crr-25`),
scored with `ocr_score.py` against a **model transcription of the scan that nobody has checked**
— so this ranks readings, it does not measure accuracy:

| reading | CER | `good` | key phrases (of 12) |
| --- | ---: | ---: | ---: |
| stored text layer (pymupdf 1.28.2 over the 2007 layer) | 0.85 | **0.22** | 0 |
| RapidOCR (PP-OCR ONNX), 200 DPI | 0.36 | 0.32 | 6 |
| deepseek-ocr, 200 DPI | 0.21 | 0.92 | 10 |
| qwen3-vl:8b-instruct, 200 DPI (3090) | 0.08 | 0.93 | 12 |
| qwen3-vl:32b-instruct, 200 DPI (3090) | 0.11 | 0.93 | 12 |

PP-OCR's detector drops the right half of every body line where the speckle is densest;
despeckling first made it worse. **One page chooses no engine**, which is why the two qwen3-vl
models were then run over the benchmark's 90 pages.

## qwen3-vl on the 90 ground-truth pages (2026-09-17, the 3090)

Run with the shipped `ocr_run.py --engine vlm` against Ollama on `home-ws-crr-25`, scored by
`ocr_score.py`; full figures in `data/ocr/runs/qwen3-vl-{8b,32b}-instruct.json`. Against the
wave's chosen engine and the frontier reference:

| engine | CER | clean | degraded | tabular | docket recall | false chars on maps | s/page |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| claude-sonnet-5 (reference, not a candidate) | 6.6% | 1.8% | 11.9% | 5.4% | 100% | 15 | — |
| **qwen3-vl:32b-instruct** | **7.0%** | **1.5%** | 13.1% | 5.6% | 91.2% | **3,187** | 20.6 |
| dots.mocr (the wave's primary) | 8.2% | 3.3% | **12.7%** | 13.4% | **100%** | **0** | ~2.7 |
| qwen3-vl:8b-instruct | 9.5% | 2.2% | 17.2% | 10.8% | 88.2% | 2,880 | 6.3 |

**The wave's pipeline stands.** 32B reads clean prose better than anything measured here
except a frontier model, and reads tables far better than dots.mocr — but it is WORSE on the
degraded tier that the suspect pages mostly are, it misses one docket number in eleven where
dots.mocr misses none (ADR 0018's edges are built from those numbers), and it writes 3,187
characters of invented text across the nine map pages where dots.mocr and PP-OCR write none.
Invention on cut lines is 8, level with dots.mocr's 7 and claude's 8.

At 20.6 s a page it is also ~182 hours for the ~31,800 flagged pages, against roughly a day
for dots.mocr. **What 32B is a candidate for** is a later pass over the prose-and-table subset,
with a cheap second reading beside it for the distance — not for the re-read decided here.

## The flagged set's own kinds — drawn 2026-09-19, labels not yet in

The order the re-read runs in is prose first (the operator's), and `text_quality.looks_like_prose`
is what obeys it. Its precision and recall rest on **five pages**: of the 166 labelled here only
32 sit below the 0.5 cut and only 5 of those are prose (`docs/deferred.md`, 2026-09-18). A rate
off five pages is not a rate, so the screen is measured on the population it actually sorts.

`kinds-flagged-sample.json`, drawn by `tools/rmi-ai-machine/kinds_flagged_sample.py`: 40 pages
from the flagged set itself — a live **primary** reading of the publisher's own **text layer**
scoring under 0.5 over the 15-token floor, 31,798 pages, 31,766 of them not already labelled
here. **Stratified on the screen's own verdict**, 20 it calls prose and 20 it does not, which is
what makes 40 labels enough for both figures: precision reads off the first stratum, recall needs
the weights the file records (4.1 and 15.9), since a page in the second stratum stands for far
more of the record than one in the first. Pool 400, seeds 20260919 / 2026091920.

The check sheet is `tools/rmi-ai-machine/kinds_check_sheet.py`: each page rendered whole at 150
DPI grey from the blob mirror, beside the text `document_text_display` serves for it, and one
question — what is this page? **Nothing is drafted on it and the score, the screen's verdict and
the layout features the screen reads are all absent** (`SHOWN` is the whitelist that keeps them
out): a reader who can see the screen's answer is not measuring it, and model labels are a
screen, never a measurement. The kinds are the operator's; scoring joins them back by `label_id`.

## Reproducing

The pass is scratch code, kept out of the repo except the feature module
(`tools/rmi-ai-machine/text_quality.py`). It builds the lexicon from the store, then writes one
row per live reading; the analysis is over that file. Production is read-only throughout:
`sqlite3.connect("file:...?mode=ro", uri=True)`, `sudo nice -n 15`, every ssh with `</dev/null`
and a remote `timeout`.

## The rotation probe (2026-09-17), and what it settles

The operator marked 9 of the 64 pages "rotate before OCR" and chose to measure orientation
before any re-read. Three things came out of it; `rotation-probe.json` holds the numbers.

**The metadata is no use.** All 9 carry `/Rotate = 0` and a PORTRAIT page box: the scan itself
is sideways and the PDF says nothing. Eight *other* pages in the 64 do declare a rotation, and
pymupdf honours those, so the declared ones already render upright. Only content can find the
rest.

**The signal cannot pick the rotation.** Each of the 9 was rendered at 200 DPI, turned 0/90/180/
270, read with PP-OCR and scored: the spread between the best and worst rotation is a few
hundredths (L01 0.465–0.512, L08 0.652–0.812), the best rotation lands on all four values across
the 9 pages, and the token counts barely move. "Render four ways and keep the best score" is not
a detector. **Caveat that bounds this**: the signal is weakest on exactly these pages — 8 of the
9 are maps, tables or drawings, whose labels are not lexicon words — so this rules the method
out rather than ruling rotation harmless.

**A vision model reads them without being told.** qwen3-vl:8b-instruct on L01 and L31 recovered
the headers at 0° as well as at 90°/270° (L01: *"Sikeston Subdivision - Essex to Miner"*), and
its 90° reading of L01 produced the column headers the 0° reading missed. It also invented at
90° on L31 — a preservation temperature and a molarity that are not on the page — which is the
same failure the benchmark measures on maps. **The wave's degraded-tier primary, dots.mocr, is
itself a VL model**, so the orientation question is narrower than it looked: it bears on
PP-OCRv6, which reads the clean and graphic tiers, and not on the reader that would take a
rotated scan.

**What it means for the re-read.** Not one of the 9 rotated pages is prose. Under the decided
order — prose first — they sit at the back of the queue, so **rotation does not block the
re-read starting**. What is still owed before the graphic and tabular pages are read: PP-OCRv6
with `use_doc_orientation_classify` on against off, over rotated pages specifically, scored
against pages somebody has checked rather than against this signal.
