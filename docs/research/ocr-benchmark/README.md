# OCR benchmark — step 1, the ground truth

Plan: [`docs/ocr-plan.md`](../../ocr-plan.md) (chosen 2026-08-28). This directory holds
what step 1 produced and what the operator checks.

## The sample

Drawn 2026-08-28 by `tools/rmi-ai-machine/ocr_sample.py` (seed 20260828) on RMI-AI-MACHINE
from the **15,085 image-only PDFs** the text layer found (of 80,271 files pulled from the
store), stratified by era — the record begins in 1996, so the eras are 1996–1999 (only 22
image-only documents carry a record date in that span), 2000–2005 (10,998) and 2006 on
(4,065) — fifty documents per era, **any page of each document**, not only the first, so
that bodies, tables and exhibits appear as they do in the record. 122 pages were rendered
at 150 dpi; `sample.json` records each with its docket, record, date, type, era and why it
was drawn.

## The tiers

The plan's tiers were assigned by looking at every rendered page (contact sheets, 2026-08-28,
by the drafting model — the operator's check of the transcriptions is also a check of these):

| Tier | In the 122 | Selected | What it holds |
| --- | --- | --- | --- |
| clean | 65 | 38 | Typescript or laser print, level, good contrast |
| degraded | 40 | 37 | Fax headers, RECEIVED stamps over text, faint or skewed copies, dense small print, two handwritten letters, a photocopied form |
| tabular | 5 | 5 | Pages carrying a true grid: the rotated dwell-time table, an environmental criteria matrix, an errata table, a rate-case corrections list, the FMCSA carrier detail panels — 12 grids in all, plus the station, bridge and connections tables drawn on two of the maps |
| graphic | 11 | 9 | Maps and exhibits with labels only — kept to measure *false text*, which the plan did not foresee |
| blank | 1 | 1 | A near-blank scan |

The tabular tier shrank from seven to five when the grid test was applied (below): a web
comment form and a printed e-mail are label/value blocks, not grids. Five of ninety makes
the **targeted top-up of tabular pages** the most useful step-1 follow-up — the plan asked
for thirty, and a random draw of pages will not find them.

**The tier is an assertion too, and it is the one most likely to be wrong**, because it was
assigned from contact-sheet thumbnails. The check page carries a Tier row so a mis-tier is
one click, reported separately from a transcription fix. First correction, by the operator
2026-08-29: `471668e9328e_p7` (AB 167 (Sub-No. 1094A)) was drawn as *graphic* and is clean
typescript — the scan's heavy black edges dominated the thumbnail. A cross-check of every
tier against the drafter's own `[graphic page]` / `[blank page]` marker — which it wrote
from the full-resolution page, independently of the tiering — found no other disagreement;
clean-versus-degraded and a missed table cannot be cross-checked that way and rest on the
operator's eye.

Tables are scarce in a random draw of pages (7 of 122). The plan asked for thirty; the
seven are kept and a **targeted top-up** of tabular pages is a step-1 follow-up, not a
reason to hold the rest.

## The transcriptions — checked, and now ground truth

`ground-truth/<png>.txt` — one file per selected page, **90 files, 137,096 characters**,
drafted 2026-08-28 by a model (Claude Fable 5, one pass per page, one agent per page) from
the rendered page image. Density by tier: clean ~1,370 characters a page with 4 `[illegible]`
marks in all; degraded ~1,890 with 72; tabular ~1,130 with 1; graphic ~1,130 with 15; the
blank page is `[blank page]`.
**Checked by the operator 2026-08-29**, every page against its scan, and accepted: one
correction was found — a table wrongly marked on FD 34890 — and it had already been fixed
during the pass. The directory is `ground-truth/`, no longer a draft.

**How it was checked, because it bounds what may be claimed.** The pass was made at reading
speed, comparing each transcription against its page, rather than word by word. That is
sound for what the benchmark decides and it is why the check was possible at all; but it
puts a floor under character error rate, since an engine's residual error at a few tenths of
a percent cannot be told apart from the reference's own. So:

- **ranking the candidates is unaffected** — every engine is measured against the same
  reference, and the comparison is what chooses one;
- **docket numbers, dates, false text on a graphic or blank page, and the table grids** are
  scored separately, are few per page, and survive a reading-speed check;
