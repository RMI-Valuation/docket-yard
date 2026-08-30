# Party types (F3's first slice) — design

> **Status: design, 2026-08-30; chosen by the operator the same day** (ROADMAP § Chosen).
> Nothing here is built; the assertion table goes to schema-critic before it exists, and
> nothing publishes before a ground truth the operator has checked — the extraction
> benchmark's discipline (`extraction-benchmark.md`), applied to a smaller question.

## What it is

Every resolved party carries a **type** — what the entity *is* — as a derived assertion
with full ADR 0007 provenance, reviewable under ADR 0016. `/parties` gains a browse by
type beside the search (which stays, per ADR 0015); a party's page and the sheets' Parties
blocks may show the label once it survives review. The Board itself is already shown as
the `agency` — the one label that exists today (`parties/seed.py`, operator-established) —
and this design generalises that, it does not touch it.

## The vocabulary, grounded

Measured 2026-08-30 over the 10,058 live `as_filed` names with a first-draft rule pass:

| type | rule-matched | example | note |
|---|---|---|---|
| `individual` | 2,583 | `Aaron Abeyta` | name-shape rule; the weakest signal — see cautions |
| `company` | 2,293 | `Basin Electric Power Cooperative, Inc.` | non-carrier corporations |
| `railroad` | 1,323 | `Allegheny Valley Railroad Company` | carriers; reporting marks (`party_name.name_kind = 'mark'`, 31 held) confirm |
| `government` | 1,122 | `Washington Grain Commission` | agencies, states, municipalities, ports |
| `association` | 682 | `Corn Refiners Association` | any organised non-governmental collective: trade groups, coalitions, **grassroots/civic committees** (the operator's convention, 2026-08-30); the trade-vs-grassroots distinction is tier 0's to quote, and a later split is an INSERT |
| `law-firm` | 27 | `Baker & Miller PLLC` | firms filing in their own name |
| `agency` | 1 | the Board | exists today; never re-derived |
| *(unmatched)* | 2,028 | `10th District of Ohio` | largely elected officials/districts (→ `government`), `And X` split artefacts, and the genuinely hard tail |

The vocabulary is a table, extensible by INSERT (`elected-official` may deserve its own
row rather than folding into `government`; the checked sample decides). Three additions
the operator made 2026-08-30, before the check:

- **`rail-holding`** — a company whose business is owning rail carriers (`Patriot Rail
  Corp`, measured as ten-plus party records). Folding these into `company` was
  unsatisfying and the graph cannot derive them yet (12 `parent_of` edges held in all);
  name signals (221 holding-ish names), Wikidata, and — as the graph fills — a
  `parent_of` a railroad corroborate.
- **`utility`** — electric and power entities (204 candidate names, `Basin Electric
  Power Cooperative`); the rate-case complainant constituency deserves its own row.
- **`port`** (the operator, same day) — port authorities and terminal/harbor operators,
  today swallowed by the `government` rule's `port of` signal, which moves here. Public
  authorities and private terminal companies share the row; the distinction, where a
  document states it, is tier 0's to quote.
- **`labor-union`** (the operator, same day) — rail labor organisations (the
  Brotherhoods, SMART-TD, Teamsters), a distinct constituency in merger and
  labor-protective-condition cases; the `union|brotherhood|federation` signals move here
  from `association`, keeping the `Union Pacific`/`Union County` guards.
- **An attorney is an `individual`; representation is a role, never a type** (the
  operator's question, 2026-08-30). `law-firm` is the organisation filing in its own
  name; a named lawyer is a person, whoever they appear for — "attorney for X" is a
  relationship the record states (signature blocks, "on behalf of") and belongs to a
  future representation layer, not to the type. The check note "counsel" flags the
  population for that later work.
- **Carrier status ("a noncarrier") is an attribute too** (the operator's question,
  2026-08-30, on `AJAK Rail, LLC`): the Board's word for an entity that has not yet
  consummated its authority — true on a date, false after consummation. An entity whose
  business is rail operation, including one formed to acquire a line, is judged
  `railroad`; carrier-vs-noncarrier at a moment is tier 0's to quote, superseded when it
  changes, exactly like class.
- **Railroad class (I/II/III) is an attribute, not a type.** The Board's own
  revenue-based classification, time-varying and rarely knowable from a name — so it is
  never judged in the name queue. It lands as its own assertion on `railroad` parties,
  fed by tier 0 quotes (*"a Class III rail carrier"*) and Wikidata's class typing, with
  supersession carrying re-classifications; the browse can facet by it once it exists.

One type per party at a time: a holding company that owns railroads is `rail-holding`,
never `railroad`; the *railroad* is the subsidiary (the succession graph relates them).
A type is never a position and never affects how a filing is read (the non-negotiables
stand).

Measured cautions, from the same pass — why rules alone do not publish:

- `3M Transportation Department` rule-matches `government` ("Department"); it is a company.
- `Ace Federal Reporters` rule-matches `government` ("Federal"); it is a company.
- Names beginning `And …` (`And Cargill;Incorporated`) are split artefacts of the Board's
  list cells; a type asserted on a malformed name compounds the earlier defect. These
  route to review of the *span*, not classification of the name. **The same rule covers a
  name that joins two entities with `and`** (`Patriot Rail, Llc And Patriot Rail Corp.`,
  two railroads as one record — the operator's observation while judging, 2026-08-30):
  `span-artefact` whatever the halves are, with the check note naming the two parties so
  the re-split knows its answer. The checked sample measures how common the joined-pair
  case is; the draft rule only catches the leading-`And` form.

## Evidence, in rank order — one discipline

**Tier 0 — the record's own words** (the operator's point, 2026-08-30). Filings and
decisions state what a party is: *"a Class III rail carrier"*, *"a Delaware
corporation"*, *"a trade association representing…"*. A type quoted from a document, with
its page and span, is not an inference at all — it is the strongest assertion this
project can make (the same rule that forbids inferring a position permits quoting one).
The citator's extraction pass is the machinery; this tier grows as extraction runs, and
where it exists it outranks every other machine tier.

**Tier 1 — ground truth first.** A stratified sample (~300 parties: every draft type, the
unmatched tail oversampled) is drafted by the tiers below and **checked by the operator**
through the ADR 0016 queue machinery (or its interim equivalent, as the labels sheet
was). No figure is published and no label ships before that check.

**Tier 2 — rules, `method = 'rule:party-type'`,** versioned, for what a name states on
its face. The reporting-mark signal joins (a party with a held `mark` name is a
`railroad` at high confidence); succession edges are **never** walked to type the
*railroad* side — `parent_of` must not leak a subsidiary's type upward (schema-critic).
The one graph-derived signal allowed is the inverse, and only as corroboration:
`parent_of` a railroad supports `rail-holding`, a definition over held rows, not a guess.

**Tier 3 — Wikidata, `method = 'link:wikidata'`, organisations only.** Probed 2026-08-30:
9 of 12 names link once suffixes are normalised, and `instance of` maps cleanly (Union
Pacific → *Class I railroad* Q249556; State of Ohio → *US state*; National Confectioners
Ass'n → *trade organization*). CC0, so licence-clean. **Individuals are never linked**:
the probe's `Sharon Williams` hit a lawyer of that name with full confidence — a wrong
link about a person is both a data defect and a privacy harm. The link itself (the Q-id)
is stored with the assertion, which seeds F3's fuller registry later.

**Tier 4 — a model for the tail,** `method = 'model:<name>'`, measured on the checked
sample before it writes anything, like every extractor.

Low-confidence and disagreeing classifications queue for review (ADR 0016;
`review_action.queue = 'party_type'`); a `human` row wins and is never overwritten. Every
assertion: the ADR 0007 block; confidence = the tier's measured precision for that type
on the checked sample, stamped from the **shared method registry** ADR 0017 decision 1
establishes (method, version, benchmark date, score file) so a re-measured figure is
traceable and a stale one is visible (schema-critic). Re-classification at a higher
method version writes new rows; nothing rewrites.

## Schema shape (revised on schema-critic's report, 2026-08-30; to the critic again with the migration)

```sql
party_type (                       -- natural key: (party_id, method, method_version, evidence_key)
  party_type_id     bigint PK,
  party_id          FK party,
  type              text,          -- FK party_type_vocab(key)
  evidence_key      text NOT NULL, -- what this row is ABOUT: 'name:<name_id>' for a rule,
                                   -- 'doc:<sha256>/<page>' for a document-stated type,
                                   -- 'wikidata:<qid>' for a link, 'party' for a model or
                                   -- human judgement of the whole party
  -- provenance + supersession block (§ 5); unique is partial, WHERE superseded_by IS NULL
)
party_type_vocab (
  key               text PK,       -- stable forever; ADDITIVE-ONLY — a rename is a new
  shown_as          text,          -- key plus a re-classification pass, never an UPDATE
  note              text           -- across assertion rows (break A2; schema-critic)
)
```

The evidence key resolves the measured collision the critic found: SEPTA's *name* says
`government` while its *mark* says `railroad`, and both assertions now exist as rows —
the pick is the projection's, with both on the record. **The projection is a pinned view
with a total order, not prose**: `method = 'human'` first, then the document-stated tier,
then confidence descending, then `asserted_at DESC, party_type_id DESC` as the
deterministic tail — tested the way `party_component` is. A human row's confidence is
irrelevant to its rank, so ADR 0017's "NULL is never projected" rule does not hide it.

**Components** (schema-critic's unjoin walk): a review's `human` row lands on the member
whose evidence was judged — never on the representative as such — so an unjoin (ADR 0015:
a split is a new party) takes the label with the evidence and nothing outlives the
component on the wrong party. The projection shows the component the label of its
highest-ranked live row across members; a cross-member disagreement queues on the member
row that lost, not on the (unstable) representative id.

**The Board**: one operator-established `human` row (`agency`), written when the table
first exists — "never re-derived" then follows from human-wins instead of being a
special case, and `resolve.py`'s render-time name match retires. Until that row exists
the current display behaviour stands.

**Licence** (schema-critic): `party_type` and `party_type_vocab` join `HELD_TABLES` in
the same migration that creates them — classifications are enriched-layer work
(`licensing.md`) and must not reach the CC0 snapshot by allowlist laziness.

## The page

`/parties` without a query shows the browse: one section per type with its count,
alphabetical within, **collapsed by default for types over ~200 parties** (`<details>`,
no script), expanded for the small ones; each entry is the component's display name
linking to `/p/<id>`. Unclassified parties are a visible section, not an absence — the
coverage counts on the page come from the store, per the trust rules; **each count names
its class mix** (how many labels are document-stated, rule, linked, model, human), per
ADR 0017's "no count without its class" (schema-critic). **The publishing gate, stated
once**: a label ships when its tier's measured precision for that type clears the
threshold the checked sample sets, review or no review; a party whose live rows disagree
shows no label ("under review") until the queue resolves it. The search keeps its
behaviour and its URL. A component whose founding span was superseded as malformed (the
`And X` artefacts) is listed under unclassified with its span review linked — it cannot
be un-minted (ADR 0015) and is not hidden.

## Review (schema-critic, 2026-08-30)

The first draft's four breaks, folded in above: the natural key collided on the seed's
own commuter agencies (name says `government`, mark says `railroad`) — resolved by the
`evidence_key`; a vocabulary rename had no lawful path — the vocab is additive-only with
a stable key and a display word; the projection was prose and nondeterministic — now a
pinned, totally-ordered view; a component-level human label outlived an unjoin on the
wrong party — human rows land on the member whose evidence was judged. Also from the
report: the `agency` label becomes an operator `human` row; both tables are HELD from the
snapshot; the method registry is shared with ADR 0017's; the publishing gate is stated
once; span-review products need § 7 to allow plural produced rows (recorded there when
the queue is built). The critic's positive finding stands: because `party_id` is
permanent (ADR 0015), a human type survives every re-classification — the stranding
hazard the citation tables must design around does not exist here.

## What this does not decide

Whether the classification feeds anything beyond browse and display (facets in search,
type-scoped subscriptions) — later choices, each cheap once the assertion exists. And
external enrichment (marks from public registries, F3's fuller registry) stays on the
capability map.
