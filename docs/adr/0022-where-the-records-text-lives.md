# ADR 0022 — Where the record's text lives

- **Status:** Accepted
- **Date:** 2026-09-02
- **Accepted:** 2026-09-02 (the operator: "ADR 0021 & 0022 are APPROVED")
- **Addendum to:** [ADR 0012](0012-deployment-topology.md), which stands unchanged
- **Companion to:** [ADR 0021](0021-the-ocr-text-grain.md), which decides what a row means
- **Drafted three times, and the lineage is kept because the mistake repeated.** The first
  draft sent the text-layer text to the blob tier on a cost-to-remake rule; the second
  reversed that and kept the same move for the runner-up reading — a smaller set of bytes,
  the identical error. Both moved bytes out without asking what *reads* them. The third
  sends one thing out, and the reasoning is in § Why two drafts were wrong.

## Context

ADR 0012 put one Lightsail instance, one SQLite file, Litestream streaming its WAL to S3,
and the document blobs in S3 with the instance holding a cache. The blob half runs on a rule
this record was expected to extend: **S3 is the store, the instance is a cache** —
`docketyard-blobs.timer` syncs every 30 minutes and `prune_blobs.py` deletes any
S3-confirmed local blob **older than 30 days**, with disk pressure below a 20 GB floor as a
*second* trigger rather than the only one.

ADR 0021 proposes `document_text`, the first text the store has ever held. So "does the text
go in the replicated file?" has never had to be answered, and answering it by default —
because a table is where strings go — would be answering it by not noticing. The file that
would grow is the one `litestream restore` pulls back when a migrating deploy rolls back.

### What it costs, measured 2026-09-02

The row overhead was the one figure that had only ever been reasoned out, and it was the one
deciding a resize, so the proposed schema was built at the census's real row counts with
realistic keys and empty text and then weighed: **365 B a row**, and **text stores at 1.051x
its own bytes**, so the components simply add.

| component | measured |
| --- | --- |
| the store today | 346 MB (+132 MB WAL) |
| `document_text`, ~1.35M rows, and its indexes | ~730 MB |
| `document_pagination`, `ocr_run`, the payload table | ~120 MB |
| text-layer text (1.37 GB at 1.051x) | 1,439 MB |
| OCR text, two readings of 247,923 pages | 797 MB |
| the page index at 0.44x of what it indexes | ~770 MB |
| | **≈ 4.2 GB** |

ADR 0021's shrink of `document_page` to a per-document `document_pagination` takes ~1.10M
rows and ~400 MB out of that total. What remains is not avoidable by moving bytes: the rows
stay wherever the text goes.

**And the instance is already at its guardrail.** 58 GB of disk, 62% used, **22 GB free**,
against `prune_blobs.py`'s floor of 20 GB — with 28 GB of that being the blob cache, and
waves 2–3 still pushing documents through the same disk.

### The index costs more than it looks

Over 443 real pages (1.21 MB of text):

| index | added | ratio |
| --- | --- | --- |
| `fts5(body)` — keeps its own copy | 2.06 MB | **1.71x** |
| `fts5(body, prefix='2 3')` — keeps its own copy | 2.67 MB | 2.22x |
| `fts5(body, content=…)` external, no prefix | 0.54 MB | **0.44x** |
| external + `prefix='2 3'` — **as `search_fts` actually ships** | 1.15 MB | 0.95x |

The trap is the first row, and an earlier draft of this record fell into a second one by
labelling row two as the shipped configuration.

## Why two drafts were wrong

Both moved bytes out because they were re-derivable or unread, and both failed to ask what
reads them.

1. **Search cannot quote what is not there.** Tested on SQLite 3.50.4: with an
   external-content FTS whose content column has been emptied, `MATCH` still finds the row,
   but `snippet()` returns a replacement character and `INSERT INTO fts(fts)
   VALUES('rebuild')` leaves the index matching **nothing** — and `search.py` rebuilds whole
   whenever the record changes, so the destructive case is the normal path.
2. **The runner-up is not unread.** Agreement is an edit distance over normalised text, not a
   digest comparison, and the review page exists to show *image beside text, the disagreement
   highlighted*. Evacuating the second reading removes the operand the confidence signal is
   computed from.
