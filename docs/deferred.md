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
