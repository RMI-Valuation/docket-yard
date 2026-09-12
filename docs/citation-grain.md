# The grain of a citation finding

**Status: CLOSED 2026-09-12. The operator decided question 0: the grain does not change.**
See § The decision, at the end. The brief is kept whole because the measurements in it are the
reason, and because two of its own drafts were wrong in ways worth being able to read. It exists
because
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

## Correction, the same day: the measurement is CITATIONS, and the loss is small

**The operator's correction, 2026-09-12:** a caption is not what this record is for. Nobody
cares whether a decision mentions itself; the question is whether it names another decision or
filing, in its own docket or another. So captions are incidental to the measurement, and the
figure that matters is how many CITATIONS the grain loses — not how many captions it mislabels.

Re-measured on that basis, and the case above is weaker than it was written:

- **A caption folded in with a citation costs nothing.** The disjunction calls the key a
  citation, the edge still publishes, and the caption is harmlessly along for the ride. The
  14.1% multi-occurrence figure is therefore NOT a loss figure, and quoting it as one was
  wrong. It bounds where a *labelling* conflict can occur, which is a review-burden fact.
- **The six multi-document pairs in the operator's own work sheet all survive.** 6 of 134
  judged pairs (4.5%) name two documents; in every one the two citations fall on DIFFERENT
  pages, the page is part of the key, and the record stores both. `52211 -> FD 36732` holds
  51913 and 51953; `52835 -> AB 290 (286)` holds 37729 and 41895. **Nothing is lost in any of
  them.**
- **The demonstrable loss is ~0.6% of stored rows**: two distinct served dates anchored to one
  key on ONE page, where the schema has room for one. Still a floor — a short-form second cite
  carries no date and cannot be counted — but a floor over a small number, not a large one.

**So the grain is wrong in principle and cheap in practice.** A per-occurrence key would make
the operator's example representable; it would not move citation recall much, because the page
is already doing most of the work a per-occurrence discriminator would do. That is an argument
for deciding it deliberately rather than urgently.

**And it separates the two problems that this brief ran together.** Citation LOSS is ~0.6% and
structural. REVIEW BURDEN is 66% of a 1,476-item queue and has nothing to do with the grain:
those rows are captions that will never publish, queued because `citation_exposed` filters on
the exposure judgement and not on `kind`. The second is what stands between the operator and a
small queue, and it is a queue-predicate question, not a grain question.

## Shape A - WITHDRAWN 2026-09-12, see the critic findings below

**The operator chose this shape 2026-09-12.** It is a draft, not a decision, and the critic is
being asked to break it before anything is written.

### The observation the shape rests on

The five citation tables already split two kinds of fact:

| table | keyed by | what it asserts |
|---|---|---|
| `citation` | document, page, kind, key | **channel-free**: this page mentions this number |
| `citation_reading` | + `reading_channel` | what THIS reading printed, and where |
| `citation_judgement` | + channel, judgement, method | caption or citation; span; exposed |
| `citation_resolution` | + channel, method | which docket, which document |
| `citation_treatment` | + channel, method | followed, distinguished, overruled (query 2) |

**An occurrence is a property of a READING, not of the document.** The text layer and dots.mocr
break the same page differently and need not find the same matches, so a line number is a fact
about one reading of a page rather than about the page. That is why the occurrence goes in the
four channel-keyed tables and NOT in `citation`.

### The change

1. `occurrence INTEGER NOT NULL DEFAULT 1 CHECK (occurrence >= 1)` on `citation_reading`,
   `citation_judgement`, `citation_resolution` and `citation_treatment`.
2. **Its definition**: the 1-based ordinal of *this* `target_key`'s matches on this page, in
   reading order. Per key, deliberately — not an ordinal over every docket number on the page,
   which would renumber `FD 00001` because an unrelated `AB 55` was found or missed.
3. The four `*_live` unique indexes gain `occurrence`.
4. `citation` and `citation_live` are **unchanged**. "This page mentions FD 00001" is true
   however many times it does, and every existing join to `citation` survives.
5. `find.find` stops folding: one finding per occurrence, each with its own `kind`, `quoted`
   and `source_location`. `FINDER_VERSION` and `RANK_VERSION` move.
6. The projection keeps folding to one edge per (citing work, target, document) — which is
   what stops a per-occurrence grain multiplying what a reader is shown.
7. Migration: every existing row takes `occurrence = 1`, which is what it means today.

### What it buys, measured

The operator's case: a heading names `FD 00001`, two paragraphs cite two different decisions of
it with their own served dates, a closing sentence names it again. Four occurrences, two
captions, two citations, two documents — today one row, one `kind`, one `cited_decision_id`.
Under this shape each occurrence carries its own answer.