- **no absolute accuracy figure may be published** from this reference — "99.4% character
  accuracy" would assert a precision the ground truth does not have. A second independent
  transcription pass, with the operator arbitrating only where the two disagree, is what
  would earn one, and is not needed to run step 2.

Rules the drafter followed, which the checker applied too:

- verbatim — spelling, capitals, punctuation, numbers, one printed line per line, a blank
  line between paragraphs; nothing corrected, expanded or summarised; docket numbers and
  dates character-exact;
- **a table is a grid**, and the test is whether a cell's *column* tells you what the cell
  means: flatten the rows into prose, and if you lose which value belongs to which column,
  it is a table. A **label/value block** — an e-mail's To/cc/bcc/Subject, a fax cover's
  Deliver to/From/Date, a letterhead, `US DOT: 982739  Docket Number: MC415708`, a
  signature block, an address — carries its label on the same line as its value, so the
  column adds nothing and it is transcribed as ordinary lines. The distinction matters
  because reading alignment as a grid *invents* relationships: on FD 34890 a first pass
  paired the sender's name with `To` and the timestamp with `cc` purely because they sat at
  the same height on the page (caught by the operator 2026-08-29). One page may hold both:
  the FMCSA carrier detail has real grids for authority and insurance and label/value lines
  for the carrier's own particulars;
- **tables** are wrapped in `[table]` … `[end table]`, one row per line, cells separated by
  a **real tab character** (never the two characters `	` — one draft wrote the escape,
  caught 2026-08-29). Every row inside a block carries the **same number of cells**, padded
  with empty ones, so the grid is unambiguous: a header spanning several columns keeps its
  text in the first and leaves the rest empty. A page holding several grids — a form of
  stacked panels, like the FMCSA carrier detail in the sample — gets a block each, which is
  what tells a reader that the differing widths are separate tables rather than a ragged
  one. A cell whose text wraps in the original is joined with a single space, as running
  prose is;
- `[illegible]` for a word, `[illegible: N words]` for a run — never a guessed docket
  number or date;
- **a fragment of another page** caught in the scan — a facing page whose margin the
  scanner captured, cut off at the edge — is transcribed verbatim inside
  `[adjacent page]` … `[end adjacent page]`, with `[cut]` where each line runs off the
  edge. `[cut]` is a different fact from `[illegible]`: the text is not unreadable, it is
  *not on this page*. **A cut line is never completed**, however obvious the ending;
  `[cut]` also marks this page's own text where the scan lost it at an edge or a tear;
- a **tab means a cell**, so tabs appear only inside a `[table]` block; indentation
  elsewhere is spaces;
- stamps, seals, handwriting, signatures in square brackets with a label
  (`[stamp: RECEIVED AUG 17 2004 OFFICE OF PROCEEDINGS]`, `[handwritten: 211823]`,
  `[signature]`); a handwritten page transcribed under a first line `[handwritten page]`;
- a map or exhibit: **every legible label, verbatim, one per line**, under `[graphic page]`
  — never a description of the map (see below); a callout stays whole on its line
  (`BEGIN ABANDONMENT`, `M.P. 54.3`, `IN GUTHRIE COUNTY, IOWA`), and a table drawn on the
  map is transcribed as a table;
- a page with no text: exactly `[blank page]`; rotated text under `[rotated page]`, in
  reading order.

### Why a map is transcribed, never described

Asked by the operator 2026-08-28. Three reasons, in order of force:

1. **A description cannot be scored.** An OCR engine emits text it read; it never emits a
   description. Ground truth written as prose about the map would score every engine at
   near-total error on these ten pages, and the tier would measure nothing.
2. **A description is an inference, and this record quotes.** Every derived assertion here
   carries method, version and confidence (ADR 0007); a sentence about what a map *shows*
   is the record speaking in its own voice. Labels are quotation.
3. **The labels are the payload.** Measured on the drawn sample: an abandonment map carries
   the begin and end **mileposts** (`MP 54.3 TO MP 48.1`), the **counties**
   (`IN GUTHRIE COUNTY, IOWA`), the **mileage** (`A TOTAL OF 6.2 MILES`), the connecting
   **carriers** (UP, BN, SOO, DM&E, IAIS, BNSF), dozens of **place names**, and often a
   station/milepost/agency **table**. That is the raw material for geography as structured
   rows (ADR 0008) and for capabilities C3 (address to docket), D1 (trail use) and D2
   (system diagram maps). A description discards all of it.

