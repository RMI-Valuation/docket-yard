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
| qwen2.5:14b (2026-08-30) | text layer | 81.0% | 74.4% | 82.2% | 87.6% / 90.0% |
| gemma3:12b (2026-08-30) | text layer | 78.9% | 86.0% | 88.9% | 89.3% / 87.8% |
| phi4:14b (2026-08-30) | text layer | 82.2% | 66.3% | 87.8% | 86.7% / 93.8% |
| llama3.1:8b (2026-08-30) | text layer | 72.9% | — | — | 76.0% / 73.1% ‡ |
| mistral-nemo:12b (2026-08-30) | text layer | 59.0% | — | — | 64.4% / 91.8% |
| qwen3:30b-a3b MoE (2026-08-31) | text layer | 83.1% | — | — | 92.4% / 91.2% |
| gpt-oss:20b MoE (2026-08-31) | text layer | — | — | — | **no usable output** ‡‡ |
| **regex + registry, "own docket" rule — no model** (2026-08-30) | text layer | 64.2% | — | — | **95.1%** / 88.1% |

‡‡ gpt-oss:20b answered all 443 pages in 8 minutes and returned **nothing readable on
every one of them** — an empty response, which the runner parses to a page with no
`findings` key at all. Scored naively that is a clean 0%, indistinguishable from an engine
that finds no citations; the scorer now separates *answered nothing* from *found nothing*
and says so. The cause is the harness meeting a reasoning model whose output shape Ollama's
`format` constraint does not fit — not a measurement of the model, and it is recorded as
untested rather than as a zero.

‡ llama3.1:8b **timed out on 41 of its 443 pages** — 9% of the sample answered nothing, so
its figures are a floor, not a measurement. The cause is the run's own shape: the schema is
forced through Ollama's `format`, and a small model that cannot satisfy the grammar loops
until the 600-second timeout. Inference took 61 minutes; the wall clock was 471, and the
410-minute difference is 41 timeouts exactly. The scorer now prints and records the count,
so a run that answered nothing on part of the sample can never again read as a weak engine.

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
### The role classifier, measured 2026-08-31 — the second half, and the answer

`benchmark_roles.py` fixes the finder (regex + registry) and asks a model one question per
hit: does the text name a DOCUMENT, only the PROCEEDING, or a FILING? Recall is capped at
the regex's own, so what this measures is the judgement.

| classifier over the same regex hits | docket-shaped recall | precision |
|---|---|---|
| **the record's own-docket rule — no model** | **95.1%** | 88.1% |
| llama3.1:8b | **96.9%** | 79.3% |
| qwen3:14b | 83.1% | **95.9%** |
| the keyword window — no model | 79.6% | 86.9% |

Both models beat the keyword window, so a model *does* judge better than a word list. But
neither beats **the record's own knowledge**: the own-docket rule wins on the combination
because it is not judging at all — it reads which proceeding the deciding decision is
entered in, which the model is never told. qwen3:14b is the most cautious judge (95.9%
precision, the best figure any engine reached on this class) and pays 12 points of recall
for it by calling 488 hits captions; llama3.1:8b calls 667 of them citations and buys the
highest recall of anything measured at the cost of precision. The pair bracket the
own-docket rule rather than beating it.

**So the shape holds end to end**: find with a regular expression, decide with the record,
and buy a model only for what neither can do.

- **So the paid extractor earns its keep on the other forms** — reporter cites, `decision
  served …` phrases, court citations, deadlines, and the role of a same-docket mention —
  not on docket numbers. ADR 0017 decision 1 records what that changes (the pre-split § Amendment candidates is in git).

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

**Drafted:** `adr/0017-citation-edges-ship-at-measured-confidence.md` (what ships, at what confidence) and `adr/0018-the-citation-assertion-families.md` (the shape that holds it) — split 2026-09-01.
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

## Local models as reviewers — measure first (the operator's decision, 2026-09-11)

