# What the OCR migrations owe

Held here rather than in [ADR 0021](adr/0021-the-ocr-text-grain.md) so that accepting a
record means accepting decisions, not mechanics. **Each section becomes its migration's
header comment when that migration is written**, which is where this project keeps this kind
of detail — migrations 0014 and 0015 both carry theirs.

**ADR 0021 and ADR 0022 were Accepted 2026-09-02**, so what follows is authorised work
rather than a proposal. **The work is split in two, on the operator's decision of the same
day.** Migration A writes
the text. Migration B builds the review layer, and it is deliberately second because
`research/ocr-benchmark/README.md` § Step 6 measured the flag rate that shapes it *after* the
first draft of the review layer had been designed, and the measurement said the design could
not work: a queue that must be cleared cannot be built on a 20–60% disagreement rate against
a fifty-page week.

---

# Migration A — write the text

Four new tables, no rebuilds of anything shipped. That is the point of the split: nothing the
citator reads is touched before the citator has run its first real load.

## The tables

1. **`document_text`** — ADR 0021 D1's grain. Append-only; natural key
   `(document_sha256, page_no, method, method_version, render_profile)` as a **partial**
   unique index over live rows, never a table-wide `UNIQUE`; surrogate `text_id`;
   `reading_channel`, `reading_role`, `route_class` with the router's method and version,
   `text`, a **nullable** `engine_confidence` distinct from ADR 0007's `confidence`,
   `confidence_state`, `measured_target` and `score_row_id` under the composite FK to
   `class_measurement`, `agreement_distance` with its rule's method and version on the
   `second` row, the payload digest and member path, the full ADR 0007 block,
   `superseded_by` and `superseded_at`.
   - `CHECK` that `method`, `method_version` and `render_profile` contain no `/`, or a
  HuggingFace-style engine id renders a review key that cannot be parsed back to columns.
   - **Two more partial unique indexes on `(document_sha256, page_no)`** — one
  `WHERE superseded_by IS NULL AND reading_role = 'primary'`, one for `'human'`. They are
  what make ADR 0021 D9's display single-valued: without them the first re-run at a new
  `method_version` leaves two live primaries, because the natural key exists precisely so
  a re-run inserts rather than collides. A re-run must therefore supersede the outgoing
  primary — **cross-key supersession**, an idiom this project has not used, so the writer
  obligation belongs in the header.
   - **Two CHECKs binding the three encodings of "human"**: `(method = 'human') =
  (reading_role = 'human')` and `(reading_role = 'human') = (confidence_state = 'human')`.
  Unbound, a model row written with `reading_role = 'human'` wins the display and is
  unprotected by the trigger, which fires on `confidence_state`.
   - A **trigger** refusing a model row that would displace a `human` one, in the idiom
  `citation_human_row_is_not_a_model_pass_to_supersede` already uses.
2. **`document_pagination`** — one row per document: `page_count`, `had_text_layer`, method,
   version, timestamp. Both values are derived, so both carry provenance (ADR 0007). It also
   needs **`pagination_outcome_vocab`** and `superseded_by`/`superseded_at` with a live
   index: without the vocabulary an undeclared typed column enters a **published** table, and
   without the supersession a re-pagination is an UPDATE — current state under the coverage
   denominator, in the only new table the snapshot publishes.
   **Two more, taken 2026-09-02/03 and recorded here because this checklist is the spec the
   migration's header answers to.** The row carries `confidence`/`confidence_state` like every
   other derived assertion — the pair qualifies `had_text_layer`, not `page_count` — and the
   state is a **`confidence_state_vocab` table**, not an inline CHECK, by this item's own
   published-typed-column rule. `'measured'` is absent from it: the gate cannot be opened by a
   pointer, because the measurement registry is held and a published `schema.sql` may not name
   a table the snapshot omits, so opening it later is an INSERT rather than a rebuild. And the
   table is in **`review_target_vocab` as `surrogate`** — its live key is a bare sha, one
   segment against `review_action`'s floor of four — which brings a human row into a table
   that had none, so it gains the human-supersession trigger `citation` carries.