A page description has a legitimate home later — alt text for the image, or a
"what is on this page" summary — but as a **derived assertion** with its method and
confidence, never as ground truth (`docs/deferred.md`).

The rendered pages themselves (37 MB) are not committed; they are at
`/data/docketyard/ocr/sample/pages/` on RMI-AI-MACHINE and `data/ocr/pages/` on the
working machine, and any page can be re-rendered from its hash with `ocr_sample.py`.

## How to check

**From anywhere**, the queue built by `ocr_check_page.py` and published privately to the
operator 2026-08-28 (the address is not recorded in this public repository): one page at a time, the scan at **full
resolution beside the transcript** — scroll to zoom, drag to pan, double-click for one
screen pixel per scan pixel, `w` to give the page the full width — with the Board's own
file one click away at `docketyard.org/document/<sha>.pdf#page=N`, since every sampled
document already answers at its permanent address. The pages are embedded by
`tools/rmi-ai-machine/ocr_page_images.py` as 1-bit PNGs at the render's own 150 dpi — 2.4 MB
for all ninety — **whole, exactly as the Board's PDF has them.** A reviewer checking a
transcription against a page must see the page, margins and all; altering the image to suit
the display would put them at one remove from the source (the operator's instruction,
2026-08-29, after a first attempt cropped them). The queue instead offers **Ink** as a
*view*, which pans and zooms until the type fills the frame and leaves the margins
off-screen — median 1.18× larger type, up to 2×, with the image untouched.

The white margin is still worth recording as a property of the renders: a 150 dpi render is
the whole PDF page, often legal-size or oversized with the scan in one corner, and the ink
occupies 70% of the render by area (85% by width) on average. Whether to trim before handing
a page to an engine is therefore a **step 2 preprocessing variable to measure**, alongside
the engines themselves — not an assumption to bake in.
Verdicts and notes stay in that browser; **Copy corrections** hands them back in one block,
which is then applied to the `.txt` files here. This is a stand-in for the `/review` queue
ADR 0016 accepts; the real queue records each check as a provenance row instead.

**At the workstation**, `check.html` in this directory does the same from the local
renders in `data/ocr/pages/` (not committed — re-render with `ocr_sample.py`). Edit the
`.txt` in place; the whitespace hooks skip this directory, so a transcription's own spacing
survives a commit.

What matters most, in order: a **docket number or date** read wrongly or invented (the two
errors the benchmark scores separately); text asserted that is not on the page; text on the
page that is missing; then the bracket conventions.

## How a transcription is scored, and what therefore matters in the check

Decided 2026-08-28, when the operator asked whether line breaks need marking. **They do
not**, because both the ground truth and every engine's output pass through the same
normaliser before CER and WER are computed, and its imperfections cancel:

- runs of whitespace, newlines included, collapse to one space — an engine that preserves
  the printed lines (Tesseract) and one that reflows into paragraphs (a vision model) are
  reading equally well, and neither may be scored for the difference;
- a line-final hyphen joins to the next line with the hyphen removed (`irresponsi-` +
  `ble` → `irresponsible`). This mangles a genuine compound broken at a line end
  (`party-of-` + `record` → `party-ofrecord`) — which is harmless, because the ground
  truth is mangled identically;
- bracket annotations are unwrapped to their content before scoring, so
  `[stamp: RECEIVED AUG 17 2004]` scores as `RECEIVED AUG 17 2004` and an engine that
  reads the stamp is neither rewarded nor punished for not knowing it was a stamp;
  `[illegible]` marks a span excluded from CER, since no reading of it can be called wrong.

What **is** scored, and therefore what the check must catch:

