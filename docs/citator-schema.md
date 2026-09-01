# The tables ADR 0017 needs — proposals

> **Status: proposals, 2026-09-01. Nothing here is accepted, and nothing here ships.**
> ADR 0017 is Proposed: its acceptance was taken on 2026-08-31 and held the same day, and its
> § What acceptance must clear first lists six items. This document works each into a concrete
> shape so that reviving 0017 is a yes or a no rather than a design session.
>
> **Revised the same day, after schema-critic review, which found 24 defects in the first
> draft — including one in its headline measurement.** What that changed is recorded rather
> than quietly corrected: the first draft published 100% precision after projection, and the
> honest figure for the shipping method is 98.2%. The difference is the whole reason the
> review was run.
>
> `schema-draft.md` § Citations is the drafted shape these revise. It is three revisions behind
> what 0017 proposes and is revised **on acceptance**, not before.

## The measurement

Decision 4 stamps confidences Claude earned on a class that, under amendment 1,
`regex-docket-cite` ships. The figure the amendment implies — regex precision on the
docket-shaped class once decision 5 has done its work — appeared nowhere in the record.

**Method.** Re-score the existing runs with `benchmark_score.py` against the checked 977-row
sheet, then classify every docket-shaped extra. Both sides normalised with the scorer's own
`norm_target` (without it `EP 328 (2)` and `EP 328 (Sub-No. 2)` read as different dockets).
The family closure is the live one — `web/cite.py`: self, children, parent, **not** siblings,
because two sub-dockets of one AB parent are unrelated abandonments. Registry:
`data/prod-copy.sqlite`, 32,605 docket rows, **0 of the sixty decisions absent from it**.

**Decision 5 does not absorb an own-proceeding mention. It suppresses one at docket level and
PROJECTS one whose span resolves to a different work** — which is the reconsideration edge Q2
exists to find. So an extra is only absorbed if its quoted span names no document; one carrying
`Decision No. …` or `slip op.` or a served date is projected, and counts against precision.

| Docket-shaped class | truth | emitted | found | recall | precision, as scored | extras decision 5 suppresses | extras it projects | precision after |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `regex-docket-cite` | 225 | 243 | 214 | **95.1%** | 88.1% | 25 | **4** | **98.2%** |
| `model:claude-sonnet-5` | 225 | 225 | 215 | **95.6%** | 95.6% | 10 | 0 | **100%** |

**Neither engine emits an edge to a proceeding the citing decision was not entered in** — 29 of
29 and 10 of 10 extras are own-proceeding, which is `citator-gate.md`'s governing rule measured
directly. But regex's four projected extras are potential wrong edges: all four are spans like
`Decision No. 1, FD 36744 et al., slip op. at 6` — the decision citing a prior decision in its
own consolidated proceeding. They may be sheet omissions rather than errors; nobody has judged
them.

**What this figure is, and is not.** It is a property of the **pair** — extractor plus decision
5 — not of the extractor, and it may only be published with the rule named beside it. It is 60
decisions, not the corpus. It is measured over the **text layer**; decision 1 ships OCR at
10.8% CER for image-only files and no figure here covers that reading. And the registry it was
filtered against is a 2026-08-26 copy holding 32,605 rows against production's 32,623 — a
smaller registry suppresses emissions, so production will emit targets that were never scored.
**That bias runs against the number, not for it.**

**Unreconciled, and it changes a queue size.** 0017 states the exposed class is "5 of 225"; the
same test applied here (a target whose last-digit-stripped reading is also a held docket) yields
**14**, and 0017's own "5 + 214" does not sum to 225 either. Decision 6 sizes its human review
queue on that number. One definition of the exposure test, written once, before acceptance.

---

## A. Decision 1 must not buy the model for the role of a same-docket mention

**Proposal.** Strike it. The model ships for reporter cites, date-named decisions, court
citations and dated obligations; the *role* of a same-docket mention stays with the own-docket
rule, on the extraction row.