3. **`ocr_run`** — one row per `(document, method, method_version, reading_channel,
   render_profile, ran_at)`. **`ran_at` is in the key**, which is what makes it append where
   `extraction_run` replaces; the coverage read takes the latest. Typed outcome, `pages_read`
   **and `pages_failed`**, because the measured failure is partial — the 300-DPI OOM died
   nine pages into a document, and `ocr_run` is the only place that can say which pages were
   attempted. Its header should say why the semantics differ from `extraction_run`'s.
4. **`text_payload`** — the engine payload's digest, size and first-seen, with `document`'s
   discipline, so a pruned payload is a visible fact and not a dangling hash.
5. **`measured_target_vocab`** gains `document_text` **with an empty `class_vocab`**, so ADR
   0021 D7's assertion gate is enforced by the schema. **Note a gap found by review and not
   yet closed:** `class_measurement` has only `recall`, `precision` and `false_veto_rate`,
   and the benchmark's figures are CER and WER — so the gate cannot be *opened* through the
   shipped table. Nothing in Migration A publishes an assertion, so it does not block; it is
   Migration B's to solve, and it must not be solved by storing a CER in `precision`.
6. **The page index** — its own FTS5 table over the display view, external content, no
   prefix index, reaching readers through its own query path (ADR 0022 D4). See § Search.

## `dump.py`, which breaks on deploy day otherwise

7. Classify every new table or the nightly snapshot raises `Unsafe`: `document_text`, the
   page FTS and `text_payload` `HELD`; `document_pagination` and `ocr_run` `PUBLIC`; per
   ADR 0022 D3. Five tables, not three — two were unclassified in an earlier draft.
8. **The view is invisible to the allowlist**, which enumerates `type = 'table'`. It is never
   classified, never dropped, and the published `schema.sql` would carry a `CREATE VIEW` over
   a dropped table. Handle views explicitly.
9. **The shadow logic is hardcoded** to names beginning `search_fts_`. A second index is a
   code change either way, and only `HELD` — dropped, taking its shadows with it — is safe.
10. **`HELD_REASON` becomes per-table.** Today it is one string, rendered verbatim on `/data`
    and shipped in `index.json`. That makes it a published-shape change: `JSON_SHAPE` bumps,
    `docs/data.md` moves with it, and `read_manifest` must not return `None` on the old shape.
11. `search.signature()` reads `MAX(correction_id)`, so a page-text correction would force a
    full rebuild of the docket/party/decision index and invalidate every cached page
    site-wide. Split the signature, or exclude corrections naming `document_text`.
    **`document_pagination` is now in this too** (2026-09-03): migration 0018 gives it a
    `review_target_vocab` row, so a corrected page count is a `correction` row with the same
    effect, and `search.py:279` / `app.py:301` both read the max unfiltered. So the second
    remedy above is not enough as written — excluding one table would leave the other. Either
    split the signature, or exclude by a SET of table names and keep it beside this item.
    **Landed 2026-09-03**: `search.PAGE_TABLES` is the set; `signature()` and the web tier's
    `stamp()` exclude corrections naming it, and the page index has `page_signature()`,
    `page_built`, `rebuild_pages()` (`search rebuild-pages`) and `page_stamp()` for the
    text render's validator.

## The review vocabulary, without importing the queue

- **`INSERT INTO review_target_vocab VALUES ('document_text', 'natural')`.** Two rows of
  DDL, and without them ADR 0021's promise that a human correction has *an author and a
  date on the day the table ships* is false: `review_action` foreign-keys
  `(target_table, target_keyed)` to that vocabulary, so there is nowhere to record who
  wrote a correction or under which convention. The five-segment key form
  `<sha>/<page>/<method>/<version>/<render>` satisfies its `GLOB '*/*/*/*'`, and D1's
  no-`/` CHECK is what keeps it parseable back into columns. **This is not the queue** —
  `review_queue_vocab` and everything in `review.py` stay in Migration B.

## Search, which ships with the text

- **A page-grained permanent address.** The viewer is `/decision/<id>/view` and
  `/filing/<id>/view`, whole-document; ADR 0021 D7 needs a per-page address carrying the
  text, the label, the band, the scan link and the report control. Under ADR 0013 that is
  a permanent URL and therefore a commitment. **Landed 2026-09-03 as `/filing/<id>/text`
  and `/decision/<id>/text`** (the operator's address): ONE address per record with
  `?file=N` for a further attachment and `#p<n>` per page — not one address per page,
  because 1.1M page addresses against 74k records is a crawler's address space, and a
  crawler walking one is this site's one real outage. Each read page carries its text,
  the label (the publisher's text layer, read once; or the engine, version, render and
  route), the band's OPERAND where a second reading exists (D8: the distance, its method
  and version, never a threshold nobody has decided), the scan and the report link; a page
  in the count with no reading says "not yet read"; a human row is labelled and dated. Its
  validator is `page_stamp`. Held from the dedication with the party module in
  `robots.txt`; not in the sitemap. `store/pages.py` is the read side.