The citator's first load held 1,945 keys for a person (1,476 after the line-wrap fix). The
operator asked whether local models on the fleet, checking one another, could take the first
pass. The table above already shows the two role classifiers erring in opposite directions:
qwen3:14b at 95.9% precision and llama3.1:8b at 96.9% recall. So the question is what their
agreement is worth, and that has not been measured. **Decided: measure before the review page
is designed.**

1. Score the stored role runs (`runs-roles/`) for agreement: the precision of the keys both
   models call a citation, and how many keys that covers.
2. Run two or three models over the 225 checked targets. Ask each the review question
   ("which docket, sub-docket and document?") and hand it the candidates the record holds:
   the registry's dockets, and the decisions served on the printed date. Report each model
   and the pair.

**Step 1 measured, 2026-09-11.** The two stored role runs were combined hit by hit, then
scored as `(decision, target)` pairs on the 225 docket-shaped targets (the page check on):

| Bucket | Pairs | Real citations | Not citations |
|---|---|---|---|
| Both say citation | 197 | 189 (95.9%) | 8 |
| Both say caption | 38 | 8 | 30 (78.9%) |
| They split: to a person | 95 | 38 | 57 |

(17 pairs fall in two buckets, split across pages. The 6 targets the regex never hit are in
none.) **Agreement is no more precise than qwen3:14b alone**: 95.9% on 197 pairs, against its
95.9% on 195. And the two dismiss 8 real citations as captions. Agreement would clear 71% of
pairs and leave 29% to a person, but both of its answers fall short of the card's 98.2%
projected precision. That is on the old question, though: "document or proceeding?" with no
record behind it. Step 2 asks the review question and hands over the candidates, and that is
where the answer lies.

