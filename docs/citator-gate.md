# The citator gate — what must be settled before C2 is chosen

**Status: open questions, not decisions — now drafted into ADR 0017 (Proposed,
2026-08-30), which makes the conventions and the two rules below decisions and names what
ships at what confidence.** This collects what the extraction benchmark has
settled, what it has exposed, and what remains, so that the ADR recording the citation-edge
shape can be written from evidence rather than from first principles. Nothing here is
accepted; an accepted ADR supersedes any of it. Capability C2 is an **STB and ICC citator**
(`capability-map.md`), and it has not been chosen.

The rule this document exists to protect: **a citation that resolves to the wrong docket is
worse than one that resolves to nothing.** A missing edge is visibly missing. A wrong edge
attaches a decision to a proceeding it never touched, reads as fact, and nothing downstream
catches it.

## Settled by the benchmark (2026-08-29, corrected 2026-08-30)

The four labelling conventions, with their reasoning and their costs, are in
`research/benchmark/README.md`. In short, and in the form the citator inherits:

| | |
|---|---|
| A decision's own docket, named as itself | **not an edge** — the record holds it already |
| A prior decision in that same docket | **an edge** — a different document, whatever docket it sits in |
| A repeated short form | **not a second edge** — edges are a set of `(citing, target)` |
| A court citation | **an edge, typed apart** — unresolvable against the docket registry |

The test that separates the first two is whether the text names a **document** or only the
**proceeding**: `Docket No. EP 787` is the proceeding, `NPRM, EP 787, slip op. at 4` is a
document. Words like `slip op.`, `Decision No.`, `served`, `NPRM` and `order` mean a
document.

**Do not try to compute that distinction from the registry.** It was proposed on 2026-08-30
— mark any target that matches a docket the decision is entered in as a false positive —
and schema-critic rejected it against validation query 2. Measured: **86 of the sheet's
citation rows** name a document in a docket the deciding decision is itself entered in, and
`Docket No. NOR 42144` and `N. Am. Freight Car Ass'n v. Union Pac. R.R., NOR 42144, slip
op. at 4` normalise to the same key in the same decision. A key comparison cannot separate
them, and the edges it would delete — a Board decision narrowing its own prior decision on
reconsideration — are the commonest negative treatment the agency produces, which is what
query 2 exists to find.

## Docket resolution: two rules, from a defect found 2026-08-30

The operator found `Docket No. NOR 421441` in EP 328 (Sub-No. 2)'s text layer. The docket is
`NOR 42144`; the trailing `1` is the marker of footnote 1, fused to the number by PDF text
extraction. The labelled sheet is clean, because the drafter read the PDF — but a model
reading the text layer emitted `NOR 421441` as a target, and that is what a pipeline would
store.

**Rule 1 — a docket target that fails the registry check is never stored as an edge.**
Record the span and the raw string; do not guess, and do not discard. In the measured run 4
of 174 distinct docket targets failed, and `NOR 421441` was one of them. Note that a failure
is not always an error: `EP 445` failed 13 times and is a real ICC-era proceeding that
predates the 1996 record, which is the legitimate unresolvable case.

**Rule 2 — try the string with a trailing digit removed, and act on how many readings
resolve.** Measured against the 21,807 held dockets:

| original number | appending a digit yields another held docket |
|---|---|
| 1 digit | 174 pairs (`AB 1` → `AB 10`) |
| 2 digits | 803 pairs |
| 3 digits | 183 pairs (`EP 445` → `EP 4451`) |
| 4 digits | 2 pairs |
| **5 digits** | **none** |

The citations in the sheet cluster at 3 digits (191) and 5 digits (286). So:

- **five-digit dockets are safe** — `FD 36873`, `NOR 42144`. A fused footnote digit always
  yields a six-digit number that does not exist, and rule 1 catches it. Where the raw form
  fails and the stripped form resolves, the repair is unambiguous.
- **three-digit `EP` dockets are the exposure.** Both readings can resolve, and no rule
  should choose between them. That is a review-queue item under ADR 0016, not a heuristic.

Neither rule belongs in the prose footnote-marker rule the labels queue uses
(`received,1 the exemption`), which requires punctuation before and lower case after and
would never fire on a docket number. A docket needs its own rule, keyed on digits.

## Open, and the operator's

- **Record cites** (`IANR Reply 2, Aug. 14, 2024, FD 36798`). The sheet holds 12; decision
  51532 alone contains about 20, so the sheet cannot measure them either way. Resolving one
  means matching party, document type and printed date against the filings table — a
  nullable `cited_filing_id` on the citation edge, per `schema-draft.md`, so the schema door
  stays open whatever is decided. The question is whether they are in C2's first slice.
- **Statutes** (`Transportation Act of 1920, Pub. L. No. 66-152, § 402, 41 Stat. 456`).
  Currently excluded, on **scope** — a statute has no STB record behind it and cannot be
  validated against the registry. Note the asymmetry that has not been argued: court
  citations were kept partly because re-labelling them later would be expensive, and that
  argument applies to statutes with equal force.
- **Anything the sheet does not hold must be explicitly not scored**, not silently absent.
  A class that leaves the sheet without that rule becomes a precision penalty against an
  engine that correctly finds it — which is how 12 record rows currently mis-measure.
- **The decided date.** A decision carries two dates and `decision_record` holds one. On the
  sixty, 52 print a `Decided:` line and 34 of those differ from the service date. Placement
  is contested: a new `kind` in the sheet, an assertion carrying the full ADR 0007 block in
  the store, and **not** a `decision_record` column (that table mirrors the latest
  observation and would destroy the history) and **not** a ledger event (a decided date is a
  third clock, and replaying it would show a decision existing before the Board served it).

## What this gate must answer before an edge is stored

1. The edge's shape against `validation-queries.md`, in particular query 2's negative
   treatment and query 3's point-in-time reconstruction.
2. Where an unresolvable citation lives, given that it is data rather than a failure.
3. What provenance an edge carries under ADR 0007 — method, method version, confidence —
   and what a *corrected* edge carries after review under ADR 0016.
4. Whether the citation target is a docket, a decision, or both, given ADR 0002's
   content-hash identity: the sheet already cites one work in two forms (`4 S.T.B. 303` and
   `FD 32760`), which a docket-keyed edge scores as two different things.
