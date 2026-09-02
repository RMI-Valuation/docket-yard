# ADR 0022 — Where the record's text lives

- **Status:** Proposed
- **Date:** 2026-09-02
- **Addendum to:** [ADR 0012](0012-deployment-topology.md), which stands unchanged
- **Companion to:** [ADR 0021](0021-the-ocr-text-grain.md), which decides what a row means;
  this record decides where its bytes are written.
- **Drafted three times in one day, and the lineage is kept because the mistake repeated.**
  The first draft sent the text-layer text to the blob tier on a cost-to-remake rule.
  schema-critic broke it: search cannot quote what it cannot read, agreement cannot be
  computed from a digest, and the public dump would have published the OCR half of the
  record and withheld the accurate half. The second draft reversed that and **kept the same
  move for the runner-up reading** — a smaller set of bytes, the identical error. The third
  sends only the engine payload out. What follows is the third.

## Context

ADR 0012 put one Lightsail instance, one SQLite file, Litestream streaming its WAL to S3,
and the document blobs in S3 with the instance holding a cache. The blob half runs on a rule
this record was expected to extend: **S3 is the store, the instance is a cache** —
`docketyard-blobs.timer` syncs every 30 minutes, and `prune_blobs.py` deletes any
S3-confirmed local blob **older than 30 days**, with disk pressure below a 20 GB floor as a
*second* trigger rather than the only one.

**ADR 0021 proposes `document_text`, and it would be the first text the store has ever
held.** Nothing of the record's own words is in SQLite today: `extract_text.py` writes JSON
on the enrichment box and the citator's findings come back without text. So "does the text
go in the replicated file?" has never had to be answered, and answering it by default —
because a table is the obvious place to put a string — would be answering it by not
noticing. The file that would grow is the one `litestream restore` pulls back when a
migrating deploy rolls back.

### What the record actually holds, measured 2026-09-02

`tools/rmi-ai-machine/text_layer_census.py` over `/data/docketyard/text` on the enrichment
box — the header of every extraction JSON, no PDF reopened. This supersedes the estimates
two drafts of this record were built on, and it corrects `ocr-plan.md`, which quoted a
single run's manifest that had skipped 13,936 already-extracted files.

| | documents | pages | characters | per page |
| --- | --- | --- | --- | --- |
| image-only | **15,085** (plus one 0-page PDF) | **247,923** | ~0 | — |
| text layer | **59,210** | **857,012** | 1,369,267,089 | **1,598** |

Three of those numbers move earlier reasoning:

- **The image-only side is 247,923 pages, not the ~175,000 `ocr-plan.md` costs everything
  against** — 42% higher. At the routed 2.71 s a page the backfill is about **187 hours**,
  not 132.
- **The text layer is 1.37 GB of characters**, from pages far more numerous and far thinner
  than the sixty labelled decisions suggested (1,598 characters against their 2,722).
- **15,085 image-only documents** is exactly what the benchmark README recorded, so the
  apparent conflict with `ocr-plan.md`'s 13,604 was never a conflict.

And the baseline was wrong in both earlier drafts. **The production store is 346 MB with a
132 MB WAL beside it**, measured on the instance the same day — not the 152 MB those drafts
quoted, which is a partial dry-run restore holding 7,638 documents against production's
104,091. The instance's disk is 58 GB, **62% used, 22 GB free**, with 28 GB of that being
the blob cache and `prune_blobs.py`'s floor set at 20 GB free. It is already at its
guardrail.

### And the index costs more than it looks

Built over 443 real pages (1.21 MB of text), 2026-09-02:

| index | added | ratio to the text |
| --- | --- | --- |
| `fts5(body)` — keeps its own copy | 2.06 MB | **1.71x** |
| `fts5(body, prefix='2 3')` — keeps its own copy | 2.67 MB | 2.22x |
| `fts5(body, content=…)` external, no prefix | 0.54 MB | **0.44x** |
| external + `prefix='2 3'` — **as `search_fts` actually ships** | 1.15 MB | 0.95x |

The trap is the first row, and a draft of this record fell into a second one by labelling
row two as the shipped configuration; `search_fts` ships external content **and** prefix.

## Why two drafts were wrong in the same way

