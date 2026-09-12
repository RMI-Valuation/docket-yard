# The grain of a citation finding

**Status: a brief for the operator, 2026-09-12. Nothing here is decided.** It exists because
a night of measurement ended at a wall that is not a bug: the record decides caption-versus-
citation at a grain coarser than the distinction itself. Everything below is measured against
a production copy (`rehearse-wrap2`, the line-wrap re-load that matched production figure for
figure) with the shipped code, not reasoned about.

## What a finding is keyed on today

`citation`, `citation_judgement` and `citation_resolution` all key on the same four columns
(`review._KEY_COLS`):

    (citing_document, page, target_kind, target_key)

One row per docket number per page. `find.find` folds every occurrence of a number on a page
into one finding and decides `kind` **disjunctively** — ADR 0017 D4, deliberately: *"one
occurrence naming a document makes the target a citation, for the same reason: the question is
whether the page cites it, and one place saying so answers"*.

## The operator's example, which the schema cannot represent

> A heading reads `FD 00001`. The first paragraph cites `Decision 4 in FD 00001 (served
> December 13, 2023)`. The next cites `Decision 3 in FD 00001 (served December 12, 2022)`.
> The last sentence says to reference `FD 00001` in all correspondence.

Four occurrences: two captions, two citations, and the two citations name **different
documents**. The key holds one `kind` and one `cited_decision_id`, so:

- call it a caption and two real edges are lost;
- call it a citation — which the disjunction does — and the two captions are wrong, and only
  one of the two documents can be stored;
- a later short-form cite of Decision 4 with no date of its own is invisible either way.

## How often this is real, measured on 4,000 sampled stored rows

| | share |
|---|---|
| the key appears **once** on the page | 85.9% |
| **more than once** — caption and citation can collide | **14.1%** |
| occurrences carry **more than one distinct served date** | 0.6% |

The 0.6% are rows where a second document is demonstrably lost: `AB 857 (2)` p4 anchored to
both 2022-02-11 and 2023-05-19; `EP 290 (4)` p2 to 2017-03-16 and 2017-04-11; `AB 55 (643X)`
p1 to 2017-05-31 and 2017-10-02. **It is a floor, not an estimate**: a short-form second cite
carries no date, so it cannot appear in this count at all, and short forms are 1,230 pages and
690 pairs (the citations brief, avenue K).

## Why this is the thing to decide, and not the finder's rules

Four separate measurements this session pointed at the same place:

1. **Two models agree 981 of the 1,476 exposed queue items are captions** (66.5%), and the
   operator judged forty of them: **39 captions, 0 citations, 1 unclear**.
2. The one unclear was unanswerable *as posed*: one key, one page, a caption occurrence and a
   real citation occurrence with `(STB served Jan. 31, 2018)`. The question had no answer at
   the grain it was asked.
3. Three of the four analyses that went wrong this session went wrong by comparing two sides
   at different grains — per-key against per-page, per-row against per-edge, first-occurrence
   against all-occurrences. The grain confusion is not incidental to the problem; it IS the
   problem, and it catches readers of this record as easily as its writers.
4. The finder's own-docket set was narrower than the projection's family closure, which is a
   real defect and is fixed on disk — but it moves 6.1% of rows and does not touch this.

**And it bears directly on the operator's stated goal: as little human review as possible,
with a correction channel rather than a queue.** A per-key verdict on a page holding two uses
of a number must be wrong for one of them, and no model panel repairs a question posed at the
wrong grain — measured: a two-model panel clears only 9.7% of the real queue. Per-occurrence
findings would let the rules answer most of this correctly without a person, which is the only
route to a small queue that does not also mean a worse record.

## What a change would touch

- **ADR 0017 D4** settles the span test as disjunctive over occurrences, and gives its
  reasons. Per-occurrence grain supersedes that. ADRs are append-only: this is a new record,
  never an edit.
- **The key**, in migration 0014's three tables and in `review._KEY_COLS`. An occurrence needs
  a discriminator that is stable across re-reads of the same page — a character offset is not
  (OCR moves it), an ordinal within the page might be.
- **`find.find`**, which folds occurrences today, and `judge`'s span test, which reads the
  joined quoted lines.
- **The projection**, whose fold publishes an edge once per (work, target) — that fold is
  probably still right, and is what keeps a per-occurrence grain from multiplying what a
  reader sees.
- **Every stored row**, which is a re-read of the corpus and a new `FINDER_VERSION`. The
  operator has priced this before.

## What is NOT proposed here

Not a citator redesign. The architecture held: the family closure suppressed every one of
these before a reader saw it, provenance let the whole thing be reconstructed after the fact,
and the version discipline refused a card measured on a different finder. What is under
question is one decision — the grain of a finding — and what it implies for the review surface.

## The questions for the operator

1. Is per-occurrence the grain, or is there a cheaper cut that gets most of it — for instance
   keeping the key but storing `kind` per occurrence, so a caption and a citation on one page
   stop contradicting each other, without multiplying the resolution rows?
2. If per-occurrence: what is the stable discriminator? An ordinal is stable only if the
   reading is; a re-read that finds a number the last one missed renumbers everything after it.
3. Does the projection keep folding to one edge per (citing work, target, document)?
4. Is this worth a re-read of the corpus now, or does it wait behind the backfill?
