# Deferred findings

Review findings and known gaps recorded for later — accepted as not-now, never silently
dropped (`CLAUDE.md` § Review before commit). Each carries the date and the release it was
found against. `TODO.md` holds only near-term work and points here; an item leaves this file
when it is fixed (the commit is the record) or graduates back to `TODO.md` when chosen.

## Web tier

- **A comment's page hit counts `?file=N` in the copy it picks; the page reads the canonical
  copy's list** (schema-critic, 2026-09-11, against the comment-text change after
  v2026.09.13). `search._COMMENT_OF` orders a cross-posted comment's copies by date before
  sub-docket, and the text page 301s to the copy nearest the parent. Were the copies ever to
  differ in date or in their file lists, `N` could name another file there and the page would
  show a document other than the one that matched, silently. **Measured on production the
  same day: 108 cross-posted comments, none differing in date or file list, and no copy
  carrying a file the canonical copy lacks** — so nothing to fix yet. When one appears: pick
  the canonical copy inside the query (`NOT EXISTS` a nearer copy of the same number and row
  ref) and drop the hit when that copy does not carry the document. `_FILING_OF` and
  `_DECISION_OF` share the shape — `N` counted in the picked copy, the page rendering the one
  `_record_docket` picks — and the same re-measure answers for them.
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

- **`drain.sh` (instance-only) should stop on a pass that makes no progress** — all that is
  left of "an unanswered attempt leaves no capture", which landed on main 2026-09-11: a
  status-0 capture on every path, rested a day (with a host's repeated 429/5xx, kept as its
  answer), schema-critic confirming no new grain.
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

## The instance resize (2026-09-02, v2026.09.1)

**ADR 0022 D7 now resizes it with the OCR migration** rather than leaving a trigger to watch:
the store crosses ~1 GB on rows alone under D6. What stays here is the operational half.

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

## Observed at Migration A's first load, 2026-09-04 (v2026.09.2 on the resized box)

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

- **From TODO, 2026-09-04 (the cap):** Cameron's idea of a cadence switch from the alert
  email and a signed-link manage page per address.

## From the critic pass on the drafted ADR 0012 addendum, 2026-09-04 (against v2026.09.8)

The addendum was withdrawn rather than accepted (see below), but the pass was reading the
blob tier's code to check the draft's claims and found things the draft was not about. Each
was verified against the file named before it was written down.

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

- **The finder's class can name 31,972 of 32,627 held dockets; 655 dockets across 13
  prefixes can never be cited to at all** (S5M 240, MC 178, EPM 164, CU 16, FSA 14, MXC 13,
  SAI 11, PTO 6, RR 6, AM 3, WC 2, CNO 1, S5R 1), and two prefixes IN the class, `FSB` and
  `PCA`, match nothing the record holds. 2.0% of the record outside the citator's reach, a
  ceiling on recall no sixty-decision sheet could show. Not a defect — a scope never
  measured, and the number to quote if the class (`citator/keys.py`) is ever widened.
  Re-checked 2026-09-10: the class list is unchanged.

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
  and the largest single block of the record that search cannot reach. **Extraction ran
  2026-09-11** on RMI-AI-MACHINE at the pin (pymupdf 1.26.0): 25,583 read, 0 failed, **12,184
  image-only** — those are the OCR half still owed. Loaded into production after v2026.09.14
  the same day (180 s): 25,612 comment files hold text, 15,137 with a non-empty page, shown at
  the comment's text page (the operator's decision: as a filing's text is). (Checked and NOT a
  gap: the 7,930 comments with no attachment at all, whose inline words are their whole
  record. Those already render on the sheet and the record page and are already indexed, and
  `sheet.present` strips `--` at every surface — display, MCP and the index. Putting them in
  `document_text` would need a synthetic document identity for a thing that is not a
  document, which is what ADR 0002 exists to refuse.)

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

## From the schema critic on migration 0022, 2026-09-05 (against v2026.09.10)

Two findings the operator left for ADR 0024's next revision rather than for the migration.
Both are the ADR's text, not the table's shape.

- **A refusal under D3's size cap has to fabricate an `ocr_run` row.** The only thing that
  takes a >64 MB document out of the queue permanently is an `ocr_run` row on the text-layer
  reading key, and `ocr_run` requires NOT NULL `method`, `method_version`, `reading_channel`
  and `render_profile` — so a refusal that never opened the file must claim a channel it
  never read on, a render it never produced and a tool version that never ran, in a PUBLIC
  table, under D8's own "Nothing here reads a PDF to make a claim". The alternative is to let
  it burn its attempts, which makes a known-permanent refusal indistinguishable from a pass
  that kept dying. `run_outcome_vocab` is a table precisely so it can be widened by INSERT —
  a `'refused'` outcome is cheap; the four NOT NULLs are migration 0018's and are the harder
  half. This is ADR 0024 § Owed item 2's real content.
