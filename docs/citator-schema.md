# The tables ADR 0018 needs — proposals

> **Status: proposals, 2026-09-01. Nothing here is accepted, and nothing here ships.**
> ADR 0017 and ADR 0018 are both Proposed and both cleared by the schema-critic. This document
> works each open item into a concrete shape so that deciding them is a yes or a no rather
> than a design session.
>
> **Decision numbers below are the pre-split ones.** ADR 0017 grew to 1,082 lines by bundling
> a shipping decision with a schema and was split on 2026-09-01. Where this document says
> "decision N", read:
>
> | pre-split | now |
> | --- | --- |
> | 1 — regex ships, registry check in resolution, one owning method | 0017 D1–D2; 0018 D1 |
> | 2 — the `citation` row, its natural key, the reading | 0018 D1–D3 |
> | 3 — resolution and precedence | 0018 D4, D7 |
> | 4 — confidence and the measurement registry | 0017 D3; 0018 D8 |
> | 5 — self-reference, the span test, the judgements | 0017 D4; 0018 D5 |
> | 6 — what is left to a human | 0017 D5 |
> | 7 — projection folds by work | 0018 D9 |
> | 8 — not in this slice; `extraction_run`; keys; the decided date | 0017 D7; 0018 D10 |
> | 9 — what a reader sees | 0017 D6 |
>
> Section names also moved: § Amendment candidates, § What the finished batch changed and § Foreclosed were pre-split sections and are in git, not on disk. "Amendment 1" is 0017 D1; "amendment 3" is 0018 D8.
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
| `regex-docket-cite`, as benchmarked (registry filter in the finder) | 225 | 243 | 214 | 95.1% | 88.1% | 25 | 4 | 98.2% |
| `regex-docket-cite`, **as decision 1 now specifies it** (check in resolution) | 225 | 249 | 220 | **97.8%** | 88.4% | 25 | **4** | **98.2%** |

**That table measures EXTRACTION. It is not what a reader sees** *(added 2026-09-01)*. Running
the whole chain — resolution, then decision 5's gate — gives **89.3%** projected recall
(201 of 225) at **98.0%** precision (201 of 205 shown). The 24-edge gap is 10 real edges the
registry cannot resolve (review queue), 9 own-family self-references suppressed by design, and
5 the finder never saw. Re-derive with `tools/rmi-ai-machine/projection_score.py`, which
reports every stage at once precisely so a figure cannot be quoted for a stage it did not
measure — the error ADR 0017 made four times.
| `model:claude-sonnet-5` | 225 | 225 | 215 | **95.6%** | 95.6% | 10 | 0 | **100%** |

**Neither engine emits an edge to a proceeding the citing decision was not entered in** — 29 of
29 and 10 of 10 extras are own-proceeding, which is `citator-gate.md`'s governing rule measured
directly. But regex's four projected extras are potential wrong edges: all four are spans like
`Decision No. 1, FD 36744 et al., slip op. at 6` — the decision citing a prior decision in its
own consolidated proceeding. They may be sheet omissions rather than errors; nobody has judged
them.

**Moving the registry check out of the finder costs nothing and recovers six real edges.**
Measured 2026-09-01 by re-running the finder with the filter removed: the six targets it had
been suppressing are `EP 445`, `EP 445 (Sub-No. 1)`, `EP 392 (Sub-No. 1)`, `FD 757`,
`FD 36873 (Sub-No. 2)` and `FD 37470` — the six this record already named as registry
unresolvables — and **every one is a real edge in the sheet**. No false positive arrives with
them, and the post-decision-5 precision is unchanged. They become the `docket, unresolved`
class and decision 6's second review queue, which a finder-side filter had emptied by
construction.

**What this figure is, and is not.** It is a property of the **pair** — extractor plus decision
5 — not of the extractor, and it may only be published with the rule named beside it. It is 60
decisions, not the corpus. It is measured over the **text layer**; decision 1 ships OCR at
10.8% CER for image-only files and no figure here covers that reading.

**And the registry bias inverts once the check leaves the finder** *(corrected 2026-09-01,
second critic pass)*. The scored run used a 2026-08-26 copy holding 32,605 rows against
production's 32,623. While the filter sat inside the finder, a smaller registry suppressed
emissions, those suppressions scored as *misses*, and the bias ran conservative — against the
number, not for it. With the check in the resolution pass it runs the other way: a **larger**
production registry, still growing through waves 2–3, **resolves** more targets, and every
newly-resolved target is a newly-**projected** edge that was never scored. That is a precision
risk, not a recall understatement, and the exposure test is the only thing standing in front
of it — which is why defining it was a blocker. **It is defined now** (ADR 0017 § The exposure
test, 2026-09-01): a bare docket number of four digits or fewer whose last-digit-stripped
reading is a held docket, which is 3 of 225.

