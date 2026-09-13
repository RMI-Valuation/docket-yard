# OCR citation benchmark — measuring the citator on the OCR channel

The citator's text-layer card (`docs/research/benchmark/`, sixty born-digital decisions) says
nothing about what the same finder does on OCR text, and ADR 0017 D3 keeps a class nobody
has scored `unmeasured`: `citator load` refuses the OCR walk (`Unscored`) until a card for
the `ocr` channel is declared. This directory is that measurement.

`docs/extraction-benchmark.md` § "OCR costs the citator nothing measurable" is not it. That
ran Textract over renders of the sixty born-digital PDFs, a lower bound, and it predates the
record's own OCR (dots.mocr and PP-OCRv6 medium).

## The population, measured 2026-09-13

With the shipped finder 2026-09-12 (v2026.09.18), `citator find --channel ocr` on
production read **1,022 decision documents** (7,430 pages) and emitted **509 citations and
1,111 captions**. Only one of the documents also carries text-layer pages.

| Engine of the page, era of the decision | Citations | Resolved | Unresolved | Documents |
|---|---|---|---|---|
| PP-OCRv6 medium, 2006 on | 305 | 282 | 22 (+1 repaired) | 150 |
| dots.mocr, 2006 on | 159 | 153 | 6 | 139 |
| either engine, 1996–2005 | 45 | 22 | 23 | 25 |

The resolution column is the shipped `resolve.resolve` over each citation's quoted passage.
The 509 citations sit in 278 documents; 744 documents have none, and no document holds more
than 13. The engine is the page's (`document_text.text_id` of the finding's page); a
document may mix both engines.

## Decided 2026-09-13 (the operator)

**The instrument is a labelled document sample, not a judgement of what the finder emitted.**
A card needs a truth count (`scorecard.read`; recall is found over truth), and only
documents labelled from their scans can see a citation the OCR destroyed. Judging emitted
citations would give a precision with no recall and would have needed a card-format change.
So, as with the sixty: a model drafts every citation and caption from each document's scan,
the operator checks the draft against the scan, and `citation_dryrun.py` runs the shipped
finder over the same documents' OCR text to build a three-stage card for `ocr`.

**The sample is about a hundred documents in four strata**, drawn with a fixed seed:

| Stratum | Documents |
|---|---|
| PP-OCRv6 medium pages, served 2006 on, with a citation found | 30 |
| dots.mocr pages, served 2006 on, with a citation found | 25 |
| served before 2006, with a citation found | all 25 |
| no citation found | 20 |

The fourth stratum is what measures recall against the OCR itself. A document whose pages
are mixed is stratified by the engine of most of its citation pages, a tie going to
PP-OCRv6.

**Long documents are labelled on a page sample (decided 2026-09-13, the operator).** A trial
draw came to 3,219 pages, 2,945 of them in the 23 pre-2006 documents: ten Environmental
Review volumes of 173–426 pages carrying one to three citations each, and a 284-page
volume carried by 38 decisions. Those 2,945 pages hold a citation on 40. So a document of
more than twenty pages is labelled on **twenty of its pages drawn at random** (seeded per
document), and the truth and the dry run are both restricted to the drawn pages, in every
stratum alike. Choosing the pages where a citation was found would have kept the likeliest
misreads in the sample, but it would have inflated the recall a card stores.

**The draw** (`tools/rmi-ai-machine/ocr_citation_sample.py`, seed 20260913, run against
production's findings and store; `sample.json` beside this file):

| Stratum | Pool | Drawn | Pages to label | Citations found on them |
|---|---|---|---|---|
| PP-OCRv6 medium, 2006 on | 146 | 30 | 170 | 77 |
| dots.mocr, 2006 on | 109 | 25 | 50 | 27 |
| pre-2006 | 23 | 23 | 274 | 15 (of 45 in the whole documents) |
| no citation found | 744 | 20 | 54 | 0 |
| **All** | | **98** | **548** | **119** |

**Two findings from the drafts, and what the operator decided (2026-09-13).** The ten drafts
hold 813 rows. Of the 157 `stb` citations whose target is a docket, **28** quote the docket in
the abbreviated form the finder reads (`FD 36500`, `AB-55 (Sub-No. 595X)`), **28** quote it
only in a long form (`Finance Docket No. 32760`, `Ex Parte No. 711`), and **101** quote no
docket at all: the drafter supplied the target from context (a prior decision in the
document's own docket named by date) or from its own knowledge (`UP/SP` as `FD 32760`). The
sixty's checked sheet, split the same way, is 403, 0 and 7.

- **The truth is the rows whose page PRINTS a docket number**, in either form. The supplied
  targets stay in the labels but outside the card's docket-shaped truth, which is what the
  sixty's truth was in effect, and a docket number taken from a drafter's knowledge is not
  something the page says.
- **The shipped finder cannot read the long forms, and that is closed before the OCR card.**
  `find.find` (finder 2026-09-12) emits nothing for `STB Finance Docket No. 34002`,
  `Finance Docket No. 32760 (Sub-No. 46)`, `Ex Parte No. 711` or `ICC Finance Docket No.
  30000`. Measured on the text layer the citator already walks (134,723 pages): **6,028
  (page, docket) long-form mentions of another proceeding the registry holds are not emitted**
  (4,078 in decisions served 1996–2005, 1,864 in 2006–2019, 86 from 2020), with 121 more naming
  a docket it does not hold, and 21,128 naming the document's own family, which lose nothing
  (counted by family, not by the finder's `kind`: an own-family mention near `Decision No.`
  reads as a citation and is suppressed at projection). Sub-numbers were not parsed, so a sibling sub-docket counted as own and the
  loss is under-counted. An OCR card measured with this finder would record its grammar, not
  the OCR, so a finder version reading `Finance Docket No.` and `Ex Parte No.` comes first,
  with its own checked sample (the sixty print no long form) and a text-layer re-load.

**The labels are drafted by subagents and checked by the operator (decided 2026-09-13).** The
548 labelled pages are rendered from the Board's PDFs; about ten subagents, some fifty-five
pages each, draft every citation and caption from the page images in the sixty's
conventions (`../benchmark/README.md` § How to label, citations and captions only); the
operator checks the draft on a page that shows the scan beside it, with the finder's OCR
reading highlighted so a miss is visible. A draft nobody checked is a Claude-flavoured target,
as the sixty's was, and the check is what removes that.

The pre-2006 pool is 23, not the 25 an earlier count gave: that count added the engine
tables' document sets together, and a document mixing engines sat in two. The truth will be
the 119 plus whatever the finder missed on the same pages, well short of the text layer's
225, so every figure the card carries is wider than that one's.