- **Its own query path, and `search.Hit` extended.** `Hit` carries `kind, path, title,
  fact, caption, snippet` — no engine, no version, no band, no scan link. Until it carries
  them, no OCR text may reach `/search`, `/suggest` or `web/mcp.py`'s `_search`, which
  hands the same object to a language model. The page index must not be joined to the
  shipped `search()`, whose `bm25()` in `ORDER BY` evaluates the select list for every
  matching row before `LIMIT`.
- **Its own signature and build row.** `search.signature()` names none of the new tables,
  so it would neither rebuild for a new reading nor notice one; and `search_meta` keys its
  build on the single row `'built'`. The page index needs both of its own — and because
  the indexed view *is* ADR 0021 D9's display rule, that rule's version belongs in the
  signature. **Landed 2026-09-03** (`PAGE_INDEX_FORMAT`, the view's migration and the display
  rule's version; `display@0020.1` since the view began omitting contact details). The page-grained
  address and `Hit`'s extension above are still owed.

## The passes

12. **Pagination runs as its own command, not inside the migration.** `migrate` is a service
    the whole stack blocks on, and every migration to date runs in one transaction; ~104k
    rows written inside it holds the write lock against `ingest` and Litestream. Batched,
    resumable, committing per document — the shape `docketyard citator load` already has.
    **Landed 2026-09-03** as `docketyard text paginate <root>` (`docketyard/text/paginate.py`)
    over the extraction directory `extract_text.py` writes, reading each record's head and
    never its text; `method` is the tool. A re-run by the same tool that agrees writes
    nothing; a changed answer or a different tool supersedes with `superseded_at`; a human
    row is held and counted. The commit is per batch of 200 with a savepoint per document
    (measured: 1.2 ms a row per-row against 0.028 ms batched), and a store that cannot be
    written aborts the pass rather than counting each remaining document as failed. It runs
    on the instance AFTER the deploy that applies 0018: `db.connect` migrates, as every verb
    does. The extractor emits no record for a non-PDF or a failed open, so `not-paginable`
    and `failed` wait on it.
13. **The loader is new**, page-grained and multi-method. It commits per batch with a
    savepoint per document (`store/batches.py`); it **streams** rather than parsing a whole
    directory into memory; and it
    shares none of `methods.stamp` (raises when a class has no measurement, which is by
    design here), `methods.declare` (its row list is citation-family) or `methods.owner`
    (hardcodes `target_table = 'citation'`). **The retire/insert/repoint helpers moved to
    `store/supersede.py` on 2026-09-03** — `retire(..., at=)` and `if_changed(...,
    retire_at=)` write `superseded_at` in the same statement when asked, so the
    biconditional both `document_text` (0018) and `decision_decided_date` (0019, ADR 0023
    D2) carry no longer refuses them; `text/paginate.py` is the first caller outside the
    citator. Pass `retire_at`: without it the write is refused, which is the right failure.
    **Landed 2026-09-03** as `docketyard text load <root>` (`docketyard/text/load.py`): one
    reading per file, page by page; the extraction record is the text layer's reading and a
    general reading document is the OCR pass's (its shape is the module's docstring); the
    file itself is the payload, content-addressed into the blob tier and recorded in
    `text_payload`; a primary of another key is displaced cross-key with `superseded_at`;
    `page_fts` is kept in step (`store/page_index.py`, one definition for every writer);
    `ocr_run` appends on `ran_at`, and an existing run row is the restart check — one
    lookup, the body unread. An agreement names the primary it was measured against, by
    key, and is refused when the live primary differs. The loop is `store/batches.py`,
    shared with `paginate`. Not here: the human writer's half of the index obligation
    (Migration B), and `search_meta.page_built` (item 11).