- **`first_seen_at` is when the bytes were FETCHED, not when the record was made**
  (`capture/documents.py`), so D3's "a decision served this morning is read this pass" is not
  delivered while a backfill wave runs: every archive document the wave fetches lands at the
  front of the newest-first walk, and D1 admits them because the erratum re-check mints a
  forward `document_source` row for every held URL. Not measured — conjecture from the
  ordering column. Ordering by the record's own date (`decision_record.service_date` /
  `filing.filed_date`) would deliver the promise and is an ADR change, not an index change.

## From the code review of the work-level resolution step, 2026-09-05

- **A bare parent printed on the same line as its own sub-docket takes the child's segment.**
  `resolve._anchored` finds the target by its printed form, and `FD 36873` matches inside
  `FD 36873 (Sub-No. 1)`, so the parent can be credited with the document that followed the
  child. Same family, so the cost is small; the real fix is a finder that reports each
  occurrence's offset, which is a `find.py` change and a re-measurement.
- **`served on <date>` is not read, deliberately.** 0.96% of pages against the matched form's
  5.43% (200,000 production pages, 2026-09-05). Admitting it would break the containment that
  makes ADR 0018 D4's "the text names a document" true by construction — `judge`'s span
  pattern does not match it either, so those edges are suppressed at projection anyway.
  Closing the gap is a `SPAN_VERSION` bump and a re-measurement of every edge stamped by the
  old one, never a widening of `resolve.SERVED` alone.
- **`decided <date>` still stays at docket level**, per ADR 0018 D4 — but the assertion it
  waited for now exists (`decision_decided_date`, migration 0019, ADR 0023). Building that
  consumer is a decision; ADR 0023's pick rule is decided (compare values, publish only when
  every live reading agrees) and nothing consumes it yet. 259 of 200,000 pages print the
  phrase, so the yield is small.

## From the second schema-critic pass and the ingest specialist on migration 0022, 2026-09-05

Findings that belong to the ADR or to the poller rather than to the DDL. The seven ADR
amendments are listed in the migration's own header; these are the rest.

- **The loader must never delete a spool file from inside `one()`.** `batches.run` returns
  aggregate counters, so a loader built on it cannot know WHICH files landed, and deleting
  inside the `SAVEPOINT` means an `aborted` batch loses the rows and the raw together — trap
  9 broken and ADR 0024 D9's own rule broken in one event. Sweep the spool after `run`
  returns and delete `<sha>.json` only where an `ocr_run` row now exists for that sha at the
  file's own reading key.
- **`run_forever` has no watchdog**, so a hung `subprocess.run` stops the poller for ever
  with nothing raised. `EXTRACT_BUDGET_SECONDS` bounds when the stage stops STARTING work, not
  how long one invocation may hang: the call needs `timeout=` and a kill.
- **The pin disagreement is never diagnosed.** The loader holds both the dispatch's
  `pinned_method_version` and the spool record's `tool_version` (D9 carries it), so "the file
  disagrees with the dispatch" is one query and turns a header comment into a control.
- **`.tmp` files left in the spool are never counted**, so "the container is dying mid-write"
  reads exactly like "the container never started".
- **The extraction service needs `cpus:` and `mem_limit`.** Two vCPU; `web`'s healthcheck
  timeout was already raised to 30 s so a bulk load could not become a restart loop, and this
  adds CPU-bound work to every pass right after the heaviest write. Three misses trips
  `docketyard-webwatch.timer`, which restarts `web`, which adds load. The pass measures no
  duration and nothing alarms on overrun (already recorded above).
- **`extraction_dispatch` carries no `ingest_mode`** — ADR 0024 § Owed 5's gap, same as
  `ocr_run`'s. Not urgent: `ADD COLUMN` survives publication, and the primary key is the only
  rebuild-class change the critic's widening survey could find.

  - `NOR 42142, Consumers Energy Company v. CSX Transportation, Inc., served January 11, 2018`
    — `v. C` is a case name, and the cut lands there
  - `FD 35348, Dec. No. 6, slip op. at 7 (STB served Oct. 22, 2010)` — `Dec. No.` cuts
  - `FD 34502, slip op. STB served Dec. 29, 2005` and `slip op. At 14 (served Feb. 19, 2026)`
    — `op. STB` and OCR's capitalised `op. At` both cut
  - `EP 542 (Sub-No. 25), slip op. app. C at 20 (STB served July 28, 2017)` — `app. C` cuts

  Against maybe three genuine donations (`AB-307 (Sub-No. 5X). By decision served November 10,
  2004`). The claim in an earlier note that the pattern "does not fire on `slip op. at 2`" was
  true only of the lowercase form, and the Board prints `Dec. No.`, `v.` and `S.T.B.`
  constantly. **Do not re-propose a sentence bound without an abbreviation list**; the real fix
  remains a finder that reports each occurrence's offset. Third member of the family with the
  parent/sub-docket overlap and `served on`.

