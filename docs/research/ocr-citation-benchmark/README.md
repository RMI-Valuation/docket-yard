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
misreads in the sample, but it would have inflated the recall a card stores. The drawn
sample is about 548 pages.