14. **Escalation is an operator-triggered CLI verb**, not an automatic stage — the operator's
    decision, 2026-09-02. A paid third reading is a pass with its own method and version,
    recorded in `ocr_run` like any other. No standing spend, and no authenticated surface
    added to the reader-facing process.

**First run, 2026-09-04**, on the resized box and under readers: `paginate` 77,567 documents
in 19 s over two runs; `load` 1,104,935 pages and 1,472 MB of payloads in 21 minutes over
seven resumes (the write-lock contention with Litestream is in `deferred.md`);
`rebuild-pages` 8 m 49 s under the write lock, index and table both 1,104,935; the store
346 MB → 3.7 GB with a 1.2 GB WAL. 15,086 image-only documents hold empty pages for the OCR.

## The infrastructure

15. **The blob prefix**, named: payloads are immutable, content-addressed by their own
    digest, `blobs/<dg[:2]>/<dg>`, one object per document per pass. Anything else is
    unsynced, unpruned, or unreadable by the process that serves readers.
16. **The resize, before the migration** (ADR 0022 D5), with the steps that lose data if
    skipped: maintenance flag on first; `systemctl mask` the dump and blob timers, both
    `Persistent=true`, or the new box fires every missed run at once on first boot; stop
    `ingest`, `web` **and `litestream`** before `PRAGMA wal_checkpoint(TRUNCATE)`, because
    Litestream holds a read transaction that prevents truncation; snapshot; **stop Docker on
    the old instance and disable it**, or two Litestream processes replicate divergent stores
    to one path; launch, move the static IP rather than changing DNS; verify; unmask; clear
    the flag. The TLS certificate lives in the `caddy-data` volume and therefore inside the
    instance snapshot — say so, because the tempting alternative loses it. **Done
    2026-09-03/04**: small_3_0 to large_3_0, 55 minutes of gap recorded as gap 2, no
    records missed; the procedure as run is `infra/deploy/README.md` § Resizing (`mask`
    fails on units that are real files; `disable --now` is the equivalent).
17. **`SQLITE_TMPDIR` on the dump service.** The plain `VACUUM` after the drops places its
    temporary database in `/tmp`, which is a tmpfs inside the `web` service's 768 MB limit.
    Point it at the volume and re-test at scale. The two failure signatures differ and only
    one leaves a message. **Landed 2026-09-04**: `SQLITE_TMPDIR=/data/tmp` on the dump's
    `docker compose run`, the directory created by `ExecStartPre`; the first nightly on
    the large box after the load is the re-test at scale.
18. **`OnFailure=` on all four systemd units**, and a Grafana alert on
    `node_filesystem_avail_bytes`. A failed dump today leaves last night's snapshot served
    under an unchanged manifest, with nothing saying so. **Landed 2026-09-04**:
    `OnFailure=docketyard-failed@%p.service` on all four, writing
    `docketyard_unit_failed{unit}` for Alloy's textfile collector and cleared by each
    unit's own success; the Grafana alerts on it and on the filesystem are the operator's.
19. **Litestream retention** raised for the window, or the pre-resize snapshot kept out of
    band (ADR 0022 D6). **The second, 2026-09-04**: the instance snapshot
    `docketyard-prod-pre-resize-2026-09-03` is kept until the migration's correctness
    question is answered; retention stays at 168h.
20. **The healthcheck during the load.** `webwatch` restarts `web` whenever it reports
    unhealthy, every minute, uncapped; a slow `/` under load becomes a restart loop. Raise the
    timeout or run the load behind maintenance. **Landed 2026-09-04**: the healthcheck's
    timeout is 30 s, was 5 s; the load runs under readers.

## The published pages, which must move in the same commit

21. `coverage.html` — *"nothing is yet extracted from inside them"* becomes wrong.
22. `methodology.html` — *"Documents are not searched"* becomes wrong, and the page needs a
    "Document text" entry under *Derived, and how* carrying the per-tier error rate and the
    caveat that the labelled sample is born-digital, so the figure is a lower bound on
    real-scan damage.
23. `docs/search.md` — records that document text is not indexed.
24. `data.html` and `/llms.txt` — the held layer gains a third member; `data.html`'s prose
    already omits the citator, which is pre-existing drift to fix while there.
25. **`robots.txt`.** The party module is disallowed for named AI agents *because* it is held
    from the CC0 dedication, on the stated ground that a permission handing over what the
    text withholds contradicts itself. Held page text inherits that rule.
