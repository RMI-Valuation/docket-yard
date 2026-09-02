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

| engine | where | per page | CER | clean | degraded | cells | map labels | invents (worst) | dockets | dates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Sonnet 5 (greyscale) | API $0.0171 | ~5 s | **5.9%** | **1.7%** | **10.5%** | — | 60.1% | 1 of 9 (52) | **100%** | 89.8% |
| Claude Sonnet 5 | API $0.0171 | ~5 s | 6.6% | 1.8% | 11.9% | — | 60.7% | 1 of 9 (139) | **100%** | 89.0% |
| dots.ocr | box, free (MIT) | 6.5 s | **8.0%** | 3.3% | **11.9%** | 58.7% | 5.1% | **0 of 9** | 94.1% | 88.2% |
| **dots.mocr** | **box, free (MIT)** | 6.5 s | 8.2% | 3.3% | 12.7% | 59.3% | 5.5% | **0 of 9** | **100%** | 89.0% |
| PaddleOCR-VL 1.6 | box, free (Apache) | **1.3 s** | 8.8% | 2.6% | 12.0% | 57.5% | 4.2% | 1 of 9 (20,368) | 91.2% | 85.0% |
| qwen2.5vl:7b (greyscale) | box, free | 8.2 s | 9.2% | 2.1% | 14.5% | — | 14.9% | **3 of 9** (16,470) | 91.2% | 86.2% |
| Textract `detect-document-text` | API $0.0015 | 4.3 s | 10.8% | 2.5% | 18.4% | — | **63.0%** | 3 of 9 (1,794) | 97.1% | 87.0% |
| **PP-OCRv6 medium** | box, free (Apache) | **0.4 s** | 11.8% | 2.6% | 17.9% | — | 47.2% | **0 of 9** | 91.2% | **90.2%** |
| HunyuanOCR-1.5 | box, **restricted** | 6.6 s | 11.9% | 7.1% | 16.3% | **86.2%** | 4.6% | 1 of 9 (5,206) | 94.1% | 81.3% |
| docTR 1.1.0 | box, free (Apache) | 1.4 s | 12.0% | 2.6% | 18.5% | — | 16.4% | **0 of 9** | 88.2% | 77.6% |
| Textract `analyze-document` TABLES | API $0.015 | 4.3 s | 12.3% | 3.7% | 20.0% | **87.4%** | 29.9% | 3 of 9 (1,798) | 91.2% | 87.0% |
| Tesseract 5.5.0 | box, free (Apache) | 0.8 s | 13.3% | 3.2% | 21.9% | — | 2.3% | **0 of 9** | 85.3% | 73.2% |

A dash under `cells` means the engine emits no table structure at all, so the tier is
unscoreable for it rather than scored at zero — see the harness note below.

**The baseline finally exists** (2026-09-01). Tesseract is the number every study reports
against, and until now nothing here had one — so no figure in this benchmark could be
compared with anyone else's. It anchors the rest.

**And with it in place, the managed service is no longer the cheap-and-adequate choice: it
is neither.** Three free local engines beat Textract's 10.8% outright, and on the degraded
tier — the third of the record that actually hurts — **dots.ocr reads at 11.9% against
Textract's 18.4%**, within 1.4 points of Claude at about a thousandth of the cost.
PaddleOCR-VL does 8.8% in 1.3 s a page, so a 175k-page backfill is roughly 63 hours of box
time nobody pays for. `ocr-plan.md`'s reasoning stands — OCR should be as cheap as is
adequate — but its conclusion was drawn before anything adequate and free had been measured.

**dots.mocr is the one to build on.** It reads at 8.2%, invents nothing on any graphic page,
is MIT, and **gets every docket number on all 90 pages — 100% recall and 100% precision**,
which only Claude also manages. On this record that is not one column among many: a docket
number is the identity key an edge resolves against, and a misread digit does not degrade a
page, it points at a different proceeding. That is the `AB 124` → `AB 1242` failure ADR 0017's
exposure test exists for. It supersedes dots.ocr (its own predecessor, rebranded from
dots.ocr-1.5), which is marginally better on characters and materially worse on dockets.

**Table structure is the one place a paid service still led, and the reason is systematic.**
Textract detects all five real tables; **dots.mocr and PaddleOCR-VL both detect four and miss
the same one** — an unruled three-column errata list, which PP-DocLayoutV3 read as nineteen
separate text blocks. The VLM layout models want visual rules before they will call something
a table; Textract goes on alignment. Unruled columnar lists — errata sheets, service lists,
schedules — are ordinary in agency filings, so that is a structural weakness, not one awkward
page. Where they do detect a table they return `rowspan`/`colspan` HTML, which is richer than
Textract's flat grid.