| Scored | What a mistake looks like |
| --- | --- |
| Characters and words (CER, WER) | A word misread, invented, or missing; two words run together *within* a line |
| **Docket numbers** (separately) | `FD 32760` read as `FD 32780`; a number invented where the page has none |
| **Dates** (separately) | `February 26, 1997` read as `February 28, 1997`; a date assembled from two |
| **Reading order** | A two-column page read straight across; a stamp or margin note spliced into the middle of a sentence — normalisation cannot repair a scrambled sequence |
| **Table grid** (tabular tier) | Rows merged into one line, cells not tab-separated, or a row with the wrong number of cells; inside `[table]` the grid is compared **cell by cell** (the block markers unwrap like any other bracket for the flowed comparison), because a grid is meaning, not layout preference |
| **False text** (graphic and blank tiers) | Any prose asserted on a page that carries only labels, or on a blank page |

**A fragment of an adjacent page is excluded from the page's CER and WER** — an engine
that reads the facing page's margin and one that ignores it are both behaving sensibly, and
neither may be scored for the choice. But the block gets a check of its own, and it is the
sharpest one in the benchmark: **an engine that emits a completed form of a cut line is
scored as invention.** A truncated line is exactly where a language model is tempted to
finish the sentence from boilerplate it knows — `initio.  Petitions[cut]` becomes
"Petitions to revoke the exemption under 49 U.S.C. 10502(d) may be filed at any time" — and
plausible invention is the failure mode this record can least afford. Measured on the draw:
one page of the ninety (`80507f745410_p1`, FD 33700, found by the operator 2026-08-29) is a
two-page spread; the other page carrying many `[illegible]` marks
(`aa59bdafb508_p46`) is a genuinely faint Federal Register page, not a spread.

The same rule governs the pipeline, not just the benchmark: text inside an
`[adjacent page]` block is **stored but never indexed as this page's**. The facing page is
almost always scanned in full elsewhere in the same PDF, so indexing the fragment here
would duplicate content under the wrong page — and let an extractor read a fragmentary
docket number (`33698, Union [cut]`) and attribute it to the wrong proceeding.

What the table convention deliberately does **not** carry: column spans as syntax, header
flags, cell types, alignment. Those are the shape of *structured extraction* — capability
D3's reference-data series is exactly a pile of tables — and they need a schema and a
schema-critic pass, not a notation invented for ground truth. The rule here is only what a
scorer needs to compare two grids.

A **graphic page is scored as a set, not a sequence**: labels are scattered across a map and
have no reading order, so an engine is scored on which labels it recovered and which it
invented (recall and precision over the label set, with mileposts and county names counted
separately), never on the order it listed them in. Sequence scoring applies to the prose
tiers.

So: an ordinary line break in running prose is not worth a mark. A break that scrambles
the order, breaks a table's rows, or falls inside a docket number or a date is.

## What the check produces

A checked file replaces the draft in place; the operator's changes are the interesting
rows and are worth a note in `CHECK-NOTES.md` (what kind of thing the drafter got wrong).
`tools/rmi-ai-machine/check_ground_truth.py` holds the conventions to account — real tabs,
a square grid per `[table]`, balanced blocks, nothing after a `[cut]`, a well-formed marker —
and every rule in it is there because a draft broke it. Run it after any re-draft; the 90
drafts pass. It judges a bracketed line only when the line opens with one of its own
keywords, because a page prints brackets of its own: the Federal Register sets its docket
line as `[STB Finance Docket No. 33700]`.

The marker vocabulary grew from the drafting, not from the plan: `[logo: …]`,
`[struck through: …]` (a caption amended by hand, whose status matters), `[handwritten page]`,
`[graphic: …]` for an inline icon, and `[stamp, rotated: …]` were all invented by the drafter
against pages the rules had not anticipated, and were adopted rather than rejected.

## Step 2 — the scorer

`tools/rmi-ai-machine/ocr_score.py` scores an engine's output against this ground truth and
enforces every rule settled while the ground truth was built: one normaliser on both sides,
`[illegible]` excluded, `[adjacent page]` excluded, bracket annotations unwrapped to their
content, docket numbers and dates as their own sets, a graphic page as a label set rather
than a sequence, a table cell by cell, and false text on a page carrying only labels.

    python tools/rmi-ai-machine/ocr_score.py --engine tesseract --dir data/ocr/runs/tesseract

It was validated before any engine existed, against three fixtures made from the ground
truth itself (2026-08-29):