Both moved bytes out of the store on the grounds that they were re-derivable or unread. Both
were wrong because they never asked what *reads* them:

1. **Search cannot quote what is not there.** Tested on SQLite 3.50.4: with an
   external-content FTS whose content column has been emptied, `MATCH` still finds the row,
   but `snippet()` returns a replacement character and `INSERT INTO fts(fts)
   VALUES('rebuild')` leaves the index matching **nothing** — and `search.py` rebuilds the
   index whole whenever the record changes, so the destructive case is the normal path.
2. **Agreement is not digest equality.** `ocr-plan.md` defines it as normalised text within
   a small edit distance, so the comparison needs both readings' bytes.
3. **The review page is a read path.** `ocr-plan.md` requires *image beside text, the
   disagreement highlighted*. The runner-up is not unread; it is the whole point of the page
   the review layer exists to serve.
4. **A re-rank reopens the comparison.** ADR 0021 D11 makes ranking data, re-issued under a
   new `rank_version`, and `ocr-plan.md` allows a third reading as a tie-break. "The
   runner-up" is not a stable role, so evacuating it destroys an operand a later decision
   needs.
5. **An evacuated row overloads a value ADR 0021 D5 spent a paragraph defining.** After the
   move there would be three causes of empty text — correctly blank, evacuated, not yet read
   — with no column telling them apart, in a table 0021 D1 declares append-only. That is a
   hidden current-state column, and the discriminator costs nothing now and an every-row
   migration later.

## Decision

1. **All of the record's text lives in the store.** Both channels, every reading, one row
   per reading as ADR 0021 D1 defines it, bytes included — the winner, the runner-up, and a
   human correction alike. What is searched, quoted, shown beside a page image or reviewed
   must be in the file that is replicated, restored and dumped as one thing.

2. **One artefact goes to the blob tier: the engine payload.** The largest per-page
   artefact, read only when blocks are projected, and already given a digest, a size and a
   first-seen date by ADR 0021 D6. Nothing else leaves. The saving the earlier drafts chased
   — ~0.4 GB of runner-up text against a multi-gigabyte total — was never worth the four
   breaks above.

3. **Agreement is computed at handover and stored in a table of its own**, `text_agreement`,
   keyed on the page and naming both readings, carrying its rule, its rule version and an
   ADR 0007 block. This is now an efficiency rather than a necessity — the operands stay in
   the store, so a re-rank or a third reading recomputes rather than being stranded — and it
   keeps an edit-distance comparison off the read path. **ADR 0021's Owed list gains this
   table**; without it the review queue has no way to find a flagged page.

4. **The page index is a separate FTS5 table over a best-row-per-page view, and nothing
   reads it yet.** External content, no prefix index, and *not* wired into `search()` or
   `/suggest` until the query surface is decided — which is ADR 0021 D8's "stored and
   unprojected" applied to search. Three reasons it cannot simply join the existing index:
   `ocr-plan.md` already specified a view selecting the best row per page, and indexing the
   raw table would return the human correction and the engine text it corrects as duplicate
   hits; `search.py` records that its own `bm25()` in `ORDER BY` defeats FTS5's internal
   ordering and evaluates the select list for every matching row before `LIMIT`, which is
   the shape of the 2026-09-02 fault and must not be handed 1.1M more rows; and dropping the
   prefix index is a **query-surface foreclosure**, not a storage saving, because
   as-you-type suggestion depends on it.