0017's own § What the finished batch changed concludes it — "the record already knows that, so
it is the one thing no extractor should be asked to decide" (own-docket rule 95.1%/88.1%,
llama3.1:8b 96.9%/79.3%, qwen3:14b 83.1%/95.9%). And decision 2's natural key has no method in
it, so a model asked for the role would either collide with the regex row for that target on
that page, or write `kind` onto a row it did not extract, which § Foreclosed forbids.

**And the same argument goes further than 0017 uses it.** Claude still ships for other classes
and will incidentally emit docket-shaped targets that regex owns. Nothing says what becomes of
them: dropping them contradicts "a row is never discarded", keeping them collides. *Proposal:*
**one owning method per `target_form`**, with out-of-scope findings recorded at run level — an
`extraction_run` row carrying counts — so "discarded" is an auditable number and not a silent
drop.

---

## B. Amendment 3 names a table that does not exist

**Proposal: a typed table, not a generic assertion row.**

```sql
decision_decided_date (
  document_sha256       FK document,   -- = the block's asserted_from_document
  date_kind             text,          -- FK date_kind_vocab: 'decided' | 'effective' | ...
  source_location       json,          -- the block's own shape (schema-draft § 5)
  reading_channel       text,          -- FK reading_vocab: 'text-layer' | 'ocr'
  method                text,
  method_version        text,
  reading_method        text NULL,     -- the OCR engine, OUTSIDE the key
  reading_method_version text NULL,
  printed_text          text NOT NULL, -- "Decided: October 5, 2017", exactly as printed
  decided_date          text NULL,     -- the ISO reading; NULL when the line will not parse
  -- provenance + supersession block (ADR 0007)
)  -- natural key: (document_sha256, date_kind, source_location, reading_channel,
   --               method, method_version)
```

Four things this settles, three of them corrections the critic made to the first draft:

1. **Typed, not EAV.** Every assertion table in `schema-draft.md` § 5 is purpose-shaped; a
   generic `document_assertion(document, type, value)` would store a date as untyped text. It
   also lets the column be indexed for the docket calendar, one of the three reasons the date
   was wanted.
2. **The OCR engine's version is OUTSIDE the key.** *(Corrected.)* The first draft put
   `reading = 'ocr:<method>@<version>'` in the key, so a re-OCR at a new version would mint a
   row that superseded nothing and double the live rows for the scanned corpus — 1,480 of 9,663
   wave 2–3 files are image-only, so not a corner. Splitting channel from engine means a re-OCR
   matches the key and supersedes.
3. **`method`/`method_version` are IN the key.** *(Corrected.)* The first draft added `reading`
   because "no rule orders two methods asserting at the same time" and then left the method
   axis open — two date extractors over one text-layer page would collide. `citation_resolution`
   is keyed the same way; this mirrors it.
4. **`printed_text` is not optional.** Dates are quoted, never computed — the comment tables
   carry this scar already (`date_received_or_sent` is a derivation, with the printed form kept
   in the payload). Recovering it later is the ~$1,335 re-run the amendment exists to avoid.

**Measured, so the projection rule needs no tie-break:** over the sixty decision texts, 55
print exactly one `Decided:` line, 5 print none, **and none prints two**. So the rule is
simply: prefer the text-layer reading where `document_page.had_text_layer`, else the
highest-confidence OCR reading.

**The five that print none have no home here, and need one.** `printed_text NOT NULL` is right,
so a document with no line gets no row — making "read, and there is no printed decided date"
indistinguishable from "not yet passed over". Both the docket calendar and `web/cite.py`'s
coverage condition need that distinction. *Proposal:* record the **pass**, not the absence — an
`extraction_run` row per `(document, method, method_version)`, which § A already wants for a
second reason.

**Projection to the work.** One work can carry rows under an erratum's bytes as well as the
original's. Decision 7 folds edges to the work; the same fold is owed here. The first draft said
"the head of the `supersedes_sha256` chain wins", which states no direction — the live column
points new → old, it lives on `document_source` (several rows per document), and § 2 warns a
regenerated file changes bytes without changing content. **The direction and the tie-break must
be written down, not implied.**

---

## C. Decision 4's confidence table stamps the wrong engine

**Proposal.** Key confidence `(method, method_version, class, reading_channel, benchmark_date)`,
append-only, carrying the score file — and let the resolution row join it rather than stamping a
number of its own.

