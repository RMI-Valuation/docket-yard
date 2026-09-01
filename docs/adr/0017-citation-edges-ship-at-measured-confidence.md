# ADR 0017 — Citation edges ship at measured confidence, with the registry and a reviewer between the model and the page

- **Status:** Proposed — cleared by the schema-critic (sixth pass) and by a 13-agent
  multi-agent review, both 2026-09-01; the operator's decision is outstanding. The exposure
  test that blocked this record is **settled below**; one measurement is still owed before any
  recall figure may be published.
- **Date:** 2026-08-30, rewritten 2026-09-01 when the record reached 1,082 lines and stopped
  being readable. The table shapes moved to [ADR 0018](0018-the-citation-assertion-families.md);
  every figure and its method are in [`../citator-gate.md`](../citator-gate.md) and
  [`../citator-schema.md`](../citator-schema.md); six critic passes are in git.

## Context

A citator answers "what cites this, and what did it do to it". Building one means reading
75,000–125,000 PDFs and asserting an edge from each citation found. Every such edge is a
derived claim about a federal agency's record, published under this project's name, and
ADR 0007 requires each to carry provenance and a confidence.

A benchmark over 60 decisions (977 labelled rows, `docs/research/benchmark/`) measured a
regex, nine local models and the API model against the same sheet. It settled two things
that were open: a regular expression is the best docket-shaped extractor available, and the
error that remains is almost entirely self-reference rather than invention.

The contested question is therefore not *can we extract citations* but **what may be
published without a human reading it first**, and on what evidence.

## Decision

1. **The docket-shaped class ships from `regex-docket-cite`; the API model is bought only
   for what regex cannot reach.** The regex emits 97.8% of docket-shaped targets — above
   Claude's 95.6% and every local candidate (best qwen3:14b, 93.8%) — at no per-page cost.
   The API model (`model:claude-sonnet-5`) ships for reporter cites, date-named decisions,
   court citations and dated obligations. It is **not** asked whether a mention is the
   citing decision's own proceeding: the record already knows which docket a decision sits
   in, and that is the one thing no extractor should be asked to decide. The local models
   write no citation edges; one ships when it scores, not before.

2. **The registry check is the first rule of *resolution*, not a filter inside the finder.**
   A finder that can only emit dockets the registry holds cannot emit an unresolvable one —
   which empties the review queue for unresolved targets by construction, makes "cites
   `EP 445` (not in the record)" a display that can never be produced, and caps recall at
   219 of 225 (the 225 docket-shaped truth rows less the six the registry cannot resolve —
   arithmetic, not a separate measurement). So the finder emits every docket-shaped hit and resolution decides what the
   registry holds. It still invents nothing: an unresolved target is stored unresolved and
   never projected.

3. **Confidence is the measured precision of the resolution's class on the checked sheet,
   never the model's opinion.** It is carried on the assertion row with a typed state and a
   pointer to the exact measurement it was stamped from (ADR 0018). A class nobody has
   scored is `unmeasured` and **projects nothing** — which is why OCR, at 10.8% CER, ships
   stored and unprojected until somebody measures it.

