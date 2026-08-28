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
| clean | 62 | 35 | Typescript or laser print, level, good contrast |
| degraded | 40 | 37 | Fax headers, RECEIVED stamps over text, faint or skewed copies, dense small print, two handwritten letters, a photocopied form |
| tabular | 7 | 7 | True tables and forms (a rotated dwell-time table, an errata table, a corrections list, a motor-carrier detail form, an e-mail header block) |
| graphic | 12 | 10 | Maps and exhibits with labels only — kept to measure *false text*, which the plan did not foresee |
| blank | 1 | 1 | A near-blank scan |

Tables are scarce in a random draw of pages (7 of 122). The plan asked for thirty; the
seven are kept and a **targeted top-up** of tabular pages is a step-1 follow-up, not a
reason to hold the rest.

## The transcriptions (drafted, awaiting the operator's check)

`ground-truth-draft/<png>.txt` — one file per selected page, drafted 2026-08-28 by a model
(Claude Fable 5, one pass per page under the rules below) from the rendered page image.
**They are ground truth only after the operator checks each against the page image**, as
`benchmark/labels.csv` was for extraction. Rules the drafter followed, which the checker
applies too:

- verbatim — spelling, capitals, punctuation, numbers, one printed line per line, a blank
  line between paragraphs; nothing corrected, expanded or summarised; docket numbers and
  dates character-exact;
- tables: one row per line, cells separated by a tab;
- `[illegible]` for a word, `[illegible: N words]` for a run — never a guessed docket
  number or date;
- stamps, seals, handwriting, signatures in square brackets with a label
  (`[stamp: RECEIVED AUG 17 2004 OFFICE OF PROCEEDINGS]`, `[handwritten: 211823]`,
  `[signature]`); a handwritten page transcribed under a first line `[handwritten page]`;
- a map or exhibit: every legible label, one per line, under `[graphic page]`; a page with
  no text: exactly `[blank page]`; rotated text under `[rotated page]`, in reading order.

The rendered pages themselves (37 MB) are not committed; they are at
`/data/docketyard/ocr/sample/pages/` on RMI-AI-MACHINE and `data/ocr/pages/` on the
working machine, and any page can be re-rendered from its hash with `ocr_sample.py`.

## What the check produces

A checked file replaces the draft in place; the operator's changes are the interesting
rows and are worth a note in `CHECK-NOTES.md` (what kind of thing the drafter got wrong).
Step 2 — every candidate engine over the same 90 pages, scored by CER, WER and by
docket-number and date errors per tier — starts when the check is done.
