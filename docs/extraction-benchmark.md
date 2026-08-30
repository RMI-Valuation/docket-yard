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

## Step 2 results (2026-08-29)

Two extractors over the sixty labelled decisions, scored by `benchmark_score.py` under the
settled conventions — citations as sets of `(decision, target)`, each `target_kind` apart:

| extractor | input | STB citations | courts | dated deadlines | **docket-shaped** (recall / precision) |
|---|---|---|---|---|---|
| qwen3:14b (local, free), old prompt | text layer | 72.3% | 29.1% | 96.7% | 85.8% / 95.1% |
| Claude Sonnet 5 | text layer | **89.8%** | 97.7% | 98.9% | **95.6% / 95.6%** |
| Claude Sonnet 5 | **OCR of the same pages** | **91.9%** | 97.7% | 98.9% | 96.4% / 95.6% |
| qwen3:14b, **current prompt** (2026-08-30) | text layer | 87.0% | 74.4% | 84.4% | 93.8% / 93.8% |
| **regex + registry, "own docket" rule — no model** (2026-08-30) | text layer | 64.2% | — | — | **95.1%** / 88.1% |

All rows are scored as of 2026-08-30 with the **on-page check** (a finding whose quoted
passage is not in the decision's text is dropped — 2 of Claude's, 97 of qwen3's) and the
scorer's docket-suffix fix (`AB 1296X` now keys as a docket; the docket-shaped truth is
225 targets, not 220). Earlier figures in this document and in `ocr-plan.md` (89.2%,
95.9% / 95.5%) predate both and differ by under a point.

On the **docket-shaped** class — what a citator resolves — three things were measured:

- **The local model is close.** qwen3:14b on the current prompt scores 93.8% / 93.8%
  against Claude's 95.6% / 95.6%, in 102 minutes on the box at no cost. Before the on-page
  check its precision read 88.8%: 13 of its extras were **verbatim copies of the prompt's
  own worked examples** (`FD 36732`, `EP 787`) on pages where that text does not exist —
  a small-model failure, and the reason the check exists. What remains weaker is courts
  (74% vs 98%) and dated deadlines (84% vs 99%). It is the first of a batch of nine local
  candidates (`tools/rmi-ai-machine/benchmark_batch.sh`).
- **The docket class needs no model.** `benchmark_regex.py` — a pattern over the text
  layer, validated against the registry, with one rule: a hit is a caption only when it
  is the citing decision's own proceeding *and* no document word sits near it — finds
  95.1% of docket-shaped targets (214 of 225; 94.7% before the scorer's quote matcher was
  corrected on 2026-08-30, which had been case-folding away its own exceptions). Its 29 extras are own-proceeding mentions,
  which ADR 0017's projection rule absorbs; its 12 misses are the six registry
  unresolvables (ICC-era `EP 445`, `FD 757`, …) and four same-docket prior decisions with
  no document word in the window. The keyword window alone, without the own-docket rule,
  is a poor classifier (79.6%): the record already knows which proceeding a decision sits
  in, and that is the one thing regex should not be asked to decide.
- **So the paid extractor earns its keep on the other forms** — reporter cites, `decision
  served …` phrases, court citations, deadlines, and the role of a same-docket mention —
  not on docket numbers. ADR 0017 § Amendment candidates records what that changes.

Two things follow, and the second was not expected.

**The extractor is the whole game.** Nearly 16 points of citation recall separate a local
14B from a frontier model on identical clean text — five times the spread between the best
and worst OCR engines. A citator that misses a quarter of its edges is not a lower-quality
citator; it is a different product.

*(The old-prompt qwen3:14b row is the run made before `target_kind` existed, scored through
the scorer's fallback; the same model on the current prompt reads 87.0%, so most of the
"16 points" was the prompt and the instrument, not the model. Corrected
2026-08-30. qwen3's figure first read 60.2%, and a 29-point gap was published
here and in `ocr-plan.md` on the strength of it. The scorer's fallback for a run made before
`target_kind` existed was routing prior-decision citations into captions — the very
misclassification the conventions had just reversed. A third of the gap was the instrument.)

**OCR costs the citator nothing measurable.** Extraction over Textract's output recovers as
many citations as extraction over the publisher's own text layer. A citation is a long,
redundant, structured string, and a 10.8% character error rate rarely destroys one. This is
a **lower bound** — the sixty are born-digital, so their renders are cleaner than a real
scan — but it is a bound of *no measured damage*, which leaves headroom before degradation
would begin to matter. `benchmark_ocr_text.py` builds that OCR side.

Precision was not reported until the operator had checked the sheet (2026-08-30): a real
citation the drafter passed over scored as a false positive against it. Read after the
check, over the text layer: STB citations **64.6%** (Claude) and 44.3% (qwen3:14b, current
prompt), and on docket-shaped STB targets alone **95.6%** — the split ADR 0017 is built on.
Most of the headline loss is reporter cites, pin-cite short forms and `decision served …`
phrases the sheet folds, none of which resolves to a docket.

## Step 3 — the decision (drafted 2026-08-30, ADR 0017 Proposed)

Recorded as an ADR: which method ships, at what confidence, and what is left to a human.
"Local is good enough" and "API for the hard tier, local for the routine tier" are both
acceptable outcomes; "ship without measuring" is not.

**Drafted:** `adr/0017-citation-edges-ship-from-the-api-extractor-at-measured-confidence.md`.
The API extractor ships; the local model does not write edges. The figure that decides it
was read only after the operator's check of the sheet (2026-08-30): on **docket-shaped
targets** — what a citator resolves — Claude scores 95.9% recall and 95.5% precision, and
all ten extras are the citing decision's own proceeding read as a citation; none is an edge
to a docket the decision never touched. The 64.2% headline precision is mostly reporter
cites, pin-cite short forms and `decision served …` phrases the sheet folds, not wrong
dockets. Six of 166 distinct docket targets fail the registry — the same six the checked
sheet holds — so the extractor invents none. Confidence is the measured precision of an
edge's class, not the model's opinion; the review queue takes the short-sequence dockets,
the in-range unresolved and the same-docket citations that do not resolve to a decision.

> Step 1 note (2026-08-26): the tabled UP–NS tracker holds 988 hand-checked documents in FD 36873 — 33 decisions among them — with a tiering scheme (A/B/C) worth reading before designing routing here; see `upns-tracker-inheritance.md`. Its page-capped extraction makes labels from long exhibits weaker evidence.

> Step 0 re-run 2026-08-26 on waves 2–3's first 9,663 new files: **1,480 image-only** (15%, against 2 of 4,273 in wave 1) — the older record is substantially scanned, which is M3's question and bounds what step 2 can read without OCR. Step 2's local candidate (qwen3:14b) ran over all 60 sampled decisions on 2026-08-26 in 2 h 07 m; output at `/data/docketyard/benchmark/runs/qwen3-14b/`, unscored until the labels are checked.
