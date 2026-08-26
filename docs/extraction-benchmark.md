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

## Step 1 — the sample (drawn 2026-08-26 — `docs/research/benchmark/`; awaiting labels)

Sixty decisions, drawn from the two years wave 1 holds, stratified: 20 with many citations
(rate cases, merger decisions), 20 routine (abandonment exemptions, notices), 20 short
orders. For each, the operator (or a reviewer the operator trusts) labels by hand:

- every citation to a Board decision or docket the text contains, in the form printed;
- every deadline the decision *sets*, as the date printed and the sentence that sets it.

Labels are the truth; a model that finds more than the labels is checked, not trusted.

## Step 2 — the runs

The same prompt and the same output schema (JSON: citations, deadlines, each with the page
and the quoted sentence) against:

- local, on RMI-AI-MACHINE via Ollama: a 14B-class dense model and a ~30B MoE, thinking
  disabled per request (TODO's note: Qwen3 thinks by default and pays for a monologue);
- an API model as the reference.

Scored per field: precision, recall, and — the one that matters for provenance — whether
the quoted sentence actually appears on the cited page. A right answer with a wrong
location is wrong.

## Step 3 — the decision

Recorded as an ADR: which method ships, at what confidence, and what is left to a human.
"Local is good enough" and "API for the hard tier, local for the routine tier" are both
acceptable outcomes; "ship without measuring" is not.

> Step 1 note (2026-08-26): the tabled UP–NS tracker holds 988 hand-checked documents in FD 36873 — 33 decisions among them — with a tiering scheme (A/B/C) worth reading before designing routing here; see `upns-tracker-inheritance.md`. Its page-capped extraction makes labels from long exhibits weaker evidence.