| Fixture | CER | WER | Docket recall | What it proves |
| --- | --- | --- | --- | --- |
| identical | 0.0% | 0.0% | 100% | nothing is penalised that is not an error |
| **reflowed** — every line break turned into a space | **0.0%** | **0.1%** | 100% | an engine that reflows into paragraphs scores like one that keeps the printed lines. This is the property the whole normaliser exists for |
| noisy — 2% of letters corrupted, every docket number's first digits transposed | 1.8% | 9.0% | **79.4%** | a transposed digit is nearly invisible in CER and unmistakable in docket recall, which is why the two are scored apart |

The noisy fixture also moved table cell recall to 76% and graphic label recall to 87% while
CER stayed near the injected 2%, which is the point of scoring those tiers on their own.

**A known limit.** An engine emits no brackets, so where the ground truth excludes a
facing-page fragment the engine's rendering of that margin cannot be excluded from its
output, and its CER carries it. One page of the ninety has such a block, and the invention
probe ignores any fragment that also appears in the page's own body — the facing page of
FD 33700 opens "Burlington Nor" and page one says "Burlington Northern" in its own right,
so a continuation there proves nothing.

## Step 3 — the engines, measured

Every figure below is CER on the 90 checked pages, by tier. `cells` is table-cell recall on
the five tabular pages, which is the only structural metric here.

`invents` counts the graphic pages where the engine emitted text the page does not carry,
with the worst page in brackets — reported as a count and a maximum rather than a mean,
because the distribution is eight zeros and an outlier and a mean of that says nothing.

| engine | where | per page | CER | clean | degraded | cells | invents (worst) | dockets | dates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Sonnet 5 (greyscale) | API $0.0171 | ~5 s | **5.9%** | **1.7%** | **10.5%** | 0.0% | 1 of 9 (52) | **100%** | **89.8%** |
| Claude Sonnet 5 | API $0.0171 | ~5 s | 6.6% | 1.8% | 11.9% | 0.0% | 1 of 9 (139) | **100%** | 89.0% |
| **PaddleOCR-VL 1.6** | **box, free** | **1.3 s** | **8.8%** | 2.6% | **12.0%** | 57.5% | 1 of 9 (20,368) | 91.2% | 85.0% |
| qwen2.5vl:7b (greyscale) | box, free | 8.2 s | 9.2% | 2.1% | 14.5% | 0.0% | **3 of 9** (16,470) | 91.2% | 86.2% |
| Textract `detect-document-text` | API $0.0015 | 4.3 s | 10.8% | 2.5% | 18.4% | 0.0% | 3 of 9 (1,794) | **97.1%** | 87.0% |
| Textract `analyze-document` TABLES | API $0.015 | 4.3 s | 12.3% | 3.7% | 20.0% | **87.4%** | 3 of 9 (1,798) | 91.2% | 87.0% |
| **Tesseract 5.5.0** | box, free | 0.8 s | 13.3% | 3.2% | 21.9% | 0.0% | **0 of 9** | 85.3% | 73.2% |

**The baseline finally exists** (2026-09-01). Tesseract is the number every study reports
against, and until now nothing here had one — so no figure in this benchmark could be
compared with anyone else's. It anchors the rest.

**And with it in place, the managed service is no longer the cheap-and-adequate choice: it
is neither.** PaddleOCR-VL 1.6, run through its own layout pipeline on the box, reads at
**8.8% against Textract's 10.8%**, and on the degraded tier — the third of the record that
actually hurts — at **12.0% against 18.4%**, which is within 1.5 points of Claude at about a
thousandth of the cost. It does it in 1.3 s a page on a 4070, so the whole 175k-page backfill
is roughly 63 hours of box time that nobody has to pay for. `ocr-plan.md`'s reasoning stands
— OCR should be as cheap as is adequate — but its conclusion was drawn before anything
adequate and free had been measured.

**Two things Textract still wins, and they decide the routing rather than the engine.** Its
docket-number recall is the best of any non-Claude engine (97.1%), and with TABLES it
recovers 87.4% of table cells against PaddleOCR-VL's 57.5% — the gap is one page of five,
where PP-DocLayoutV3 read an unruled three-column errata list as nineteen separate text
blocks and never called it a table at all. On the four it does detect, it returns HTML with
`rowspan`/`colspan`, which is richer structure than Textract's flat grid.