**HunyuanOCR-1.5 closes that gap and opens a licence question instead.** At 1B parameters and
2.0 GB of VRAM it is the only free engine that detects all five tables, at **86.2% cell recall
against Textract's 87.4%** — but it reads ordinary prose distinctly worse than the others
(7.1% on the clean tier, more than double every engine but Tesseract), reads dates worse than
anything except Tesseract and docTR, and invents 5,206 characters on a graphic page. And its Tencent Hunyuan Community License excludes
the EU, UK and South Korea from the grant and forbids using outputs to improve any AI model,
which cannot be reconciled with publishing them in a CC0 dump. **That is an operator decision,
not a measurement**; it is recorded here so the decision has numbers under it.

**docTR is dominated and can be closed out.** PP-OCRv6 medium reads the same clean tier,
a better degraded one, three times the map labels and 90.2% against 77.6% on date recall,
while being three times faster. docTR edges it on two minor measures — tabular CER 37.4%
against 38.2%, and date *precision* 98.5% against 97.4% — neither of which describes a tier
anyone would route to it. There is no tier where docTR is the right choice.

**The graphic tier inverts the ranking, and what it measures is a tail risk rather than an
accuracy one.** Five engines invent nothing on all nine pages — Tesseract, docTR, PP-OCRv6
and, alone among the generative models, **dots.ocr and dots.mocr**. The rest invent on at
least one, and severity separates them: Claude 52 characters at worst, HunyuanOCR 5,206,
**PaddleOCR-VL 20,368 on a single page** — a whole invented page of prose about a map. Read
carefully, though: PaddleOCR-VL does that on one page of nine and is silent on the other
eight. Only qwen fails repeatedly, on three of nine.

So the honest reading is that *most* generative readers carry a rare, catastrophic failure
mode on graphic pages rather than a general inability — and *rare and catastrophic* is exactly
what a confidence layer is for, since one such page would otherwise enter the record as
fluent, plausible, wholly fabricated text. That the dots models avoid it entirely is the
single strongest point in their favour. **Nine graphic pages cannot settle how often it
happens**, and the frequency is what decides whether routing or gating is the answer. That
needs a larger graphic sample before any rule is built on it.

**PP-OCRv6 medium is the engine for those pages, and not because of its CER.** It reads
**47.2% of map labels while inventing nothing**, where every VL model is effectively blind to
a map (4–6%) and Textract reads more (63.0%) but invents on three pages of nine. A detector
plus a recogniser cannot write a sentence that is not on the page; its worst case is silence.
At 0.4 s a page it is also the fastest thing measured.

**The aggregate hides the shape, and the shape is what decides the pipeline.** On clean
typescript — about 53% of a random draw of image-only pages — **every engine but HunyuanOCR
lands between 1.7% and 3.3%**, and the free local ones (qwen 2.1%, PaddleOCR-VL and PP-OCRv6
2.6%, dots 3.3%) sit inside that band alongside Textract's 2.5%. Nothing on that tier is
worth paying for. On degraded scans,
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
an *element* recogniser: fed a whole 150-DPI page it tokenises at native resolution, holds
the GPU for over 27 minutes and then runs out of memory on a 12 GB card. And the pipeline's
own `native` generation backend needs over eight minutes a page. The same page through a
**vLLM server** takes 1.1 s — a factor of roughly 450, and the difference between unusable
and the fastest engine in the table. `run_paddleocr_vl` in `ocr_run.py` carries the
invocation.

The version measured is **PaddleOCR-VL 1.6** with **PP-DocLayoutV3** in front of it, both
the current defaults of the `paddleocr` package. Its `transformers` path is a trap worth
naming: the model card asks for `transformers>=5.0.0` and `AutoModelForImageTextToText`, but
5.16.1 raises `'PaddleOCRVLConfig' object has no attribute 'text_config'` and 4.x raises
`KeyError: 'default'` in `ROPE_INIT_FUNCTIONS` — the same on the HF repo and on the copy
paddlex mirrors. **No `transformers` version participates in a scored run**, because the
pipeline drives the layout model through PaddlePaddle and the VL model through vLLM.

## What the measurements route to

Not a recommendation of one engine — the tiers disagree about which is best, and that is the
finding. Each line below is the engine this benchmark measured as best for that tier, at the
tier's share of a random draw of image-only pages:

| tier | share | engine | why |
| --- | --- | --- | --- |
| clean | ~53% | **PP-OCRv6 medium** | every engine but HunyuanOCR lands 1.7–3.3%; take the fastest that cannot invent (0.4 s, free) |
| degraded | ~33% | **dots.mocr** | 12.7% free, against Textract's 18.4%; no invention; perfect dockets |
| graphic | ~9% | **PP-OCRv6 medium** | 47.2% of labels with zero invention; every VL model is blind here and some fabricate |
| tabular | ~4% | **unsettled** | HunyuanOCR 86.2% and Textract 87.4% both detect all five; dots.mocr 59.3% misses unruled lists |
| blank | ~1% | any | all engines correct once the harness stopped discarding them |