26. **The `/corrections` promise already covers a misread date.** Decide whether a misreading
    is a correction under that promise — a person reads every report, usually within seven
    days — or say plainly on the viewer that it is not.
    **Items 21–26 landed 2026-09-03.** 21, 23, 24 (with the citator named on `data.html`),
    25 as the code changed; 22 with the benchmark's per-tier figures and TWO caveats — the
    transcription was checked at reading speed, so the figures rank rather than state an
    accuracy, and nothing is measured yet on the pages read at scale; 26 decided by the
    operator: **reports welcome, no promise** — a misreading is read but sits outside the
    seven-day expectation, said on the text page and on `/corrections`.

## Before it ships

27. **schema-critic on the migration**, before the tables exist. Grain, identity and
    provenance at once, which `CLAUDE.md` requires.
28. **Tests**: an empty reading writes a row and a failed read does not; `ocr_run` appends
    where `extraction_run` replaces; the human key is pinned and a model pass cannot displace
    it; `/` is refused in the three key columns; `document_pagination` publishes with its
    provenance and `document_text` is dropped, in a real `dump.scrub`; **a view over a held
    table does not survive into the snapshot**.

---

# Migration B — the review layer

Not scoped here beyond what is owed, because § Step 6 says the design has to be redone
against the measured flag rate before it is worth specifying. What is known to be owed:

- **The `assertion_method` rebuild** — SQLite cannot alter a `CHECK`. Three indexes
  reproduced, `route_class` added, and the rank index re-formed as
  `UNIQUE (rank_version, target_table, COALESCE(route_class, ''), precedence_rank)` — the
  `COALESCE` because SQLite treats NULLs as distinct, so without it the five citation tables
  lose the rank uniqueness migration 0014 built that index to guarantee.
  **`assertion_method_identity` must gain `route_class` too**, or two rank rows differing only
  in route class collide and the whole decision is unimplementable. `methods._COLUMNS` and
  `_already_declared` move with it — not `declare`'s INSERT, whose explicit column list is
  what makes it safe.
- **`RANK_VERSION` is one module constant shared by the citator and anything else that ranks.**
  `project.py` inner-joins on it, so bumping it for an OCR re-rank empties the citation
  projection site-wide, silently. It needs a per-target namespace before a second ranked
  table exists.
- **The `correction` CHECK**, extended to `document_text` in the same transaction.
- **The review queue.** `review.QUEUES`, `_unanswered`, `_base` and `pending()` are all
  citation-shaped; `/review` filters the vocabulary by `LIKE 'citation_%'`; `owed()`
  materialises every row as a dict on every page load, which at page grain is the 2026-09-02
  shape. The page-grained exclusion must be a `GLOB` prefix, not a `LIKE`.
- **`text_agreement`**, if a stored judgement earns a table once the flag rate is known.
- **`class_measurement`** needs somewhere to put a CER, or `document_text`'s gate cannot open.
- **`page_route`**, if anything needs the router's rejected alternatives.

## Live now, and not waiting for either migration

- **`methods.stamp()` has a channel term since 2026-09-03.** Until then it selected on
  `(measured_target, class)` only, so the first OCR-channel citator load would have stamped
  every row with the *text-layer* measurement, marked it `measured`, and published it — a
  live ADR 0017 D3 violation waiting for a load that had not happened. Now `stamp` and
  `measure` both carry the channel, `citator load` refuses a batch that mixes channels, and
  the loader checks the stamps it is handed against the measurement rows themselves
  (`load.WrongChannel`), which also refuses a null or `human` channel on a model pass. An
  OCR load is therefore `Unscored` until somebody measures the OCR channel, which is ADR
  0017 D3's "stored and unprojected until measured" read as a refusal rather than as an
  unmeasured row; if the OCR pass is to *store* unmeasured rows, that is a deliberate flag
  on the load verb, not a fallback inside `stamp`. And a measured channel nobody has
  *ranked* is refused too (`methods.ranked`): `declare` ranks the text layer only, and the
  projection's rank join is channel-matched, so the alternative was rows no page shows and
  an exit of 0. Ranking OCR is a new `rank_version` (ADR 0018 D7) — the namespace question
  item 8 above already holds.