## From reviewing migration 0023 and the work-grain step, 2026-09-05

- **`resolve._anchored` ends a segment only at another DOCKET-SHAPED number.** A non-docket
  intervening target still donates its date: `"See FD 36873; see also Decision No. 5 (STB
  served Mar. 12, 2021)."` hands FD 36873 a date the page attributed to Decision No. 5. Same
  class as the parent/sub-docket overlap and the trailing clause — and like them it moves
  membership of the 16,051, so it is a measurement and the operator's call. The sentence-bound
  attempt above is the warning: the obvious pattern was worse than the defect. `keys.DOCKET`
  also carries no `re.I`, which is deliberate elsewhere but worth confirming here.
- **`ocr_run` publishes a judgement about the bytes with no provenance.** After migration 0023
  it says `not-paginable`, which is what `document_pagination` asserts WITH ADR 0007's whole
  block — confidence, state, supersession, a human-protection trigger, a `review_target_vocab`
  row. Two public tables now answer the same question and only one of them is an assertion.
  The migration names `document_pagination` as the assertion of record and a test pins that
  they never disagree, but `ocr_run` still has no correction path: a `review_target_vocab` row
  for it (`surrogate`, on `document_pagination`'s precedent) would give one, since `run_id` is
  followable for the same reasons `pagination_id` is.

## From the fleet gate's fix, 2026-09-11 (v2026.09.13)

- **`queue_server.py` answers 401 to a POST without reading its body**, and on Windows the
  client can then see `ConnectionAbortedError` (the peer reset before the response is read)
  instead of the 401. `test_the_transport_refuses_a_bad_token` failed once that way in six
  runs, right after a new test that also sends refused requests; it predates the gate fix.
  The fix: drain `Content-Length` (bounded) before replying 401 in `do_POST`.
- **RMI-AI-MACHINE's worker loop relaunches a worker a minute after it exits "queue empty"**,
  the churn the workstation gate no longer does. Cheap there — its vLLM is always up by design
  — but the same `GET /pending` check would quiet it.

## From the schema critic on the finder's line wrap, 2026-09-11 (branch `finder-line-wrap`)

Fixed on the branch: stamps refused unless measured on the findings' own finder version (D1);
a retraction points at its successor sub-docket row where there is exactly one (D2); only
pages the pass read are retracted, `pages_walked` in the interchange (D3); a stale reading on
another channel no longer holds a key (D4); an old finder's batch refused before it can take
the new rank (D5); an open review action holds a key (D7, part); `restamp.stale` and
`unstamped_work_rows` read live keys only (D8, part). Deferred:

- **Which ranking was in force on a date is undated** (D6; ADR 0018's one accepted deferral).
  There were two from 2026-09-11 (v1, then v2 for the new finder's owner row) and nothing
  records which the deployed code bound. No reader has seen an edge, so nothing unrecoverable
  is lost yet — **it must be recorded before any page renders the citator**: an additive
  `projection_rule` table (rank_version, in force from, release) was the critic's shape.
  `PROJECTION_RULE` also reads `rank=v2` though v2 differs from v1 only in the owner row.
- **A self-pointing retraction is undated and reasonless** (D2, residue). Where no single
  successor exists the row points at itself with no `superseded_at` — the citator's families
  carry none (2026-09-01) — and an interrupted supersession looks the same. A nullable
  `superseded_at` is an ALTER, not a rebuild; a `correction` row per retraction would move the
  search signature and the ETag (`MAX(correction_id)`), so it is not the vehicle.
- **A key a person holds is neither stored nor queued** (D7, residue). `retraction_held` is
  printed, never stored, and nothing puts the parent key a reviewer answered in front of a
  person when the sub-docket appears beside it; the parent keeps projecting beside the new key.
  A queue predicate over "live citation at a non-owner version with a human row" is the shape.
- **The retraction counts are printed, not stored** in `extraction_run` (D9).
- **Readers without the live-`citation` join, harmless today** (D8, residue): the `cited_by`
  work gate (a retracted row can open it; `CITED_BY_WORK` filters each row) and
  `tools/rmi-ai-machine/work_check_sheet.py` (drafts claims on retracted keys if pointed at a
  store that holds retractions).
- **`restamp` does not reach `citation_judgement`** (D11): an unchanged span `true` keeps its
  pointer at the older projection measurement after a new card.
- **Between deploy and the first v2 declaration the projection is empty and exits 0** (D10) —
  the runbook's order covers it while nothing renders the citator.

And from the stb-ingest-specialist on the same branch (its items 1, 2, 4, 10 and 11 were the
critic's D1, D3, D4, D8 and D7, fixed; 3, 5, 9 and 12 fixed or in the runbook):

- **A two-column table row can graft a sub-number onto the wrong docket** (item 7): `FD 35087
  FD 36873 ↵ (Sub-No. 8) (Sub-No. 1)` keys the right-hand docket `FD 36873 (8)`. Not seen in
  the sixty decisions; a layout-aware reading is the real fix.
- **A differently-named extractor taking over the class retracts nothing of its predecessor's**
  (item 8): the retraction scopes on `method = ?`. Until a second extractor exists it cannot
  arise.
- **A page line ending in `|` joins as ` | `** (item 13), the separator `resolve._anchored`
  splits on — it only shortens the window (dates lost, never misattributed).

## From restoring the text stage's pruned blobs, 2026-09-11 (v2026.09.13)

- **The stage never reads a pruned blob, and nothing restores one.** The parser has no
  network and no store key (ADR 0024 D2), so a document queued after the pruner took its
  blob (30 days, or under 20 GB free) is never dispatched: 21 sat that way every pass from
  10:18 UTC until they were fetched from S3 by hand at the operator's request; the 12:48 pass
  dispatched them and the 13:18 pass loaded all 22 due, none refused. The guard: before
  dispatch, the ingest side — which holds the store key — restores a due document's blob from
  S3 and checks its hash, as the `/document/` route already does for a reader. The container's
  isolation is untouched because the fetch happens outside it. Until then the problems line
  counts them every pass.

## From a high code review of v2026.09.12 itself, 2026-09-11

Run against the released range by mistake (the unreleased range was reviewed after it); what
it found is in the released code and is recorded here rather than dropped.

- **An `extract` outage longer than the admit window strands documents at the pin.**
  Requests wait in `data/extract/requests` while the container is down and are answered when
  it returns; a document dispatched at T, T+6 h and T+12 h whose readings arrive at T+40 h has
  every reading quarantined ("no dispatch precedes it") and every attempt spent. The halt
  bounds how many (one canary a pass), and the designed reset is the pin bump. A fix would
  let the container drop a request older than the window unread, or count an attempt only
  once its reading is refused rather than when it is handed over. The loader-clock floor
  added 2026-09-11 adds the poller's own outage to this, and that case heals: the stale
  records are quarantined and their documents, with attempts left, are asked for again.
- **`citator declare` tells the operator the wrong thing** (`cli.py` ~420, and
  `project.unstamped_work_rows`'s docstring): "nothing re-stamps an unchanged answer", in the
  release that ships `citator restamp --apply`, which does.

## From the no-answer fetch's reviews, 2026-09-11 (v2026.09.12)

stb-ingest-specialist and schema-critic on the status-0 change; what was fixed is in the
commit. Left:

- **Were truncated documents minted? Measured 2026-09-11 00:40 UTC: no sign of it.**
  `download` streamed through `shutil.copyfileobj` from v2026.08.25 (2026-08-26 17:36 UTC)
  until 2026-09-11, and a body cut short of its Content-Length read as a clean end
  (reproduced on CPython 3.13). Of the 92,322 PDFs first seen since, the 82,946 still on the
  instance ALL carry `%%EOF` in their last kilobyte, and the record holds no
  `document_replaced` event at all. The other 9,376 are pruned to S3 and unchecked; the
  fleet's blob mirror could close that, if certainty is ever wanted.
- **`_LAST_FETCH` counts an unanswered attempt as a check**, so `/methodology`'s "checked
  about every N days" is an attempt, not a check, while the host is silent. Wording or a
  filter; the re-check has done this on purpose since v2026.08.35.
- **A verdict crash window**: `save_capture` commits before `_record_attempt`'s verdict
  update, so a kill between them leaves an unjudged row. The success path shares it.
- **A CLI `fetch attachments` over a wave's backlog with the default `--mode forward`**
  stamps its captures `forward`, which pulls those documents into the text stage's scope
  (`text/queue.py` D1). Predates the stage; `drain.sh` passes `--mode backfill`.
- **A truncated error body** raised inside `consume(e)` escapes the retry (it is raised from
  within the `HTTPError` handler) and leaves no capture. Rare; noted.

## From the schema critic on ADR 0024 Owed 5, the dispatch stamp, 2026-09-11 (v2026.09.12)

The operator chose `ocr_run.dispatch_id`, echoed (ADR 0024 addendum 2026-09-11). Left for later:

- **A single-column REFERENCES cannot enforce "a dispatch of THIS document".** The admit step
  checks it; a BEFORE INSERT trigger (same document, `dispatched_at <= ran_at`) would make
  the store check it too, and names only public tables. It would NOT catch a reused id:
  `dispatch_id` has no AUTOINCREMENT, so a keys-off DELETE of the newest cited dispatch lets
  the next one take its integer and an existing reading silently names another document's
  dispatch. AUTOINCREMENT needs a rebuild of a published table; 0026's header says do not
  delete dispatches. Both, or neither, deliberately.
- **Nothing proves the published `schema.sql` parses** for a third party: the tests check it
  by regex. Loading it into a fresh database is the test; 0026 spliced a column into
  `ocr_run`'s stored DDL.
- **The spool file name loses answers**: `extract.py` writes `<sha>.json`, so two requests
  for one document served back to back (after an outage) keep only the second record, and
  the first dispatch publishes as unanswered — true of the store, but a lost answer.
- **`correction.target_key = 'dispatch_id'` names a column, not a row**, as 0022's
  `'excerpt'` did before it; migration 0014's convention is a row's natural key.
- **Admit and the loader can parse different heads**: a record whose first 4 KB carry
  `"reading_role": null` passes admit's shape test while the loader parses it whole, so a
  duplicate key after `page_text` changes what the loader sees. Not exploitable — the stamp
  re-runs the same rule on the loader's own header, so it names this document's dispatch or
  refuses — but admit's one rule is then two reads (security review, 2026-09-11).
- **`document_pagination` has the same blindness about its producer.** Not on the halt path.
- **Which off-instance machine loaded a root** stays unrecorded on `ocr_run`;
  `producer_declaration.declared_by` and the pass key (ADR 0025 D2) carry what is needed, and
  `text load` declaring from the root's `_manifest.json` (below) is still the open step.

## From the schema critic on migration 0024, the producer registry, 2026-09-05

- **Nothing declares a pin, so ADR 0024 D6 is inert while the record reads as though it is on.**
  `pinned()` returning None means both "deliberately unpinned" and "nobody got round to it", at
  every read site and in the CC0 snapshot, where an empty table and a considered decision are
  the same bytes. The fix belongs with the poller stage, and it is **the first thing that stage
  owes**: the registry becomes the SOURCE of the dispatch row's pin, and the stage refuses to
  dispatch — loudly, into `problems` — when there is none. That gives D6 the coupling it wants
  without the foreign key it forbids. Secondarily, `load.run` could say once per pass that it
  loaded at an undeclared key.
- **A pin refusal is recorded nowhere.** `load_reading` raises before the `ocr_run` INSERT, so
  the store holds no evidence a reading arrived and was turned away — ADR 0018 D10's "absence
  is not a measurement" and ADR 0024 D5's "a refusal is recorded as a run" both crossed by the
  guard D6 asked for. Nothing is LOST (D9 deletes a spool file only on a landed outcome), but
  the record of the refusal is a log line and a count. The honest cheap version is a `problems`
  row per pass; the full version waits on § Owed 2, since an `ocr_run` row would have to claim
  a method and version that never ran.
- **A wave-wide version mismatch arrives as N document failures.** `Unreadable` is counted per
  document by `batches`, each with its own savepoint, rollback and log line, and the pass walks
  the whole root before saying anything — where an operator-level condition ("this root is at
  the wrong version") wants to stop, the way migration 0023's halt-is-a-query does. A distinct
  exception counted apart by `batches._apply` would do it. Also semantically: `Unreadable` is
  documented as what the STORE shows to be wrong with the READING, and a pin mismatch is wrong
  with the configuration.

## From the release review of v2026.09.10..HEAD, 2026-09-10 (against v2026.09.11, before tagging)

- **`producer_declaration`'s live predicate is `retired_at IS NULL`**, not the store's
  `superseded_by IS NULL`, deliberately (the migration's header says why: an un-pin must be
  distinguishable from a crash). Cost: `store/supersede.py` does not serve it and
  `text/load.py` carries its own retire-and-append. Any reader walking the table must use its
  predicate. If a second pinned table appears, lift the idiom into `supersede.py` with a
  `retire_col` parameter rather than copy the loader's.
- **The fleet's pass key and the store's pin are two registries for one fact.**
  `tools/fleet/pagequeue.PASSES` (which is `ocr_wave.DOTS`) and `producer_declaration` share
  nothing but a convention; `_manifest.json` carries the key and `text load` never declares
  or checks a pin from it. When the poller stage lands, `text load` should read the root's
  manifest and `declare_producer(by=manifest)` before loading, so the two are one declaration.
- **Failure ownership in the queue is a string prefix** (`page:`, `server:`, `blob:`,
  `lease`, `operator:`), enforced at `fail(final=True)` and read by `LIKE 'page:%'`. A column
  `owner TEXT CHECK (owner IN (...))` on `job` is the stronger form; the live queue would
  need a one-off migration, and the workers on both machines updated together.
- **`CPUQuota=50%` on the user slice bounds one of the outage's two contributors**; the blobs
  timer in `system.slice` is unbounded and `web` has no reservation. `CPUWeight` shares (the
  service high, the timers and the user slice low) would resolve contention in the service's
  favour whatever the source, and leave ad-hoc work unthrottled on an idle box. Infra design;
  the operator's call.
- **Queue-side costs, real but small**: `seed_pass` asks the queue per document (three point
  queries each, ~40k documents; tens of seconds); the worker opens the PDF once per page
  rather than once per document; the lease is extended after every page where every fourth
  would do. None moves the pass's clock, which is the engine's.
- **`resolve.MONTHS`/`served_date` and `web/cite.py`'s `_MONTHS`/`parse_date`** are two
  month tables and two date parsers that already differ at the edges (`cite` takes `m/d/Y`
  and ISO; `resolve` takes full names). One shared module under `docketyard/text/` would do;
  the resolver's table was measured over 200,000 pages and is the one to keep.
- **`review._raw_docket` is the sixth hand-written `SELECT raw_docket FROM docket`**; an
  accessor beside `dockets.canonical_of` would give every surface the same label and fallback.
- **`db.migrate` runs `PRAGMA foreign_key_check` over the whole store after every script**:
  280 s each on the 4.28 GB production copy (measured 2026-09-10), so a three-migration
  release costs fifteen minutes behind the wall for checks that a table-creating script
  cannot fail. `PRAGMA foreign_key_check(<table>)` over the tables the script names — or
  every table whose DDL the script touched, read from `sqlite_master` before and after —
  would keep the guarantee at seconds. Not urgent: the window is behind the wall.

## From the schema critic on migration 0025, the work class, 2026-09-10

The critic found eleven items against the change that lets a work-level answer be scored.
Six were fixed before the commit (the missing transaction, the header's false claim about
`CITED_BY_WORK`, the unfiltered work query, the unchecked work stamp in the loader's guard,
the dry run's stamp assertion, and the class missing from every published count). These are
what was accepted as not-now, and one is a question for the operator.

- **Nothing re-stamps a row whose class should have changed, and there is no verb that
  would.** `supersede.if_changed` compares `(outcome, cited_docket_id, cited_decision_id)`,
  so a measurement declared after a load never reaches the rows that preceded it: they keep
  the class they were stamped with for ever. ADR 0017 § Consequences promises "re-measurement
  is a scorer run, not a migration", and today the only path from a re-scored class to its
  rows is hand-written SQL over every one — the migration-touching-every-row shape the five
  queries exist to catch. The work class makes it two classes needing it independently, on
  different cadences (the scorer's run against the operator's judging sitting). **What
  shipped instead is the number**: `project.unstamped_work_rows` counts live rows naming a
  document that are not work-stamped, and `citator declare` prints it, so the ordering is
  visible when it is broken rather than silent. **And `citator restamp` was built the same
  day** (the operator's decision): it retires a live row and appends an identical assertion
  under the newest measurement of the class the row's own shape calls for, so 0017's promise
  is true rather than aspirational, and what a reader saw before the re-stamp stays in the
  table. This item is closed; it is kept here because the reasoning is what the verb is for.
- **A reviewer's `accepted` carries a work-level claim they were never shown.**
  `review.pending` shows the docket, the printed target and the passage — never the drafted
  document — and `decide` carries the machine row's `cited_decision_id` onto the human row at
  confidence 1.0. Publishing that as a work-level edge would assert, at the record's highest
  confidence, a claim the reviewer did not make: the house rule against inferring a position
  from an adjacent decision, applied to reviewers. **Closed for now by publication**:
  `CITED_BY_WORK` requires a work-class measurement and a human row is stamped from none, so
  those rows are stored and shown nowhere. Before a human work-level edge may publish, the
  queue must show the reviewer the drafted document and take a second verdict on it, or
  work-level claims need a queue of their own.
- **A row now says which class stamped it** (migration 0025, the operator's decision):
  `citation_resolution.measured_class`, foreign-keyed with `score_row_id` and
  `measured_target` to `class_measurement`'s triple, so the store refuses a docket-only row
  carrying the work figure and the reverse — which the pair key could not, since both classes
  of a resolution measurement satisfied it identically. Taken as a rebuild while every
  citator table held zero rows; after the first load it is a rebuild of the largest table in
  the citator. What remains deferred is the same shape one table over: `citation_judgement`
  and `citation_treatment` still carry the pair, and each carries one class today.
- **`class_measurement.resolution_method_version` says `rule-1` for a sheet that includes
  rule-2 repairs.** `methods.measure` writes it for every non-`citation` target, so the work
  measurement — and the docket resolution measurement before it, which has carried this since
  2026-09-04 — names one rule where the judged population holds two (`resolve.py`: "A REPAIR
  REACHES THE WORK TOO"). Pre-existing and inherited rather than introduced. Fixing it is a
  provenance decision about what one column may say, not an edit.
- **A class change is ordered but not dated.** The citator families carry no `superseded_at`
  (`store/supersede.py`, deferred 2026-09-01), so "what confidence did a reader see on date
  T" reconstructs for a row's own history but not across a re-stamp. That deferral now has a
  second customer.

## From the operator's judging of the work-level sheet, 2026-09-10

He judged all 106 drafted claims and 23 of the 105 docket-level stops. **106 of 106 name the
document the citation names**; the one he first marked wrong (51532 citing NOR 42144 at 50117)
he corrected the same day — it is a reference to a prior decision in the same proceeding,
which the benchmark's own conventions call a real edge. `data/work-verdicts-2026-09-10.tsv`
is the sheet; `data/work-block-2026-09-10.json` is the card block it produces.

**No recall was emitted, and that is the rule working.** 82 stops are unjudged, so a truth
count over what was judged is a lower bound and a recall from a lower bound is an upper bound
published as a measurement. `class_measurement.recall` takes NULL.

What his 23 judged stops found, kept because each names a cause rather than a count:

- **A served date whose year wraps to the next line is unreachable** — four instances, each
  named by him. The finder quotes ONE line, so the date never reaches `resolve.SERVED`.
  **Chosen as a Ripe candidate on `ROADMAP.md`, 2026-09-10**, priced there: a `SPAN_VERSION`
  bump and a re-measurement of every edge stamped by the old one.
- **A citation whose date is printed only at its first mention** (52295 citing FD 35873). The
  span test is disjunctive over the whole citing work (ADR 0017 D4); the resolver's date
  anchor is per page and per occurrence. The asymmetry is deliberate and now has an instance:
  the edge is not lost, because the fold at projection publishes the pair once from the page
  that carried the date.
- **The Board itself prints `served` against a decided date** (51532 citing NOR 42060 (1);
  the record's service date is 2007-01-26). The rule read the page correctly and the page was
  wrong. Nothing to fix, and a reason the work grain will never be perfect on the corpus.
- **A day holding two decisions where one is a correction of the other** (52280 citing FD
  34901: 37219 and 37282, and he reads 37282 as the answer). ADR 0018 D4 declines to
  arbitrate a day holding two, which is why this stays at docket level. Preferring a
  correction would be a D4 refinement and therefore an ADR, not an edit.
- **Five of his sixteen corrections are a second page of a pair that already resolved.** The
  fold at projection publishes an edge once, so those cost nothing; only eleven are edges the
  rule does not reach at all.

## From the code review of the review harness, 2026-09-11 (`benchmark_review.py`, v2026.09.15)

Seven of the eight findings were fixed in the commit that first tracked the file; the numbers
in `extraction-benchmark.md` were re-scored against the fixed scorer and are unchanged. One is
deferred, because acting on it means discarding twelve runs:

- **The snippet is cut around the mention's FIRST occurrence, while the class, the served date
  and the offered decisions come from every occurrence** (`benchmark_review.py:191`,
  `locate()` returns the first match only). 155 of the 768 mentions appear more than once on
  their page, so for a fifth of the measurement the model reads one passage and is asked about
  the evidence of another — it can be offered a decision whose date is printed somewhere it
  cannot see, and `find.py` already warns that the first occurrence biases toward
  "proceeding". **Not fixed, because the fix invalidates every run**: all twelve were asked
  the same way, so the comparison between models and between machines is sound, and the
  conclusion (no model reaches the rules' 99.6% recall) has a 25-point margin that a snippet
  change cannot close. Fix it before any *new* run is scored beside the old ones, and re-run
  the lot rather than mixing the two prompts.

- **Two runs' recall is a floor, not a measurement, and they stay that way.** 59 of
  gemma3:4b@jetson's 768 mentions and 13 of qwen3:4b@jetson's never reached the model (Ollama
  returned HTTP 500 as the model process restarted under the Orin's memory pressure, the same
  fault the section already records). Re-running cannot change a conclusion: if every errored
  mention had been answered perfectly, gemma3:4b tops out at 76.9% recall and qwen3:4b at
  34.7%, against the rules' 99.6%. The scorer now prints the floor beside the figure, and the
  resume no longer skips a decision whose answers failed.

- **Two of the work sheet's `should-be` verdicts name their id in prose**, so
  `should-be:References (\d+)` misses them and both pairs leave the truth set: 51532 NOR 42060
  (1) `(see 36657)` and 52211 FD 36732 `(51953)`. The scorer now prints them by name instead
  of counting them. **The sheet is the operator's judged work, so normalising the two rows is
  his**, not a scorer change; until then the document column is scored over 147 documents
  rather than 149.

## The workstation's gate does not survive a reboot, 2026-09-11 (v2026.09.15)

**Found by its cost, not by a review.** The operator restarted RMI-WS-CRR-2025 during the
morning of 2026-09-11. The gate had last logged `HOLD: the node has nothing to lease` at
07:17:44 — true then, the `dots` queue was empty — and died with the reboot. The comment
scans were seeded into that queue eight hours later, at about 15:55 local, and nothing on the
workstation was left to notice: its six workers had read two-thirds of the pass's pages, and
the fleet ran on RMI-AI-MACHINE's single worker at 310 pages an hour instead of about 1,400.
The gap was invisible for eleven hours because a dead gate looks exactly like a held one from
the node: no worker, no alarm, `last seen` simply ageing.

- **Register the gate as the ONLOGON scheduled task its own header already documents**
  (`workstation-gate.ps1`, the `schtasks /Create /TN "Docket Yard fleet gate"` line). It is
  written down and was never run; nothing else is needed. Offered to the operator 2026-09-11
  and deferred by him to a later sitting.
- **The monitor cannot tell a gate that is holding from a gate that is gone.** A node that
  once read and now does not is worth a line on the page — the fleet has a stall alarm for a
  pass, and none for a machine that has stopped asking. This is the same want as the
  `systemd --user` note below: the fleet's own liveness, not the queue's.

## From the code review of the queue panel, 2026-09-11 (`review_queue_panel.py`, v2026.09.15)

All seven findings were fixed before the run that matters was started; the first was caught
with the run already in flight and cost a restart. Recorded because two of them are the same
mistake the benchmark harness made, in a file written an hour after that one was fixed:

- **The served date was anchored on the normalised key rather than the number as the page
  printed it.** `resolve._anchored` takes the raw form, which `resolve.resolve` and
  `benchmark_review` both pass. Measured over the real queue: **43 of 1,476 exposed items**
  lost their date, so their offered decision list collapsed to `"none"` and they could never
  have cleared — a floor on the clearing rate, reported as a rate. Every hyphenated printing
  (`AB-564`, `AB-12`) was affected. The two runs made before the fix are set aside in
  `data/` as `.superseded-served-date-bug` rather than deleted.
- **A page whose live reading is `human` was shown to the panel**, though `walk.documents`
  narrows `_PAGES` to the machine channels and the finder therefore never read it. Copying a
  query without copying the filter that follows it is the trap; `pages_of` now takes the
  channel set.
- **`decision_attachment` is not unique by document**, so keeping one arbitrary carrier named
  a decision whose own dockets are not the union the finder used. `walk.own_by_document` is
  the shipped answer and is now called rather than re-derived.
- Three guards the benchmark scorer already had were absent here: a division by zero on an
  empty run, two runs collapsing on a shared basename, and a "panel" of one agreeing with
  itself. **A sibling tool is not a review** — the guards have to be carried over deliberately.
- The keys the panel would clear were computed and thrown away. They are now written out with
  `--clears`, because a clearing rule cannot be accepted on a rate: a slice of those keys is
  what gives it a measured precision (ADR 0017 D3).

## Deadline engine (C4), graduated from TODO 2026-09-11

Not started, and not blocked on anything but a decision. The STB's decision JSON carries no
obligations (measured 2026-08-26), so every deadline would have to be read from the decision's
own words — which is the one thing `CLAUDE.md` says is never inferred. A hand-checked fixture
of 8 deadlines for FD 36873 exists in `../up-ns-merger-tracker/briefs/2026-08-25.md`
(read-only, do not modify that project) and is what a first measurement would score against.