**The graphic tier inverts the ranking, and what it measures is a tail risk rather than an
accuracy one.** Only Tesseract invents nothing on all nine pages. Every other engine invents
on at least one, and the severity is what separates them: Claude adds 52 characters at
worst, Textract 1,794, **PaddleOCR-VL 20,368 on a single page** — a whole invented page of
prose about a map. Read carefully, though: **PaddleOCR-VL does that on one page of nine, and
is silent on the other eight.** Only qwen fails repeatedly, on three of nine.

So the honest reading is that a local VLM carries a rare, catastrophic failure mode on
graphic pages, not a general inability to handle them — and *rare and catastrophic* is
exactly what a confidence layer is for, since one such page would otherwise enter the record
as fluent, plausible, wholly fabricated text. **Nine graphic pages cannot settle how often it
happens**, and the frequency is what decides whether routing or gating is the answer. That
needs a larger graphic sample before any rule is built on it.

**The aggregate hides the shape, and the shape is what decides the pipeline.** On clean
typescript — about 53% of a random draw of image-only pages — **every engine lands between
1.7% and 3.2%**, and the two free local ones (qwen 2.1%, PaddleOCR-VL 2.6%) sit inside that
band alongside Textract's 2.5%. Nothing on that tier is worth paying for. On degraded scans,
a third of the draw, the spread is 11 points: 10.5% to 21.9%, with the paid reader best and
free software worst. A single engine over the whole record therefore either overpays for the
clean tier or underreads the degraded one. Both are avoidable, and the plan's own
agreement-as-confidence mechanism is already the router: where two free local readings agree,
ship; where they disagree, escalate.

**Table structure was never measured before 2026-09-01, and the zero was ours.** Every
engine scored `cells` recall 0.0% — five engines failing identically is a harness result,
not an engine result. The ground truth marks 167 cells in `[table]` blocks, no engine was
ever *asked* to emit that markup, and Textract was called with `detect-document-text`, which
has no table feature at all; `analyze-document --feature-types TABLES` does, and recovers
**87.4%** of cells. The 0.0% stood for four days as if it described the engines.

**`analyze-document` is not a general-purpose engine, and its other tiers here measure a
routing mistake rather than the engine.** It reads a two-column caption block, a service
list and a signature block as tables — 29 non-tabular pages, including all nine graphic
ones — and the reconstruction then wraps real body text in `[table]`, where it drops out of
the body comparison. That is why its clean tier is 3.7% against the plain call's 2.5%.
**Textract's own table confidence cannot separate the two**: genuine tables score 98.4–100
and false ones reach 99.9. The obvious filter is a column count — every false positive is
2-column, every real table 3+ — and it is deliberately **not** taken, because tuning a
threshold against the tier labels of the very sample being scored is how the party-type
rules reached 83.3% on the sheet they were fitted to. Choosing which table to believe needs
a page classifier measured on its own, not a constant read off this table.

**A blank page read as blank was recorded as a failure.** The runner treated empty output as
an error and dropped the page, so the pages an engine gets *most* right vanished from its
score — and it penalised exactly the safest behaviour. Tesseract lost two of its nine graphic
pages this way, the two where it correctly emitted nothing, while an engine that invents
prose about a map keeps all nine. Fixed 2026-09-01; an empty read is written and scored, and
every engine above is now scored on all 90 pages.

**How PaddleOCR-VL has to be run**, because two obvious ways both fail. The 0.9B weights are
an *element* recogniser: fed a whole 150-DPI page through `transformers` it tokenises at
native resolution, holds the GPU for over 27 minutes and then runs out of memory on a 12 GB
card. And the pipeline's own `native` generation backend needs over eight minutes a page.
The same page through a **vLLM server** takes 1.1 s — a factor of roughly 450, and the
difference between unusable and the fastest engine in the table. `run_paddleocr_vl` in
`ocr_run.py` carries the invocation.

**Still open.** The tabular tier rests on five pages — too thin to conclude from, and drawing
more needs fresh ground truth the operator checks. dots.ocr and docTR are not in the table
yet. Preprocessing is not evaluated at all, though the greyscale runs are already one result
in that direction: greyscale took Claude from 6.6% to 5.9%.