4. **An edge to the citing decision's own proceeding is a self-reference: suppressed at
   docket level, kept in the store, and projected when it names a different work.** The
   family is the docket, its sub-dockets and its parent — `web/cite.py`'s closure — taken as
   the union over every docket a consolidated decision is entered in.

   **The classifier is the quoted span, and it is a stored assertion.** An extra is absorbed
   only when its span names no document; a span carrying `Decision No. …`, `slip op.` or a
   served date is projected. That test yields **98.2%** precision after the rule.

   The alternative test this record first stated — *project when the target resolves to a
   different work* — is **blind, not conservative**, and the difference was measured:
   `decision_record.decision_number` is populated for 0 of 23,713 rows in production, and
   none of the four disputed spans carries a served date. Under it all four extras are
   suppressed and precision reads 100% — the figure this record retracted as false — by
   hiding four candidate wrong edges behind a resolver with no data.

   Because the span test decides what every published edge *is*, it is an assertion with its
   own method, version and confidence, never a predicate computed inside a view. Its default,
   where nothing has judged an edge, is to **suppress**.

   **The test is disjunctive over every occurrence of the target in the citing work: one
   occurrence naming a document projects the edge** *(settled 2026-09-01, multi-agent review,
   which found the occurrence undecided and the stored span systematically unrepresentative —
   the extractor quotes the FIRST match's line, which is usually the running caption)*. The
   question the rule answers is "does this decision cite that work as a document", and a
   single occurrence saying so answers it yes; requiring the *first* occurrence to say so
   would let a caption on page 1 decide an edge argued on page 9. This is what was measured:
   the 98.0% and 89.3% above join every occurrence's span before testing. It errs toward
   projecting a real edge rather than suppressing one, which is the right direction for a
   rule whose other side is already the conservative default.

5. **What is left to a human** (ADR 0016), in order of yield: the exposed class and every
   rule-2 repair; unresolved docket targets whose number falls inside the held record (an
   ICC-era number is expected to fail and is not queued); same-docket citations naming a
   document that did not resolve to a work; and every reader report. A review writes a
   `human` row, which a model pass may never supersede.

6. **What a reader sees.** Per edge: the citing passage, its page, the extraction method and
   version, the class and its measured confidence, and the reviewer's credit name where a
   human resolved it. **No count is published without its class.**

7. **Not in this slice, doors kept — and what that means on day one.** Every edge is `cites`,
   so **validation query 2 returns nothing until the treatment pass runs**: it joins
   `citation_treatment` and filters on a negative polarity, and no treatment row exists yet.
   What ships is "what cites this" — the cited-by list and the citing passage at 89.3%/98.0% —
   which is the wedge, and is worth shipping. Neither record may present query 2 as the day-one
   payoff *(stated 2026-09-01 after the multi-agent review; both records had cited Q2 as their
   justification without saying it returns an empty set on the day they ship)*. treatment typing, a
   reporter→work resolver and record-cite resolution are later passes (ADR 0018). Statutes
   are not extracted — adding them costs a re-extraction (~$1,335), not a migration. The
   decided date **is** extracted in the same pass, because doing it later costs that re-run:
   55 of 60 decisions print a `Decided:` line, none prints two, and 34 of 52 differ from the
   service date, so this record and a paper copy disagree today with nothing explaining why.
   It is stored as an assertion carrying ADR 0007's block — **never a `decision_record`
   column** (that table mirrors the latest observation and would destroy the history) and
   **never a ledger event** (a decided date is a second clock; a replay would show a decision
   existing before it was served). Those two fences are the grain constraint, not a detail:
   the extraction decision without them is the cheap half.

   One limit on decision 5, stated because a reader will assume the opposite: `citing_document`
   is a sha256, so **a human review of an edge in the original does not follow into an
   erratum's bytes**. The fold to the work is for edges; a review is anchored to the document
   it was taken on.

## The exposure test, settled 2026-09-01

An **exposed** target is one where a footnote marker may have fused onto the docket number —
`AB 124` followed by footnote `2` read as `AB 1242` — so the extraction resolves confidently
to the wrong proceeding. That class goes to review; everything else ships unreviewed, which
is why this definition decides what gets published without a person looking.

**The test: a bare docket number of four digits or fewer whose last-digit-stripped reading is
a held docket.** On the sheet that is **3 of 225** — `AB 1014`, `AB 1071`, `AB 1242`.

This record previously offered 3, 5 or 14 and called the choice the operator's. It is not a
choice; the wider readings are excluded by the extractor's own grammar, on three independent
checks made 2026-09-01:

- **Measured.** Across **994** printed docket forms in the 60 benchmark decisions, exactly
  **one** has a digit abutting the complete form: `Docket No. EP 665 (Sub-No. 2)1`
  (decision 52526, whose footnote 1 reads "These proceedings are not consolidated"). The
  marker lands **after the closing parenthesis**. Every other form is followed by punctuation
  or a space.
- **Mechanical.** `DOCKET` ends a match three ways: a closing paren (`EP 665 (Sub-No. 2)`), a
  letter suffix (`AB 1296X` — the `[A-Z]` consumes it), or a bare digit run. **Only the third
  can swallow a following digit.** The extractor proved it on the live case: it emitted no
  fused value for 52526 at all.
- **The length cap.** `\d{1,5}` bounds the sequence, so a five-digit docket cannot absorb a
  sixth digit — greedy matching takes `NOR 42144` and leaves the marker. Only four-digit and
  shorter bare numbers are at risk, which is exactly the membership above. It is not a
  coincidence; it is the only shape that *can* be exposed.

So the five suffixed targets a wider reading adds — `AB 1296 (X)`, `AB 1305 (X)`,
`AB 1321 (X)`, `AB 1339 (X)`, `AB 578 (X)` — cannot be fusions. Flagging them is not caution,
it is noise in a queue, which trains a reviewer to skim.

**Measured on both populations, because they are not the same set.** The 225 are the *truth*
targets; what actually ships is the 249 *emitted*. Both give the same three — 1.3% and 1.2% —
so the figure holds on the denominator that matters.

**This does not contradict `../citator-gate.md`'s "three-digit `EP` dockets are the
exposure".** That describes which held dockets are *at risk* of being mis-read; this test
detects the *result* of the mis-reading, which is one digit longer. `EP 445` fused with a
footnote is emitted as `EP 4451`, a four-digit bare number whose stripped reading is held —
caught. None occurred in these 60 decisions, which is why the sample's three are all `AB`.
Registry-wide, **1,160 of 21,807 distinct dockets (5.3%)** are shaped so a fused digit could
land on another held docket; that is the population at risk, not the rate at which it fires.

**Cost:** ~1.2% of emitted targets, so roughly a dozen review items a month on the forward
poll, and a four-figure one-time queue across the backfill.

## The figures, by stage

Measured 2026-09-01 by `tools/rmi-ai-machine/projection_score.py`, which is in the repository
so every number here is re-derivable. **Each line is true of a different thing, and quoting one
for another is the error this record made** — it published 95.1% for the projected class, a
figure measured before the gate that suppresses edges.

| stage | of 225 | |
|---|---|---|
| **extraction** — the finder saw it | 220 | **97.8%** |
| **resolution** — and the registry resolved it | 210 | **93.3%** (10 real edges to review) |
| **projection** — and a reader sees it | 201 | **89.3%** |

**Precision of what projects: 201 true of 205 shown = 98.0%.**

The 24-edge gap between what is found and what is shown is not error, and the record must not
present it as loss: 10 are real edges the registry cannot yet resolve, which go to review and
appear as "cites `EP 445` (not in the record)"; 9 are own-family self-references decision 4
suppresses on purpose, because the record already holds that membership; 5 the finder never
saw.

*(Two of those suppressions were a defect, not the rule: the span test read
`served\s+\w+\s+\d` and so missed `(STB served Mar. 12, 2021)` — the Board abbreviates the
month and the period broke the match. Fixed in the committed classifier; it moved projected
recall from 88.4% to 89.3% and left precision unchanged.)*

**Publish the projection line, never the extraction line.**

## What is still open

Nothing blocks acceptance. What is owed before the first edge reaches a page is in ADR 0018's
§ Owed at the migration, and one honesty item is in decision 7 below: **query 2 returns nothing
on the day this ships**, because every edge in this slice is `cites` and treatment typing is a
later pass.

## Consequences

The first slice can be built and its numbers are known before an edge is stored: **89.3% of
docket-shaped citations reach a reader, at 98.0% precision** (§ The figures, by stage).

The 95.1% this record previously published for that class was measured **before** the
projection gate and was wrong — the fourth time in this record's life a published figure
described a configuration the pipeline does not run. The pattern is always the same: measure
one stage, quote it as the whole. The scorer now reports every stage at once so the error is
harder to repeat than to avoid.

Re-measurement is a scorer run, not a migration. A better extractor supersedes rather than
rewrites. What becomes hard: every published figure is a property of a **pair** — extractor
plus projection rule — and may only be published with the rule named beside it.
Re-measurement is a scorer run, not a migration. A better extractor supersedes rather than
rewrites. What becomes hard: every published figure is now a property of a **pair** —
extractor plus projection rule — and may only be published with the rule named beside it.

## Cost of reversing

Cheap while it is paper: no citator table exists in any migration. After the first edge,
changing the *extractor* is a supersession; changing the *projection rule* re-measures every
published confidence; changing the *class definitions* is a resolution re-run over kept
rows. Only the "cited by" count is a public number that cannot be quietly restated.

## Checked against `../validation-queries.md`

Query 2 (negative treatment) is the query this record exists to serve, and it is writable
against ADR 0018's tables. The SQL is on disk at [`../citator-query-2.sql`](../citator-query-2.sql), so this is checkable rather than asserted. Queries 1, 3 and 5 read no
table this record proposes. Query 4 (lifecycle and provenance) reads no citation table and is untouched; what 0018
protects for it is the natural-key-plus-supersession discipline that stops a re-extraction
doubling an instrument's history. The five queries were re-checked against these decisions on 2026-09-01.
