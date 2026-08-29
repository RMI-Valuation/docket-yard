# The extraction benchmark — plan

> **Status: plan, 2026-08-26.** The roadmap's background item: before any extraction pass
> commits to local output on RMI-AI-MACHINE, measure local models against an API model on
> a hand-labelled sample. Nothing here publishes anything; it decides what the citator and
> the docket calendar will be built on.

## What it gates

Two capabilities need text read from documents: the **citator** (citations from decision
text — "cited by", negative treatment; validation query 2) and the **docket calendar**
(deadlines *as set by decisions*, quoted with provenance; interface.md). Both are derived
assertions under ADR 0007 and must name their method and version. The benchmark chooses
the method.

## Step 0 — the text layer (running first, no model)

`tools/rmi-ai-machine/extract_text.py` pulls every held PDF's text per page with a named
tool and version, and flags image-only files. This is groundwork every option needs, it
measures the OCR burden directly (stb-data-source.md estimated ~1% image-only for modern
files), and it costs no model time. Output stays on the box beside the blobs until the
internal API exists to carry assertions back (architecture.md § seam).

## Step 1 — the sample (drawn 2026-08-26; drafted, awaiting the operator's row check)

Sixty decisions, drawn from the two years wave 1 holds, stratified: 20 with many citations
(rate cases, merger decisions), 20 routine (abandonment exemptions, notices), 20 short
orders. For each, the operator (or a reviewer the operator trusts) labels by hand:

- every **citation** to a decision, in the form printed, typed `stb`, `court` (a court
  case) or `record` (a filing in this proceeding, where the docket number is an address
  rather than the target). A prior decision counts **even when it sits in this decision's
  own docket** — it is a different document, and citing it is a real edge;
- every reference to the decision's own proceeding named as **itself**, naming no document
  — caption, heading, table header, a bare docket number, the all-pleadings paragraph —
  typed `caption`/`self`. These are not edges in the citation graph. They are labelled
  because telling one from a citation is the task, and they are the sheet's only negative
  examples. The test is *document versus proceeding*: `Docket No. EP 787` is a caption,
  `NPRM, EP 787, slip op. at 4` is a citation;
- every **deadline** the decision *sets*, as the sentence that sets it plus, where the page
  prints one, the date. Where it does not, the target is typed rather than left blank:
  `reference` (an effective date that is the service date), `period` (only a period is
  printed, so the sentence is the whole answer) or `indefinite` (until further order, or
  tolled by a lapse in appropriations). A date is quoted, never computed.

The conventions behind those types were settled 2026-08-29 and are recorded, with what each
one costs, in `docs/research/benchmark/README.md`. Labels are the truth; a model that finds
more than the labels is checked against the PDF, not trusted.

## Step 2 — the runs

The same prompt and the same output schema (JSON: citations, captions and deadlines, each
with its page, its quoted text and its `target_kind`) against:

- local, on RMI-AI-MACHINE via Ollama: a 14B-class dense model and a ~30B MoE, thinking
  disabled per request (TODO's note: Qwen3 thinks by default and pays for a monologue);
- an API model as the reference.

Scored per field: precision, recall, and — the one that matters for provenance — whether
the quoted sentence actually appears on the cited page. A right answer with a wrong
location is wrong. Three rules follow from the settled conventions:

- **Citations are compared as sets of `(decision, target)` pairs**, not as lists of
  occurrences. A repeat adds no edge, so an engine is neither rewarded for finding every
  short form nor penalised for finding them. Deduplicated, the sheet holds 360 STB edges,
  86 court and 7 record.
- **Each target kind is scored on its own.** Court targets cannot be validated against the
  docket registry and stay out of the citator's first slice, so folding them into one
  recall figure would flatter or punish an engine for something the product does not use.
- **Captions are a precision test.** An engine that emits a bare docket number as a
  citation is wrong, and the 86 caption rows are what catches it. They are the sharpest
  probe in the sheet: separating `Docket No. EP 787` from `NPRM, EP 787, slip op. at 4`
  is the distinction the citation graph is built on.

## Step 3 — the decision

Recorded as an ADR: which method ships, at what confidence, and what is left to a human.
"Local is good enough" and "API for the hard tier, local for the routine tier" are both
acceptable outcomes; "ship without measuring" is not.

> Step 1 note (2026-08-26): the tabled UP–NS tracker holds 988 hand-checked documents in FD 36873 — 33 decisions among them — with a tiering scheme (A/B/C) worth reading before designing routing here; see `upns-tracker-inheritance.md`. Its page-capped extraction makes labels from long exhibits weaker evidence.

> Step 0 re-run 2026-08-26 on waves 2–3's first 9,663 new files: **1,480 image-only** (15%, against 2 of 4,273 in wave 1) — the older record is substantially scanned, which is M3's question and bounds what step 2 can read without OCR. Step 2's local candidate (qwen3:14b) ran over all 60 sampled decisions on 2026-08-26 in 2 h 07 m; output at `/data/docketyard/benchmark/runs/qwen3-14b/`, unscored until the labels are checked.