| method | class | reading | recall | precision after decision 5 | projected? |
| --- | --- | --- | --- | --- | --- |
| `regex-docket-cite` | docket, resolved, unexposed | text-layer | 95.3% | **98.2%** (whole class) | yes |
| `regex-docket-cite` | docket, resolved, exposed | text-layer | — | — | to the review queue |
| `regex-docket-cite` | any | ocr | **unmeasured** | **unmeasured** | never, by decision 4's own rule |
| `model:claude-sonnet-5` | reporter, date-named, court, deadline | text-layer | as `extraction-benchmark.md` | — | not in this slice; stored |

Three corrections to the first draft, all the critic's:

- **`reading_channel` belongs in the key.** Every figure was measured over the text layer, and
  decision 1 ships OCR at 10.8% CER. Without it the first backfill stamps a text-layer
  confidence on OCR edges and decision 9 shows it to a reader.
- **`benchmark_date` and the score file belong in it too**, or re-measuring the same
  `method_version` is an UPDATE on a published number — break A2. Decision 1 already created a
  `method` registry for exactly this; the first draft dropped it.
- **One home for the number.** Decision 4 stamps confidence on the row; this table also holds
  it. The row should carry none and join.

**On publishing it.** Not as "100%", which the first draft did and which was wrong; and not as
"no wrong docket in 225 measured edges" either, which overclaims three ways — 225 is the truth
count, not what was checked (243 were emitted); it includes the exposed class this same document
routes to humans *because it could be wrong*; and it describes the pair, not the method decision
9 displays beside it. If it is published at all: *"of the 243 docket-shaped targets
`regex-docket-cite` emitted on the sixty-decision sheet, four named a proceeding the decision
was entered in and would still be projected as edges."*

---

## D. Decision 8's supersession path

**Proposal — and not the first draft's.** The first draft hashed decision 2's natural key into
an opaque `citation_key`. That is unsound: the normalisation has already changed once (the
scorer's docket-suffix fix moved the docket-shaped truth from 220 to 225 targets on 2026-08-30),
and under a digest that class of change rewrites every key and strands every human row — the
exact failure the column exists to prevent. A digest also cannot be read on a review page, cannot
be partially indexed, and hides the change that strands the rows.

**Instead:** carry decision 2's four natural-key fields as typed columns on `citation`, and have
`citation_resolution` reference them as a composite — the draft's idiom everywhere else
(`place_mention`, `document_party`, `service_list_member` all declare natural keys on typed
columns). Where a single text key is wanted, render it canonically
(`<sha256>/<page>/<target_kind>/<key>`) rather than digesting it, and carry `key_version` so a
normaliser change is a migration somebody can see.

**It is more urgent than when it was deferred, not less.** The deferral was priced against a
~$1,335 re-run: rare and dear. Amendment 1 moves the docket class — the only class projected
unreviewed, and the one both of decision 6's queues sit on — onto a **free** extractor, so the
stranding event is now cheap and frequent.

**Two limits to state rather than imply.** ADR 0016's column for the row under review is
`review_action.target_key`; `produced_key` names the row the action *wrote*, and pointing it at
the citation would break § 7's authoritative join to `reviewer.credit_name`. (The first draft
named the wrong column.) And because `citing_document` is a sha256, a human review of an edge in
the original does not follow into an erratum's bytes: decision 7 folds *edges* to the work at
projection, not *human resolutions*.

---

## E. The on-page veto's reading scope

**Proposal.** Three clauses:

1. It is a `citation_resolution` row like any other, with its own ADR 0007 block. The extraction
   is never discarded for failing it; the reason is recorded.
2. **It names the reading it checked, and that must be the extraction's own reading.** Measured
   on born-digital text (15 failures of 977, all page-spanning quotes); decision 1 ships OCR at
   10.8% CER, and a text-layer extraction checked against OCR text would be vetoed spuriously.
3. **What it carries is a false-veto rate, not a confidence** *(corrected)* — those 15 failures
   were all false vetoes, at 1.5%, over every class on born-digital text only. It is unmeasured
   for OCR, and a veto *suppresses* a projected edge, so an unmeasured veto must never suppress:
   otherwise decision 4's "a NULL confidence is never projected" is inverted by the back door.