5. **The dump classification covers every new table, and page text is held.** `dump.py`
   raises `Unsafe` on any table it does not know, so `document_text`, `document_page`,
   `page_route`, `ocr_run`, `text_agreement` and the payload table must each be classified
   or the nightly snapshot fails on deploy day. Three of them are not close calls:
   - **`document_text` is `HELD`**, which in `dump.py` means *dropped*, not emptied — and
     which also deletes every `correction` row naming it, so a human correction to page text
     is absent from the only copy a third party can hold. Accepted knowingly: CC0 does not
     revoke, and `ocr-plan.md` records an engine whose licence forbids using its outputs to
     improve any model. Held can become public later; public cannot become held.
   - **`document_page` is `PUBLIC`.** It is pagination of a federal document, not derived
     work, and ADR 0021 D4 makes it the thing that lets read, flagged and unread be counted.
     `coverage_gap` is already public; publishing gaps without the pagination that makes
     coverage countable would be half an answer.
   - **The page FTS table is `HELD` too, and only `HELD` is safe.** Classified `DERIVED` it
     would be emptied and rebuilt — which errors on an external-content table whose content
     table has just been dropped — and its surviving `%_data`/`%_idx` shadows hold a
     positional inverted index from which the withheld text is largely reconstructible. That
     is the leak `dump.py` exists to prevent. `dump.py`'s shadow handling is also hardcoded
     to names beginning `search_fts_`, so this is a code change, not an allowlist entry.
   - **`HELD_REASON` must stop being one string.** It currently says the held tables are
     "derived work whose licence awaits review", which is false for the text-layer channel:
     the Board's own words are a U.S. government work, which `licensing.md` puts in the
     freely-dedicated bucket. Either a per-table reason, or a filtered publication of the
     text-layer channel alone. Withholding is defensible; the stated reason must be true.

6. **The store is expected to reach 4–5.5 GB, which is larger than either earlier draft
   said.** Measured and counted rather than estimated:

   | component | size |
   | --- | --- |
   | the store today | 346 MB (+132 MB WAL) |
   | text-layer text | 1.37 GB |
   | OCR text, two readings of 247,923 pages | ~0.76 GB |
   | rows and their indexes — ~3.2M across six tables | 1.2–1.9 GB |
   | the page FTS at 0.44x of what it indexes | ~0.77 GB |

   The row count is the part both earlier drafts got wrong: `document_text` is ~1.35M rows,
   but `document_page` is another ~1.10M (ADR 0021 D4 needs one per page of every held PDF),
   `page_route` ~248k, plus `ocr_run`, `text_agreement` and the payload table. Moving bytes
   was never going to touch that; the rows stay wherever the text goes.

7. **So the instance is resized, and it is a writer-stopping operation, not an ADR 0020
   window.** Not in response to the outage of 2026-09-02 — that was a quadratic query, and a
   larger box would have absorbed more crawler traffic before failing, which means meeting
   the same fault later and worse. It is resized because of what decision 6 does to three
   things a 2 GB box has to do in memory: `search.py`'s external sort, a whole-index rebuild,
   and the dump's `VACUUM INTO` plus `VACUUM`, which runs inside the `web` service's 768 MB
   limit with `/tmp` on a tmpfs — a transient nobody has priced at gigabyte scale and which
   should be tested before it is met. Disk is now a constraint too: 22 GB free against a
   20 GB floor, with the dump keeping one archive a month and pruning none.

   **ADR 0020's window does not cover it.** That record's defining property is that `ingest`
   and `litestream` do not observe maintenance — the record keeps being kept. A resize stops
   the box, so it **opens a coverage gap** and is recorded as one. It also needs the writers
   stopped and `PRAGMA wal_checkpoint(TRUNCATE)` before any snapshot, exactly as the seed
   path in the runbook already does, or the snapshot copies a WAL-mode store mid-write.

8. **The handover is a new interchange, page-grained and multi-method, loaded from files.**
   Nothing POSTs today, whatever `citator/load.py`'s docstring says: the shipped path is a
   directory of JSON loaded by `docketyard citator load`, and `web` reads through a read-only
   URI with an IAM key that writes nothing. One shipped property is carried, three are
   broken, and the record names all four rather than leaving them to be discovered:
   - **Carried**: the loader commits **per document**, deliberately, so a wave killed at
     40,000 keeps 40,000 and the poller is not locked out.
   - **Broken, and safely**: it refuses a mixed batch, one `(method, method_version)` per
     load. A routed read violates that by construction. The rule's own reason — one owner per
     class per `rank_version` — is dissolved by ADR 0021 D11's `route_class`.
   - **Broken, and necessarily**: it parses every file in the directory before the loop
     begins. At page-grained OCR interchange that is gigabytes resident on a 2 GB box; the
     new loader streams.
   - **Broken, and quietly**: `methods.stamp` raises when a class has no measurement, and
     ADR 0021 D8 leaves `document_text`'s `class_vocab` empty *by design*; `methods.declare`
     writes a hardcoded citation-family row list; `methods.owner` hardcodes
     `target_table = 'citation'`. The OCR loader shares none of these three.