**Settled 2026-09-01, and it was never really two definitions.** This section read "14" and
0017 read "5". Re-measured against the sheet, the answer is **3 of 225** — `AB 1014`,
`AB 1071`, `AB 1242` — and the wider readings are excluded by the extractor's own grammar
rather than by preference: a `DOCKET` match ends in a closing paren, a letter suffix or a bare
digit run, and only the last can swallow a following digit; `\d{1,5}` then caps the sequence so
a five-digit docket cannot absorb a sixth. Across 994 printed forms in the 60 decisions exactly
one carries a fused marker — `Docket No. EP 665 (Sub-No. 2)1`, decision 52526 — and it lands
after the paren, where the extractor never absorbs it. The "5" was measured against a
220-target sheet before the scorer's suffix fix. Full argument in ADR 0017.

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
**one owning method per `(target_kind, target_form)`** (settled in ADR 0018 decision 1;
keyed on the form alone, regex would own `docket` while only ever emitting `target_kind =
'stb'`, so the model's **court** docket numbers fall out of class), with out-of-scope
findings recorded at run level — an `extraction_run` row carrying counts — so "discarded" is an auditable number and not a silent
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
)  -- natural key: (document_sha256, date_kind, reading_channel,
   -- `source_location` REMOVED from the key 2026-09-01 (fifth critic pass): it is JSON, and
   -- with exactly one `Decided:` line measured per document it buys no uniqueness while a
   -- layout-parser change would mint a row that supersedes nothing — this section's own
   -- point 2, one column over. It stays as payload, which is what ADR 0007 requires of it.
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
simply: prefer the text-layer reading, else the OCR reading whose own confidence is
higher. (`document_page.had_text_layer` is paper-only — it is in `schema-draft.md` and in
no migration — so the rule keys off `reading_channel`, which is in the key, and not off a
column that does not exist.)


**The five that print none have no home here, and need one.** `printed_text NOT NULL` is right,
so a document with no line gets no row — making "read, and there is no printed decided date"
indistinguishable from "not yet passed over". Both the docket calendar and `web/cite.py`'s
coverage condition need that distinction. *Proposal:* record the **pass**, not the absence — an
`extraction_run` row per `(document, method, method_version, reading_channel)` — the channel
is in the key from the start (ADR 0018 decision 10), because a text-layer pass and an OCR pass
over one document at one method version otherwise collide, and re-keying later touches one row
per document per method across 75,000–125,000 documents — which § A already wants for a
second reason.

**Projection to the work.** One work can carry rows under an erratum's bytes as well as the
original's. Decision 7 folds edges to the work; the same fold is owed here. The first draft said
"the head of the `supersedes_sha256` chain wins", which states no direction — the live column
points new → old, it lives on `document_source` (several rows per document), and § 2 warns a
regenerated file changes bytes without changing content. **The direction and the tie-break must
be written down, not implied.**

---

## C. Decision 4's confidence table stamps the wrong engine

**Settled in ADR 0018 decision 8, 2026-09-01.** This section originally proposed keying
confidence `(method, method_version, class, reading_channel, benchmark_date)` and letting the
resolution row **join** it rather than stamp a number of its own. That is **not** what shipped,
and this paragraph is corrected rather than left standing, because the acceptance sentence binds
both documents and they cannot declare two shapes for one table. What the ADR settles:

- The row **carries** `confidence NOT NULL` plus a typed `confidence_state`, because deleting
  the column departs from ADR 0007 further than the NULL it was avoiding, and because decision
  9's per-edge display needs a value on the row it is displaying.
- The registry is **one append-only table**, `class_measurement`, keyed `(extraction m+v,
  resolution m+v, class, reading_channel, projection_rule_version, benchmark_date)` and
  carrying the score file, recall and precision. The row's `score_row_id` names the exact
  measurement it was stamped from. *(This bullet described a split into `confidence_class` +
  `class_measurement` and carried its argument — that holding `projection_rule_version` in
  the FK'd key would force an every-row UPDATE. Both are **withdrawn**, 2026-09-01: a pointer
  into an append-only table never needs updating, because a rule change mints a measurement
  and earlier rows keep the historical one, which is the snapshot Q3 wants. `confidence_class`
  does not exist.)*

**ADR 0018 decision 8 governs where the two disagree.**

| method | class | reading | recall | precision after decision 5 | projected? |
| --- | --- | --- | --- | --- | --- |
| `regex-docket-cite` | docket, resolved, unexposed | text-layer | **no figure until the exposure test defines this class** | — | yes |
| `regex-docket-cite` | docket, resolved, **whole class** (exposed and not) | text-layer | **89.3% projected** (201 of 225) — the finder emits 97.8% and the registry resolves 93.3%; neither is what a reader sees | **98.0%** of what projects (201 of 205), under `cite.py`'s closure | — measurement only |
| `regex-docket-cite` | docket, unresolved | text-layer | — | — | never; to decision 6's second queue |
| `regex-docket-cite` | docket, resolved, exposed | text-layer | — | — | to the review queue |
| `regex-docket-cite` | any | ocr | **unmeasured** | **unmeasured** | never, by decision 4's own rule |
| `model:claude-sonnet-5` | reporter, date-named, court, deadline | text-layer | as `extraction-benchmark.md` | — | not in this slice; stored |

Three corrections to the first draft, all the critic's:

- **`reading_channel` belongs in the key.** Every figure was measured over the text layer, and
  decision 1 ships OCR at 10.8% CER. Without it the first backfill stamps a text-layer
  confidence on OCR edges and decision 9 shows it to a reader.
- **`benchmark_date` and the score file belong in it too**, or re-measuring the same
  `method_version` is an UPDATE on a published number — break A2. *(Corrected 2026-09-01: this
  cited decision 1's `method` registry, which is **struck** — it overlapped `class_measurement`
  on every column, and one number may not have two homes.)*
- **One home for the number, and it is the row plus a pointer.** *(Corrected 2026-09-01, fifth
  critic pass: this read "The row should carry none and join", which is the position ADR 0017
  decision 4 was corrected away from — deleting the column departs from ADR 0007 further than
  the NULL it avoided, and decision 9's per-edge display needs a value on the row it displays.
  The row carries `confidence` and `score_row_id`; `class_measurement` holds the measurement.
  One number, one home, one pointer.)*

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
inert**, and the projection view should not reference it until it is measured on both readings.

*(Reconciled with ADR 0018 decision 7 — decision 3 pre-split — 2026-09-01, third critic pass: the veto still holds
rank 2 in the resolution order, which is not a contradiction of "ships inert" — it is ranked
for when it is measured, and referenced by no projection until then. One thing the order does
have to say: **the projection predicate `confidence_state IN ('measured','human')` is applied
to the CANDIDATE SET**, and a `suppress` row carries `confidence_state = 'measured'` so the
predicate does not filter it out. *(This paragraph said the opposite — "applied to the rank-1
row, not to the candidate set" — under a heading claiming reconciliation, until 2026-09-01.
The rank-1 reading was retired when `role` was introduced: a suppressor is evaluated by its own
existence and never by rank, so it cannot be filtered out of a ranking it does not enter. Left
on the rank-1 row the predicate instead DELETES edges, because an unmeasured OCR resolution
outranking a measured text-layer one takes rank 1 and the edge vanishes. ADR 0018 decision 7
governs.)*

---

## F. Two columns Q2's own join needs

- **`treatment` has no home.** *(Corrected from the first draft, which put it on
  `citation_resolution`.)* Treatment is an edge-level reading of the citing sentence; resolution
  is target identification. Sharing a row forces a typing pass to restate the resolution or write
  NULLs into a column whose NULL already means three things. *Proposal:* `citation_treatment`,
  its own assertion table keyed `(citation natural key, method, method_version,
  reading_channel)` with its own ADR 0007 block *(the channel added 2026-09-01 — stated
  without it here and with it below, which is two keys for one table)* — the separation 0017 already made between extraction and resolution, once more.
- **`cited_decision_id` keys on a key of no table.** *Proposal:* `decision_work
  (stb_decision_id text PRIMARY KEY)` **and nothing else** — no attributes, or current state
  enters a registry by the back door; written **only by ingest** from `decision_observed`,
  rebuildable from the ledger; the resolver may reference but never insert.

  **Measured before proposing a primary key, because it is a one-way door:** 1,736
  `stb_decision_id`s carry more than one `decision_record` row, and **not one of them disagrees**
  on service date or decision number. Consolidation, not collision. The key is safe.

**Settled in ADR 0018 decision 4 (2026-09-01); ADR 0018 governs.** This paragraph read
"**Q2 still does not run**", and declared `citation_resolution` keyed
`(citation_id, method, method_version)`. Both are superseded. The key is the citation's
**natural key** plus `(method, method_version, reading_channel)` — no surrogate id — and the
typed `outcome` and the precedence rank this paragraph said were owed are now decided: the
outcome is a column, the rank is on the resolution method rather than on every row. What this
paragraph got right and is kept for: several resolutions ARE live per edge, so a "cited by"
count that does not pick one is inflated.

`citation_treatment` takes `reading_channel` in its key for the same reason
`citation_resolution` does — a typing pass over a text-layer and an OCR reading of one page
otherwise collides on the whole key, which is the defect § B fixed for
`decision_decided_date`.

---

## G. Settled by the operator, 2026-09-01

**A typed `confidence_state`, and `confidence` stays NOT NULL.** The state is `measured` |
`human` | `unmeasured` | `not-applicable` (ADR 0017 decision 4; `human` was added
2026-09-01 because a review has a confidence, and folding it in with the veto forced every
reviewed row to zero while `human` sat in the projection predicate).

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
- ~~**The exposure test has two definitions** — 5 in 0017, 14 here~~ — **settled 2026-09-01
  as 3 of 225**; see above and ADR 0017 § The exposure test.
- **The classifier is not in the repository.** It ran from the scratchpad. If the figure is to be
  published it needs to live beside `benchmark_score.py` and be re-runnable.
- **Nothing here is exercised by a validation query.** `decision_decided_date` serves display,
  the calendar and paper reconciliation; none is one of the five. That is not a reason to reject
  it, but its grain is unvalidated by the mechanism this project uses to validate grain — and
  0017's own re-check already conceded Q4 gains little, so this document should not borrow Q4's
  endorsement, as its first draft did.
