# Deferred findings

Review findings and known gaps recorded for later — accepted as not-now, never silently
dropped (`CLAUDE.md` § Review before commit). Each carries the date and the release it was
found against. `TODO.md` holds only near-term work and points here; an item leaves this file
when it is fixed (the commit is the record) or graduates back to `TODO.md` when chosen.

## Web tier

- **Search rebuild is whole, not a diff** (2026-08-26, v2026.08.28): any moved id rebuilds
  every row; a diff by `(kind, ref)` would write only what changed. **The timing half of
  this item is answered and closed; the diff half stands.** Measured on the instance
  2026-08-31 at 96,225 rows: 22.4 s deriving (no lock), a **5.6 s** write transaction,
  24.1 s in all — the numbers and their meaning are in `search.md`. A diff would still save
  most of the 22.4 s, which is why this stays open; it is an efficiency, not a correctness
  problem.
- **Two curated "what changed" lists** (2026-08-26): the ETag stamp and the search signature
  each enumerate max ids; one store-level record version (a counter bumped by every writer)
  would make both correct by construction.
- **The largest sheets are unpaginated**; measure DOM cost on a low-end phone before changing
  anything (external review, 2026-08-26). **Re-measured 2026-08-31** and both halves of the
  original note were stale: FD 36873 is now **2,164,447 bytes / 1,142 entries**, and the
  heaviest page on the site is not the merger but **`/d/AB-167/sub/1189X` at 2,641,718 bytes
  / 1,861 entries**, 1,533 of them environmental comments. The cost is DOM, not bandwidth —
  Caddy gzips FD 36873 to ~120 KB, while the page carries 27,537 elements and 2,233 inline
  SVG icons, one per entry link. Two cheaper moves were to be priced before pagination:
  **the `<symbol>`/`<use>` collapse shipped 2026-09-01** — measured on a production copy,
  FD 36873 fell 1,797,300 to 1,429,672 bytes and ~22,997 to ~18,271 elements (-20%), and
  `/d/AB-167/sub/1189X` 488,615 to 413,035 bytes. A year window is still unbuilt, and the
  phone measurement is still the open question (`navigation-review.md` § D).

## Party module (M10, 2026-08-26)

- An address following two ids that are later joined receives each filing twice per pass
  (dedup is per subscription, not per component).
- The follow form on a 301'd page follows the representative, so a later unjoin narrows the
  subscription silently.
- `--cite` on `parties join` is free text, not a typed filing/decision reference.

## Alerts (M8, 2026-08-26)

- Dead webhook endpoints should self-suppress after N failures; a per-pass delivery budget;
  one delivery loop over a channel object; TTL-cache feeds on the ledger head.

## Document viewer (PR #10, 2026-08-27)

