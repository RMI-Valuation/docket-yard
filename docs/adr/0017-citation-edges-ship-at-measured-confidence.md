# ADR 0017 — Citation edges ship at measured confidence, with the registry and a reviewer between the model and the page

- **Status:** Proposed — cleared by the schema-critic 2026-09-01 (sixth pass); the operator's
  decision is outstanding. One blocker is named below and is not resolved.
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

5. **What is left to a human** (ADR 0016), in order of yield: the exposed class and every
   rule-2 repair; unresolved docket targets whose number falls inside the held record (an
   ICC-era number is expected to fail and is not queued); same-docket citations naming a
   document that did not resolve to a work; and every reader report. A review writes a
   `human` row, which a model pass may never supersede.

6. **What a reader sees.** Per edge: the citing passage, its page, the extraction method and
   version, the class and its measured confidence, and the reviewer's credit name where a
   human resolved it. **No count is published without its class.**

7. **Not in this slice, doors kept.** Every edge is `cites`; treatment typing, a
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

## The blocker this decision does not resolve

**The exposure test has no single definition.** An "exposed" target is one whose
digit-stripped reading is also a held docket (`AB 1242` / `AB 124`), and that class is
precisely what ships *without* review. The same test yields **3, 5 or 14 of 225** depending
on the reading, and the "5" on file was measured against a 220-target sheet before a scorer
fix and never re-taken — which is why the arithmetic in `../citator-gate.md` does not close.

Until it is written down once: no figure may be published against the shipping class, and
the size of the first review queue is unknown. Moving the registry check into resolution
(decision 2) *enlarges* what the test must catch, because a fused footnote now always emits
and resolution decides against a registry that only grows.

**This is a measurement decision, and it is the operator's.**

## Consequences

The first slice can be built and its numbers known before an edge is stored: 95.1% of
docket-level edges project unreviewed at 98.2% precision after decision 4 (88.4% as scored).
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