**The routing needs a classifier**, and the obvious filter is one this benchmark refuses to
take: every false table detection is 2-column and every real one 3+, but fitting that
threshold to the tier labels of the sample being scored is how the party-type rules reached
83.3% on their own sheet. `PP-DocLayoutV3` — already on the box as a dependency of
PaddleOCR-VL, and layout-detection only — was the candidate, and **step 4 below measures it**:
free at 0.05 s a page, safe on the graphic call, unsafe on the blank one, and carrying an
unconfirmed signal on the clean/degraded split it was assumed blind to. The dots models return
the same categories alongside their text, and were the second candidate; § Step 4 measures
dots.mocr asked for layout alone and finds it 75× dearer for no net gain.

## Step 4 — the page router, measured

Run 2026-09-02 by `tools/rmi-ai-machine/ocr_router_probe.py` over the same 90 checked pages,
`PP-DocLayoutV3` through PaddlePaddle with no recogniser and no vLLM server behind it;
999 regions, 16 distinct labels; `runs/router/{regions.json,run.json}`.

**It is effectively free, which was the first thing that had to be true.** 0.05 s a page
(median 0.04 s, worst 0.48 s) — an eighth of PP-OCRv6's read and a hundred-and-thirtieth of
dots.mocr's. A router that cost as much as the read it chooses would not be worth having;
this one is a rounding error on either.

The rule below was **fixed before the first run** and no threshold in it is fitted: no content
region → blank; else any `table` region → tabular; else figure area at least half the content
area → graphic; else text. Column count is not used, for the reason Step 3 gives.

| operator tier | pages | ≥1 table | ≥1 figure | no content | regions/page |
| --- | --- | --- | --- | --- | --- |
| clean | 38 | 0 | 9 | 1 | 8.5 |
| degraded | 37 | 1 | 24 | 0 | 16.5 |
| tabular | 5 | **4** | 1 | 0 | 9.2 |
| graphic | 9 | 1 | 6 | **2** | 2.1 |
| blank | 1 | 0 | 0 | 1 | 0.0 |

| class | pages that are | pages called | precision | recall |
| --- | --- | --- | --- | --- |
| text (clean ∪ degraded) | 75 | 75 | 97.3% | 97.3% |
| graphic | 9 | 5 | **100%** | 55.6% |
| tabular | 5 | 6 | 66.7% | 80.0% |
| blank | 1 | 4 | **25.0%** | 100% |

**What it can do: say which pages are pictures, and never say it of a page that is not.**
Graphic precision is 100% — every page it calls graphic is one. Recall is 55.6%, so it misses
four of nine, but the errors are one-directional and that is the useful shape: a missed map
is read by the wrong engine, whereas a false one would send prose to a reader chosen for
labels.

**What it cannot do: be trusted when it finds nothing.** Three of the four pages it calls
blank are not blank — two maps and a clean typescript page whose only regions were page
numbers. Only one true blank exists in the sample, so 25.0% precision is one page's worth of
evidence, but the direction is the point: **"no regions" must never be wired to "skip this
page"**, or a map's labels leave the record silently. Route an empty detection to a reader,
not to a decision.

**The table miss is the one Step 3 already named, now seen directly.** Of five real
tables it detects four; the miss is `7ab81af43a79_p3`, the unruled three-column errata list,
which comes back as nineteen separate `text` blocks. Step 3 inferred that from the engine
outputs; this is the detector's own answer, so it is the same model confirming itself rather than a
second opinion — the top-up is what would test it. Against it are two false tables — a
degraded page and a *graphic* one — for 66.7% precision, which is the same weakness Textract's
`analyze-document` shows and the reason the tabular route stays unsettled. **Five tabular and
nine graphic pages decide nothing**; both figures move on a top-up.

**And the claim this probe was built on turned out to be too strong.** The rule folds clean and
degraded into one class because layout detection is structure and the difference is image
quality. The raw counts disagree: a degraded page fragments into roughly twice the regions of
a clean one (median 18.0 against 8.5), and is about twice as likely to pick up a spurious
picture region — 18 of 37 carry a literal `image` against 8 of 38 clean, or 24 against 9 if
letterhead (`header_image`/`footer_image`) is counted as a picture too.

| quantity | clean median | degraded median | AUC |
| --- | --- | --- | --- |
| regions per page | 8.5 | 18.0 | **0.843** |
| figure regions, any label | 0.0 | 1.0 | 0.720 |
| figure regions, literal `image` | 0.0 | 0.0 | 0.646 |

The figure row is given both ways because the answer moves with the definition: counting a
letterhead as a picture is a judgement, and it is worth 0.074 of the AUC. The region count,
which needs no such judgement, is the stronger signal anyway.

AUC is reported **instead of** a threshold, deliberately — it commits to no cut-off, so there
is nothing in it to tune, and each quantity was a column the probe printed before the
question was asked. 0.843 is a real signal on the split that matters most: clean and degraded
are ~86% of a random draw and they route to different engines, so this is the largest routing
decision in the pipeline and the one a layout model was assumed unable to make. **It is a
lead, not a rule.** Turning it into a cut-off against these same 90 pages is exactly the
party-type mistake; it needs the second, unseen sample first.