**Step 2 runs on every machine (the operator's decision, 2026-09-11).** The sixty decisions
hold 768 mentions, and the Mac mini takes 2.3 s a mention with qwen3:14b. llama3.1:8b, the one
model that fits on all four boxes, runs over all 768 on the Mac, RMI-AI-MACHINE, the Jetson and
the NUC (on its CPU, at low priority), with qwen3:14b too wherever it fits. Two things are
measured. The first is the pace on each box. The second is whether the same model, weights
and temperature give the same answers on Metal, CUDA and CPU. If they don't, the host is part
of a model judgement's method key, as another engine is already another pass
(`compute-fleet.md`).

**Measured the same day: llama3.1:8b does not fit on the Jetson.** It needs 5,027 MiB of GPU
memory, and only about 4,460 MiB of the Orin's 7.3 GiB of shared memory is free once the
system has its share. Ollama tried to load it again on every request (89 requests, load
average 13) until the run was stopped. **The Jetson runs qwen3:4b instead** (the operator's
decision, 2026-09-11), and the Mac runs it too, so the Metal-and-CUDA comparison still has a
Jetson half.

**qwen3:4b measured on the Jetson, 2026-09-11.** It kept the Mac's pace, 2.89 s a mention
(the Mac's qwen3:14b: 2.75 s), and 13 of 768 requests failed as its model process restarted
under memory pressure. But it is too cautious to review: on "is it a citation" it scored
91.8% precision and 29.8% recall, and on "which document" 34 of the 35 it named are right
(97.1%), at 23.1% recall. qwen3:14b on the Mac scored 91.0% / 81.3% on the first question and
88.5% / 78.9% on the second. **Two more runs (the operator's decision, the same day):**
gemma3:4b on the Jetson, to tell the small size from the model family, and gemma4:e4b on the
Mac. gemma4:e4b is 9.6 GB, so it cannot run on the Jetson. NVIDIA's nemotron-3-nano:4b (2.8 GB)
follows gemma3:4b on the Jetson, at the operator's suggestion.

**The same model does not answer the same way on different machines (measured 2026-09-11).**
Each run used the same weights, temperature 0 and the same prompt, and was compared mention by
mention over the whole answer — the kind, the docket and the document named:

| Model | Machines | Identical answers | Pace, seconds a mention |
|---|---|---|---|
| qwen3:14b | Mac (Metal) vs RMI's 4070 (CUDA) | 96.5% (27 of 768 differ) | 2.75 vs 0.74 |
| qwen3:14b | Mac vs the NUC's CPU (224 mentions) | 92.0% | 2.75 vs 22.70 |
| qwen3:4b | Mac vs the Jetson's Orin (CUDA) | 90.4% | 0.99 vs 2.89 |
| llama3.1:8b | Mac vs RMI's 4070 | 89.1% | 1.48 vs 0.41 |
| llama3.1:8b | Mac vs the Jetson, headless | 88.4% | 1.48 vs 3.29 |
| llama3.1:8b | Mac vs the NUC's CPU | 88.0% | 1.48 vs 11.40 |
| llama3.1:8b | the Jetson vs RMI's 4070 | 87.2% | 3.29 vs 0.41 |
| llama3.1:8b | the NUC vs RMI's 4070 | 86.3% | 11.40 vs 0.41 |
| llama3.1:8b | the Jetson vs the NUC | 83.7% | 3.29 vs 11.40 |
| nemotron-3-nano:4b | the Jetson, desktop on vs headless (224) | 87.9% | 3.73 vs 3.24 |

**The bigger the model, the steadier it is across machines**: qwen3:14b holds 96.5% between
two GPUs, llama3.1:8b 83.7–89.1% across four boxes. So if a model's judgement is ever stored,
**the machine is part of its method key**, just as another OCR engine is another pass.

(The 91.9% recorded earlier for qwen3:4b was taken before the later runs landed; recomputed
over the whole answer it is 90.4%. On the citation question alone the two hosts agree 97.0%.)

RMI's 4070 was the fastest reviewer by far, at 0.41 s a mention for llama3.1:8b and 0.74 s for
qwen3:14b — the whole 768 in under ten minutes. The NUC's CPU is 28–31× slower than that same
4070 on the same weights: 11.40 s a mention for llama3.1:8b, and 22.70 s for qwen3:14b, which
is 17 minutes for one decision. **qwen3:14b on the NUC was stopped at 5 of 60 decisions
(the operator's decision, 2026-09-11): its pace is the finding, and 11 further hours would
not have changed it.** A CPU-only box is not a reviewer, whatever it scores.

**Step 2 measured in full, 2026-09-11** — twelve complete runs of all sixty decisions, scored
against the 225 checked docket-shaped targets and, for the document, against the work sheet
(147 documents over 148 pairs, 8 of them where stopping was right):

| Run | Host | Is it a citation? P / R | Which document? P / R | s/mention |
|---|---|---|---|---|
| **the record's own rules** | **no model** | **87.2 / 99.6** | — | — |
| gemma4:e4b | Mac | 95.7 / 88.0 | 86.7 / 61.9 | 1.47 |
| qwen3:4b | Mac | 92.4 / 32.4 | 97.4 / 25.2 | 0.99 |
| qwen3:14b | RMI's 4070 | 91.9 / 80.9 | 90.6 / 78.2 | 0.74 |
| qwen3:4b | the Jetson | 91.8 / 29.8 † | 97.1 / 23.1 | 2.89 |
| qwen3:14b | Mac | 91.0 / 81.3 | 88.5 / 78.9 | 2.75 |
| gemma3:12b | Mac | 85.8 / 93.8 | 76.2 / 89.1 | 3.63 |
| llama3.1:8b | Mac | 80.1 / 68.0 | 77.1 / 57.1 | 1.48 |
| llama3.1:8b | RMI's 4070 | 79.3 / 69.8 | 77.5 / 58.5 | 0.41 |
| llama3.1:8b | the Jetson, headless | 79.3 / 68.0 | 77.4 / 55.8 | 3.29 |
| llama3.1:8b | the NUC's CPU | 76.1 / 70.7 | 73.9 / 57.8 | 11.40 |
| gemma3:4b | the Jetson | 76.4 / 68.9 † | 58.7 / 48.3 | 4.83 |
| nemotron-3-nano:4b | the Jetson, headless | 70.7 / 51.6 | 75.3 / 39.5 | 3.24 |

† **A floor, not a measurement.** 59 of gemma3:4b's 768 mentions and 13 of qwen3:4b's
never reached the model: Ollama answered HTTP 500 as the model process restarted under the
Orin's memory pressure, with the desktop up. Even if every one had been answered perfectly,
gemma3:4b reaches 76.9% recall and qwen3:4b 34.7%, so neither can approach the rules and
re-running them was declined (2026-09-11). Every other run in the table is complete.

**No single model replaces the record's own rules** — but replacing them was never the job.
The finder alone recalls 99.6% of the real citations at 87.2% precision. The best model recall
is gemma3:12b's 93.8%, six points short, and the best precision, gemma4:e4b's 95.7%, costs
twelve points of recall. Every model except gemma3:12b finds fewer real citations than the
rules do. **Read as candidates for the finder's job, none of them is one.**

**That is the wrong question, and the first draft of this section asked it** (corrected
2026-09-11, on the operator's challenge). The rules are not up for replacement: they have
already found these citations, and every one of the 257 pairs they call a citation goes to a
person today. The question the review page turns on is whether agreement between models can
CLEAR part of that queue — publish without a person — and that is a filter on the rules'
output, not a competitor to it.

**Measured as a filter, agreement clears.** A key clears only when every model in the panel
agrees on both halves: that the mention is a citation, and which document it names. Scored
over the 148 of the rules' 257 pairs that the operator settled on the work sheet:

| Panel | Clears | Right | Wrong | Precision | Queue cut |
|---|---|---|---|---|---|
| gemma4:e4b + qwen3:14b | 70 | 70 | 0 | 100.0% | 47.3% |
| gemma4:e4b + qwen3:14b + gemma3:12b | 64 | 64 | 0 | 100.0% | 43.2% |
| qwen3:14b + gemma3:12b | 93 | 92 | 1 | 98.9% | 62.8% |
| gemma4:e4b + gemma3:12b | 71 | 70 | 1 | 98.6% | 48.0% |

Two models agreeing settle about half the queue with no error in this sample, or 63% with one.
Agreement is also a good filter on the rules' own mistakes: where gemma4:e4b and qwen3:14b both
say citation, **28 of the rules' 33 false positives are caught** and do not clear. And the
document half is where agreement earns the most — the two models name the same document 70
times and are right 70 times, against 88.5% and 86.7% for those models taken singly.

**Two things bound this, and neither is fatal.** First, **a clean run does not establish what
it looks like**: 70 of 70 has a 95% lower bound of 94.8%, and 92 of 93 one of 94.2% — both
under the 98.0% the citation class already ships at. This is the wall the work card hit at
106 of 106, where the operator's decision was to store the raw figure and show a reader no
number. Second, **these 148 pairs are a sample of the record, not of the queue**: the 1,476
exposed keys are exposed because something about them was uncertain, so they are a harder
population by construction and these figures are most likely a ceiling. **Decided 2026-09-11:
run the panel over all 1,476 before any clearing rule is written**, and score it on a slice
the operator checks.

**The models stray from the candidate list they are handed, and straying is the model's
property, not the machine's.** Each was given the registry's dockets and the decisions served
on the printed date, and asked to pick from them. Naming something that was never offered:

| Model | Names a docket not offered | Names a decision not offered |
|---|---|---|
| qwen3:14b | 0.3–0.4% | 2.9–3.8% |
| gemma3:12b | 1.0% | 21.1% |
| gemma4:e4b | 1.8% | 5.7% |
| gemma3:4b | 3.8% | 28.4% |
| llama3.1:8b | 12.1–12.5% | 9.8–11.7% |
| nemotron-3-nano:4b | 16.1% | 15.8% |
| qwen3:4b | 31.5% | 0.0% |

The ranges are the same model on different hosts, and they barely move — llama3.1:8b strays on
the docket 12.1% on the Mac, 12.1% on the 4070, 12.4% on the Jetson and 12.5% on the NUC, while
its *answers* differ between those hosts on 11–16% of mentions. The machine changes which
answer comes out; it does not change the model's discipline. qwen3:4b's 31.5% is the extreme:
it almost never invents a decision id but rewrites the docket number a third of the time, which
is why its recall is 32.4% while what it does name is 97.4% right.

**The 8B model could not run beside the Jetson's desktop at all.** Its one attempted decision
returned 88 empty answers. Headless, the same weights answered all 768 at 3.29 s a mention —
recorded in `compute-fleet.md`. nemotron-3-nano:4b, small enough to load either way, agrees
with itself 87.9% across that boundary: even freeing memory changes the answers.

**What this measures: a panel of local models is a plausible FIRST pass over the review queue,
and no model is a reviewer on its own.** Singly, every one of the seven is worse than the rules
the record already runs, and the worst of them invent docket numbers they were never offered.
In pairs, where both must agree on the citation and on the same document, they settle about
half the benchmark's queue without an error and catch most of the rules' false positives on the
way. The review page is still designed for a person — but for a person looking at the half that
did not clear, with the cleared half shown as cleared and overturnable.

### The panel over the real queue, measured 2026-09-12

gemma4:e4b and qwen3:14b each answered all 1,476 `citation_exposed` items on the Mac, 0 errors,
34 and 52 minutes. **The benchmark's figures did not carry, and the gap is nearly fivefold:**

| | benchmark (148 judged pairs) | the real queue (1,476 items) |
|---|---|---|
| the panel clears | 47.3% | **9.7%** (143) |
| left to a person | 52.7% | 90.3% (1,333) |

That alone justifies the operator's instruction to run on the queue before writing a rule.
A clearing rate of 9.7% does not buy much, and a rule built on the benchmark's 47.3% would
have been sold on a number that was never true of the population it applied to.

**The clearing rate is not the finding, though.** Asked what each mention IS, the two models
agree far more than they clear:

| both models independently say the mention is | |
|---|---|
| a **proceeding** — a caption, naming no document | **981 (66.5%)** |
| a document | 277 (18.8%) |
| a party's filing | 5 (0.3%) |
| they split | 213 (14.4%) |

Of those 981: **649 are the citing decision's own docket**, and **964 have no served date**
anywhere the resolver could anchor. Sampled passages read `Docket No. AB 1261`,
`STB Docket No. AB-878`, `SERVICE LIST FOR STB EP 558` — bare numbers and headers.

**There is a mechanism, and it is in the shipped finder.** `find.py:190` reads

    names_document = bool(DOC_WORDS.search(context)) or key not in own

so a mention of the citing decision's OWN docket still becomes a citation whenever `served`,
`Decision No`, `order` or `slip op` appears within ±160 characters — which is exactly what a
decision's own caption block contains. The own-docket rule (ADR 0017 D1) is a disjunct, not a
veto, and the caption block supplies the words that defeat it.

**Finder 2026-09-12 widens `own` to the family** (self, parent and sub-dockets, the closure
the projection already suppresses on). Measured 2026-09-13 on a copy mirroring production's
citator: 1,229 keys move from citation to caption and none the other way, none of them a
projected edge, and 349 of them in the exposed queue as v2026.09.17 gates it (854 before). The
649 above was counted under the old, docket-only rule.

**What is NOT established.** Two models sharing one prompt are not two witnesses: the prompt
tells them a bare number naming no document is a proceeding, so their agreement is partly the
prompt talking to itself. The passages and the code path are independent of the models; the
agreement is not. **Forty of the 981 were drawn for the operator to judge**
(`caption_check_sheet.py`, seed 20260912; 29 own-docket, 38 with no served date) — enough to
tell "mostly captions" from "mostly citations", which is all this question needs.

Two figures this session produced and then withdrew, recorded so they are not repeated: a
claim that 73.4% of the queue could never publish, derived by re-implementing the projection's
family clause rather than running it. It used `judgement='span'` where the vocabulary says
`span_names_document`, and it tested per resolution row where the projection is DISTINCT over
(decision, kind, key). Checked against live rows, 7,816 family/no-span rows ARE projected, so
the reading was wrong. **Whether these items would publish after review is unmeasured**, and
the way to measure it is to write approvals on a copy and run the shipped projection.

**The panel's precision is measured THROUGH the review page, not in a sitting of its own (the
operator's decision, 2026-09-11).** The question put to him was how large a slice to judge —
150 for a 96.3% lower bound at one error, 300 for parity with what the rules already achieve.
His answer was to push back on the premise: the project has one person, a great deal has
already been measured by hand, and every request of that kind has to earn itself.

Two things settled it. **Nothing already judged can be reused**: of the 1,476 exposed keys,
only 2 appear among the 148 pairs of the work sheet, and only 3 fall inside the sixty checked
decisions at all. The queue really is a different population, which is the reason for running
the panel over it and is also why there is no free measurement in it. **And a slice is not
extra work**: it is a sample of a queue that is otherwise reviewed in full, so the alternative
to judging 150 is judging 1,476.

So the measurement is folded into the work rather than added to it. The review page shows the
panel's answer as a suggestion — *both models read this as `AB 87`, the last digit a footnote
marker, citing decision 35863* — and each key the operator settles is both a settled key and a
data point. After about a hundred the class has a measured precision, and clearing can be
switched on for the rest, or not. Three things follow from that shape: no judgement is spent
only on measurement, the rule is watched on real work before it is trusted with any, and the
figure comes from the same population it would be applied to.

**No threshold is adopted, because this record does not have one and declines to invent one.**
ADR 0017: "the projection admits a row on its `confidence_state`, not on the size of its
confidence, and nothing in this record compares, orders or thresholds on the value." The 98.0%
is a measurement of the current rules, not a bar. What a model-cleared edge owes is what every
derived assertion owes — its method, version, host, channel and its own measured figure (ADR
0017 D3, ADR 0007) — and a reader shown what was checked. The text tier is the precedent:
`/methodology` publishes a 12.7% character error rate on degraded scans, openly and with its
caveats. Switching clearing on remains an ADR 0017 addendum and the operator's.

Nothing ships from this yet. A model's answer is an assertion with its method, version, host
and channel, stamped with its measured precision (ADR 0017 D3), and **letting agreement clear a
held key needs an ADR 0017 addendum, which is the operator's decision.** The measurement that
addendum should rest on is the panel over the real 1,476 exposed keys, not these 148.

> Step 1 note (2026-08-26): the tabled UP–NS tracker holds 988 hand-checked documents in FD 36873 — 33 decisions among them — with a tiering scheme (A/B/C) worth reading before designing routing here; see `upns-tracker-inheritance.md`. Its page-capped extraction makes labels from long exhibits weaker evidence.

> Step 0 re-run 2026-08-26 on waves 2–3's first 9,663 new files: **1,480 image-only** (15%, against 2 of 4,273 in wave 1) — the older record is substantially scanned, which is M3's question and bounds what step 2 can read without OCR. Step 2's local candidate (qwen3:14b) ran over all 60 sampled decisions on 2026-08-26 in 2 h 07 m; output at `/data/docketyard/benchmark/runs/qwen3-14b/`, unscored until the labels are checked.
