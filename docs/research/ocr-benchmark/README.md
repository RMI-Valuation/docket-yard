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
| clean | 63 | 36 | Typescript or laser print, level, good contrast |
| degraded | 40 | 37 | Fax headers, RECEIVED stamps over text, faint or skewed copies, dense small print, two handwritten letters, a photocopied form |
| tabular | 7 | 7 | True tables and forms (a rotated dwell-time table, an errata table, a corrections list, a motor-carrier detail form, an e-mail header block) |
| graphic | 11 | 9 | Maps and exhibits with labels only — kept to measure *false text*, which the plan did not foresee |
| blank | 1 | 1 | A near-blank scan |

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

## The transcriptions (drafted, awaiting the operator's check)

`ground-truth-draft/<png>.txt` — one file per selected page, **90 files, 137,096 characters**,
drafted 2026-08-28 by a model (Claude Fable 5, one pass per page, one agent per page) from
the rendered page image. Density by tier: clean ~1,370 characters a page with 4 `[illegible]`
marks in all; degraded ~1,890 with 72; tabular ~1,130 with 1; graphic ~1,130 with 15; the
blank page is `[blank page]`.
**They are ground truth only after the operator checks each against the page image**, as
`benchmark/labels.csv` was for extraction. Rules the drafter followed, which the checker
applies too:

- verbatim — spelling, capitals, punctuation, numbers, one printed line per line, a blank
  line between paragraphs; nothing corrected, expanded or summarised; docket numbers and
  dates character-exact;
- tables: one row per line, cells separated by a tab;
- `[illegible]` for a word, `[illegible: N words]` for a run — never a guessed docket
  number or date;
- **a fragment of another page** caught in the scan — a facing page whose margin the
  scanner captured, cut off at the edge — is transcribed verbatim inside
  `[adjacent page]` … `[end adjacent page]`, with `[cut]` where each line runs off the
  edge. `[cut]` is a different fact from `[illegible]`: the text is not unreadable, it is
  *not on this page*. **A cut line is never completed**, however obvious the ending;
  `[cut]` also marks this page's own text where the scan lost it at an edge or a tear;
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

**From anywhere**, the queue at
<https://claude.ai/code/artifact/664789dc-93ce-42b2-b23e-fe56c6c7d8f7> (private to the
operator, published 2026-08-28): one page at a time, the scan at **full
resolution beside the transcript** — scroll to zoom, drag to pan, double-click for one
screen pixel per scan pixel, `w` to give the page the full width — with the Board's own
file one click away at `docketyard.org/document/<sha>.pdf#page=N`, since every sampled
document already answers at its permanent address. The pages are embedded by
`tools/rmi-ai-machine/ocr_page_images.py` as 1-bit PNGs at the render's own 150 dpi — 2.3 MB
for all ninety — and **trimmed to the scan itself**. A 150 dpi render is the whole PDF page,
often legal-size or oversized with the scan in one corner: measured 2026-08-29, the content
is 55–76% of the render on half the sample, so fitting the page fitted mostly white and the
type came out small (reported by the operator the same day). Blank margins and the scanner's
solid black bars are trimmed from the edges inward, never from the middle, counting ink on
the thresholded image rather than brightness on the grey one — trimming on brightness clipped
the right edge off a light-toner letter, since a column of faint glyphs still averages
near-white. Measured after the fix: 0.2% of ink lost on average, and the worst case (15%) is
a solid black scanner bar, not text. With the trim and a wider column the type is about
twice the size it was.
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
| **Table grid** (tabular tier) | Rows merged into one line, or cells not separated by tabs; a table's grid is meaning, not layout preference, so it is compared cell by cell as well as flowed |
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
Step 2 — every candidate engine over the same 90 pages, scored by CER, WER and by
docket-number and date errors per tier — starts when the check is done.