So the router is not settled, but it is no longer nothing: the structural half is measurable
and cheap, the graphic call is safe in the direction that matters, the blank call is not safe
at all, and the clean/degraded split — the expensive one — has a free signal in it that has
yet to be confirmed on pages nobody has scored.

### Can dots.mocr just classify? Yes — and it is still not the router

Asked 2026-09-02, because the dots models return a category per block and it would be tidy if
the router were the same family as the reader. The model's prompt contract has a layout-only
mode: bbox and category, no text field. `ocr_router_probe.py run-dots` uses it, mapping dots'
vocabulary onto PP-DocLayoutV3's so **one rule scores both** and the comparison is of
detectors rather than of two rules; the mapping is recorded in `run.json`.

It works, and it is genuinely cheaper than reading: **3.78 s a page against the 6.5 s full
read**, so dropping the transcription saves about 42%. But it is **75× PP-DocLayoutV3's
0.05 s**, and that is what decides it.

| | PP-DocLayoutV3 | dots.mocr, layout only |
| --- | --- | --- |
| cost a page | **0.05 s** | 3.78 s |
| graphic | 100% precision, 55.6% recall | 88.9% / **88.9%** |
| tabular | **66.7%** / 80.0% | 36.4% / 80.0% |
| blank | 25.0% / 100% | never called (misses the one blank) |
| text | **97.3% / 97.3%** | 98.6% / 92.0% |
| clean vs degraded, AUC | 0.843 | **0.873** |

**Where dots is better it is really better.** It finds eight of the nine maps against
PP-DocLayoutV3's five, and it never returns an empty page — so it does not have the
false-blank failure that is PP-DocLayoutV3's worst property. It reads the clean/degraded
difference slightly better too.

**Where it is worse, it is worse in the generative way.** It calls eleven pages tabular and is
right about four: it puts a `table` region on ordinary correspondence — `text ×17` plus a
lone `table` — on six separate pages of the text tier. That is the same invention risk the
text side shows on graphic pages, moved into the structural channel — and it makes the tier
the routing most needs settled the tier it is least trustworthy on. It also misses the same
unruled errata list, coming back
with three `text` blocks where PP-DocLayoutV3 gives nineteen.

**The economics close the question.** Routing to the engines § What the measurements route to
names, the expected read is 2.66 s a page. Add the router:

| pipeline | cost a page |
| --- | --- |
| PP-DocLayoutV3 + routed read | **2.71 s** |
| dots.mocr layout-only + routed read | 6.44 s |
| no router, dots.mocr everywhere | 6.50 s |

**dots.mocr as the router saves 1% over having no router at all.** And the split it is best at
is the one it cannot economically serve: paying 3.78 s of dots.mocr to decide whether to pay
6.5 s of dots.mocr is most of the read to avoid the read.

**Asking for layout alone does sharpen it**, which is worth knowing for anyone who uses dots
at all. The scored `dots-mocr` read already recorded a category per block as a byproduct
(`runs/dots-mocr-layout/layout.json`); against the layout-only run on the 87 pages both cover,
scored by the same count-based rule — *not* the area rule the table above uses, because the
byproduct carries no bboxes — the graphic call goes from 66.7% precision at 22.2% recall to
80.0% at 44.4%, and tabular is unchanged. The model classifies better when it is not also
transcribing. (Those numbers are lower than the table's because the count rule is weaker than
the area rule on this tier, not because the run is different.)

Two caveats, both against dots rather than for it being dismissed. Both engines were timed one
page at a time; vLLM batches well and PP-DocLayoutV3's lead would narrow under concurrency,
though not by 75×. And its graphic recall is a real advantage — if the false-blank problem
proves to be the thing that matters, a cheap detector plus a dots second opinion on the pages
that come back empty would cost far less than routing everything through it. That is a
composition worth measuring; running dots.mocr as *the* classifier is not.

## Step 5 — preprocessing, measured per engine class

Run 2026-09-02. Seven renderings of the same 90 pages built by
`tools/rmi-ai-machine/ocr_preprocess.py`, read by the two engines the routing actually uses —
**PP-OCRv6 medium** for the detector-plus-recogniser class and **dots.mocr** for the VLM class
— and scored against the one ground truth, which every variant leaves valid because none of
them changes what is printed. Scores in `runs/preprocess/`; both tables come from
`ocr_preprocess.py compare`, not from a throwaway script.

**Read the paired columns, not the means.** Every variant reads the same pages, so the
per-page differences are paired, and a mean over them hides how it was earned: `binarise` has
the *better* mean of the two and loses on 44 pages of 81. Win/loss/tie says which happened.

### PP-OCRv6 medium

