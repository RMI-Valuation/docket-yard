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

**From anywhere**, the queue at
<https://claude.ai/code/artifact/664789dc-93ce-42b2-b23e-fe56c6c7d8f7> (private to the
operator, published 2026-08-28): one page at a time, the scan at **full
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

Step 2 — every candidate engine over the same 90 pages, scored by CER, WER and by
docket-number and date errors per tier — starts when the check is done.
