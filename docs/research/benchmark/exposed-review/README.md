# The exposed-class check, in `/review` (2026-09-11)

The citator's first load (2026-09-11 16:55 UTC, `docs/runbook.md` § first load) held **1,945**
exposed keys for a person: bare docket numbers of four digits or fewer whose last-digit-stripped
reading is also a held docket, the shape a fused footnote marker produces (ADR 0017). For
**1,359** of them the citing decision is filed in the very docket the number names.

The operator's decision (runbook § Blocker 2): he works `/review/citation_exposed` as it
stands, and **the first fifty own-docket keys he answers are the sample** that measures a rule
clearing that class. The queue is served in the citing document's sha256 order
(`review.pending`, pinned by a test), which is independent of anything on the page.

## `queue-at-load.json`

Captured **2026-09-11 16:58:52 UTC with 0 review actions in the store** — before any answer, so
no answer can have shaped it. It holds the queue in its served order: each position, the key's
four columns (`citing_document`, `page`, `target_kind`, `target_key` — joined with `/` they are
the key `review_action.target_key` names) and whether the citing decision is filed in the named
docket. The key was first written as one string, which the repository's secret scanner read as
an API key; it was split before the first commit, losslessly and with the values unchanged. `sample_positions` are the positions of the first fifty own-docket keys; the
fiftieth is at **92**.

## How the answers are read

From `review_action` (queue `citation_exposed`), matched to this capture by key:

- `accepted` — the number is the docket it names;
- `corrected` — a shorter docket with a footnote digit run on (the correction names it);
- `escalated` — cannot tell, counted apart;
- `rejected` — neither; read from its note.

**No `corrected` among the fifty** puts the class's fused rate under about 6% at 95% confidence
(three in fifty, the rule of three) — not at zero; whether that is enough is the operator's
decision, in an ADR 0017 addendum. **One `corrected`** rejects the rule as drafted, and its
case says what a narrower rule must exclude. Keys answered outside the fifty are real
decisions and count toward nothing here.