After amendment 1 the veto protects nothing currently projected — regex quotes are on-page by
construction, and every model-shipped class is stored rather than projected. **It would ship
inert.** The projection view should not reference it until it is measured on both readings.

---

## F. Two columns Q2's own join needs

- **`treatment` has no home.** *(Corrected from the first draft, which put it on
  `citation_resolution`.)* Treatment is an edge-level reading of the citing sentence; resolution
  is target identification. Sharing a row forces a typing pass to restate the resolution or write
  NULLs into a column whose NULL already means three things. *Proposal:* `citation_treatment`,
  its own assertion table keyed `(citation natural key, method, method_version)` with its own
  ADR 0007 block — the separation 0017 already made between extraction and resolution, once more.
- **`cited_decision_id` keys on a key of no table.** *Proposal:* `decision_work
  (stb_decision_id text PRIMARY KEY)` **and nothing else** — no attributes, or current state
  enters a registry by the back door; written **only by ingest** from `decision_observed`,
  rebuildable from the ledger; the resolver may reference but never insert.

  **Measured before proposing a primary key, because it is a one-way door:** 1,736
  `stb_decision_id`s carry more than one `decision_record` row, and **not one of them disagrees**
  on service date or decision number. Consolidation, not collision. The key is safe.

**Q2 still does not run**, and neither draft made it. `citation_resolution` is keyed
`(citation_id, method, method_version)` with supersession *within* a method, and §C blesses two
methods while §E adds a veto row — so several resolutions are live per edge with no precedence
column, and any "cited by" count is inflated. **A typed outcome and a precedence rule are owed
before the first projection**, which 0017's own re-check said and neither draft closed.

---

## G. Settled by the operator, 2026-09-01

**A typed `confidence_state`, and `confidence` stays NOT NULL.** The state is `measured` |
`unmeasured` | `not-applicable`.

The question was that decision 4 permitted a NULL confidence "where the class is unmeasured",
which narrows ADR 0007's categorical text — every extracted fact carries a confidence — inside
a record that is not 0007, and against the live convention (`0006_parties.sql` declares
`confidence REAL NOT NULL CHECK (> 0 AND <= 1)` on all four party tables). Amendment 1 widened
the reach of that NULL, because the classes the model keeps are exactly the ones with no
readable precision.

Three ways were on the table: write ADR 0018 to narrow 0007 explicitly; drop the NULL case so
an unmeasured class does not ship; or this. It was the schema-critic's suggestion and it was
not among the options 0017 itself considered. What it buys:

- **ADR 0007 is not narrowed at all**, so no second record is owed and 0017 stops making a
  decision that belongs elsewhere.
- **"Only a measured confidence is projected" becomes a positive predicate** on the
  projection view, rather than a NULL test — decision 4's rule enforced by the schema instead
  of by prose.
- **It avoids the NULL-comparison trap**, where `WHERE confidence >= 0.9` and
  `WHERE NOT (confidence < 0.9)` disagree on NULL rows: a real hazard on a projection view
  that a reader's "cited by" list is built from.

What it costs, and what must be decided with it: an unmeasured class still has to put *some*
number in `confidence`, and whatever that number is must never be read. The state is the
predicate; the number is inert. Say so where the column is declared, or the next reader will
average it.

## Still open, and named rather than hidden

- **The four projected extras have not been judged.** Are they sheet omissions or real wrong
  edges? Four spans, one sitting; it decides whether 98.2% is a floor or the number.
- **The exposure test has two definitions** — 5 in 0017, 14 here — and decision 6's queue is
  sized on it.
- **The classifier is not in the repository.** It ran from the scratchpad. If the figure is to be
  published it needs to live beside `benchmark_score.py` and be re-runnable.
- **Nothing here is exercised by a validation query.** `decision_decided_date` serves display,
  the calendar and paper reconciliation; none is one of the five. That is not a reason to reject
  it, but its grain is unvalidated by the mechanism this project uses to validate grain — and
  0017's own re-check already conceded Q4 gains little, so this document should not borrow Q4's
  endorsement, as its first draft did.
