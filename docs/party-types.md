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
| `association` | 682 | `Corn Refiners Association` | trade groups, unions, coalitions |
| `law-firm` | 27 | `Baker & Miller PLLC` | firms filing in their own name |
| `agency` | 1 | the Board | exists today; never re-derived |
| *(unmatched)* | 2,028 | `10th District of Ohio` | largely elected officials/districts (→ `government`), `And X` split artefacts, and the genuinely hard tail |

The vocabulary is a table, extensible by INSERT (`elected-official` may deserve its own
row rather than folding into `government`; the checked sample decides). One type per
party at a time: a holding company that owns railroads is a `company`; the *railroad* is
the subsidiary (the succession graph already relates them). A type is never a position
and never affects how a filing is read (the non-negotiables stand).

Measured cautions, from the same pass — why rules alone do not publish:

- `3M Transportation Department` rule-matches `government` ("Department"); it is a company.
- `Ace Federal Reporters` rule-matches `government` ("Federal"); it is a company.
- Names beginning `And …` (`And Cargill;Incorporated`) are split artefacts of the Board's
  list cells; a type asserted on a malformed name compounds the earlier defect. These
  route to review of the *span*, not classification of the name.

## Method: three tiers, one discipline

1. **Ground truth first.** A stratified sample (~300 parties: every draft type, the
   unmatched tail oversampled) is drafted by rule and model, then **checked by the
   operator** through the ADR 0016 queue machinery (or its interim equivalent, as the
   labels sheet was). No figure is published and no label ships before that check; the
   sample is the truth the tiers are measured against.
2. **Rules, `method = 'rule:party-type'`,** versioned, for what a name states on its face
   — measured precision per type on the checked sample decides which types (if any) ship
   unreviewed at rule confidence. The reporting-mark and succession signals join the
   rules (a party with a held `mark` name is a `railroad` at high confidence).
3. **A model for the tail,** `method = 'model:<name>'`, batched locally or via API —
   *measured on the checked sample before it writes anything*, like every extractor.
   Low-confidence and disagreeing classifications queue for review (ADR 0016;
   `review_action.queue = 'party_type'` joins the vocabulary); a `human` row wins and is
   never overwritten.

Every assertion: the ADR 0007 block, confidence = the tier's measured precision for that
type (the benchmark's convention), supersession on re-runs. Re-classification at a higher
method version writes new rows; nothing rewrites.

## Schema shape (to schema-critic before it exists)

```sql
party_type (                       -- natural key: (party_id, method, method_version)
  party_type_id     bigint PK,
  party_id          FK party,
  type              text,          -- FK party_type_vocab
  -- provenance + supersession block (§ 5): method, method_version, asserted_at,
  -- confidence, superseded_by; asserted_from_* null for rule rows (the source is the
  -- held name, named in source_location as {"name_id": …})
)
party_type_vocab (type text PK, note text)
```

The projection reads one live row per party (highest-confidence live assertion; a `human`
row outranks by the standing rule). A same_as join takes the component's representative's
type; a disagreement inside a component queues for review rather than picking silently.

## The page

`/parties` without a query shows the browse: one section per type with its count,
alphabetical within, **collapsed by default for types over ~200 parties** (`<details>`,
no script), expanded for the small ones; each entry is the component's display name
linking to `/p/<id>`. Unclassified parties are a visible section, not an absence — the
coverage counts on the page come from the store, per the trust rules. The search keeps
its behaviour and its URL.

## What this does not decide

Whether the classification feeds anything beyond browse and display (facets in search,
type-scoped subscriptions) — later choices, each cheap once the assertion exists. And
external enrichment (marks from public registries, F3's fuller registry) stays on the
capability map.