- 14.1% of stored rows hold a key that appears more than once on its page.
- ~0.6% demonstrably name two documents on ONE page; the schema has room for one. A floor:
  a short-form second cite carries no date and cannot be counted.
- ADR 0017 D4's disjunction ("one occurrence naming a document makes the target a citation")
  becomes unnecessary rather than wrong — each occurrence answers for itself. **Superseding D4
  is a new ADR, never an edit.**

### The five validation queries

Query 2 (negative treatment) is the only one that reads these tables. It asks what narrowed or
overruled a decision, keyed to the DECISION rather than a content hash. `citation_treatment`
gains the column and its live index; the query's grain is the edge, which the projection still
folds, so the answer set is unchanged. Queries 1, 3, 4 and 5 read segments, the event ledger,
trail-use filings and service lists, and touch no citation table.

### What the critic is asked to attack

1. **Cross-reading stability.** An ordinal is stable only if the reading is. When dots.mocr
   re-reads a page the text layer already read and finds three matches where there were two,
   what supersedes what? `citation_reading_live` is per channel so the two coexist — but
   `citation_judgement` and `citation_resolution` are also per channel, and the projection
   ranks across channels by `precedence_rank`. Does occurrence 2 of one channel mean the same
   passage as occurrence 2 of another? **If it does not, ranking across channels is comparing
   different sentences, and that is the defect this shape could introduce.**
2. **Re-reads within one channel.** A better finder that catches a number the old one missed
   renumbers every later occurrence of that key. The live index would treat the renumbered rows
   as new rather than as supersessions, so the store would hold both. Is `occurrence` therefore
   the wrong discriminator, and should it be `source_location` (block and bbox, which ADR 0003
   already captures) with the ordinal derived for display only?
3. **The human path.** `review_action` records a decision against the queue's four columns and
   `review.decide` writes an assertion on them. A human answer about occurrence 2 must not
   clear occurrence 3. Does anything in migration 0015 key a human row in a way that would
   silently widen?
4. **The `citation` join.** Leaving `citation` at page grain means one document-level row for
   several reading-level rows. `review._base` joins `citation` to `citation_reading` on four
   columns; with occurrence added to one side only, does that join fan out, and where?
5. **Whether the split is right at all** — should `citation` itself carry the occurrence, and
   is "this page mentions this number" a fact worth keeping separately?

## Schema-critic broke shape A, 2026-09-12. What it found, and what replaces it

**Shape A above is withdrawn.** It is left in place because the reasoning is worth reading
beside what was wrong with it, not because it is a live proposal.

### Three breaks that matter

1. **Validation query 2 breaks, and the draft asserted it did not.** `citator-query-2.sql`
   joins `citation_treatment` and `citation_reading` on the four key columns. Both tables gain
   `occurrence` under shape A and neither ON clause mentions it, so a key with three
   occurrences yields 3 x 3 rows. `SELECT DISTINCT` cannot collapse them — the treatment, the
   raw string, the quoted passage and the source location are all in the select list and all
   differ per occurrence. A negative polarity then matches when ANY occurrence carries one and
   is returned beside ANOTHER occurrence's passage. Query 2's product is "this decision
   overruled that one, and here is the passage"; the fan-out makes the polarity and the passage
   come from different sentences. `citation_treatment` is empty today, so the defect is latent
   — which is how it would have survived review.

2. **The store had already rejected both candidate discriminators, in its own DDL.**
   Migration 0014 on `decision_decided_date.ordinal`: a positional, parser-assigned ordinal
   mints a row that supersedes nothing the day a layout change reorders two printed lines, and
   `source_location` was removed from a key for the same reason. Shape A offered a choice
   between exactly those two and proposed to make that dormant defect live on the three largest
   citator tables. Two finder changes on 2026-09-11 alone moved match sets inside existing
   pages (628 wrapped sub-dockets, 3,438 continuation lines), so renumbering is not theoretical.

3. **The human path would DELETE, not widen.** `review.decide` retires every live resolution on
   the key and inserts one replacement. With `occurrence` in the live index, answering
   occurrence 2 retires occurrences 1 and 3 with no successor: their edges leave the projection
   with no reviewer having been asked, and `review_action` records only the one decision.
   `_human_reading` returns early if any human reading exists on the key, so every reviewed
   occurrence after the first gets a resolution and no reading, and the projection's INNER
   reading join drops it.

### Two findings worth acting on whatever happens to the grain