| variant | CER | clean | degraded | tabular | dockets | dates | map labels | invent | completed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base (150 DPI, colour) | 11.8% | 2.6% | 17.9% | 38.2% | 31/34 | 222/246 | 47.2% | 0 | 1 |
| dpi300 | 11.7% | 2.6% | 18.0% | **37.4%** | 31/34 | 220/246 | 44.6% | 0 | **0** |
| grey | 11.8% | 2.6% | 17.9% | 38.2% | 31/34 | 222/246 | 47.3% | 0 | 1 |
| deskew | 11.9% | 2.6% | 18.1% | 39.2% | 31/34 | 220/246 | 46.6% | 0 | 2 |
| crop | **11.6%** | **2.4%** | **17.6%** | 39.4% | 30/34 | 221/246 | 45.5% | 0 | **4** |
| binarise | 11.7% | 2.6% | **17.8%** | 38.1% | 30/34 | 212/246 | 33.3% | 0 | 1 |
| denoise | 12.1% | 2.8% | 18.2% | 40.8% | 30/34 | 213/246 | 29.2% | 0 | 1 |

| variant | vs | better | worse | tie | mean delta |
| --- | --- | --- | --- | --- | --- |
| dpi300 | base | 39 | 29 | 13 | −0.02pp |
| grey | base | 0 | 1 | 80 | +0.00pp |
| deskew | base | 11 | 17 | 53 | +0.13pp |
| crop | base | 35 | 22 | 24 | **−0.16pp** |
| binarise | grey | 24 | 44 | 13 | −0.04pp |
| denoise | grey | 20 | 50 | 11 | +0.37pp |

### dots.mocr

Only the three variants with a mechanism for a VLM were run against it; `deskew`, `binarise`
and `denoise` are measured for the recogniser class only, and `dpi300` could not be run at all.

| variant | CER | clean | degraded | tabular | dockets | dates | map labels | invent | completed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 8.2% | 3.3% | 12.7% | **13.4%** | 34/34 | 219/246 | 5.5% | **0** | **7** |
| grey | 8.2% | 3.3% | 12.7% | **13.4%** | 34/34 | 219/246 | 5.5% | **0** | **7** |
| crop | **7.9%** | **2.8%** | **12.3%** | 15.3% | 34/34 | 220/246 | 6.2% | 4 | 8 |

| variant | vs | better | worse | tie | mean delta |
| --- | --- | --- | --- | --- | --- |
| grey | base | 0 | 0 | 81 | +0.00pp |
| crop | base | 21 | 14 | 46 | **−0.29pp** |

### The DPI curve has an optimum, and it is 200

Added 2026-09-02, because the first pass tested only 150 and 300 and found a wash at one and a
crash at the other. Between them the picture is different, and it is different per engine.

| DPI | PP-OCRv6 CER | clean | degraded | tabular | dots.mocr CER | clean | degraded | tabular | dots a page |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 150 | 11.8% | 2.6% | 17.9% | 38.2% | 8.2% | 3.3% | 12.7% | 13.4% | 6.5 s |
| 200 | 11.7% | 2.6% | 17.8% | **37.0%** | **7.9%** | 3.2% | **12.1%** | 13.4% | 9.0 s |
| 250 | **11.6%** | **2.5%** | 17.8% | 37.4% | 8.3% | 3.9% | 12.4% | **12.0%** | 12.2 s |
| 300 | 11.7% | 2.6% | 18.0% | 37.4% | — OOM — | | | | — |

**PP-OCRv6 is flat, and its best CER comes with something the CER does not show.** Every DPI
lands within 0.2pp of every other, and the paired tests agree: 200 is 39 pages better and 28
worse, 250 is 36 and 29, 300 is 39 and 29. But at 200 and 250 it starts reading marks off a
map as characters — **90 and 154 of them on one graphic page**, where 150 and 300 read none.
It is one page and the effect is not monotonic, so it is noise rather than a trend; it is
recorded because 250 is the row with the best CER and that is not the whole of what it did.
There is no resolution this engine wants that 150 does not give it. It is also the engine
the router sends the clean tier to, which is 53% of the record, so **the largest share of
pages should stay at 150 DPI** and the cheapest render is the right one.

**dots.mocr has a real optimum at 200, and 250 overshoots it.** At 200 the degraded tier — the
third of the record this engine exists for — goes 12.7% to **12.1%**, the paired test is 20
better against 11 worse, all 34 docket numbers survive, tables are untouched, nothing is
invented and `completed` does not move. **It is the only change measured in this section that
improves an engine while leaving both invention probes exactly where they were.**

At 250 it reverses: clean goes 3.2% to 3.9%, the overall mean turns positive (+0.22pp on the
text tiers), and one docket is lost. The curve is not monotonic and the peak
is narrow.

**250 does buy the one thing 200 does not**: tabular CER 13.4% to **12.0%**, the best tabular
figure dots has posted, and 223 of 246 dates against 219. If the tabular route ever settles on
dots rather than Textract or HunyuanOCR, it should settle at 250 DPI — a per-tier render, not
a per-record one.

**300 DPI is where it stops.** `torch.OutOfMemoryError` in the vision rotary embedding, nine
pages in, the engine core dead. 200 and 250 both complete 90 of 90 with no failures, so the
ceiling on a 12 GB card at `--gpu-memory-utilization 0.95` and 16,384 context is between 250
and 300.