3. **An evacuated row overloads a value ADR 0021 D5 defines.** There would be three causes of
   empty text — correctly blank, evacuated, not yet read — with no column telling them apart,
   in a table 0021 D1 declares append-only.

## Decision

1. **All of the record's text lives in the store.** Both channels, every reading, bytes
   included — primary, second and human alike. What is searched, quoted, shown beside a page
   image or reviewed must be in the file that is replicated, restored and dumped as one
   thing.

2. **One artefact goes to the blob tier: the engine payload**, and it is immutable and
   content-addressed by its **own** digest, under the `blobs/` prefix, two levels deep, one
   object per document per pass. Every clause is load-bearing: `docketyard-blobs.service`
   syncs `--size-only` on the stated ground that "blobs are content-addressed and never
   change", and `prune_blobs.py` deletes a local file when S3 holds **an object of that key**
   without comparing digests — so a mutable bundle can be silently replaced by a stale one.
   Two levels because the prune globs `*/*` and the fetch path is `blobs/<sha[:2]>/<sha>`; a
   deeper key is never pruned. Per document rather than per page because the prune lists
   every key into memory every 30 minutes, and page-grained objects would take that from
   ~214,000 to over a million on a 2 GB box.

3. **The dump classification, which is the one-way door in this record.** `dump.py` raises
   `Unsafe` on any table it does not know, so every new table is classified before the
   nightly snapshot runs after the migration — and the classification is a publication
   decision, because CC0 does not revoke.
   - **`document_text` is `HELD`**, which in `dump.py` means *dropped*, not emptied — and
     which also deletes every `correction` row naming it, so a human correction to page text
     is absent from the only copy a third party can hold. Accepted knowingly. `licensing.md`
     places page text in neither of its two buckets: a machine transcription of a US
     government work is a derived assertion with a measured error rate, not the Board's own
     words. Held keeps the question open; public closes it by accident.
   - **`document_pagination` is `PUBLIC`.** ADR 0021 D4 gives it its own method, version and
     timestamp, so it publishes with its provenance rather than as a bare machine claim,
     which is what a per-page table without provenance would have done. **Being public makes
     its shape published too**: the DDL enters the snapshot's `schema.sql` and third parties
     hold it, so D4's typed outcome needs a declared vocabulary and its supersession columns
     from the first row, not added later as a published-shape change.
   - **The page index is `HELD` too, and only `HELD` is safe.** Classified `DERIVED` it would
     be emptied and rebuilt, which errors on an external-content table whose content table
     has just been dropped, and its surviving `%_data`/`%_idx` shadows hold a positional
     inverted index from which the withheld text is largely reconstructible. `dump.py`'s
     shadow handling is hardcoded to names beginning `search_fts_`, so this is a code change.
   - **`HELD_REASON` stops being one string.** It currently says the held tables are "derived
     work whose licence awaits review", names the party module and the citator, is rendered
     verbatim on `/data`, and ships in `index.json` that third parties hold. Page text needs
     its own reason, so the field becomes per-table — which changes a published JSON shape
     and moves with `docs/data.md`'s version.
   - **`ocr_run` is `PUBLIC` and `text_payload` is `HELD`.** Both were unclassified in an
     earlier draft, which would have failed the nightly snapshot on its first run — loudly,
     which is what the allowlist is for, but leaving a publication decision to whoever is
     unblocking a broken dump at three in the morning. `ocr_run` says which documents are
     image-only and which reads failed, which is coverage and belongs beside `coverage_gap`;
     `text_payload` holds digests of objects carrying the text `document_text` is held for,
     so publishing it would name the withheld artefacts.
   - **A view is invisible to this check.** `dump.py` enumerates `type = 'table'`, so
     decision 4's view is never classified and never dropped, and the published `schema.sql`
     would carry a `CREATE VIEW` over a table the snapshot does not contain.