- **`keys.render` has no version.** `review_action.target_key_version` records the NORMALISER's
  version, not the render convention. A five-segment rendering would compare unequal to every
  four-segment string in the store — stranding every human decision already made, **including
  the forty judged on 2026-09-12** — silently, as an empty result rather than an error. The
  four-segment CHECKs are shape-only and would not catch it. `review_action` and `correction`
  want a `render_version` while those tables are still small.
- **`source_location` is declared but not written.** Migration 0014 declares
  `{page, block_id, bbox}` and ADR 0003 requires layout capture; `load.py` writes the page and
  nothing else. So the fallback shape A offered — key on `source_location` instead — does not
  exist to fall back on.

### The shape that replaces it

Keep every key exactly as it is. Make the occurrence a child of the reading's surrogate id:

    citation_occurrence(reading_id REFERENCES citation_reading(reading_id),
                        ordinal, cited_raw, quoted, kind, source_location,
                        PRIMARY KEY (reading_id, ordinal))

A re-read supersedes the READING — one row, one live index, semantics unchanged — and replaces
its whole occurrence list atomically. Nothing renumbers across a supersession because the old
ordinals stay attached to the old reading. No live index, no projection term, no queue
predicate and no rendered key moves. An occurrence only means anything relative to one reading,
which was shape A's own opening observation followed through properly.

It does NOT buy two `cited_decision_id`s for one key on one page — the measured ~0.6%.

### Why offsets come first (the operator's decision, 2026-09-12)

**The recall claim in this section is measured and it is wrong** — see § The one number
nobody had, below, which was run before the code was written. The decision to report
offsets stands on provenance, not on recall; the reasoning is left here as it was written.

`resolve._anchored` anchors on the printed string, not on the occurrence: it runs over every
match of that string in the passage, so where two citations of one key share a LINE both
findings anchor to the same text, the served-date reader sees several dates and returns none,
and the second document is lost anyway. Its own docstring says so — a finder that reports
offsets is still the real fix.

So `find` reporting each match's offset and block pays three debts at once: a discriminator
that is stable within a reading, a window the anchor can actually use, and the
`source_location` ADR 0003 requires and that is not being written. **And it makes measurable
the one number nobody has: what share of the multi-document pages have both citations on one
line.** The grain decision is then made with that figure in hand rather than ahead of it.

## The questions for the operator

0. **Is the grain worth changing at all**, now that the loss is measured at 0.69% of rows and
   every multi-document pair the operator judged survives? The review burden — the thing that
   costs him time — is a queue-predicate question and can be answered without touching this.
   **Read § The one number nobody had first**: 14.4% of the loss is recoverable by no grain
   change at all, and the 85.6% that is needs a per-occurrence RESOLUTION — which is shape A,
   the shape the critic broke, and not the child table that replaced it.
1. If it is: per-occurrence, or a cheaper cut — keeping the key but storing `kind` per
   occurrence, so a caption and a citation on one page stop contradicting each other, without
   multiplying the resolution rows?
2. If per-occurrence: what is the stable discriminator? An ordinal is stable only if the
   reading is; a re-read that finds a number the last one missed renumbers everything after it.
3. Does the projection keep folding to one edge per (citing work, target, document)?
4. Is this worth a re-read of the corpus now, or does it wait behind the backfill?

## The one number nobody had, measured 2026-09-12 before any code was written

**The question was written down first** — what grain each side was at and what result would
falsify it — because three of the four analyses that went wrong the night before went wrong by
comparing two sides at different grains. Both sides here are one row of `citation_reading`,
one (citing_document, page, target_kind, target_key, reading_channel). The reader is the
shipped `resolve._anchored` with the shipped `SERVED` and `MONTHS`, called once over the whole
passage exactly as `resolve.resolve` calls it at `resolve.py:239`, and once per `" | "`
element of the same passage. Over **all 73,838 live readings** in `rehearse-wrap2`, not a
sample of 4,000:

| | rows | share |
|---|---|---|
| live `citation_reading` rows | 73,838 | |
| **>= 2 distinct served dates on the key-page — the document is lost** | **506** | **0.69%** of readings |
| the dates are separated **by line** | 421 | 83.2% of the loss |
| both dates sit inside **one line** | 85 | 16.8% of the loss |

The 0.69% confirms the sampled ~0.6% over the whole store. The second measurement is the one
that matters, and it **breaks the reason offsets were chosen**. Counting matches of the printed
number per line, with `_anchored`'s own compiled pattern rather than a hand-rolled one:

- **73 of the 85 hold ONE match of the number with several dates hung off it.**
  `EP 558 (Sub-No. 22), slip op. at 2 (STB served Aug. 6, 2019), corrected (STB served
  Sept. 30, 2019)`. `FD 36168, slip op. at 8 & n.8 (STB served Mar. 15, 2019), pet. for recon.
  denied (STB served June 20, 2019)`. **An offset cannot separate these**: there is one match,
  so an occurrence-anchored window is the same window as today's, holds both dates, and
  `served_date` still returns None.
- 12 hold two or more matches — and all twelve are also subsequent history
  (`reconsideration denied, NOR 42125 (STB served Dec. 23, 2015)`); seven of them are one
  document.
- **78 of 85 (91.8%) have a history word between the two dates** — `corrected`, `aff'd`,
  `vacated`, `recon. denied`, `modified`, `clarified`, `stay den.`, `reopening denied`.

### What that settles

1. **Offsets are not a recall fix.** They uniquely recover **12 of 506 rows — 2.4% of the
   loss, 0.016% of live readings.** § Why offsets come first says a shared LINE is where the
   second document is lost; measured, a shared line is 16.8% of the loss and five sixths of
   that is one citation, not two. **They remain worth reporting on their own merits** — the
   `source_location` ADR 0003 requires and `load.py` does not write, and a discriminator that
   is stable within a reading — and that is the claim they should be landed on.
2. **The per-LINE split is where the recall is**: 421 rows, 83.2% of the loss. But it needs a
   per-occurrence **`citation_resolution`**, one `cited_decision_id` per occurrence. The child
   table that replaced shape A explicitly does not buy that ("It does NOT buy two
   `cited_decision_id`s for one key on one page"), and the shape that did is the one the critic
   broke on validation query 2. So the 83% is gated on the hard problem, not the cheap one.
3. **14.4% of the loss is reachable by no grain change at all.** 73 rows are one printed number
   carrying its subsequent history, and the record has no representation for `corrected`,
   `aff'd` or `vacated`. That is a separate design question from the grain, and it is the
   question the 78-of-85 history-word figure actually asks.

**What would falsify this**: a count of two-match lines materially above 12, or one-match
multi-date lines that are two independent citations rather than a history string. Neither is
in the 85. The floor caveat still holds in the same direction as before —
`find.py:206` de-duplicates identical lines, so two occurrences printing the same line collapse
to one element and cannot enter the one-line count; a collapsed identical line cannot carry two
different dates, so the 85 is a floor.

## The decision, 2026-09-12: the grain does not change

**The operator answered question 0: no.** ADR 0017 D4 stands, unedited and unsuperseded — the
span test remains disjunctive over occurrences, `find.find` keeps folding, and
`(citing_document, page, target_kind, target_key)` remains the key of a finding.

The reasons, all measured and all in this document above:

- **The loss is 0.69% of rows** — 506 of 73,838 live readings, confirmed over the whole store
  rather than the 4,000-row sample.
- **14.4% of that loss is reachable by NO grain change.** 73 of the 85 one-line cases are one
  citation carrying its subsequent history — `corrected`, `aff'd`, `vacated`, `recon. denied` —
  with a single match of the number and several dates hung off it. 78 of the 85 have a history
  word between the dates. A finer grain cannot separate what the page prints as one cite.
- **The 85.6% that IS reachable needs a per-occurrence `citation_resolution`**, which is shape
  A — withdrawn because it breaks validation query 2. Measured again on 2026-09-12 from the
  other side: it is a four-table key change (`citation_resolution`, `citation_judgement` and
  `citation_treatment` all key on `reading_channel` as the only handle on a reading) plus a
  fan-out fix at three join sites — `project.py:170-173`, `citator-query-2.sql:199-203` and
  `review._base` (`review.py:92-94`) — where `cited_raw` and `quoted_passage` differ per row so
  `SELECT DISTINCT` cannot collapse them.
- **Every multi-document pair the operator judged survives today.** 6 of 134 judged pairs name
  two documents and in all six the citations fall on different pages, which the key already
  distinguishes.

**And the thing that actually costs him time was never a grain question.** The review burden is
66% of a 1,476-item queue, because `citation_exposed` filters on the exposure judgement and not
on `kind`. He chose to fix that predicate the same day. It needs no schema change, no ADR and no
re-read — which is the whole reason this brief separated citation LOSS from REVIEW BURDEN, and
the reason closing it costs the record nothing.

**What stays open, deliberately:** `citation_occurrence` — the critic's child-table shape — is
not adopted and not refused. It would make the operator's `FD 00001` example representable and
stop a caption and a citation on one page contradicting each other, without touching a key. It
recovers none of the 0.69%. If it is ever wanted, ADR 0026's § Foreclosed prices the rebuild it
would want to share.