**What it costs.** dots at 200 is 9.0 s a page against 6.5 s. Through the router's tier shares
the whole pipeline goes from **2.71 s to 3.54 s a page** — 132 hours to 172 hours over 175,000
pages, on a box nobody pays for. That is the trade for 0.6pp on the tier that hurts, and it is
the operator's to make rather than mine.

### Masking the non-text regions, rather than cropping to them

The `crop` result raised the obvious follow-up: cropping fails because it removes the page
margin, so cut lines stop looking cut. **Masking the non-prose regions in place has the same
motive and does not touch the margins.** `maskfig` whites out what PP-DocLayoutV3 calls a
picture; `masktab` whites out tables too, which is the shape of reading tables in a separate
later pass. The router already measured that detector at 0.05 s a page, so the masks are
nearly free to produce.

It reaches 33 of the 90 pages (8 clean, 18 degraded, 6 graphic, 1 tabular) over 39 regions,
whiting out a mean 6.0% of the page; `masktab` reaches 37 pages and 46 regions at 6.5%. Which
page and which box is recorded in `runs/preprocess/masks/`, so those counts are re-derivable
rather than asserted.

| variant | engine | CER | clean | degraded | tabular | dockets | dates | invents | completed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | PP-OCRv6 | 11.8% | 2.6% | 17.9% | 38.2% | 31/34 | 222/246 | 0 of 9 | 1 |
| maskfig | PP-OCRv6 | 11.7% | **2.4%** | 17.9% | 38.2% | 28/34 | 218/246 | 0 of 9 | **1** |
| masktab | PP-OCRv6 | 12.3% | **2.4%** | 18.0% | 47.2% | 28/34 | 217/246 | 0 of 9 | **1** |
| base | dots.mocr | 8.2% | 3.3% | 12.7% | 13.4% | 34/34 | 219/246 | 0 of 9 | 7 |
| maskfig | dots.mocr | **7.9%** | **2.6%** | 12.7% | 13.4% | 30/34 | 219/246 | 0 of 9 | 8 |

**On the pages it is meant for, it works.** Restricted to the clean and degraded tiers and to
the pages a figure was actually masked on, PP-OCRv6 is 15 better against 9 worse, mean
−0.26pp; on the clean tier alone, 5 better against 3 worse at −0.61pp. dots.mocr reaches its
**best clean-tier figure of anything measured, 2.6%**, better than crop's 2.8%.

**It escapes most of crop's invention, but not all of it.** `completed` stays at **1** for
PP-OCRv6 where crop took it to 4, and neither engine asserts a character on a graphic page
where crop had dots.mocr writing 36. But dots.mocr's `completed` goes 7 to **8 — exactly
crop's figure**, so on that engine masking finishes the same extra cut line. One line is one
line and does not separate the two techniques; what separates them is the graphic-page
invention and PP-OCRv6's fourfold `completed`, both of which masking avoids.

**The cost is real and it is not where it looks.** Both engines lose docket numbers under
`maskfig` — PP-OCRv6 31→28, dots 34→30 — and **every one of those losses is on a graphic
page**, where masking the figure removes the map the docket is printed on. Those pages would
never be routed through masking: this is a technique for primarily-text pages by construction,
and on those pages dots keeps all its dockets. What it does cost on text pages is **dates: 5
of 246 across four degraded pages**, where a stamp or a letterhead the detector called a
picture had a date inside it.

**`masktab` prices the second pass.** Tabular CER goes 38.2% to **47.2%** and the overall mean
turns +1.45pp: that is the table text simply not being read, which is what a later pass would
have to recover. The prose is unaffected — on the text tiers `masktab` and `maskfig` are within
0.05pp of each other — so splitting the page costs nothing but the tables themselves, exactly
as the idea assumes. Whether the second pass earns it depends on the tabular route, which is
still unsettled between Textract (87.4% cells) and HunyuanOCR (86.2%).

**Where this leaves it.** Masking is better-behaved than cropping and the gain is small: about
a quarter of a point on a third of the pages, at the price of a handful of dates. It is worth
re-asking on the second sample alongside crop, and the question to ask is whether the date loss
scales — because a date is quoted, never computed, and one lost to a whited-out stamp is a
fact the record no longer holds. **Nothing here is adopted on 90 pages.**

### What it settles

**Nothing here is adopted, and one thing is now worth deciding.** No image operation earns a
place in the pipeline; the render resolution is a different matter, because dots.mocr has a
real optimum at 200 DPI and the choice is a cost question rather than a measurement one.

**Greyscale is a no-op on this record, and the reason is the record rather than the engines.**
It ties on 80 of 81 pages for PP-OCRv6 and on **all 81** for dots.mocr, because **86 of the 90
pages are already exactly R == G == B** — the Board's scanned record is monochrome, and
greyscaling it produces the same pixels. Only two pages carry real colour, both coloured maps.
This also re-frames the one prior result: greyscale moved Claude from 6.6% to 5.9%, and since
it removes no information here, whatever it did for Claude came from the channel count or the
encoding rather than from the image. No pipeline should spend a pass on it.