- **Sandbox the document response.** `Content-Security-Policy: sandbox; frame-ancestors
  'self'` on `/document/*` would put the PDF in an opaque origin (the pdf.js CVE-2024-4367
  class could not reach the site's origin). Not shipped because a `sandbox`ed PDF's
  rendering in Chrome's viewer must be checked in a browser first; the site sets no cookie
  and holds no per-user state, so the exposure today is small.
- **The sitemap advertises pruned documents.** A crawler walking every document address
  pulls every pruned file back from S3 (egress at ~$0.09/GB; the prune re-bounds the disk).
  Watch the `document` class on `docketyard traffic`; drop the section or add `crawl-delay`
  if it costs. **Sharper since F7** (2026-08-31): `robots.txt` now names thirteen AI agents
  and welcomes them, so the population that would walk it is larger by invitation. The
  invitation was the right call and this is its one measurable cost — watch the class before
  changing anything.
- **The S3 key layout** `blobs/aa/<sha>` is spelled in `web/documents.py`, `prune_blobs.py`
  and the sync unit; one `records.blob_key(sha)` when any of them next changes.

- **A description of a page, as a derived assertion** (raised 2026-08-28, when the operator
  asked whether map pages should be described rather than transcribed): alt text for a
  scanned exhibit, or a one-line "what is on this page", would help accessibility and
  search. It is not ground truth and never replaces the labels — it would be a derived
  assertion carrying method, model, version and confidence (ADR 0007), published only above
  a measured threshold, like any other. Wait until the OCR text layer exists.

## Store and operations

- **Key rotation** for `DY_EMAIL_KEY` (decrypt under old, seal under new; four sealed columns
  across three tables since 0008) — unwritten; ADR 0014 records the gap.
- **Credentials**: Lightsail has no instance profile, so production runs on a bucket-scoped
  IAM user's keys; decide EC2 t4g / Roles Anywhere / accept (ADR 0012 gap).
- **Schema chore**: a poll item that is permanently bad for a reason other than a refused
  document (which rests a week from its capture, PR #10) still has no attempt counter.
- **Re-check bytes** (2026-08-27, v2026.08.35): the errata re-check downloads each held file
  whole (≤64 MB; ~1,900 a day, tens of GB per six-week cycle from the Board's bucket). S3
  honours `If-None-Match`; recording the response `ETag` on the fetch capture and sending
  it on re-check would make an unchanged file a 304. Larger files are the operator's
  `fetch attachments --refresh`, which has no age floor and no default limit.
- **Streamed downloads** (2026-08-26, v2026.08.25): no Range-resume on a mid-body failure;
  the file is written, hashed and sniffed in three passes rather than one; one commit per
  document is the dominant DB cost of a wave.
- **Enriched layer into the snapshot and JSON** after the attorney review (`licensing.md`
  § Open): remove `dump.HELD_TABLES`, restore the Parties block, bump `JSON_SHAPE`, announce
  on `/data`. **F7 added a fourth place the same review governs**: `robots.txt` disallows
  `/p/` and `/parties` to the named AI agents, and `/.well-known/mcp.json` declines to label
  the surface CC0, because the dedication does not cover the party module — all four must
  move together or the rules and the prose will contradict each other. Money on
  `/contribute` is omitted by decision until the same review and the entity question.

## Benchmark scorer (code review 2026-08-30, against v2026.08.39)

- **Two definitions of "is this quote in the decision"**: `benchmark_score.flat()` and
  `labels_check_page.stripped()` each reduce text their own way (the queue also strips
  page markers and the Board's running head). Measured the same day: reusing `stripped()`
  recovers none of the 15 page-spanning sheet quotes the scorer cannot locate (18 fail
  under it), so the divergence costs nothing yet — but the next furniture fix will land in
  one and not the other. Extract one `locatable(text)` helper into a shared module and
  import it from both.
- **The `<stratum>-<id>.txt` naming convention is parsed in four places**
  (`benchmark_score`, `benchmark_run`, `benchmark_ocr_text`, `labels_check_page`), each
  differently. One `decision_id_of(path)` in the shared module.
- **`benchmark_ocr_text.py` discards Textract's per-page confidence** (`cfg['_conf']`
  accumulates, `_write_conf` is never called): re-calibrating the escalation threshold
  from that pass means re-paying Textract. Only matters if the 60-decision OCR side is
  ever re-run; the OCR benchmark's own runs recorded confidence separately.
- **A model that dies mid-run shows as "running" on the status page**: benchmark_run
  reports the stop under the decision id (`52238: stopped at page 3`), the page's FAIL_RE
  keys on the model name, and nothing maps one to the other. The stop is visible in the
  log tail; attribute it properly if the page outlives this batch.
- **`off_page` is one undifferentiated count**; recording it per `kind/target_kind` would
  match the rest of the result's shape. The dropped quotes themselves are listed, so the
  drop is auditable.

## Schema draft (schema-critic on § 7, 2026-08-30, against v2026.08.39)

- **`correction_target.target_pk bigint` carries § 7's original defect**: it cannot name a
  sha256-keyed or composite-keyed row (`document_page`, the planned `document_text`).
  Widen to the same canonical text key `review_action.target_key` now uses when the table
  first reaches a migration; it exists in no migration today.
- **Credit-name history is current-state debt, accepted with eyes open**: an archived page
  shows a name the store cannot reconstruct after a rename. Revisit if the trust pages
  ever need "as shown at the time".

## Docket sheet (code review 2026-08-30, v2026.08.39)

## AB sub-docket numbering (measured 2026-08-30, not yet explained)

Raised while building the series index. Nothing here blocks anything; it is recorded so
the next person does not re-derive it.

- **Sub-numbers are per-parent, not a shared pool** (the operator's hypothesis, tested):
  Sub-No. 1 is used by 337 different AB parents, and Sub-No. 552 exists under AB 55,
  AB 167 and AB 290.
- **AB 290's numbering is broadly chronological**: median earliest-record year by band —
  subs 150–199 → 1997, 250–299 → 2006, 350–399 → 2015, 400–449 → 2021. The series is
  current at 424 (2026), so the numbers above it are the future, not a gap in this record.
- **Scattered single absences are the Board's own.** 413X, 416X and 423X are missing
  between held neighbours; the operator searched the Board for **AB 290 (Sub-No. 416X)
  on 2026-08-30 and it does not exist**. AB 55's longest absent run is 4, AB 167's 14 —
  consistent with numbers assigned and never docketed.
- **Two outliers remain unexplained**: AB 290 (Sub-No. 552X), whose 2011–12 decisions are
  *also* entered in AB 55 (Sub-No. 710X) and AB 167 (Sub-No. 1191X) — a joint NS/CSX/
  Conrail proceeding where all three numbers sit high in their own series — and
  AB 290 (Sub-No. 553X), 2024, which our record shows entered nowhere else. A joint filing
  drawing from a high range would explain the first and not the second.

## Caption refresh (stb-ingest-specialist, 2026-08-31, against v2026.08.40)

Raised on the poll's caption lookup; the blocking findings (asking by family, and asking
for ever) were fixed before it shipped. These were triaged as not-now:

- **`_uncaptioned` scans the registry each pass** (~32,600 dockets, index seeks). Free at
  this size, and it will not stay free.

## Found 2026-08-31, during the machine-agent surface

- **One unreproduced failure of `test_snapshot_omits_readers_and_measures_itself`.** Seen
  once in a full run; the same run's other 290 passed, and it has not recurred in four
  full runs since, in isolation, or with `test_mcp.py` ordered before and after it. Checked
  and ruled out: the dump's work directory is per-test (`tmp_path/.dump-work`), and
  `build_store` writes to a per-test `tmp_path`, so no store or output path is shared
  between tests. The remaining plausible cause is environmental — `dump` does a
  `VACUUM INTO` and an atomic replace, and the basetemp sits inside the repo on Windows
  where an indexer or scanner can hold a handle briefly. Recorded rather than chased: if it
  recurs, capture the assertion output, which this occurrence did not keep.

## Found 2026-08-31, reviewing the navigation Tier 1–2 release (v2026.08.45)

- **`EXPECTED_EMPTY_MONTHS` is a declaration, and `covered()` now rests on it**
  (stb-ingest-specialist). `walk.py` skips the reconciliation proof for a month declared
  expected-empty, so a run with the wrong criteria pair would answer the same envelope and
  be written `empty` with nothing proving it — and `covered()` counts `empty` as walked.
  Pre-existing and bounded to one measured month (`FILINGS:2025-10`); this release does not
  widen it. Smallest hardening is in `walk.py`: attempt the proof for expected-empty months
  too and fall back to the declaration only when the proof cannot be obtained.
- ~~**`_connect_rw`'s 30 s wait is shorter than a rebuild**~~ (schema-critic, code review).
  **Measured on the instance 2026-08-31 and withdrawn: it is not.** Two reviews and this
  file read the 32 s whole-command wall time as lock time; `rebuild()` derives on reads
  first and the write transaction is **5.6 s** at 96,225 rows, well inside the 30 s wait.
  The derive was already split from the write — that is what the module docstring meant by
  "writes in one short transaction". A concurrent `/subscribe` waits about five seconds in
  the worst case and does not fail. Kept here, struck through, because a plausible finding
  that three passes believed is worth leaving visible: the lesson is that a wall-clock
  number is not a lock number, and nobody had measured the difference.

## Found 2026-09-01, clearing five from this pool

- **The caption control cannot tell a withdrawn row from a broken query.** If the Board ever
  stops publishing the docket row the control asks about, the pass raises the same problem
  line for ever: the choice is deterministic (`ORDER BY docket_id LIMIT 1`), there is no
  attempt budget and no rotation. Two consecutive failures before raising, or a small
  rotating candidate set, would fix it. Nobody has seen a Board-side withdrawal yet
  (stb-ingest-specialist).
- **`gap_shadows` excludes `events` failures, and that is a judgement.** An `events` gap
  usually means captures arrived and nothing parsed - those are retained and re-consumed, so
  the days self-heal, and shadowing them would leave a week at `partial` for ever over
  records the store fully holds. But an `events` gap can also mean captures that quarantined
  and were never re-asked, which SHOULD shadow. The failure taxonomy cannot tell the two
  apart; a fifth failure kind, or a quarantine count on the gap, could.

## Found 2026-09-01 (v2026.08.51, migration 0014), reviewing the citator schema

- **`class_measurement` carries no scorer version and no evaluation-set identity.** Its key
  is exactly the one ADR 0018 D8 names, so a re-score at unchanged pipeline versions ON THE
  SAME DAY cannot be inserted — which is the 98.2% → 98.0% correction of 2026-09-01, and
  ADR 0017 § The exposure test measures two populations (225 truth, 249 emitted) on one day.
  The fix is `score_method_version` (and/or `benchmark_set`) in the table and in
  `class_measurement_identity`: an `ALTER` plus a reindex, cheap now and cheap later.
  **Not taken, the operator's decision, 2026-09-01**, on grounds worth keeping: the benchmark
  figures are a spot in time and move as the registry grows through waves 2–3 (the bias
  inversion in `citator-schema.md`), so re-measurement lands on a new `benchmark_date`
  anyway and the same-day collision is rare. Widening the key would also depart from an
  accepted record for a rare case. Pull this in if the scorer ever changes twice in one day
  (schema-critic, second pass).
- **`docs/citator-query-2.sql`'s `family` CTE keys on `stb_decision_id`** while
  `citing_work_id` COALESCEs to a raw sha256 for a filing-mined edge, so for those the family
  EXISTS is always false and every filing self-mention projects. The file says so at the CTE.
  ADR 0018 D9 provides for filing edges, so this needs its branch before extraction moves
  beyond decisions — which this slice does not (schema-critic, both passes).
- **No `superseded_at` on any citator assertion table.** A superseded row is dated only by
  its successor's `asserted_at`, and a self-pointer retraction has no date at all — so
  "what a reader saw on date D" is not fully reconstructible for the citator layer. This is
  the 0006/0009 house idiom rather than anything 0014 invented, but it is now load-bearing
  for a published number (schema-critic, second pass, against validation query 3).

## Found 2026-09-01, reviewing `docketyard.citator` (code-review high + stb-ingest-specialist)

The serious ones were fixed in the same session and are pinned by tests in
`tests/test_citator_pipeline.py`. These are what was left, each with why it waits.

- **The exposed class and every rule-2 repair reach a page unreviewed.** ADR 0017 D5 routes
  both to a human *before* publication — that is what the exposure test was defined for. The
  loader computes the keys and `citator load` prints them, but `review_action` (ADR 0016) is
  in no migration, so nothing stores or gates on them. **This is a shipping blocker, not a
  deferral**, and it is in `TODO.md`; it is here so the finding is not lost if that line is
  pruned.
- **`targets_out_of_class` and `targets_emitted` are on different grains.** Out-of-class
  counts findings; emitted counts distinct `(page, key)` pairs. So the two do not add up to
  what the producer sent, and "not kept" is auditable only against a known dedup rule. A
  `findings_received` column, or counting distinct out-of-class raws, fixes it.
- **The resolver has no version of its own.** `citation_resolution.method_version` carries
  the RULE name (`rule-1`, `rule-2-repair`), so a change to `resolve.resolve` — the exposure
  threshold, say — mints no new key, supersedes nothing and is invisible in every
  measurement, against ADR 0007. Carry the rule as part of the method and add a real
  `RESOLVER_VERSION`.
- **A six-digit fusion is outside both the repair and the exposure test.** ADR 0017's
  argument rests on the finder's `\d{1,5}`; `keys.DOCKET` allows six, because 104 held
  dockets have six-digit sequences and a five-digit cap would key them as nothing. So a
  five-digit docket that absorbed a marker is neither repaired nor flagged. Widening either
  rule is a change to an accepted definition.
- **`citation_key.key_version` belongs to whoever inserted first.** `INSERT OR IGNORE` on
  the four-column key leaves the old value when a re-run under a bumped `KEY_VERSION`
  produces the same key — the same "whichever channel inserted first owns it for ever"
  defect ADR 0018 D2 rejected `cited_raw` over. A differing `key_version` on an existing key
  is a re-normalisation event worth being loud about.
- **`cited_by(work_id=...)` always returns nothing**, because no writer populates
  `citation_resolution.cited_decision_id`: ADR 0018 D4's verb gate (a phrase's own verb
  decides whether `served <date>` matches `service_date`) is a later pass. The docket grain
  is the one to use, and `project.cited_by`'s docstring says so.
- **The family closure is written twice** — `web/cite.py` and `project.py` — which ADR 0018
  D7 says the projection may not depend on. `methods.PROJECTION_RULE` also hardcodes
  `closure=cite.py@2026-09-01`, a date somebody must remember to edit.
- **No `superseded_at` on any citator assertion**, so a self-pointer retraction has no date
  and "what a reader saw on date D" is not fully reconstructible for this layer. The
  0006/0009 house idiom, but now load-bearing for a published number.
- **The findings body is not identified.** `asserted_from_capture` stays NULL and
  `extraction_run` records no payload hash, so an edge traces to `(method, version)` and not
  to the enrichment run that produced it — the capture-first invariant met by convention
  rather than by the store. The file's sha256 in `extraction_run.note` is the cheap fix.
- **An empty `quoted_passage` can project.** A finding with no `quoted` text passes NOT NULL
  as `''`, and the edge then reaches a reader with no citing passage, against ADR 0017 D6.
- **`WB25-53` keys as `WB 25`**, because `\b` accepts the hyphen as a boundary. That is the
  accepted design — emit, let resolution decide — but if `WB 25` is held it resolves
  confidently, and the exposure test does not cover it because it is not a fusion.

## Found 2026-09-01, schema-critic on migration 0015 (the review queue)

Its Tier 0 and Tier 1 findings were fixed in the same session and are pinned by
`tests/test_citator_review.py`. These are what was left.

- **`decide()` does not open a transaction, though its docstring says one.** It relies on
  `sqlite3`'s implicit deferred transaction and on the CLI's `con.commit()`. Nothing loses
  data today — an uncaught `IntegrityError` rolls back — but the self-pointer window opens
  the moment a caller uses an autocommit connection, and a self-pointer "cannot be told
  apart from a deliberate retirement" (migration 0014's own words). An explicit `BEGIN` is
  the fix; the same is true of `load.load_document`, which at least says so.
- **The exposed queue is a superset of the gated set.** It applies neither the family/span
  term nor the confidence predicate, so an exposed edge the family term already suppresses
  is queued although it can never reach a page. That is the safe direction, but it is the
  noise ADR 0017 § The exposure test narrowed the definition to avoid — queueing expected
  non-events "trains a reviewer to skim".
- **`pending()` materialises the whole queue then slices**, runs one `MIN/MAX` query per row
  for the held-record test, and has no `DISTINCT`. ADR 0017 projects "a four-figure one-time
  queue across the backfill", so this is not free. `cli.py` also calls it with `limit=10_000`
  just to find one key.
- **ADR 0016's re-attribution is replaced by a rule recorded outside the ADR set.** 0016 says
  the party seed and joins "**are re-attributed** to the operator's reviewer id when the
  table exists". The table exists now; 0015 does not create reviewer zero and re-attributes
  nothing. `schema-draft.md` § 7 substitutes "a `human` assertion no live review action names
  is the operator's", which has good reasons and no code. **A departure from an accepted
  record, and the operator's to settle** — recorded here so it does not pass unnoticed.
- **ADR 0014's rotation promise now covers four tables and says three.** `reviewer` holds
  `email_enc`; 0014 § Consequences says rotation is "an all-rows pass over three tables that
  is not yet written", and no code enumerates them. A constant in `alerts/vault` naming the
  tables is the cheap fix.
- **`review_action` records the queue but not the question.** All three citation queues write
  `target_table = 'citation_resolution'`, so `target_key` and `produced_key` are the same
  string today and "which exposed judgements has a human checked" is answerable only through
  `queue`. The distinction the column pair exists for pays nothing yet.
- **No sign-in.** `reviewer_token` has no writer and no reader: magic-link sign-in is in ADR
  0011's decision and not in code, so a grant cannot be used by the person it was granted to.
  `docketyard citator grant` and `decide` serve reviewer zero; `/review` is the blocker.

## Found 2026-09-01, reviewing the finder (code-review high + stb-ingest-specialist)

The silent-data findings were fixed the same session and are pinned by
`tests/test_citator_find.py` and `tests/test_citator_pipeline.py`. These are what was left.

- **A hyphenated sub-docket resolves to the PARENT.** The Board prints `WB25-33` for
  `WB 25 (Sub-No. 33)`, and decision 52676 in the benchmark is docketed that way and cites
  `WB-20-50`. `keys.DOCKET` stops at the number, so the key is `WB 25` and the published edge
  points at the parent proceeding. `find.printed` now absorbs the tail so `cited_raw` is
  honest, but the KEY does not carry it — that is a `keys.py` change and an ADR question
  (116 WB dockets), and it should be decided rather than slipped in. Its second effect: for
  that decision the own-docket rule inverts, because `own` holds `WB 25 (33)` while the
  finding keys `WB 25`, so its own caption reads as a citation and is saved from publication
  only by the family closure's parent term.
- **The grammar is not the measured tool's**, so migration 0016's table reproduces ADR
  0017's configuration rather than being it. `keys.DOCKET` allows six digits where
  `benchmark_regex.py` capped at five; it does not accept the interposed words in
  `NOR Docket No. 42183` (decision 52616's caption), so that form is now lost outright; and
  `SUBNO` takes a bare `(X)` the old pattern did not. Reconciling the two grammars, or
  retiring the old one, is the fix.
- **A six-digit fusion is outside both the repair and the exposure test.** `resolve.py`'s
  comments still assert the finder's old `\d{1,5}` cap as the reason. `FD 368731` — a
  five-digit docket with a fused footnote marker, the shape `docs/stb-data-source.md` names —
  now keys as a six-digit unresolvable that neither rule 2 nor the exposure test looks at.
- **The `projection` measurement stores the RULE's figure, under a rule version that names
  the gate.** `methods.PROJECTION_RULE` carries `gate=exposed@…`, but the stored recall and
  precision are what the rule projects before the gate holds anything back. What a reader
  sees depends on review backlog, which no single measurement can carry. A second
  `class_measurement` row under its own class — `docket, after review gate` — is the fix.
- **The regenerated run records neither the registry it was made against nor a fingerprint
  of it.** `kind` is a function of `own`, which comes from the registry, and 0016's own
  argument is that the old figures were un-re-derivable partly because of which registry they
  were scored against. Writing the path and `SELECT COUNT(*) FROM docket` beside the run
  closes it.
- **An orphan decision silently lowers every figure.** A decision with no `decision_record`
  is skipped, its truth targets stay in the 225 denominator, and the response is a `print`
  fifty lines above the numbers. It should be fatal, or printed beside them.
- **`kind` is work-relative but stored per document.** The own-docket rule is defined against
  the citing WORK's dockets; the judgement key has no work in it. ADR 0018 D9 measured 5
  documents of 20,992 hanging under two decision ids — for those, loading from each work in
  turn writes opposite `kind` values on one key and grows an oscillating supersession chain.
  Nothing reads `kind`, so no edge moves; the chain still grows.
- **Captions enter the exposed review queue.** No queue carries a `kind` term, so a human can
  be asked to clear a self-reference the projection suppresses whichever way they answer.
  Bounded noise, but it is the "trains a reviewer to skim" cost ADR 0017 narrowed the
  exposure test to avoid.
- **`target_kind` means two things either side of the seam.** The benchmark run shape uses it
  to distinguish caption from citation; in the store it is the target's namespace (`stb` vs
  `court`) and `load` hardcodes `'stb'`. Nothing breaks only because `load` ignores the field.
- **The dry run's agreement check will report NO for something ADR 0017 D4 permits.** The
  Python side counts citation-kind findings only; the store now holds captions, and an
  in-family caption whose own line names a document SHOULD project — that is the
  reconsideration edge query 2 exists to find. It needs naming as a fourth legitimate
  difference beside the rule-2 and review-gate exclusions.
- **`find` drops a finding whose raw will not normalise, with no counter.** `load` has
  `out_of_class` for exactly that, so a drop inside the finder is the one drop nothing can
  audit. Near-unreachable today, one line to close.
- **A backfill pass and a forward pass over one document are indistinguishable afterwards.**
  `extraction_run` carries no `ingest_mode`. Citation edges reach no alert join, so the
  trap's usual hazard is absent, but the distinction is gone.

## Found 2026-09-02, fixing the drain's un-fetchable URLs (stb-ingest-specialist + code-review medium)

The en-dash fix (`_wire_url`, `capture/stb.py`) closed two causes of a never-fetchable URL.
The reviewer's point is that the *class* is wider than its two causes, and these are what is
left of it.

- **An unanswered attempt leaves no capture, so nothing rests it — this is the mechanism, and
  it is still open.** `capture/documents.py:106` records the status-0 attempt only `if
  refresh`. On the drain and forward paths a failure that produced no response is invisible to
  the ledger, so `recently_refused` never sees the URL and `attachments(unfetched_only=True)`
  re-selects it every pass. Still reachable: an S3 5xx or 429 surviving three retries, a reset
  or read timeout doing the same, a disk-full `OSError` inside `consume` (not retried at all),
  and a lone surrogate in a stored URL, which makes `quote` itself raise (**measured
  2026-09-02: 0 of 110,110 attachment URLs carry one**, so that cause is theoretical today).
  In a poll pass the cost is bounded by `--limit`; in a `remaining == 0` drain loop it is the
  same non-termination, with a different first line in the log. **Dropping the `if refresh:`
  guard is the small fix and it is not obviously right**: a network outage mid-drain would
  then rest every URL it touched for `REFUSAL_REST_DAYS`, and a backlog that merely went quiet
  would read as drained. Capture-first says the attempt belongs on record either way, which
  makes this a provenance-grain question — **Cameron's, and schema-critic's before his.** The
  other half is `drain.sh` (instance-only, not in this repo): it should stop on a pass that
  makes no progress, not only on `remaining == 0`.
- **`_wire_url` percent-encodes the netloc along with the path.** A no-op on the two hosts that
  exist (measured 2026-09-02: 110,107 `dcms-external.s3.amazonaws.com`, 3
  `dcms-external.s3.us-east-1.amazonaws.com`, both ASCII), and the docstring now says so. A
  non-ASCII host would need IDNA, which percent-encoding would break into an unresolvable
  name; split-and-quote-per-part is the fix if a host ever arrives from data.
- **`html.unescape` on the href could in principle mangle a URL into a fetchable wrong one.**
  The legacy semicolon-less entities (`&reg`, `&copy`, `&sect`, `&times`, …) resolve inside a
  query string at parse time (`ingest/observations.py:226`). Before `_wire_url` such a URL was
  a hard local stop; now it would be sent. **Measured 2026-09-02 and it is currently empty: 0
  of 110,110 URLs match a legacy entity or move under `html.unescape`** (80 contain an `&`,
  every one of them a railroad in a file name — DM&E, EJ&E, "Kevin & Mary"). Recorded because
  the parser, not the client, is where it would be fixed: unescape only the five named and the
  numeric references on an href, leaving `clean()` its full unescape for cell text.
- **The ledger records the stored URL, never the wire URL.** `documents.py:113-123` passes the
  stored form as both `endpoint` and `request_params`. `endpoint` **must** stay that way —
  `recently_refused` and `recheck_urls` join it against `source_url` — but `request_params` is
  free, and for the three en-dash rows the capture will not show what was actually requested.
  Reproducibility survives (`_wire_url` is deterministic and in-repo); one line adding
  `("wire_url", wire)` when it differs would make the capture self-describing.

## Found 2026-09-02, three production outages: the comment page is O(docket)

The defect, its blast radius and its containment. **This is the highest-priority open item in
this file** — it took production down twice and stopped the record being kept for 6 h 52 m.

- **A record page builds its entire docket sheet to read one field off it.**
  `_comment_entry` (`web/app.py`) calls `sheet.docket_sheet()`, which assembles every filing,
  decision and comment on the docket with attachments, documents and parties joined, then
  linear-scans `s.entries` for the single entry it wants. `_record_entry` does the same for
  filings and decisions. **`record.html` uses exactly one field of that sheet: `sheet.title`.**
  So the cost of one page is the size of its docket, and a crawler walking a docket is
  quadratic in it.
- **The record has a docket that makes this fatal.** FD 35087 holds **12,031 of the 34,255
  comments** (next largest 4,245; then 2,044). Each of its comment pages builds a
  ~12,600-entry sheet. **Measured 2026-09-02: median 21.5 s a page, p90 25.0 s.** With
  uvicorn's 40-thread sync pool, roughly two requests a second saturates the box.
- **The site invites the crawl.** Every comment address is published in our own paginated
  sitemap, so a well-behaved crawler walking FD 35087 asks for all 12,031.
- **The attachment drain sharpened it.** Before 2026-09-01 those comments' attachments were
  unfetched; the drain fetched 26,816 of them, so every entry in that sheet now carries a
  document to join and render. The first crawl to meet the heavier sheet was the 02:10 load
  climb on 2026-09-02.
- **What it cost.** Load 15-21 on two vCPUs from 02:10 to 06:40; captures stopped at 03:26
  while the site still answered until 05:06; the box wedged until a manual reboot at 10:18
  (coverage gap 1, 6 h 52 m). It recurred twice more within the hour, each cleared by
  `docker compose restart web`. The poller and Litestream were never at fault and kept
  working whenever the box had CPU.
- **The fix** is to fetch the one entry and the docket's title directly instead of building
  the sheet. It is not a one-liner: `_fold_family_duplicates` means an entry's identity
  depends on its family, so the targeted lookup has to reproduce that or document why it need
  not. Both call sites want the same helper. **It cannot ship without a deploy**, and
  production is four migrations behind (schema 13 against 17).
- **Containment, written and NOT YET APPLIED** (`infra/deploy/Caddyfile`): a 503 with
  `Retry-After` for `/d/FD-35087/comment/*`. Costs a reader nothing they had — those pages
  already time out unanswered — and 503 rather than 404 because the address is permanent
  (ADR 0013). Applying it needs a write on the instance. **Delete that block with the fix.**
- **The fix is measured on the real store now, 2026-09-02.** Against a Litestream restore of
  production at schema 17: the busiest FD 35087 member holds **12,031 comments** and the old
  path built **12,633 entries** to answer for one; `one_entry` is **34x** faster on the same
  data and returns the identical entry. End to end through the app the comment page renders
  in **19 ms** where production measured 21.5 s — though the two are not the same
  measurement, because 21.5 s was taken while forty threads contended on two vCPUs and this
  was one request on an idle machine. What the fix removes is the quadratic that made the
  contention possible, not 21 seconds of any single request.
- **The viewer still builds the whole sheet, and it is one click away.** `/filing/<id>/view`
  and `/decision/<id>/view` need the entry's neighbours (prev/next) and the sheet's Parties
  block, so they cannot use `one_entry` and still call `docket_sheet` — on FD 35087 that is
  the same ~12,600-entry assembly the record pages just stopped doing. Narrower than the
  comment pages (549 filings and 43 decisions there, not 12,031) and a comment has no
  `/view` route at all, so the crawl that caused the outages cannot reach it; but "Read it
  here" links to it from every record page and it is not disallowed in `robots.txt`. Fixing
  it needs a cheap ordered neighbour query, and the sheet's order is computed in Python
  (`_numeric` over comment numbers), so it is not a straight translation to SQL.
- **Two guards worth having whatever the fix is**: a memory cap on the `web` container, so it
  cannot take `ingest` and `litestream` down with it — that is the difference between "the
  site blipped" and "the record stopped for seven hours" — and something that acts on the
  healthcheck, which correctly reported `unhealthy` while nothing restarted it.

## The instance resize (2026-09-02, v2026.09.1)

**ADR 0022 D7 now resizes it with the OCR migration** rather than leaving a trigger to watch:
the store crosses ~1 GB on rows alone under D6. What stays here is the operational half.

- **Not a response to 2026-09-02.** That outage was a quadratic query, and a larger box would
  have absorbed more crawler traffic before failing — the same fault, later and worse. Fixed
  (`sheet.one_entry`). Recording the temptation is the point.
- **A resize is a rebuild, not a slider.** Lightsail has no in-place resize: snapshot, launch
  the larger instance, move the static IP. Maintenance-window work; ADR 0020 gives the window.
  Check plan pricing at the time rather than assuming the ladder.
- **Where it stands, measured 2026-09-02**: the schema-16 restore in `data/` is **152 MB**,
  `web` is capped at 768 MB of the instance's 2 GB, and the blob cache holds ~32 GB against a
  corpus heading for 150–250 GB with the prune keeping 20 GB free.
- **Two things the resize does not fix**, so they need their own answer: `litestream` keeps
  `retention: 168h` while the bucket keeps noncurrent versions 30 days, so the store's undo
  window is the shorter one (ADR 0022 D10); and `dump.py` keeps one monthly archive for ever
  and prunes none, which at gigabyte scale competes with the blob cache's 20 GB floor.

## Found by the four-lens panel, 2026-09-02 (against the Proposed ADRs 0021/0022)

- **`data/public` is synced nowhere.** `docketyard-blobs.service` copies only `data/blobs`,
  so the monthly CC0 archives — which `dump.py` writes and never prunes, and which `/data`
  lists by SHA-256 — exist in exactly one place, on the instance's disk. Losing them makes
  the page quietly stop listing archives it once published, which is a withdrawn public
  artefact and the one direction CC0 was chosen to avoid. Nothing to do with OCR; found while
  measuring for it.
- **No systemd unit has `OnFailure=`,** and `config.alloy` collects no systemd metrics, so a
  failed timer is invisible to the detector ADR 0019 built. The dump's failure is worse than
  absent: `scrub` raising leaves last night's snapshot served under an unchanged manifest, so
  a third party downloading it has no signal.
- **`/coverage` is uncached** where `/stats` sets `PUBLIC_CACHE`, and already runs ~20 scalar
  subqueries per request. Anything counted over `document_text` lands on an uncached public
  page.
- **Every future migration pays a full `PRAGMA foreign_key_check`** over the whole database
  (`db.migrate`), which at ~1.35M new rows makes every subsequent migrating deploy slower —
  a cost that lands on the rollback story, not just the deploy.

## Found by code review, 2026-09-02 (against migrations 0018/0019, unreleased)

- **A restored public snapshot cannot be migrated forward.** Every migration that touches a
  held table names it unconditionally — migration 0019 does `DROP TABLE decision_decided_date`
  and selects from it; 0018 inserts into `measured_target_vocab` and `review_target_vocab` —
  but `dump.py` DROPS every `HELD_TABLE` from the snapshot while `PRAGMA user_version` is
  stamped at the release's schema. So a third party who restores an archive and opens it with
  a later release gets a bare `no such table`, not a message. Pre-existing and class-level: it
  affects every held table and every future migration, not 0019, which is why it is recorded
  here rather than worked around in one script. The fix is a decision about what a published
  snapshot IS — a readable artefact at a pinned schema, or a store the code will migrate —
  and `dump.py`'s docstring currently implies the second ("a restored copy is at the release's
  schema and `docketyard search rebuild` remakes it").

## Found 2026-09-03, code review on `methods.stamp`'s channel term (main at 682fe97, unreleased)

- **`declare` ranks no channel but the text layer.** RANKS carries `text-layer` only and the
  projection INNER-joins every resolution and judgement to its rank row on the channel, so
  a measured OCR load would store rows no page can show. `citator load` now refuses an
  unranked channel (`methods.ranked`), so the failure is loud; the gap itself is a new
  `rank_version` carrying OCR at ranks 3 and 4 under ADR 0018 D7, which waits on the
  namespace question in `ocr-migration.md` item 8. A decision, not a default.
- **The `citation` identity row takes the stamp of whichever pass asserted it.** The key
  carries no channel and `unchanged` is keyed on (method, version) alone, so a document
  read OCR-first keeps the OCR figure through a same-version text-layer pass, and a newer
  version on OCR re-stamps it while the live text-layer resolution still projects. Nothing
  published reads that figure — the projection takes `confidence` from the channel-keyed
  resolution and uses this row as a state gate — but validation query 3's "what stood
  behind this edge" answers per family. Either the identity row is stamped from a
  channel-independent measurement (not expressible: `reading_channel` is NOT NULL) or its
  semantics are stated in 0014's § citation. Comment at the insert in `load.py`.
- **The review queues have no registry join.** `review._base` joins resolution to reading
  on the channel and never to `assertion_method`, so a resolution on an unranked channel
  enters `citation_exposed`/`repaired`/`unresolved` although it can never project; a
  document read on both channels queues one question twice. Moot while the CLI refuses
  unranked channels; live for any direct caller.
- **The channel/measurement agreement is Python, not schema.** Migration 0014 made
  `(measurement_id, measured_target)` UNIQUE so every assertion table could FK the stage
  pair; the channel is the same shape of error and is held by `load.WrongChannel` and the
  CLI. The schema fix is widening that pair to include `reading_channel` and re-pointing
  the four channel-keyed families' FK — a rebuild of held tables in the 0019 pattern, for
  Migration B's `assertion_method` rebuild to carry.

## Found 2026-09-03, code review on the pagination pass and the loader (unreleased)

- **`citator load` still runs its own loop.** `store/batches.py` was hoisted for the two
  text passes; the citator's loop in `cli._citator` commits per document (the measured
  1.2 ms a row) and counts an `OperationalError` per document — the wait-fail-count-for-hours
  shape `batches` exists to refuse. Folding it needs `load.Loaded` mapped to an outcome word.
- **`page_index.visible` infers, it does not record.** Whether a primary is in `page_fts`
  is read off the display view's rule as it stands, so a human row inserted without
  `leave(primary)` leaves the index holding text the view no longer shows and the loader
  cannot tell. The review layer's human writer (Migration B) owes `leave`/`enter`; until
  then a hand-written human row owes them by hand.
- **A batch aborted after `save_blob` leaves its readings' files under `blobs/`** with no
  `text_payload` row, shipped by the sync and never pruned. Bounded by one batch and
  re-derived to the same address on the re-run; an orphan audit must join `text_payload`.
- **`ATTACHED`/`NOUN` per pass are the exit-status contract**, read by `cli._text`; a new
  outcome word in a pass that is not added to its `ATTACHED` exits 1 on a successful run.
- **`search.PAGE_TABLES` is a literal list**, not derived from `review_target_vocab`: a
  page-tier table Migration B adds a correction path for is counted against the record
  index and the site-wide ETag again until it is added here, and its page keeps its old
  validator. A test asserting the set against the vocabulary would need "page-tier" named
  somewhere the schema can read.
- **The text page renders a document whole.** The mean is ~15 pages; the tail (EIS volumes,
  merger applications) runs to hundreds, ~2-4 MB of HTML per request at 300 s cache life.
  A bounded window without new addresses is a query address family (`?from=`), which is the
  address-space question the one-address rule was adopted against — the operator's.
- **The record page and the viewer link the text page unconditionally**, never on whether
  readings exist: `stamp()` no longer moves on the page tables, so a link conditioned on
  them would answer 304 with the pre-load rendering. Nothing under `stamp()` may read them.
- **Item 22's methodology entry** (the per-tier error rate and the born-digital caveat) is
  still owed; the page's sentence on document text was corrected, the entry was not added.

## Found by schema-critic against migration 0018's `document_pagination`, 2026-09-03

- **Four tables may be held for no reason anyone weighed, and unholding them would restore a
  real foreign key.** `dump.py` classifies "the citator block (migration 0014)" wholesale, so
  `reading_vocab`, `measured_target_vocab`, `class_vocab` and `class_measurement` are HELD.
  `docs/licensing.md` names entity resolution, the carrier registry, the citation graph,
  classifications and extracted deadlines — **it does not name the measurement registry**,
  whose contents (recall, precision, benchmark date, score file) the site already publishes
  verbatim on `/methodology` and in ADR 0017 § The figures. The cost of the current
  classification is concrete: `document_pagination` cannot point at `class_measurement` to earn
  `'measured'` and `ocr_run.reading_channel` is a CHECK where the house idiom wants a foreign
  key, both because a PUBLISHED table may not reference a HELD one. The four move together or a
  new dangler appears (`class_measurement` references the other two).

  **The operator's, and one-way in one direction only**: held can become public later, public
  cannot become held, so deferring costs nothing and acting is irreversible. Recorded because
  it was suggested and not taken, not because it should be.

## Found by the cloud bughunter review, 2026-09-03 (branch `migration-a-passes`, unreleased)

Twenty-eight agents over the five commits since `682fe97`; the run hit its wall clock with
four confirmed, all nits, three reported and one dropped by its quality cap. Nothing blocking.

- **"The text" is offered for records whose only viewable file is a JPG.** `record.html`
  gates the button on `viewable_index`, whose set is `INLINE = {pdf, jpg}`; the text route
  picks from `PAGINABLE = {pdf}`. `viewer.html` links the text page unconditionally. A
  JPG-only record shows the affordance and lands on the "not a kind whose text is read"
  fallback. Gate both on a PAGINABLE pick — a static property of the file list, so it does
  not run into the `stamp()` rule the item above records.
- **`_page` accepts a bool as `agreement.distance`.** `load.py` checks the distance with a
  bare `isinstance(x, int | float)`; every other numeric field in the loader (`page_no`,
  `engine_confidence`, `pages_failed`) pairs it with a bool guard. A JSON `true` passes and
  is stored as `1.0`, inside the CHECK's range, shown to a reader as a band operand.
- **`_STAMP_TERMS` spells out `NOT IN (?, ?)`** where `search._NOT_PAGES` derives its
  placeholders from `PAGE_TABLES`. Both `stamp()` and `page_stamp()` bind the tuple into the
  two literal marks, so the page-tier table Migration B adds (the `PAGE_TABLES` item above)
  would raise a binding-count error on every reader page until both sites agree. Derive the
  placeholders once, in `search`, and import them.

## Observed at Migration A's first load, 2026-09-04 (v2026.09.2 on the resized box)

- ~~**A bulk pass and Litestream trade the write lock, and the pass loses.**~~ FIXED
  2026-09-04 (v2026.09.7). `text load` aborted six times (`OperationalError: database is
  locked` after the 30 s busy timeout) at 35,903, 41,524, 42,107, 43,831, 45,366 and 57,559
  documents, and `text paginate` once at 59,105; Litestream logged `checkpoint:
  mode=TRUNCATE err=database is locked` through each, and a shell loop of twelve finished it
  on the seventh attempt. The pass now rolls the batch back — which is what hands the lock
  over — waits, and REPLAYS it, up to five times with a doubling backoff
  (`batches.under_lock`). Replay is safe because the rollback left nothing and the payload
  blobs are content-addressed. A lock that never clears still aborts, and a failure that is
  not a lock aborts at once.
- ~~**`search rebuild-pages` holds the write lock for its whole run**~~ FIXED 2026-09-04
  (v2026.09.7) — 8 m 49 s at 1,104,935 rows, then **27 m 26 s** with migration 0020's
  function on every row, and the poller lost its 01:03 pass to it. FTS5's `'rebuild'` does
  the whole read-and-index in one transaction; it is now `'delete-all'` plus keyset-paged
  batches of 2,000, with the per-row masking running in the SELECT outside any transaction
  and the lock released between batches. Measured on a synthetic 100,000-page store: a
  second writer was refused the lock on 8 of 21 probes before and 0 of 255 after, for 3.2 s
  against 4.0 s of wall time; re-measured on 40,000 pages of 3,827 characters (a real page's
  length, after the page-hit benchmark below was found to have been taken on pages too short
  to see the cost) the answer holds — 9 of 19 against 0 of 312, 3.7 s against 4.3 s. **The
  production figure at 1.1M rows is not verified** — the next real rebuild is what confirms
  it.
- **A rebuild started while `text load` is already running is not detected.** The loader
  refuses to START while `search_meta.page_built` says `rebuilding` (`page_index`), which
  closes the common direction; there is no marker for "a load is in flight", so the reverse
  is not enforced. `rebuild_pages` reports `moved` when the page signature changed under it,
  which is how the operator learns of it after the fact. Found by review 2026-09-04; the fix
  is a claim both passes take, and nothing needs it before Migration B.
- **2,704 of the 80,272 extraction records name no `document` row** (`unknown_document`):
  the blob copy on RMI-AI-MACHINE holds files the store does not list as documents, and the
  extractor v2 writes a stub for every file it sees. The count is the loader's report, not a
  defect; which files they are has not been checked.

## Found by the cross-file tracer on the merged page search path, 2026-09-04 (v2026.09.4)

- ~~**No per-document cap on the twenty page hits.**~~ FIXED 2026-09-04 (v2026.09.8). A
  phrase printed on every page of one 300-page assessment filled the whole section with that
  document's pages 1-20 and hid every other document that matched; the record-hit path cannot
  fail this way because its grain is one row per docket. Two hundred ranked rows are now
  scanned and folded to three a document (`PAGE_PER_DOCUMENT`, `PAGE_OVERFETCH`) before the
  cut to twenty, and both surfaces say when pages were folded away. The fold reads no text
  (SQLite runs the masking function only for selected columns), which review caught and is
  the whole of the cost: on a 40,000-page store at 3,827 characters a page, a term matching
  every page took 36.7 ms before, 49.0 ms with all two hundred rows read through the view,
  and 37.6 ms as shipped.
- ~~**`PageResults.dropped` is computed and read by nobody.**~~ FIXED 2026-09-04
  (v2026.09.8). It is the one signal that the page index has drifted from the display view (a
  human row inserted without `leave`, a store restored from a replica), and it is now a
  process counter behind `/metrics` as `docket_yard_page_index_stale_rows_total`. A store
  query would be the masking function over 1.1M rows on every scrape, so it counts what
  searches have MET — it moves only when a reader reaches a stale row, which is when it
  starts to matter, and it resets with the process. It counts DRIFT only: `dropped` also
  covers a comment attachment's pages, which have no text address and are dropped from every
  search of a healthy store (review, 2026-09-04).
- **From TODO, 2026-09-04 (the cap):** Cameron's idea of a cadence switch from the alert
  email and a signed-link manage page per address.

## From the critic pass on the drafted ADR 0012 addendum, 2026-09-04 (against v2026.09.8)

The addendum was withdrawn rather than accepted (see below), but the pass was reading the
blob tier's code to check the draft's claims and found things the draft was not about. Each
was verified against the file named before it was written down.

- ~~**A `StoreMismatch` is a `print()` and a 503, with no gauge behind it.**~~ FIXED
  2026-09-04: `/metrics` carries `docket_yard_document_store_refused_total{kind}` with THREE
  kinds counted apart, because they are answered differently — `mismatch` (the bytes at a hash
  were not that content) and `absent` (a 404: the object is gone) both mean the store has lost
  a document and somebody must look, while `unreachable` is an outage and waiting is the
  answer. Review caught that a 404 was landing in the outage bucket, which would have had an
  operator wait out an outage that was not happening while the blob stayed lost. Original note: `web/app.py`'s
  document route calls it "never served, never quiet", and it is genuinely never served — but
  quiet is exactly what it is: a stdout line in a container log, for the condition that means
  S3 answered a hash with other bytes. That is a silent failure of the class `docs/alerts.md`
  decomposes, and `/metrics` has a counter for page-index drift and none for this. The fix is
  a counter beside `docket_yard_page_index_stale_rows_total`, which is the same shape.
- ~~**The web tier's fetch-on-miss writes into a directory the prune cannot reclaim.**~~
  **CORRECTED 2026-09-04, and no code was needed — I had overstated it.** The parts that are
  true: `documents._fetch_into_place` streams to `blobs/.tmp/ws-*`, the sync excludes
  `.tmp/*`, and `prune_blobs.py` skips `parent.name == ".tmp"`, so the prune cannot reclaim
  that directory. What I did not check before writing it down: **the fetch cleans up after
  itself on every path it can reach** — `except BaseException` unlinks and re-raises, a hash
  mismatch unlinks, and success `replace`s the file out of staging altogether. So a `ws-*`
  survives only a hard kill (OOM, SIGKILL, power), and `records.sweep_staging` clears those
  older than six hours at the start of every fetch run, which the poller makes every thirty
  minutes. The exposure is one temp file per fetch in flight, not an accumulation, and a
  floor-aware sweep on the web side would defend against nothing that happens.
- ~~**`documents._in_flight` never shrinks.**~~ FIXED 2026-09-04: the lock is dropped when
  the fetch ends, on the failing paths too. It is a device for the seconds a fetch takes and
  correctness never rested on it — the fetch hashes on the way in and `replace` is atomic.
  Original note: One `threading.Lock` per SHA, added by
  `setdefault` and never removed, in a process capped at 768 MB whose steady state is
  110-170 MB. At 104,091 documents that is a slow accumulation of dict entries for a
  correctness device that only matters during a fetch. Drop the entry when the fetch ends.
- ~~**`web`'s own credential can stop the record being kept.**~~ FIXED 2026-09-04: the
  compose guard is `:-`, not `:?`, so `web` refuses ALONE — `capture.s3.from_env` raises when
  `DY_S3_BUCKET` is set and the keys are not, and `create_app` calls it at construction.
  **Not "nothing is lost", which is what I first wrote**: the refusal is now a crash-loop
  under `restart: unless-stopped` rather than a clean `compose up` abort, and with the bucket
  itself blank nothing checks the keys at all — the same pair is the web tier's SES
  credentials, reported by `_sender`'s "mail not configured" line and a 503 from the subscribe
  form rather than by interpolation (review, 2026-09-04).
  Original note: `compose.yaml` guards
  `DY_WEB_AWS_*` with `${...:?}`, which fails interpolation for the WHOLE file — so
  `docker compose up -d ingest` fails too if the reader key is missing or mid-rotation. Nine
  lines below the guard, the file shouts "THE READER-FACING PROCESS MUST NOT BE ABLE TO TAKE
  THE RECORD-KEEPING ONE WITH IT", which is coverage gap 1's lesson and ADR 0020's premise.
  The guard belongs in `serve`'s startup check, where it fails the reader alone.
- **The web tier holds `DY_EMAIL_KEY`.** `compose.yaml`'s `web` takes `<<: *mail`, so the
  internet-facing process holds ADR 0014's key — the one under which subscriber addresses are
  ciphertext at rest. `docketyard-dump.service` blanks it explicitly for the dump; the
  long-running reader-facing process does not. Whether it SHOULD hold it is a real question
  (it sends the confirmation email, which needs the address), and it is Cameron's: the
  answer is either a documented consequence or a split between sending and reading.
  Not a defect until decided, but `infra/deploy/README.md`'s "and nothing else" is wrong
  today, and that sentence is what a reader of the topology would rely on.

## From the citator's first run over the record, 2026-09-04 (dry run, nothing loaded)

`citator find` over a `VACUUM INTO` copy of production, never the live store: 20,062
readings, 139,805 pages, **73,103 findings — 41,915 captions and 31,188 citations** over
5,176 distinct targets. **29,229 of the 31,188 citations (93.7%) resolve to a proceeding the
registry holds.** `citation` still holds 0 rows; nothing was loaded. The two things in the
6.3% that are worth having written down:

- **A sub-number the Board prints as `0X` does not resolve, and the proceeding IS held.**
  FIXED the same day (d1233f4), and **what the fix actually did is not what the first
  measurement of it said** — see the correction under the critic's findings below.
  43 instances over 19 distinct targets, all of which the registry holds under another key:
  the Board writes `AB 1182 (Sub-No. 0X)`, `keys.normalise` reads that to `AB 1182 (0X)`,
  and `keys.registry_key` builds the held docket's key from its parsed columns as
  `AB 1182 (X)` — the raw `AB_1182_0_X` having lost the `0` at ingest. So the two ends of
  ADR 0017 D2's resolution disagree about one spelling, and a real edge is refused as
  unresolvable. Small (0.14% of citations) and precise; the fix is in the seam between
  `ingest.dockets` and `citator.keys`, and whichever end moves, BOTH readings of the same
  proceeding must land on one key or the edge splits in two.
- **`SO 2` is cited 855 times and the record does not hold it** — 44% of every unresolved
  instance, in one target. The record holds 22 `SO` dockets, so the prefix is walked and
  this proceeding is not among them. That is a coverage statement rather than a defect, and
  it is exactly the display ADR 0017 D2 designs for ("cites SO 2 — not in the record");
  whether the backfill should reach it is the operator's.

Left on the instance for the next step, and to be deleted if it is not taken:
`/srv/docketyard/data/citator-dryrun.sqlite` (3.4 GB) and `data/citator-findings` (84 MB).
The step not taken is the rest of the chain — judge, load, project — which needs the
benchmark's measurements declared in the copy before `load` will write a row, and would give
the projected-edge figure to set against the published 94.7% / 97.7%.

## From the schema critic on the key fix, 2026-09-04 (verified; the fix shipped without them)

The `0X` fix went in with two of the critic's findings folded into it — the scorer copies
(`benchmark_score.norm_target`, `projection_score.printed`) and the glued-suffix path that
would have named the wrong docket. These are the rest, each checked against the file named.

**One of the critic's premises was wrong and the advice resting on it does not hold:** it
said migration 0014 is unapplied, so a missing column could be added by editing the file.
0014 is migration 14 and production is at schema 21 — it has been applied since 2026-09-02.
Both column items below therefore need a NEW migration, which makes them Cameron's and a
schema-critic pass of their own, not a tidy-up.

- **`class_measurement` cannot say which normaliser a figure was measured under.** It carries
  `extraction_method_version` and `resolution_method_version`; the normaliser is INSIDE the
  extractor (`find.py` calls `normalise` and decides `kind` by `key not in own`), so today's
  change moved the extractor's behaviour while no version on any measurement row moved. A
  `citation` row would point at a measurement taken under a normaliser it cannot name — an
  ADR 0007 gap, and a ninth item for ADR 0018 § Owed. Free of data cost while the citator
  holds 0 rows; a table rebuild afterwards.
- **`correction.target_key` has no `target_key_version`; `review_action.target_key` has one.**
  Same rendered `<sha>/<page>/<kind>/<key>` string, same normaliser, and 0015's own comment
  says why the version is needed ("without it a re-normalisation strands every human row").
  Zero rows today.
- **The exposure test's membership widened, accepted rather than avoided.** `resolve` uses
  `keys.BARE_KEY` as a proxy for "the printed form ended in a bare digit run", and ADR 0017
  settles the 3-of-225 membership on that equivalence. A printed `(Sub-No. 0)` now renders a
  bare key, so a form that ended in a closing paren — mechanically unable to fuse a footnote
  marker — becomes eligible for the flag. Zero occurrences in the corpus (all 43 were `0X`).
  Taken because the alternative is a rule that folds a zero only when a suffix follows, which
  cannot be stated in one sentence; and because `exposed` flags a correctly-resolved row for
  review rather than changing what it resolves to. If one is ever seen, it resolves right and
  is merely reviewed.
- **`docket.sub_sequence = 0` is legal SQL and now collides with the parent's key.** No row
  holds it (`parse_docket_id` maps 0 to None; measured 0 rows in production) and only ingest
  writes `docket`, so it is unreachable — but `docket_identity` keeps 0 and NULL as two rows
  while `keys.registry()` is a dict comprehension, so the second would silently overwrite the
  first and the registry would lose a proceeding without a word. A guard in `registry()` that
  raises on a duplicate key is one line and catches it loudly; the CHECK constraint is a
  table rebuild.
- **The site prints a docket in two forms its own citation grammar cannot read, and one of
  them names a DIFFERENT proceeding.** `urls.printed_docket` renders `AB_1182_0_X` as
  `AB 1182-X` and `urls.cite_docket` as `STB Docket No. AB 1182-X`; `keys.DOCKET` cannot take
  a hyphen between the digits and the letter, so `normalise` drops the suffix and returns
  `AB 1182` — the PARENT. `cite_docket`'s long form for FD and EP (`STB Finance Docket No.
  36873`) carries no prefix token at all and normalises to None. Re-measured against the store 2026-09-04 (the
  note's 2,707 was wrong): **2,711** held dockets are of the suffixed shape and **2,646**
  of them, printed by this site, named a different held docket; 655 across 13 prefixes are
  out of class, confirmed exactly. **The reviewer's half is FIXED** (`review.find_docket`
  now resolves a typed string through `urls.lookup` — the record's own identity parser — and
  falls back to the citation grammar only when the string does not parse; that also lets a
  reviewer name one of the 655 out-of-class dockets, which `normalise` refused outright).
  **Left, and untouched:** the two renderings themselves. `printed_docket`'s `AB 1182-X` is
  this site's invention — the Board prints `AB 1182 (Sub-No. 0X)` and `keys.registry_key`
  spells it `AB 1182 (X)` — so the site shows a reader a third spelling of a key the citator
  will publish under a fourth. Changing it moves reader-visible text on every sheet, in alert
  mail and on `/cite`, so it is **Cameron's**, not a code fix. Related: whether `keys.DOCKET`
  should learn the Board's long names the way `urls.lookup` has (`_LONG_FORMS`) — that widens
  the citation class and moves `KEY_VERSION` and every measured figure, so it is an ADR 0017
  question, not a patch.

## Measured while the citator first ran, 2026-09-04: what the citation class cannot name

The finder's class is a fixed prefix list (ADR 0017 D1 buys one class deliberately). Checked
against the registry: **the class can name 31,972 of 32,627 held dockets. 655 dockets across
13 prefixes can never be cited to at all** — S5M 240, MC 178, EPM 164, CU 16, FSA 14, MXC 13,
SAI 11, PTO 6, RR 6, AM 3, WC 2, CNO 1, S5R 1. Two prefixes IN the class, `FSB` and `PCA`,
match nothing the record holds. That is 2.0% of the record outside the citator's reach, and
a ceiling on recall that no sixty-decision sheet could have shown. Not a defect — a scope
that was never measured, and the number to quote if the class is ever widened.

## Correction, 2026-09-04: what the `0X` fix actually changed

The fix was measured on RESOLUTION and reported as "29,229 to 29,272 resolving, exactly the
43, and no other row moved" — in the commit message (d1233f4) and here. That was an
incomplete account, and the schema critic said so before the fact: `normalise` sits inside
the EXTRACTOR too, because `find` decides `kind` by `key not in own` and `own` is built with
`registry_key`. Re-running the finder under the fixed normaliser and diffing the two runs:

- **39 findings flipped from `citation` to `caption`.** Those documents were naming their
  OWN proceeding in the Board's `(Sub-No. 0X)` spelling; the old normaliser could not match
  it against `own`, so it called them citations of another docket.
- 2 findings disappeared, folding into a key already found on the same page (`find` keeps
  one finding per page and key).
- 4 remained citations and now resolve.
- After: 41,954 captions, 31,147 citations, 29,231 resolving — **93.85%**.

**So the fix mostly avoids 39 false edges rather than gaining 43 true ones.** A caption is
stamped `unmeasured` and projects nothing, so the effect on what a reader would be shown is
39 spurious "X cites Y" edges that will now never be drawn — a better outcome than the one
first claimed, and a different one. The lesson is the critic's: a measurement of one stage
of a pipeline is not a measurement of the change, and this normaliser is in three stages
(extractor, resolver, exposure test).

The findings directory on the instance was re-made under the fixed normaliser; the stale one
is deleted, per the rule that a findings directory is written once.

## The citator's first full chain, 2026-09-04 (dry run into a copy; production untouched)

`citator find` -> `load` -> `project`, the shipped code, against the `VACUUM INTO` copy with
migration 0016's benchmark figures declared as the measurements — which is what a real first
load does. Production's `citation` is still 0 rows.

    readings            20,062        (documents x machine channel; all text-layer today)
    findings            73,101        41,954 captions, 31,147 citations
    citation rows       73,101        one per finding; 219,303 judgements, 3 per finding
    extraction runs     20,062
    resolution          71,185 resolved, 1,915 unresolved, 1 REPAIRED (rule 2 fired once)
    exposed             1,946 held for review, excluded from the projection
    span test           13,928 true, 59,173 false
    PROJECTED           18,907 rows, and **15,164 distinct (citing work, target) edges**
                        over 5,294 citing works and 3,529 proceedings cited
    failures            0 failed, 0 unreadable, 0 out of class

**WHAT THIS DOES NOT DO IS VALIDATE THE PUBLISHED FIGURES**, and an earlier framing of this
work said it would. 94.7% projected / 97.7% precision are recall and precision against a
sixty-decision sheet with hand-made ground truth. There is no ground truth for 19,229
decisions, so a corpus run cannot compute either number: every one of those 15,164 edges is
stamped with a precision measured on sixty decisions, which is exactly the claim ADR 0017 D3
makes and exactly what a bigger run cannot check. What the run DOES establish is that the
shipped chain chews the whole record without a failure, what volume a load produces, and how
big the review backlog is on day one.

**The review backlog is the number to look at before a real load: 1,946 keys owed a human
review.** On the sixty-decision sheet the same gate held five. That is the difference between
the benchmark's 93.3%-to-a-reader and what a real load would show, and it is a question about
review capacity rather than about code.

**CORRECTION (2026-09-04, later the same day): the queue is NOT missing.** The load printed
those keys under "NOT YET QUEUED" and this note repeated it — that "the queue is in TODO's
owed-with-the-pipeline and does not exist, so those edges would be held with nothing to
release them". Both are wrong. Migration 0015 shipped `review_action` and
`review_queue_vocab`; `citator.review` derives the queues from these very rows; `/review`
renders them with the evidence beside the question (ADR 0016). Measured on the loaded copy:
`citation_exposed` 1,946 owed, `citation_unresolved` 489, `citation_repaired` 1 — each item
carrying its key, the raw as printed and the quoted passage. `citation_unresolved` is 489
rather than 1,915 because `review.in_the_held_record` declines to queue a number the record
was never going to hold, which is the design working. The verb's message and the comment
behind it were stale, and are fixed.

Left on the instance for whatever comes next, to be deleted otherwise:
`data/citator-dryrun.sqlite` (now ~4 GB, loaded) and `data/citator-findings` (84 MB).

## Owed before a real citator load, found by planning it, 2026-09-04

- ~~**There is no operator verb that declares a method or records a measurement.**~~ FIXED
  2026-09-04: `citator declare --scores` reads a card the scorer writes (the operator's choice
  of three shapes; `citator/scorecard.py` keeps the reasoning and what the other two cost).
  Original note: The shipped
  citator verbs are `find | load | cited-by | grant | revoke | review | decide`; production
  holds `class_measurement` 0 and `assertion_method` 0; and `citator load` refuses a batch it
  cannot stamp (`methods.Unscored`, ADR 0017 D3). So a real load cannot be performed with the
  shipped CLI at all — the rehearsal used a hand-written script, which is not a thing an
  operator should do, because it stamps a published precision onto every row a load writes.
  **The shape is Cameron's**: a verb that hardcodes migration 0016's figures makes the claim
  for him; one that takes them as arguments makes him state what is claimed and where it came
  from, which is what "every derived assertion carries provenance" points at and the more
  tedious command. `docs/runbook.md` § The citator's first load, Blocker 1.
- ~~**`reviewer` is 0 rows**~~ GRANTED 2026-09-04: reviewer 1, the operator, credited
  "Cameron Rex" — ADR 0016's reviewer zero. **The capacity question is what remains**: 1,946
  exposed keys is roughly sixteen hours of reading at thirty seconds each, against five on the
  sixty-decision sheet, and one reviewer holds the whole of it. Loading first is allowed
  because the edges are simply held, which is what the gate is for.

## Found by fixing decision_work, 2026-09-04

- **`Resolution.decision_id` is declared and never assigned**, so `citation.cited_decision_id`
  is written NULL on every row and the foreign key to `decision_work` cannot fire today. The
  registry's drift was therefore LATENT, not breaking — I said it would have failed the first
  real load, and that was wrong (stb-ingest-specialist, 2026-09-04). Populating it is part of
  ADR 0018's owed list, not of this fix; the invariant is worth holding either way, and now
  is when it is cheap.
- **The `globally_addressed` comment described a refusal the code does not make.** A second
  docket claiming a held record id is counted (`id_collisions`) and reported by the poller —
  and the second record is still written, because the row was observed. The comment read "an
  anomaly to report rather than a row to write", which a reader could take for a refusal.
  Corrected, with the ordering constraint named: if a refusal is ever wanted it belongs in
  `ingest_capture` before `_upsert_record`, never inside it, where the work-registry write
  would already have minted a row for a refused record.
- **The row-level `work_healed` counter has a named blind spot**: a drifted id first
  re-observed under a SECOND docket has no `record_pk` for that row, so it reads as an
  ordinary new decision and is repaired without being counted. Knowing better would cost a
  query per row; the pass-level reconciliation catches it and everything else, so the counter
  is per-capture attribution rather than the guarantee.

## Measured while planning forward text extraction, 2026-09-05 (against v2026.09.10)

Found by asking a question the pipeline had never been asked — *when does a new filing get
text?* — and answering it against the store rather than the plan. Nothing here is a
regression; all three are gaps that have always been open and were never counted.

- **The OCR wave routed whole DOCUMENTS, and 51,189 pages sit inside documents it therefore
  skipped.** Of 74,295 extracted documents, 14,961 are fully image-only (the wave's set),
  55,590 are fully texted, and **3,744 are MIXED** — a born-digital brief with scanned
  exhibits, the commonest shape there is. Those mixed documents hold **51,189 pages with no
  text layer** that were never routed to a reader and still display "not yet read". That is
  30% again on top of the 169,516 pages the `ppocr-primary` load landed the same day. THE
  RULE THIS FIXES IS THE QUEUE'S GRAIN: a page needs OCR, not a document, and the store is
  already page-grained (`document_text` is one row per page), so the queue is a query —
  pages whose live text-layer reading is empty and which have no live OCR reading. The wave
  tool selects per document (`ocr_wave.py`, `route`), and widening it is the fix.
- **26,438 environmental-comment attachments hold no text at all, and for 90% of them the
  PDF is the only record of what a person said.** Of the 26,332 comments owning one, 23,748
  carry only the `--` placeholder inline, 2,278 have 20-499 characters and 306 have 500+. So
  the inline `comment_text_printed` does NOT stand in for the attachment: it is a short note
  beside the letter, not the letter. Wave work — extraction then OCR on the enrichment box —
  and the largest single block of the record that search cannot reach. (Checked and NOT a
  gap: the 7,930 comments with no attachment at all, whose inline words are their whole
  record. Those already render on the sheet and the record page and are already indexed, and
  `sheet.present` strips `--` at every surface — display, MCP and the index. Putting them in
  `document_text` would need a synthetic document identity for a thing that is not a
  document, which is what ADR 0002 exists to refuse.)
- **The `--` placeholder rate had drifted from its measurement and two comments still quoted
  the old one.** `0011_enviro_comments.sql` and `search._comment_docs` both said "about half
  the rows"; re-measured 2026-09-05 it is 23,902 of 34,384, **69.5%** — the backfill added
  26,438 comments and moved it. Both corrected in place, with the date and the reason the old
  figure was right when written. Worth repeating because it caught me too: `--` is TRUTHY and
  is not NULL, so a test for emptiness reads an absence as content, and that is exactly the
  bug ultrareview found in `mcp.py` on 2026-08-31.

## From reviewing ADR 0024 as a change to the forward pass, 2026-09-05

The stb-ingest-specialist's pass over the draft. Two findings stand on their own, whatever
becomes of that record.

- **`forward_pass` records no duration, and nothing alarms on an overrun.** `run_forever`
  does `time.sleep(max(0.0, every - elapsed))` — a pass that takes longer than its interval
  sleeps zero and the next one starts immediately, with no measurement, no summary key and no
  problem raised. The only external signal is `alerts/build.py`'s `LATE_AFTER = 3 hours`, so
  a pass could run six times its interval unnoticed. Today's worst case is ~14-15 minutes of
  the 30 (captures ~120 s, captions ~25 s, `FETCH_LIMIT` 200 at the polite interval ~400 s,
  `RECHECK_BUDGET_SECONDS` 300, plus alerts, party resolution and the index). **Two published
  claims rest on the cadence**: `/coverage` says the Board's record search is asked "every
  thirty minutes", and `/methodology` computes `recheck_cycle_days` from `POLL_MINUTES = 30`.
  A pass that quietly takes 45 minutes makes both false, which is the drift `CLAUDE.md`
  forbids. A `duration` in the summary and a problem when it exceeds the interval is cheap
  and is owed whether or not ADR 0024 ships.
- **The errata re-check gives archive documents a forward `document_source` row, continuously.**
  `recheck_urls` selects held URLs across the whole record and `fetch_attachments` then loads
  EVERY attachment row for them (`unfetched_only=False`), including rows whose
  `document_sha256` is NULL — which take the `old_sha == sha256` path and gain a
  `document_source` row under the re-check's forward capture. So "forward" by document is a
  growing set that reaches the whole record about every six weeks. Not a defect: the re-check
  is doing its job, and ADR 0024 D1 takes the consequence deliberately. Recorded because any
  future count of "what the poller owns" that uses this join will be larger than a count of
  forward-observed records, and the two numbers will disagree for a reason nobody remembers.