4. **The page index is its own FTS5 table over the display view, external content, no prefix
   index — and it reaches readers through its own query path.** ADR 0021 D7 puts search in
   the same migration as the text, because findability is what the work is for. The
   conditions are what keep that safe.

   It indexes a **view selecting the row ADR 0021 D9 displays**, not the raw table, or a
   human correction and the engine text it corrects both come back as hits. It is **not
   joined to the shipped `search()`**, whose own comments record that `bm25()` in `ORDER BY`
   defeats FTS5's internal ordering and evaluates the select list for every matching row
   before `LIMIT` — the shape of the 2026-09-02 fault, which must not be handed a million
   more rows. **No OCR text reaches `/search`, `/suggest` or MCP until `search.Hit` carries
   the label, the band and the scan link**: it has `kind, path, title, fact, caption,
   snippet` today, and `web/mcp.py`'s `_search` passes the same object to a language model.

   It needs **its own signature**, because `search.signature()` names none of these tables
   and would neither notice a new reading nor rebuild for one — and because the view *is* the
   display rule, so its version belongs in that signature. Dropping the prefix index is a
   **query-surface** choice rather than a storage saving: prefix queries still work, falling
   back to a vocabulary scan.

5. **The instance is resized, and it is a precondition rather than a companion.** Not in
   response to the outage of 2026-09-02 — that was a quadratic query, and a larger box would
   have absorbed more crawler traffic before failing, which means meeting the same fault
   later and worse. It is resized because the permanent +3.9 GB puts free disk **under**
   `prune_blobs.py`'s floor, so the first prune after the migration evicts roughly a third of
   the blob cache, oldest first — which under decision 2 means evicting reader-facing PDFs to
   keep cold payload bundles. The dump's transient compounds it, and it recurs nightly rather
   than once: `VACUUM INTO` copies the **whole** ~4.2 GB store before any table is dropped,
   then the plain `VACUUM` that follows places its
   temporary database in `/tmp`, which in the `web` service is a tmpfs inside a 768 MB limit.

   **ADR 0020's window does not cover it.** That record's defining property is that `ingest`
   and `litestream` do not observe maintenance — the record keeps being kept. A resize stops
   the box, so it **opens a coverage gap** and is recorded as one, on a page whose vocabulary
   has no member for a planned stop. It also needs the writers stopped, `litestream` among
   them, and `PRAGMA wal_checkpoint(TRUNCATE)` before any snapshot, or the snapshot copies a
   WAL-mode store mid-write. The runbook steps are in `../ocr-migration.md`.

6. **Litestream's retention is raised for the migration window, or the pre-resize snapshot is
   kept out of band.** `retention: 168h` bounds the rewind horizon, and this is the first
   change whose correctness question takes longer than seven days to answer: 187 hours of
   reading before there is text, and no measurement until later still. On day eight there is
   no pre-migration point left to restore to.

## Consequences

**What becomes easy.** Search quotes what it finds. The confidence signal is computable, and
stays computable after a re-read. One restore restores everything, which is the property ADR
0012 was built around.

**What becomes hard, or costs.** The file Litestream ships and restores is roughly twelve
times bigger, so the rollback is minutes rather than seconds — and nothing about a larger
instance changes that. A resize, a recorded coverage gap, and a runbook. The monthly CC0
archive grows and `dump.py` prunes none of them. And ADR 0012's *"the store is rebuildable by
replay from captures and blobs"* stops being true for this layer: a human correction replays
from nothing, and ADR 0021 D2 notes the engines may not reproduce their own output.

**What this forecloses.** The cheap version, twice over.

## Validation

None of the five queries reads a page's *words* — Q1 and Q5 join through ADR 0021 D1's
reading pointer, Q2 through `citation_key`, Q3 through the assertion's dates, Q4 not at all
today — so no query in the set is affected in either direction. **The consumers this record
exists for are not among the five**: search and the public snapshot. That is a limit of the
set, not evidence the decision is free, and it is why both earlier drafts passed a validation
check while being wrong.

## Cost of reversing

**Moving bytes out later: cheap, and now clearly not worth doing.** ADR 0021 keeps the digest
and the provenance on the row, so a tier assignment reverses as a copy and a re-point. Twice
in one day that cheapness invited a move four other things depended on; the cost of reversing
was never the reason to be careful here.

**The resize: a rebuild**, and reversing it is another one.

**The dump classification: one-way in one direction only.** Held can become public. Public
cannot become held.

---

*Accepted 2026-09-02, after the check against `../validation-queries.md` recorded in
§ Validation. Two consequences were accepted deliberately with it: the resize opens a
recorded coverage gap, and the dump classification is one-way in one direction — held can
become public, public cannot become held.*