**Resolution is per engine and the optimum is not 300** — see the DPI curve above. PP-OCRv6
is flat from 150 to 300, so the 53% of pages routed to it should stay at the cheapest render.
dots.mocr peaks at 200, gaining 0.6pp on the degraded tier for 38% more time, and 300 kills
the server outright. The usual "300 DPI floor" advice does not survive contact with either
engine here.

**Binarise and denoise are real losses.** Both lose the majority of pages outright (44 and 50
of 81), both drop about ten of the 246 dates, and both collapse map-label recall — 47.2% to
33.3% and to 29.2%. Otsu and a median blur eat thin strokes, which is what a faint photocopy
is made of.

**Deskew was measured twice, because the first measurement was of a bug.** The obvious
implementation — `minAreaRect` over `np.where(mask)` — feeds (row, col) into a function
expecting (x, y), which reflects the frame and negates the angle, and OpenCV has changed that
return value's sign convention between versions besides. Injecting a known −3° skew, it
estimated −5.8° and the correction left a **−11.7° residual: it amplified skew**. The
replacement does not derive an angle from geometry at all — it rotates by each candidate and
keeps whichever makes the horizontal ink profile most peaked, so the sign cannot be wrong by
construction, and it recovers injected angles to within its 0.25° step. It now rotates 40 of
the 90 pages, where the broken one mostly did nothing. **Correctly deskewed, it is still a
small net loss**: 11 pages better, 17 worse, +0.13pp. Resampling blur costs this engine more
than alignment buys it.

**Crop improves CER and pays for it by inventing.** dots.mocr goes 8.2% to 7.9%, clean 3.3%
to 2.8% and degraded 12.7% to 12.3%, winning 21 pages to 14. But it is the only variant that
makes **both** invention measures worse. `completed` — `[cut]`
lines an engine finished, which the scorer calls the sharpest probe in the benchmark — goes
from 1 to 4 on PP-OCRv6 and 7 to 8 on dots.mocr, and dots.mocr asserts **36 characters on
one graphic page that carries none** where the base asserts nothing. The mechanism is the obvious
one once seen: cropping to the content box removes the margin that tells a model where the
scan ends, so a line running off the edge of the page stops looking cut and gets completed.
**Step 3's whole argument about the graphic tier is that a rare, confident fabrication is
worse than a percentage point of character error**, and crop buys 0.3pp by trading exactly
that. It is not carried forward on this evidence.

So the plan should add no image-processing stage. Two things are worth re-asking on the
second, unseen sample: **crop**, where the question is not CER but whether the invented text
scales, and **masking**, where it is whether the lost dates do. The render resolution is the
one live decision, and it is a cost question: 200 DPI for the degraded tier buys 0.6pp for
40 hours over the whole backfill.

**Two limits on all of the above.** Every figure is 90 pages, and the paired counts are the
honest read of how thin some of these margins are. And the dots.mocr baseline is the scored
run of 2026-09-01, which predates `run.json` and so records no weights or server
configuration, where the variants beside it do. Re-running that baseline would close the gap;
it is free and it has not been done.

## Step 6 — agreement as confidence, measured

Run 2026-09-02 by `tools/rmi-ai-machine/ocr_agreement.py` over the same checked pages, using
this benchmark's own `normalise` and `edit_distance` so the comparison sits on the footing
every other figure here does. **81 of the 90 pages**: the graphic tier carries no CER, being
scored on invention instead, so it cannot enter a discrimination measure.

`ocr-plan.md` § The review layer proposes agreement as the confidence signal — two engines
read every page, matching readings ship, differing readings are flagged. It is the reason a
second reading is worth 187 hours of box time, and **it had never been measured**. It is two
questions, and they have opposite answers.

**Does disagreement predict error? Yes, strongly.** AUC of the normalised distance between
dots.mocr and PP-OCRv6 medium against dots.mocr's own measured CER:

| predicting | AUC | positives |
| --- | --- | --- |
| CER > 5% | **0.972** | 43 of 81 |
| CER > 10% | 0.946 | 21 of 81 |
| CER > 20% | 0.934 | 7 of 81 |

**And it is not merely detecting the degraded tier**, which was the obvious objection since
degraded pages both disagree more and read worse. Split each tier at *its own* median CER,
so the tier is held constant: clean **0.936** (n=38), degraded **0.933** (n=37). Within a
tier, the disagreement still ranks the worse half above the better one — a stronger signal
than the 0.843 the router's region count gives for a coarser question. On the tabular tier it
inverts (0.167, n=5), which five pages cannot settle either way.

AUC is reported instead of a threshold, deliberately and for § Step 4's reason: a cut-off
fitted to the 81 pages it is scored on is the party-type mistake.