9. **The payload objects are immutable and content-addressed by their own digest**, under
   the `blobs/` prefix, two levels deep, one object per document per pass rather than one per
   page. Every one of those clauses is load-bearing: `docketyard-blobs.service` syncs
   `--size-only` on the stated ground that "blobs are content-addressed and never change",
   and `prune_blobs.py` deletes a local file when S3 holds **an object of that key**, without
   comparing digests — so a mutable bundle can be silently replaced by a stale one. The two
   levels matter because the prune globs `*/*` and the fetch path is
   `blobs/<sha[:2]>/<sha>`; a deeper key is never pruned. And the per-document grain keeps
   the prune's key listing near today's ~214,000 rather than the 1.4M a per-page object would
   make, which is the memory shape of the incident this record refuses to buy hardware for.
   `document_text` therefore carries the bundle's digest **and** a member path.

10. **Two off-box gaps, stated correctly.** Litestream's `retention: 168h` is a *rewind
    horizon*, not durability — a human correction is replicated within ten seconds and
    survives — so what seven days costs is the ability to rewind past an undetected
    corruption. The blob tier's current objects never expire; its 30-day rule is for
    noncurrent versions, and `prune_blobs.KEEP_DAYS` is a local cache rule, not a retention
    at all. The real gap is neither: **`data/public` is synced nowhere.** The monthly CC0
    archives that `dump.py` never prunes exist in one place, on the disk decision 7 is about
    to snapshot and replace.

## Consequences

**What becomes easy.** Search quotes what it finds. Agreement is computable, and remains
computable after a re-rank. The review page has both readings to put side by side. One
restore restores everything, which is the property ADR 0012 was built around.

**What becomes hard, or costs.**

- **The file Litestream ships and restores is ten to fifteen times bigger**, so the rollback
  a migrating deploy depends on is minutes rather than seconds. Only a smaller file changes
  that, and decision 1 says no.
- **A resize, a coverage gap, and a runbook** — plus the transient disk of a dump at
  gigabyte scale, against a floor the instance is already sitting on.
- **ADR 0012's "the store is rebuildable by replay from captures and blobs" stops being true
  for this layer.** A human correction replays from nothing, and ADR 0021 D2 notes the
  engines are sampling decoders that may not reproduce their own output — so every `text_id`
  a `place_mention` or `citation_reading` points at would dangle on a replay.
- **`docs/search.md` says document text is not indexed**, and becomes wrong the day this
  ships. It is a published-page source, so it moves with the code or the drift rule is
  broken.

**What this forecloses.** The cheap version, twice over. Also as-you-type suggestion over
page text, until someone decides the query surface and pays for a prefix index.

## Validation

Checked against `docs/validation-queries.md`.

- **Q1, Q5** join through ADR 0021 D1's reading pointer and are unaffected by this record now
  that decision 1 keeps every reading's bytes: "show me the sentence this came from" resolves
  for a runner-up as well as a winner. Under the previous draft it did not.
- **Q2** touches no text and is untouched.
- **Q3** is the query the earlier drafts broke and this one does not: evacuating bytes would
  have been an undated in-place `UPDATE` on an append-only table, which is a hidden
  current-state column in the one table this pair of records spent a reversal to keep
  event-grained. Nothing here mutates a row.
- **Q4** is unaffected today and inherits Q1 the day a NITU date is quoted from a page.

**The consumers this record exists for are not in the five**: search, the review page and the
public snapshot. Their absence from the validation set is a limit of the set, not evidence
that the decision is free — and it is why both earlier drafts passed a validation check while
being wrong.

## Cost of reversing

**Moving bytes out later: cheap, and now clearly not worth doing.** ADR 0021 keeps the digest
and the provenance on the row, so a tier assignment reverses as a copy and a re-point. Twice
today that cheapness invited a move that four other things depended on; the cost of reversing
was never the reason to be careful here.

**The resize: a rebuild**, and reversing it is another one.

**The dump classification: one-way in one direction only.** Held can become public. Public
cannot become held.

---

*Proposed, not accepted. Accept only after this decision has been checked against
`../validation-queries.md`.*