**Can the flagged pages be reviewed? No, by two to three orders of magnitude.** The same
distances, as a flag rate, against the census's 247,923 image-only pages and the review
budget `ocr-plan.md` records — about fifty pages a week:

| flag when distance > | pages flagged | share | at 50 a week |
| --- | --- | --- | --- |
| 0.05 | 149,978 | 60.5% | 58 years |
| 0.10 | 101,006 | 40.7% | 39 years |
| 0.20 | 48,972 | 19.8% | 19 years |
| 0.30 | 21,425 | 8.6% | 8 years |
| 0.50 | 12,243 | 4.9% | 4.7 years |

There is no threshold that both catches the errors and fits the budget, because the
disagreement is not rare: its median is **0.078** overall and **0.158** on the degraded tier.
Two engines reading a faint photocopy differ on roughly a sixth of its characters, and most
of that difference is real error in one of them — which is what the AUC says.

**So the signal is good and the queue is impossible, and that is a design finding rather than
a measurement failure.** A review layer that must clear its queue cannot use this. A review
layer that *ranks* — the operator reviews the worst fifty pages this week, for as long as it
is worth doing, and the rest publish with a stated confidence or do not publish at all — can
use it exactly as measured. Which of those the record is choosing is the operator's, and
neither `ocr-plan.md` nor ADR 0021 currently says.

**Two cautions.** The pair matters: dots.mocr against dots.ocr — the same family, one
rebranded from the other — has a median distance of **0.003** and a much weaker AUC (0.792),
so two readings from one lineage agree by construction and measure little. And PP-OCRv6 as
the second reader is the cheap choice (0.4 s a page) rather than the best one; PaddleOCR-VL
gives a slightly lower flag rate (46.9% at 0.05) at 1.3 s.

## Are these the right versions, run the right way?

Asked deliberately 2026-09-01, because two engines had already been caught running wrongly —
PaddleOCR-VL fed whole pages when it is an element recogniser, and HunyuanOCR given an English
prompt that silently selected its `layout` task and returned no text at all. A figure from a
misconfigured engine is worse than no figure.

**Versions confirmed current**: PaddleOCR-VL **1.6** (`_DEFAULT_PIPELINE_VERSION`, newest of
`v1`/`v1.5`/`v1.6`; a live instance reports `pipeline_version = v1.6`, which maps to
`PaddleOCR-VL-1.6`, and the pipeline requests `PaddleOCR-VL-1.6-0.9B` from the server) with
**PP-DocLayoutV3**, the newest layout model; **dots.mocr**, which is dots.ocr-1.5 rebranded;
**HunyuanOCR** at the 1.5 weights; Tesseract 5.5.0; docTR 1.1.0. PaddleOCR's own tutorial
recommends the full pipeline plus a dedicated VLM service, which is what is run here, and
documents `use_doc_orientation_classify` and `use_doc_unwarping` as defaulting to off, which
is how they were left.

**The package default was checked rather than trusted, and it held.** `PaddleOCR()` resolves
to PP-OCRv6 medium — the largest of the v6 line (tiny/small/medium) — but `PP-OCRv5_server`
models also exist and are larger. Both alternatives are worse:

| PP-OCR configuration | CER | clean | degraded | dockets | dates |
| --- | --- | --- | --- | --- | --- |
| **v6 medium, preprocessing off** | **11.8%** | **2.6%** | **17.9%** | 91.2% | **90.2%** |
| v6 medium, preprocessing on | 12.3% | 4.4% | 18.8% | 82.4% | 85.8% |
| v5 server det+rec | 13.4% | 3.7% | 20.0% | **94.1%** | 53.3% |

**PaddleOCR's own preprocessing hurts this corpus** — page orientation, unwarping and textline
orientation together take the clean tier from 2.6% to 4.4% and drop docket recall nine points.
That is a result for the preprocessing question below, not just a configuration note: the
obvious preprocessing is not free, and on scans of this kind it costs.

**And the runs now record what produced them.** Until 2026-09-01 a run file said
`"engine": "ppocr"` and nothing else — no weights, no flags, no versions — so a published
figure could not be checked against the engine that made it, and a package default that moved
between releases would break the link silently. `ocr_run.py` writes a `run.json` beside the
text (weights, flags, package versions, host, timestamp) and `ocr_score.py` copies it into the
scored output. **The runs above predate that record**; the free engines can be re-run to
backfill it.

**Still open.** The tabular tier rests on five pages and the graphic tier on nine — both too
thin to conclude from, and drawing more needs fresh ground truth the operator checks; the
tabular routing above cannot be settled without it. Preprocessing is not evaluated at all,
though the greyscale runs are one result in that direction — greyscale took Claude from 6.6%
to 5.9% and changed Textract by nothing, which is itself evidence that preprocessing has to be
measured per engine class rather than chosen once. The pages are rendered at **150 DPI** where
the usual floor is 300, and `ocr_page_images.py` records that content occupies only 55–76% of
the render on half the sample while explicitly deferring cropping as "a step 2 preprocessing
variable to measure".
