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
  (116 WB dockets), and it should be decided rather than slipped in. Its second effect was
  that the own-docket rule inverted, `own` holding `WB 25 (33)` while the finding keyed
  `WB 25`. Since finder 2026-09-12 `own` is the family, so `WB 25` is the parent and its caption
  reads as a caption again; the KEY defect above is what stands.
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
  Nothing reads `kind`, so no edge moves; the chain still grows. **Widened by finder
  2026-09-12** (ingest specialist, 2026-09-13, finding 6): `own` unions the FAMILIES of every
  carrier, while the projection's family is per work, so a citation to carrier B's parent or
  sub-docket with no document word near it now reads as a caption for work A too, where it is
  not family and used to project. Same five documents; unmeasured.
- **The card's `own` is per decision; production's is per document** (Codex review on PR #27,
  2026-09-13, deferred by the operator). `citation_dryrun.own_dockets` builds one family per
  decision id, while `walk._DOCUMENTS` unions the families of every decision carrying the
  bytes, and the dry run skips a repeated hash, so for a multi-carrier attachment the first
  decision's rule would be measured. MEASURED: 0 of the sixty benchmark decisions' documents is
  carried by more than one decision in `data/prod-copy.sqlite` (and 0 registry-wide there), so
  the 2026-09-12 card is exactly production's rule. The fix, when a benchmark document has two
  carriers: build `own` per document from all carriers, with a multi-carrier parity test.
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
  36873`) carried no prefix token at all and normalised to None (it keys since
  `norm-docket@2026-09-13`, below). Re-measured against the store 2026-09-04 (the
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
  mail and on `/cite`, so it is **Cameron's**, not a code fix. Related, and taken up
  2026-09-13 by the operator's decision: whether `keys.DOCKET` should learn the Board's long
  names the way `urls.lookup` has (`_LONG_FORMS`) — branch `finder-long-forms` (`keys.
  LONG_DOCKET`, `KEY_VERSION` norm-docket@2026-09-13, finder 2026-09-13, rank v4, a new card).
  Whether that widening wants an ADR 0017 addendum was put to him with it.

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

## A human citation reading copies the machine's printed string and passage, 2026-09-12 (v2026.09.15)

**Schema-critic, 2026-09-12, reviewing ADR 0026.** That record's D4 says attributing a
machine's character offsets to a person as their own reading is the same class of error as
inferring a party's position from who filed a document — and the shipped code already makes the
weaker form of that copy. `review._human_reading` takes `item["cited_raw"]` and
`item["quoted_passage"]` straight off the machine reading it is answering (`review.py:90`,
`492-493`) and writes them on a row whose `confidence_state` is `human`.

It is defensible as it stands: a reviewer answering a queue item IS looking at that passage, so
the row records what was in front of them. But the principle ADR 0026 states does not
distinguish the passage from the offsets, and one of the two has to give.

- **Decide which**, and write the reason on whichever survives. Either the offsets differ in
  kind from the passage and ADR 0026 should say why, or the passage copy wants the same look.
- Not urgent: no human `citation_reading` rows exist outside the forty judgements of
  2026-09-12, and none of those went through `review.decide`.

## `text load`'s lock budget is shorter than a poll's write window, 2026-09-12 (v2026.09.15)

**Found by its cost, and the first write-up of it named the wrong mechanism.** Loading
`ocr/ppocr-second` (6,664 documents) and `ocr/ppocr-graphic` (1,298) into production both
**aborted** on the write lock, the first having loaded 1,459 and the second nothing. Both
succeeded later, unchanged, once the real blocker was gone — an orphaned read-only query of
mine holding a read lock for 33 minutes (see § the WAL note in the same session's commits).

**The mechanism, corrected 2026-09-12.** `db.connect` passes `timeout=30` to the driver, so
there IS a 30-second busy timeout and the first draft of this entry was wrong to price the
budget at "about 62 seconds". The budget is never spent: `batches._apply` opens its transaction
with `con.execute("BEGIN")` (`batches.py:158`) — **deferred** — so it reads, then upgrades to a
write, and on contention SQLite returns `SQLITE_BUSY` **at once** rather than waiting, because
waiting cannot resolve a read-to-write upgrade. Measured: the aborting run took 71 seconds,
which is `under_lock`'s 2+4+8+16+32 = 62 seconds of backoff plus overhead, with every one of
its six attempts failing instantly and using none of its 30 seconds.

The abort is correct behaviour and nothing was corrupted — the loader rolls back, says
"re-run when it is free", and resumes on the next run.

- **`BEGIN IMMEDIATE` is the fix**: take the write lock up front and the busy timeout applies,
  turning six instant failures into six 30-second waits — which is what would have carried
  these loads through. **The trade-off to weigh, not gloss:** the load would then hold the
  write lock for a whole 200-document batch, which can make the poller wait instead. Substantive
  code, so `/code-review` before it lands.
- `lock_retries` also has no CLI route (`batches.under_lock`), which is a smaller knob on the
  same problem.
- Either way `batches.py`'s own docstring records the want, for Migration A: "A shell loop of
  twelve restarts was doing this by hand, one whole pass at a time" — what `under_lock` was
  built to replace and does not yet fully.

## From the ingest specialist on migration 0028's pipeline code, 2026-09-12 (ADR 0026)

Six of its ten findings were fixed in the same branch — the span predicate is now executed
(`find.verify_spans`, called by the walk), a store reading may not come from marked-up text,
the loader refuses spans it cannot anchor, the runbook's two wrong verbs are corrected, the
load exits non-zero on a failed document, and `find.OFFSET_METHOD` no longer collides in scope
with `methods.SPAN_METHOD`. These four are recorded instead.

- **`load._human_held` skips the `citation_reading` rewrite, so those keys keep `'pre-0026'`
  for ever** (F8). Unreachable today: `review.py` writes a human `citation_resolution` and a
  human `citation_reading`, but nothing sets `citation.confidence_state = 'human'`, so the
  branch never fires. The day a review layer does, that key's machine reading is silently
  outside ADR 0026 D2's denominator — `'pre-0026'` being exactly what the predicate gates out.
  It belongs in the ADR's stated floor beside the human-corrected page; the ADR is Accepted and
  append-only, so it is here.
- **`find.printed` and `find()`'s inline copy are two implementations of one rule** (F10,
  sharpened by checking the callers). `find.py`'s loop computes the collapsed slice itself
  ("`printed`, without a second scan"), so `cited_raw` and every span's `raw` come from the
  inline copy — but `printed` is NOT dead: `tools/rmi-ai-machine/benchmark_review.py:120` calls
  it to match a page match against a key. So a correction to `printed` — a new sub-docket form,
  say — would move the BENCHMARK's answer and not the store's, and the two would disagree about
  what a page printed while both looked right. Deleting it is not the fix; making `find()` call
  it, or making both call one helper, is.
- **Validation query 2's `SELECT DISTINCT` key changed, and not only because of `text_id`**
  (F5, second half). `citator-query-2.sql` selects `rg.source_location`, which since 0028
  carries the spans — and spans differ per document even where the printed string does not. So
  two documents of one work that used to collapse can now return two rows. Measured on a
  production copy: **38 groups** agree on every other selected column. `citation_treatment` is
  empty, so the query returns nothing today and this is latent; the same measurement is why
  `project.py` was NOT given the column (its comment carries the reasoning).
- **The `text_ref` refusal raises `WrongChannel`**, whose name and docstring are about the
  reading channel. Cosmetic today — `cli._citator` catches `Exception` — and a mis-triage
  waiting for the first caller that counts `WrongChannel` as "wrong channel, skipped".

## `keys.render` has no version, and human decisions are keyed on its output, 2026-09-12 (v2026.09.15)

**Schema-critic, 2026-09-12, on shape A of the citation grain** (`docs/citation-grain.md`).
`review_action.target_key_version` records the NORMALISER's version, not the render
convention. Change how a key is rendered — a five-segment form where the store holds
four-segment strings — and every human decision already made compares unequal to every row it
was made about, **including the forty the operator judged on 2026-09-12**. It fails silently,
as an empty result rather than an error, and migration 0014's four-segment CHECKs are
shape-only and would not catch it.

- **`review_action` and `correction` want a `render_version`** while both tables are still
  small. That is the whole fix, and it is cheapest now.
- The second finding from the same pass — `source_location` is declared `{page, block_id,
  bbox}` and `load.py` writes only the page — is **not** deferred: it is the justification the
  offsets work now stands on (`TODO.md` § Next), after the recall claim for offsets measured at
  12 of 506 rows.

## Deadline engine (C4), graduated from TODO 2026-09-11

Not started, and not blocked on anything but a decision. The STB's decision JSON carries no
obligations (measured 2026-08-26), so every deadline would have to be read from the decision's
own words — which is the one thing `CLAUDE.md` says is never inferred. A hand-checked fixture
of 8 deadlines for FD 36873 exists in `../up-ns-merger-tracker/briefs/2026-08-25.md`
(read-only, do not modify that project) and is what a first measurement would score against.

## Docket forms the long-form finder leaves out, 2026-09-13 (branch `finder-long-forms`)

The finder of 2026-09-13 reads `Finance Docket No. N` and `Ex Parte No. N` (the operator's
decision, closing 6,028 missing text-layer citations before the OCR card). The same count of
spellings on the 134,723 text-layer pages the citator walks found three more forms it does
not read, each small or ambiguous enough to want its own decision:

- **`F.D. No. N`** — 22 pages. Keying it is one alternative in `keys.LONG_DOCKET`; the cost is
  the period-laden form matching inside a reporter or an initials string, which was not
  measured.
- **`MC-F-N`** — 25 pages. `keys.DOCKET` holds `MCF` but not the hyphen inside the prefix.
- **A bare `Docket No. N` with no prefix** — 5,050 (page, number) mentions in the first 4,000
  decision documents alone. The page does not say which prefix, and a guess (NOR, most likely
  for five-digit numbers) is a key the page never printed: the one failure the citator must
  not have. It needs the citing decision's own docket, or a measured rule, before it can key.
- **A long form printed with no `No.`** — `Finance Docket 32760`, `Ex Parte 711`: about 200
  page mentions in the count, own-family captions included, against some 30,000 with `No.`.
  The code review of 2026-09-13 showed why `No.` is required: optional, it keyed prose
  (`ex parte3` as EP 3, `Finance Docket↵14` as FD 14). A rule admitting them would need the
  capitalised words and a same-line number at least, measured on its own false positives.
- **A footnote digit fused onto a five-digit long form stays unresolved and unreviewed**
  (ingest specialist F6). *(Decided 2026-09-13 by the operator: measure a six-digit repair across
  both forms, draw a sample for him to judge, and bring an ADR 0017 addendum proposal before any
  code. Ten misses across the two long-form gates were this pattern.)* **Measured the same day** on
  the production mirror after the long-form re-load: 352 six-digit findings whose last digit
  stripped is a held docket, in 337 documents — **346 of them the document's own docket** with a
  footnote marker fused on (`STB Finance Docket No. 340071` in FD 34007), which are captions, and
  **6 another proceeding** (`NOR 421278 (STB served April 20, 2023)` for NOR 42127). **Decided
  (the operator): a finder rule** — a six-digit number whose last digit stripped is the
  document's own docket is keyed as that docket, so the 346 become the captions they are; its own
  finder version, card and a small check. The 6 other-proceeding cases stay here.
  *(Re-measured 2026-09-14 on a restore of that day, rule applied to finder 2026-09-13b's output:
  346 text-layer findings in 331 documents, 0 on OCR, no six-digit key a held docket, all 346
  `citation` today and `caption` once keyed as the own docket; 6 other-proceeding. Decided the
  same day by the operator: THE FINDING CARRIES ITS KEY — `find` applies the rule and emits the
  key, `load` and the span check read it and refuse any other departure from the printed number,
  `cited_raw` stays as printed; schema-critic before code.)*
  *(Schema-critic on that design, 2026-09-14, verified the same day. It changes ADR 0018 D1's
  identity — a key becomes the normaliser plus a rule over registry data — so it needs an ADR 0018
  addendum, and `KEY_VERSION` must move (0014:560-561 define `target_key` as the normalised target
  and `key_version` as its normaliser). Breaks, each confirmed:*
  - *177 of the 346 sit on a page that also emits the stripped own key (116 caption, 61
    citation), so `find` merges the two forms and `verify_spans`, which checks each span against
    `normalise(target)` (`find.py:324,340`), fails the document;*
  - *`own` is registry data still growing, and retraction fires only across versions
    (`load.py:903`), so a same-version re-load after `own` changes leaves both keys live, and
    nothing records the `own` a key was built from;*
  - *`resolve._anchored` keys occurrences by `normalise(printed)` (`resolve.py:211,234`), so a
    re-keyed target misses the other printed form;*
  - *`load` must check the stripped key is own, or a forged file re-keys one of the 6
    other-proceeding cases to a measured, unexposed, unreviewed edge;*
  - *ADR 0018 D2 has a mis-keyed row point at its replacement, not at itself;*
  - *`benchmark_review.py`, `review_queue_panel.py` and the check sheets also re-derive or anchor
    from the printed form.*
  *Decided by the operator the same day: ship the resolver fallback as its own finder version
  first; the six-digit rule follows as an ADR 0018 addendum, critic passes and his acceptance, then
  its own finder version.)* Measured on the production mirror: **176** long-form matches key a
  six-digit number the registry does not hold, and in every one the five-digit parent IS held
  (`STB Finance Docket No. 340871↵TRINIDAD RAILWAY` — a caption with its footnote marker
  fused). Rule 2 repairs only five printed digits and `review.in_the_held_record` queues nothing
  above the held range, so they are stored `unresolved` and never shown or reviewed. Before
  this finder they were not emitted at all, so nothing regressed. Widening rule 2 to six
  digits reopens ADR 0017's exposure reasoning (`keys.py` names the cost), so it is the
  operator's decision, not a patch.
- **The resolver's family limit: a parent takes its own sub-docket's served date.** *(Decided
  2026-09-13 by the operator: he judges the 12 answers retiring it would change, and the count
  decides.)* **Re-measured against the live resolver** (key anchor, limit kept) the 12 were 2: the
  figure had compared the old spelling anchor. `EP 575` in decision 39033 (FD 35134) cites "STB Ex
  Parte No. 575 and STB Ex Parte No. 575 (Sub-No. 1) (STB served Oct. 30, 2007)" — decision 36758
  is filed in both dockets, so the limit is right; `FD 34554` in decision 41393 (FD 34554 (Sub-No.
  140)) cites "FD 34554 (STB served Oct. 7, 2004) … FD 34554 (Sub-No. 2) (STB served February 11,
  2005)" — the limit makes the parent see both dates and name nothing, where notice 35093 is right.
  **Decided (the operator): every citation should reach its own document**, which a FALLBACK
  anchor does — strict key first, the family's occurrences only when that finds no service date.
  Checked on both pages: EP 575 and EP 575 (1) keep 36758; FD 34554 gains 35093 while FD 34554
  (2) keeps 35555 (served 2005-02-11). To be built with the fused-digit finder rule below, as one
  finder version. *(Measured 2026-09-14 on a restore of that day, main's resolver against the
  branch `finder-fallback-anchor`'s over every live reading, 104,765 on both channels: ONE answer
  changes, reading 308248, `FD 34554` gaining 35093; nothing lost or altered.)*
  *(Codex on PR #32, 2026-09-14, P1, verified: the fallback changes what a resolution ASSERTS, but
  the row is still `registry-match@rule-1`/`rule-2-repair`, and `FINDER_VERSION` lives on `citation`
  and `citation_reading`, not on `citation_resolution`. `resolve.py`'s own note of 2026-09-10 says
  "any LATER widening of what a row asserts is a version bump", and `_anchored`'s docstring
  contradicts it. Decided the same day by the operator: BUMP THE RESOLVER'S VERSION, schema-critic
  scoping how older-version rows are superseded, ranked and queued before any code; rehearse again.)*
  *(Schema-critic's scope, verified 2026-09-14: `citation_resolution` has NO human-row trigger (the
  loader's `method = 'registry-match'` filter is the only guard); the projection inner-joins
  resolutions to rank rows by `method_version` (`project.py:52-57`), so a row left at the old
  version stops publishing; `measure` writes `RULE_1` into the card and `stamp` never checks it.
  Design: bump both rules (`rule-1/2026-09-14`, `rule-2-repair/2026-09-14`), retire every older
  resolver row on the key and channel onto the new one, read `work_gained`/`work_lost` against any
  version, `stamp` refuses a card of another resolver version, rebuild both cards, rehearse on a
  fresh restore. Decided by the operator: THE RE-LOAD MUST REACH EVERY LIVE RESOLUTION and the
  release waits for 0 left at the old version on live keys; FINDER_VERSION stays 2026-09-14.)* Pinned by
  the 2026-09-10 review as a limit that must survive (`test_the_anchor_finds_the_target_as_
  printed_and_stops_at_a_sentence`), and kept when `resolve._anchored` moved from a spelling to
  a key (ingest specialist F1, 2026-09-13): `FD 36873` anchors on `FD 36873 (Sub-No. 1) (STB
  served …)` and names the parent-docket decision served that day, if exactly one. Measured on
  the production mirror 2026-09-13, retiring it would change **12** work-level answers — **8**
  documents lost and **4** gained — and at least one kept answer is wrong: `EP 575` on
  `1c1d6d2eab12` p1 takes the date of `Ex Parte No. 575 (Sub-No. …)` beside it. Whether a
  same-day decision entered in both dockets makes the parent's answer right often enough to
  keep is a question about published claims, so it is the operator's.
- **The span test cannot see an own-family citation by reporter or by name.** Finder
  2026-09-13b reads an own-family mention's kind from `judge.names_document` (the operator's
  decision), and on the sixty two truth citations became captions: decision 51532's `EP 328`
  (`Investigation of Tank Car Allowance Sys. (EP 328), 3 I.C.C.2d 196`) and decision 53052's
  `FD 36873 (1)` (`… Union Railway, Docket No. FD 36873 (Sub-No. 1). However, the Board will hold
  both`). Both were already suppressed at projection, so nothing published changed (projection
  217/221 either way); what the old window's `I.C.C.`/`v.` words caught, the span test does not.
  Widening the span test is a SPAN_VERSION bump and a re-measurement of every edge it stamps.
- **A long form whose words wrap is not a quote boundary** (ingest specialist F8).
  `find.quoted` looks for the next docket number within the line, so `…; see Finance↵Docket No.
  34002 (…` does not end the earlier target's rest-of-line there, while `resolve._anchored`,
  reading the joined line, does. The effect is a shorter quote (the next line is not added), not
  a wrong answer.
- **The gap after `No.` needs no width limit, measured** (ingest specialist F4): 0 long-form
  matches on the production mirror have more than two spaces between `No.` and the number.
- **The second number of a `Nos.` list** — `Finance Docket Nos. 32760 and 32760 (Sub-No. 1)`
  keys the first only, as `FD 36744 et al.` already does for the abbreviated form. Not counted.

## Two channels' readings of one page, and what assumes a key has one, 2026-09-13 (branch `ocr-card`, rank v5)

Rank v5 ranks OCR below the text layer for every method (ADR 0018 D7), which makes an OCR load
possible. The schema critic found three places that assume a (document, page, key) is read on
one channel only. **Measured the same day on the production mirror: 0 pages carry live citation
readings on both channels, and 0 pages whose live primary reading is OCR carry live text-layer
citation readings** — so none of the three can happen on the record as it stands; each needs a
page read again on the other channel (a re-OCR of a text-layer page, or the reverse).
*(Decided 2026-09-13 by the operator: `citator load` refuses a document that would write a page
already carrying another channel's live citation readings, and the fixes wait here.)*

- **The `citation` identity row carries no channel** (`load.py`, gated by `project.py`'s
  `c.confidence_state` term). A second channel's pass that reads the key as a caption supersedes
  a measured citation with an `unmeasured` one and the first channel's edge disappears; the
  reverse publishes an edge the higher-ranked channel withheld; re-running either flips it back.
  Cheapest fix: never change the identity row's state while a higher-ranked channel holds a live
  reading of the key. The alternative — gate the edge on the channel-keyed resolution alone — is
  a grain decision against ADR 0018 D2.
- **The review queue shows a key once per channel, and an answer can be recorded against the
  loser** (`review._base`, `review.decide`, `review_routes`' POST). `stored` is the newest
  non-human resolution, not the ranked winner, so accepting an exposed text-layer edge while an
  OCR reading of the same key is `unresolved` writes a human `unresolved` row — which `refused`
  then holds against the edge for good, with `review_action` saying accepted. Fix: the winner
  only, from `project`'s own ranked CTE, and the channel in the POST's match.
- **`span` is ranked across channels** (`project.py` and `docs/citator-query-2.sql`). A text-layer
  `false` is stored `unmeasured` and never a candidate, so an OCR `true` for the same key lets the
  text layer's in-family edge publish on OCR's judgement, beside the text-layer passage and
  figure. Fix: partition and join `span` on the reading channel, as `suppressed` already is — a
  change to D7's judgement rule, so the operator's.
- **The text-layer projection figure names rank v4.** It is exactly v5's while no page has two
  channels; if the guard is ever lifted, re-score it under the rank then in force.
- **The guard's refusal never clears, and costs the document's other OCR pages** (ingest
  specialist, F1). A page whose live primary reading moves to OCR keeps its text-layer readings
  live — no text-layer walk visits it again — so every OCR load of that document is refused whole,
  counted `refused_shared` and exiting 3. Retiring the readings of a page that changed channel is
  the operator's decision, and belongs with the 903 retraction residue already owed (TODO).
  *(Measured 2026-09-13 on a restore taken after the OCR load: 0 such pages. The operator decided
  the same day to retire a retracted key's readings with its citation — TODO.)*
- **A retracted key's resolutions and judgements stay live, and cannot be dated** (2026-09-13,
  v2026.09.20). ADR 0018 D2 retires `citation` alone; the operator chose to retire the READINGS
  with it now and leave these two for later, because neither table has `superseded_at` and a
  retirement there would be undated. Today: 903 live resolutions and 2,709 live judgements on the
  903 retracted keys, reaching nothing (every consumer joins a live `citation`). Dating both tables
  first — a schema change of its own — then retiring them the same way is the owed shape.
- **OCR readings will carry `reading_method` NULL** (F3). `walk.documents` never supplies the
  engine and one document can mix two; `text_id` → `document_text` still names it per page. Fill
  it in `walk` per page, or correct `load.py`'s interchange docstring, which says it is set.
- **A rule-2 repair read on OCR publishes at a precision that never scored one** (Codex on PR #29,
  2026-09-13). The projection admits `repaired` beside `resolved` and holds only the exposed class
  for review, so a repaired OCR edge is shown stamped with the OCR card's 83.7%; the benchmark's
  sample holds no repair (`ocr_citation_dryrun.py` now writes no card when it does), while the full
  rehearsal's load added one (repaired queue 1 -> 2). Scoring repairs needs a sample that has them,
  or holding rule-2 repairs on OCR for review — the operator's decision.
- **A fractional page is truncated, not refused** (F2 of the same review, low, not new): `4.7`
  is page 4 in the guard and in the insert alike. Refuse a non-integer page at the boundary.

## A migration script that errors partway can leave its earlier DDL committable, 2026-09-13 (v2026.09.20)

Found by the schema critic on the ADR 0018 retirement addendum; tested the same day in
v2026.09.20's image (SQLite 3.46.1). `db.migrate` runs each script with `executescript`. A
statement that fails to PARSE partway (not a `RAISE`) raises with the script's `BEGIN` still
open, and a caller that keeps the connection and commits keeps whatever ran before the error
(the test kept a `CREATE TABLE`, with `user_version` unchanged). Production is safe today only
because the `migrate` service's connection closes on the exception, which rolls back. A
`RAISE(ROLLBACK, '<fixed text>')` left nothing. Fix: `db.migrate` rolls back explicitly before
re-raising, with a test that commits after a failing script.

## SQLite 3.53.4 in production, 2026-09-13 (v2026.09.20)

*(Decided 2026-09-13 by the operator: the next release carries Debian's `deb13u2` fixes on the
same 3.46.1; the upgrade below is its own decision, later. `deb13u2` shipped in v2026.09.22,
2026-09-14: the Dockerfile now upgrades `libsqlite3-0` itself.)* Every figure was measured or read
from its primary source that day.

- **Engines on the record:** production image 3.46.1 (`libsqlite3-0 3.46.1-7+deb13u1`, Debian 13,
  `python:3.12-slim`); Debian stable now `deb13u2`; Litestream v0.3.14 bundles 3.42.0
  (`go-sqlite3 v1.14.17`); the operator's workstation 3.50.4; CI probably Ubuntu 24.04's 3.45.1
  (unverified). Newest: 3.53.4, 2026-07-24, also in Debian testing.
- **The WAL-reset corruption bug** (sqlite.org/wal.html) affects 3.7.0 through 3.51.2: two
  connections in separate processes writing or checkpointing one WAL at the same instant.
  Production's shape: `web`, `ingest` and Litestream. Rated about as rare as an SSD fault. No
  Debian backport. Whether Litestream's bundled 3.42.0 must move too is unestablished.
- **ALTER for constraints (3.53.0), tested on 3.53.4:** `ADD CONSTRAINT … CHECK`, unnamed
  `ADD CHECK`, `DROP CONSTRAINT` and `ALTER COLUMN … SET NOT NULL` work and rewrite the stored
  `CREATE TABLE`. Any existing row that fails is refused, and a NULL counted as failing
  `CHECK (x > 0)` there. That would have spared the CHECK-only rebuilds (0004, 0012, 0017), not
  0028's.
- **`RAISE` with an expression (3.47.0)**, and a behaviour change: from 3.53.0 a REAL rendered
  as text gets 17 digits (`json_object` printed `0.83720930232558144`). No SQL in `src/` renders
  a REAL today.
- **Drift:** local tests on 3.50.4 can pass on features production lacks.
- **Route:** build 3.53.4 into the image (not `pysqlite3-binary`: one maintainer, Beta, x86_64
  only, bundled version unstated), align CI and local engines, and consider Litestream separately.
  Rehearse every migration and the suite on the new engine.

## From reviewing the own-fused rule's build, 2026-09-14 (branch `six-digit-own-docket`, finder 2026-09-14b)

Schema-critic, the ingest specialist and `/code-review` medium on the ADR 0018 addendum of 2026-09-14,
each finding verified against the code the same day. **Fixed on the branch:** a finding with no `key`
is refused (`Departed`) rather than keyed at load; a benchmark reading keeps each occurrence's printed
form (`printed`) so `key_rule` and the registry check see every re-keyed number; the retraction's
own-key successor is used only where this pass re-keyed that number on the page; `resolve.resolve`
takes `own` with no default; the scorers read `key` only in a finder run, since a review run's `target`
is the model's answer. **How the build reads the addendum**, for the operator to see:

- item 7 is ONE test, `own_key(normalise(x), own) == key`, for the finding and each span. It is
  stricter than "normalises to the key, or re-keys to it" in one place only: a six-digit finding the
  rule would NOW re-key (`own` gained the stripped docket since `find`) is refused, and loads on the
  next walk. Expect `refused_departed` above 0 while waves 2-3 add dockets between a walk and a load;
- `key_rule.printed_keys` is a list, since one page can print two fused digits;
- `Departed` counts a forged span over another proceeding's number with drift, as item 7 says, so the
  count no longer tells a corrupt file from a changed family.

**Left, and why:**

- **`walk.own_of` runs once per document** at load, and `docket.parent_docket_id` has no index (its
  third branch). Measured by the rehearsal's load time; an index is a schema change.
- **`work_check_sheet.py` anchors with the citing DECISION's family** (`citation_dryrun.own_dockets`),
  not the loader's per-document union, so a document carried by decisions in unrelated dockets can
  miss a re-key on the sheet. The tool only.
- **`tools/rmi-ai-machine/panel_check_sheet.py`** (untracked, the operator's) calls `_anchored` without
  `key`/`own`. No re-keyed key can reach the exposed or repaired queue it reads (a re-keyed key is a
  five-digit own docket, rule 1, never exposed).

## The OCR wave's unloaded pages, and three owed items scoped, 2026-09-15 (v2026.09.24, schema 29)

**The question**, written before measuring: the citator walk skips 37 decision-carried documents
(43 pages) for want of text (`walk.py`'s blank test) — why did `ocr_wave.image_only_documents` miss
them, and is it a rule gap or a data gap? Measured with the shipped walk on a Litestream restore of
production taken 2026-09-15 ~21:05 UTC, joined to the OCR roots on rmi-lan and the fleet coordinator.

**It did not miss them.** All 37 have a text-layer record flagged `image_only`, a route file and a
PP-OCRv6 cache. The TODO's "36 never OCR'd" was wrong: PP-OCRv6 read every one. What kept the text out
of the store is routing:

- **35 documents / 41 pages: every page routed `tabular`.** ocr-plan decision 3 keeps tables out of
  this wave; decision 6 gives them to HunyuanOCR-1.5 in their own pass, last. That pass is not built.
  The cache holds 196–2,022 characters on each page.
- **1 document (FD 34064, 2013): a `degraded` page dots refused** (`page: oversize: 8.4 MP`). No
  primary means no second reading either (`run_second` needs one), so nothing loaded; the cache holds
  1,623 characters. compute-fleet.md § The oversize guard says such pages "wait for a pass under another
  profile" — a recorded design, not an oversight.
- **1 document (NOM 41491, 1996): `unrouted`, PP-OCRv6 read it as 0 characters**, loaded as such.

**Record-wide** (every routed page no loaded root holds, then the store's live readings):

| page | no live text: decision-carried | no live text: other | cache has text |
| --- | --- | --- | --- |
| `tabular` | 1,394 pages, 100 docs (35 wholly blank) | 24,851 pages, 3,259 docs (171 wholly blank) | all but 6 |
| `degraded`, dots refused | 7 pages, 6 docs (1 wholly blank) | 114 pages, 79 docs (25 wholly blank) | all |
| `clean`/`unrouted`, no primary | 0 | 160 pages, 75 docs (1 wholly blank) | none (engine read blank) |

(29,200 `clean` pages the coordinator's root lacks DO have live text: the comment pass's primaries live
on rmi-lan's `comment-pass/`, not in the coordinator's root. The store was the check.)

**A reader-facing gap, the operator's:** decision 3 promised a tabular page reads *scanned; contains a
table we have not read*. No template says it. The store holds no route class for these pages (routes
were loaded only with OCR readings; the live row is the blank text-layer primary), so
`text.html` shows **"Read as blank."** — the kind of absence the decision called dishonest. Showing
the marker needs the router's verdict in the store, which is a provenance question (ADR 0021 D4).

**Proposed, each with the count it changes — none started, all the operator's:**

1. **Build decision 6's tabular pass** (a fleet pass like `dots`; HunyuanOCR's licence is answered by
   ADR 0022 D3). Changes 26,245 pages; 1,394 decision-carried in 100 documents; the 35 wholly blank
   decision documents. Box time only. OR, as an interim, load the PP-OCRv6 cache as their primary
   (benchmark: PP-OCRv6 tabular CER 38.2%; HunyuanOCR is the only free engine that detected all
   five grids) — which reverses decision 6's reader.
2. **A fallback for pages dots refuses** (PP-OCRv6's cached reading as primary, route `degraded`):
   121 pages in 85 documents, 7 decision-carried, 1 wholly blank. Reverses the oversize guard's "wait".
3. **The route in the store** so a tabular page can say it is unread: a schema/provenance change,
   schema-critic first.

**Decided by the operator the same day:** (1) **build decision 6's HunyuanOCR tabular pass** on the
fleet (branch + PR; loading waits for his go); (2) for the pages dots refused he asked whether an
LLM reading on the 3090 or, if needed, Claude should read them — **open, facts owed to him**; (3) **the
route in the store: scope it, schema-critic first**; (4) **start all three builds**: the per-page
failure record, the veto trigger, and the decided-date consumer (each design and critic before code;
any ADR addendum is his to accept).

**Decided by him later the same day:** (5) he allows me to stop and start the fleet's tmux sessions on
rmi-ai-machine (the dots server held 9.2 GB of the 4070 with its queue drained); (6) **the pages dots
refused get a Claude Sonnet 5 batch** (~$2.30 for 134 pages, measured 10.5% CER on the degraded tier),
its own pass with its own key, loading on his go; (7) the recommended defaults for three designs —
veto trigger (any-version rule; the row's own measurement carries a rate; the rate on the veto's own
channel; a D7 addendum), failure record (`ocr_page_failure`, public with detail, the 134 back-filled by
a sidecar load, the size refusal counted not written; an ADR 0024 addendum), route in the store (held
`page_route`, `text route` verb, the marker on blank tabular text-layer pages only, not counted read;
an ADR 0021 addendum). The decided-date defaults were NOT accepted: its questions go back to him.
Measured for the tabular pass: 26,294 tabular pages at 150 DPI, median 2.1 MP, p99 2.4, 29 over 6 MP.
**The Claude batch RAN** (2026-09-15, his scoped key): 134 of 134 refused pages read, **0 failed**,
none over the per-image limit, in two batches of 110 and 24; 649,320 input and 225,373 output tokens,
**about $1.78** at batch pricing (the estimate was ~$1.30). 98 reading documents at render
`200-max2576-grey`, written to the session scratchpad, NOT loaded — loading is his go. The first
attempt was refused twice: colour renders broke the 256 MB batch and 10 MB image limits, then an
unscoped key returned 400. Nothing was charged for either.

**The tabular pass's parity probe PASSED** (2026-09-15, on rmi-ai-machine with the dots server
stopped and the card otherwise empty): HunyuanOCR-1.5 through `ocr_run.run_hunyuan_ocr`, the
benchmark's own path, on the benchmark's five `tabular` pages — **all five byte-identical to the
saved run**, 3.3–10.3 s a page, peak 2.4 GB VRAM. So the worker's in-process transformers path is
the measured one, and its 4 GiB load floor holds. The dots sessions are left stopped: their queue is
drained (46,838 done, 134 final failures) and the tabular worker needs the card.

Then: (8) the Claude key goes in a short-lived `.anthropic-key` on the workstation — he put it at the
REPOSITORY ROOT, where `*.key` did not cover it, so `.gitignore` names it (48a90d9); the first key was
not scoped to a workspace and every request was refused 400 until he swapped it; (9) he adds the
fleet permission rule to `.claude/settings.local.json` himself (writing it was refused as
self-modification); (10) decided dates: **measure first** on a production copy, numbers to him before
any addendum or code.

**Decided dates, measured the same evening** (a NEW line-anchored `Decided:` regex — no shipped
extractor exists — over the shipped walk's documents and row rule, on the 2026-09-15 restore): of
21,003 decision-carried documents, **16,029 print the line on the text layer** (15,771 once, 258 twice
or more), 30 on OCR only; lines sit on page 1 11,177 / page 2 1,427 / page 3+ 3,853 — a sample of ten
page-3+ lines were all genuine end-of-decision `Decided:` headers, so page 1 alone would lose ~30%;
**99.7% parse** (16,355 of 16,403 text-layer lines; 52 of 54 OCR); 11 documents carry two distinct
dates; text-layer and OCR never both read the line on one document; OCR primary vs second on one page
agree 16, differ 1. Against the carrying decision's service date: same day 4,511, served 1–30 days
later 14,548, other 40. Script: session scratchpad `measure_decided.py`.

**Decided by the operator 2026-09-16, on the night's rehearsals:** (11) **the three addenda
accepted** (0018 the veto's trigger, 0024 per-page failures, 0021 the router's verdict) and the PRs
merged in number order — #35 `ecbe527`, #37 `c66ff2c`, then #36 once Copilot has read its last fix;
each rehearsed in v2026.09.24's image (SQLite 3.46.1) on the 2026-09-15 restore, figures on each PR;
releasing and deploying stay his. (12) **The Claude batch LOADED into production** 2026-09-16,
restore point **11:29:23Z** (Litestream generation `073494ca664fa87f`): `{'loaded': 98}` in 4 s; 134
live `claude-sonnet-5` primaries (unmeasured), 98 `ocr_run`, 98 payloads on the box; the 134
`pymupdf` primaries they supersede were 121 empty pages and 13 holding only the Board's 9-character
e-filing stamp, which each new reading repeats. Rehearsed first on a second copy with the same
figures. (13) **The tabular pass STARTED** 2026-09-16 11:46Z: coordinator on `hunyuan-tabular`
`67b1762` (detached; queue server and monitor restarted on it), the workstation's fleet code the
same commit (its previous copy in `~/fleet-code-backup-2026-09-16.tgz`), pymupdf 1.28.2 — the
router's — added to `~/ocr-bench/.venv`; seeded 26,294 pages in 3,385 documents. Stop:
`touch /data/docketyard/ocr/.stop-tabular` on the workstation. (14) **Decided dates: build the
extraction pass only** — no pick, no display, ADR 0018 D4 untouched; the grain (the positional
`ordinal`) goes to an addendum and schema-critic first.

**Three owed items, scoped against the ADRs** (each claim below checked in the code):

- **"Not in the record" joining live `citation`** (0014_citations.sql § the projection; ADR 0017 D2,
  ADR 0018 D2). No page renders the display today, and every consumer that exists (`review._base`,
  `project`) already joins live `citation`. Owed only when the display is built; no schema. Building it
  publishes a coverage statement — the operator's.
- **The veto's trigger** (0014 item 7, ADR 0018 D7): two cross-row conditions — a suppress method's
  measurement carries `false_veto_rate`, and its resolutions are `measured`. No suppress row is written
  (`methods.py`), and 0014 judged a trigger for an inert mechanism not worth its weight. A new migration
  with triggers, so schema-critic; the rule is already decided. Build with the veto, not before.
- **A consumer for ADR 0023's pick rule**: `web/cite.py` sends a `decided` phrase to the sheet, and
  nothing writes or reads `decision_decided_date` (only `dump.py` and `supersede.py` name it). Owed
  first: a decided-date extraction pass, then the pick, a disagreement queue, and ADR 0018 D4 (which says
  `decided` stays at docket level) revisited. Schema-critic and a decision; 259 of 200,000 pages print
  the phrase (§ 2026-09-05 above).
- **ADR 0024 Owed 2, the per-page failure record's backlog**: the table, vocabulary, loader contract
  and both producers were built 2026-09-15 (migration 0031; the addendum accepted 2026-09-16). The 134 final
  dots pages already collected (98 documents: `finish_reason length` and `oversize`) carry a count
  only; they get a one-off sidecar load from the queue's `job.error` through
  `ocr_wave.page_failure`, under the runs their reading documents wrote (the conditions are in the
  next section).

**From the schema critic and PR #36 on migration 0032 (`page_route`), 2026-09-15** — what was NOT
fixed on that branch (the omitted-page counts and the forward-only retirement triggers were):

- **A file's silence still leaves a verdict live.** `text route` compares only the pages a file
  names, so a page a later file no longer classifies keeps its old verdict; the pass now counts
  the document under `omits_live_pages` rather than passing it over, but nothing retires the
  orphan. The converse too: an OLDER root still fills a page that has no live row because the
  newer run failed there, staleness being judged only against a live row. Whether a re-route
  should retire what it omits is a decision, not a bug.
- **Page search does not consult `page_route`** (`store/search.py`, the page hits): a hit is built from
  the indexed text, so a page the text page hides behind the table marker — a blank or junk text layer
  on a tabular page — can still be found and shown with that text. Whether search should mask it too
  is the operator's call (found on PR #36, 2026-09-15).
- **`document_pagination`'s retirement history is still rewritable**: `superseded_by` and
  `superseded_at` can be re-pointed, back-dated or cleared in place there. `page_route` closed
  this at 0032 and `citation_reading` at 0028; the published table is the one left, and it is a
  rebuild, not an ALTER.

## From the schema critic on migration 0030, 2026-09-15 (branch `veto-trigger`, against v2026.09.24)

- **A veto's measurement is not pinned to a rate-bearing class.** The triggers ask only that the
  measurement carry a non-NULL `false_veto_rate`, so a declaration or a bound row may name a `docket`
  or `work` measurement that also carries one (`test_restamp_leaves_a_class_it_does_not_own_alone`
  writes such a card). A flag on `class_vocab` marking the rate-bearing classes, read by the triggers,
  would pin it. Not built: nothing declares a veto.
- **`restamp` and a bound row, conjectured and not reproduced.** `restamp.stale` selects by the row's
  class (`_OURS` = docket, work), not by its method's role. A row of a suppress triple stamped from a
  docket-class measurement would be picked up, re-inserted from the docket card, which carries no
  rate, and refused by `citation_resolution_veto_row_is_measured_on_a_rate` — an IntegrityError in
  the middle of a pass. Owed with the first veto: reproduce it, then filter `stale` on role.

## From the schema critic on migration 0031, 2026-09-15 (branch `ocr-page-failure`, schema 31)

- **A restart ignores a different failure list.** `load_reading` returns `restart` on the run's key
  and `ran_at` before it reads the body, so a reading document re-posted with the same `ran_at` and
  a corrected or newly added `page_failures` writes nothing and says nothing. The 134-failure sidecar
  therefore cannot go through `text load`: it inserts directly, all of a run's rows or none, matched
  on the queue's `collected.ran_at == ocr_run.ran_at` for the document and key, and only where the
  run's `pages_failed` equals the number of failed jobs it would write.
- **Earlier runs of re-read documents cannot be recovered.** `seed` deletes a re-read document's jobs,
  errors included, so a run collected before the re-read has no reasons left to load.
- **Nothing forbids changing a run under its failure rows.** The triggers check `ocr_run.outcome`
  and `pages_failed` at INSERT of a failure row only; a later UPDATE of either leaves rows that no
  longer fit. Nothing updates `ocr_run` today. A BEFORE UPDATE trigger on `ocr_run` refusing the
  change while failure rows exist is the stronger form.
- **`ocr_run.note` already publishes exception text into the CC0 snapshot.** `load._note` keeps a
  producer's reason verbatim up to 500 characters — "the exception", in ADR 0024's own words — and
  `ocr_run` is PUBLIC. That is the leak `ocr_page_failure.detail`'s closed shapes were built to
  close: a path or a host in an exception reaches a snapshot that cannot be withdrawn.

## From reviewing the tabular pass's build, 2026-09-15 (branch `hunyuan-tabular`, not yet run)

- **OCR producer pins cannot tell two engines apart at one profile and role.** Producer pins are
  keyed `(channel, render_profile, role)`, so `hunyuan-ocr` 1.5 at `ocr`/`150`/`primary` shares a pin
  key with `pp-ocrv6-medium`: the first OCR pin would refuse one of the two roots. No OCR pin exists
  yet, so nothing refuses today. Found by the stb-ingest-specialist on this branch; schema-critic
  decides the key when OCR pins arrive.

## The independent graders, 2026-09-16 (against v2026.09.24, live MCP of four tools)

Five cold-start AI graders — an STB practitioner, a researcher, an API developer, an assistant
using the MCP server, a skeptical auditor — each graded the live site and the public repo
without this repository's planning files, and a separate verifier re-checked every finding.
Grades: B, B, B, B+, B; every verifier held its grade. **The data itself held up** (about twenty
records checked field by field against stb.gov, all identical); what follows is where it falls
short. The operator's reading: not a failure, a list to work through. Verdicts are the
verifier's; "partly" means true but overstated, and the narrowed form is what is recorded.

Merged 2026-09-17 and not yet released: the first fixes (#39: decision summaries through MCP,
JSON misses, wording an assistant repeats, README and CONTRIBUTING, the `/api` example) and the
operator's nine decisions (#40: early years, last checked and JSON shape 3, parties and text for
user-directed fetchers, the CC0 label, served dates, timestamped webhook signatures, the
repeated-filer prose, an as-of cite). Those items have left this file; the commits are the record.

### Fix now — still open

All three fixed 2026-09-18 (`6f9b44a`), except the half below that was always the larger one.

- **`/openapi.json` publishes no response schemas** (developer I2, the half that was never the
  mechanical one). The `/review` routes and the duplicate HEAD operation ids are gone; what a
  route *returns* is still undescribed, and waits with F5's next step.

### The operator's to choose later

- **A monthly snapshot deposit with a DOI** (researcher I8; his decision 9, 2026-09-16): the cite
  now carries an access date and the newest kept archive; a third-party deposit (Zenodo) publishes
  permanently, so it waits for him to choose it.

### From review of the tabular pass's last fixes, 2026-09-17 (PR #34, merged)

- **`page_index` and `register_or_exit` exist twice, in `dots_worker.py` and `hunyuan_worker.py`**
  (`/code-review` low): the twins are duplicated on purpose (hunyuan_worker's docstring: a rule
  change belongs in both, and the dots loop runs), and these two pure helpers were added to both
  in one commit. A shared fleet module would stop them drifting; worth doing when the dots worker
  is next changed, not while a pass runs on it.

### Capability-scale — chosen from the menu, not fixed in passing

- **No filings by filer and date** (practitioner I1, partly — MCP search does return parties):
  `/p/<id>` folds sub-dockets into a family row with no date filter and has no JSON. F3.
- **Search has no filters, operators, recency, paging or totals** (practitioner I4, researcher
  I4, assistant I5; confirmed). F4, Ripe #2.
- **Aggregates by prefix and year** (researcher I3, confirmed) — PR #38's `count_filings` is the
  MCP half; `/stats` has none.
- **Paging**: a large sheet is one 870 KB document with a store-wide ETag (developer I5), MCP
  sheets stop at 100 entries (assistant I4), feeds at 100 events with no archive (practitioner
  I5 partly — about seven days on `/feed`; developer I6).
- **The snapshot has no caption or summary columns and no codebook** (researcher I6, confirmed);
  counting units (`DISTINCT stb_filing_id`) are undocumented. A view is a schema question.
- **586 of 723 AB rows are captionless series parents** (researcher I7, partly — 92.4% of all
  docket rows carry a caption).
- **No decision numbers or schedule pointer on a sheet** (practitioner I6) — extraction.
- **`create_app` is one ~1,900-line closure** (developer I9); **error formats differ by route**
  (developer I10: 422 JSON on some, HTML 404 elsewhere; `.JSON` case-sensitive).
- **Capture provenance is in the snapshot but not the JSON twin** (auditor I8, partly).

## Text-layer quality, 2026-09-17 (against v2026.09.28; `docs/research/text-quality/`)

Found while measuring why `/filing/18005` shows garbled text. The operator's four decisions of
the same day are in `TODO.md` § Next; what is recorded here is what was measured and NOT acted
on.

- **The image-only test is per document and has no quality dimension.** `extract_text.py` and
  `infra/extract/extract.py` call a document image-only only when EVERY page holds under 20
  stripped characters, so one readable page keeps a whole scanned document on the text-layer
  path, and a garbled layer is never second-read by anything (ADR 0024 D7's queue takes empty
  pages only). Deferred: whether the forward pass should route a new document's *pages* rather
  than the document.
- **`noisy` text layers are invisible to a lexicon check.** 6 of 16 sampled pages scoring ≥0.7
  were readable-but-frequently-wrong (`infonnalion`, `Buriington`). Sixteen pages cannot size
  the class, and no cheap signal in this family will find it — the errors are word-shaped. A
  second reading with a distance is the only instrument that would, which is ADR 0021 D8's
  operand over 866k pages. Deferred until the ≥0.7 sample exists.
- **Broken font encodings are a distinct failure with a distinct repair.** Born-digital PDFs
  whose `ToUnicode` map is wrong yield a substitution cipher (`Pd_ed KWY_\_Y` for `Union
  Pacific`, `Qixve` for `Metra`); they are why 2020–26 leads the low-score table, and OCR of
  the render fixes them outright. No detector for them beyond the score.
- **~5,500 pages score <0.3 in 2020–26**, the era whose documents the forward pass reads today.
  The re-read decision covers the backlog; whether the FORWARD pass should score a page as it
  lands, and re-read it there, is not decided.
- **The signal is weak on engine readings** (AUC 0.59 against the wave's measured
  `agreement_distance` on 55,356 degraded primaries) and **blind to invention**: a local
  `deepseek-ocr` reading of 18005 invented fluent sentences and scored 0.96. Nothing here
  should be used to judge an OCR reading.
- **1,104,935-page-era note:** blank text-layer pages inside otherwise-text-layer documents
  (14,894 in 2000–04 alone) remain outside both the OCR queue and this signal's floor.

## From the operator's check of the text-quality labels, 2026-09-17

He checked all 64 pages against their scans (`docs/research/text-quality/labels-checked.json`);
the figures in that README are now his, not the drafting pass's.

- **The wave reads a sideways page sideways.** `ocr_wave.py` builds PP-OCRv6 with
  `use_doc_orientation_classify=False` and `use_textline_orientation=False` (466-468), and
  **9 of his 64 pages carry "rotate before OCR"**, 6 of them scoring under 0.3. The benchmark's
  `ppocr-pre` run measured those toggles as worse (12.3% CER against 11.8%) — but on the 90
  IMAGE-ONLY pages, a population where rotation is rarer than in this text-layer sample. Owed
  before the re-read: measure orientation detection on rotated text-layer pages specifically,
  and decide whether the render or the reader fixes it.
  **MEASURED 2026-09-17, and it rules out the cheap fix: all 9 of those pages carry
  `/Rotate = 0` and a PORTRAIT page box** — the scan itself is sideways and the PDF says
  nothing. Neither the rotation flag nor the aspect ratio finds them (8 other pages of the 64
  DO declare a rotation, and pymupdf already honours those, so the declared ones render
  upright). Only a content-based orientation classifier or the layout model's own reading
  order can detect the other kind, which is the toggle the wave turns off.
  **PROBED 2026-09-17** (`docs/research/text-quality/` § The rotation probe): rendering each of
  the 9 at four rotations and scoring the PP-OCR reading does NOT pick the upright one — the
  spread is hundredths and the winner lands on all four values — so that cheap detector is out.
  A VL model read the two tried at 0° about as well as turned, and **dots.mocr is itself a VL
  model**, so this bears on PP-OCRv6's tiers, not on the degraded-tier reader. None of the 9 is
  prose, so it does not block the prose re-read. Still owed before the graphic and tabular
  pages: the toggles on against off over rotated pages, scored against checked truth.
- **No table page keeps its grid.** 20 table/mixed pages carry a structure verdict: 5 ordered,
  9 scrambled, 7 absent, 0 grid — and 7 of them have clean words. A table's text layer is
  usable for search and useless for reading a row, at any score. Nothing in the display says
  so; whether a table page should say it is the operator's, and it is an argument for the
  HunyuanOCR tabular pass rather than for this re-read.
- **The drafting pass was systematically kinder than the check.** 46 of 53 quality drafts
  agreed, and 4 of the 7 corrections moved a page from `partial`/`noisy` to `garbage`
  (L09, L56, L62, L63). Any future model-drafted label set for this work should be treated as
  a lower bound on the damage until checked.
- **The sample cannot size the record.** Eight pages a cell puts garbage between 16,000 and
  205,000 pages and "at least noisy" between 127,000 and 488,000 (Wilson, 95%). The >=0.7
  band's 866k pages dominate both intervals. The ~100-page top-up of that band is what narrows
  them; until it exists, no coverage figure may be published from this work.
- **`mixed` pages are the worst class** (7 of 9 garbage) and the router has no such class:
  a page that is half map and half prose goes to one reader whole.

## From the top-up sample, 2026-09-17 (`docs/research/text-quality/`)

102 pages above 0.7, labelled twice blind and 31 of them checked by the operator.

- **Model labellers are miscalibrated in BOTH directions, and neither direction is safe.** The
  64-page pass was too kind (4 of 7 corrections moved a page to `garbage`); the two top-up
  passes are too harsh, over-calling faults ~2.5x — he overruled both of them on 8 pages, every
  one `noisy` to them and `clean` to him. They missed nothing he called faulty (0 of 13
  both-clean pages). Any future label set here needs a checked subsample before its rate is
  used; a blind pass alone is a screen, never a measurement.
- **~110,500 of 931,392 judged text-layer pages are faulty (65,300-330,000), about one in
  eight.** 29% sit in the 3.4% the signal flags below 0.5; the rest are spread across the
  0.9+ band, whose SIZE now drives the interval's width. Narrowing it further means more
  labelled pages there, not a better signal — and the operator's time is the binding cost.
- **What "faulty" is up there is not what it is down here.** Above 0.7 the failures are a lost
  signature name, one party name wrong in every occurrence, a fused address — pages that read
  fine and defeat a search for the one term that matters. Re-reading them with OCR is not
  obviously a repair: the text layer is right about the body and wrong about the name.
- **A text layer can be a SUPERSET of its page.** T086 carries three lines that appear nowhere
  on the rendered page (a statement date and two notices). Nothing checks that the layer's text
  is on the page; the display shows it as the page's text.

## From the schema critic on the 0021 quality addendum, 2026-09-17 (branch `text-layer-quality`)

Two of its findings were errors in the MEASUREMENT and are corrected in
`docs/research/text-quality/README.md`: `good` was printed under two denominators
(`hits/word-shaped` in the 18005 table, `hits/letter-bearing` everywhere else — 0.56 against
0.22 for one reading), and garbage recall was 0.92 from a 16-page cell that held no garbage,
against 0.68 once the top-up's 1-in-102 is carried. Both are recorded in the addendum itself
so the correction travels with the decision. What is left open:

- **`class_measurement` cannot name a lexicon.** The addendum makes the lexicon an operand of
  the score, but the measurement registry has no column for it and its identity index has
  none either: a row scored under lexicon B may legally point at a measurement taken under
  lexicon A, and two measurements of one cut under two lexicons on one day collide. Widening
  that key is ADR 0018 D8's, declined 2026-09-01 as a rare same-day collision; the lexicon
  makes a second, likelier instance, because the vocabulary grows with the record. Re-open
  when the quality migration is written.
- **`document_text_display` exposes `asserted_at` but not `superseded_at`, and takes no as-of
  parameter.** So "the display row live on date D" cannot be read from the shipped view, and
  0028 forbids re-deriving the human-over-primary rule against `document_text`. Validation
  query 3 leans on this for text pages TODAY, before any quality row exists; the quality
  addendum is only the first record to rely on it as though done.
- **The operational join is left unbuilt, deliberately**:
  `citation_reading.text_id = text_quality.text_id` would give the citator a re-walk queue —
  edges read off pages the signal flags — on a graph built from numbers read out of that same
  text. Not foreclosed, not argued.

## From the third schema-critic pass on the 0021 quality addendum, 2026-09-17

Three passes, each finding real breaks, twice in the previous pass's own repair. Open against
the third draft; none is acted on, because the scope question above them is the operator's.

- **A new lexicon blanks every warning on the site until the re-score finishes.** The writer
  scores under the live rule's instrument, so the moment a new rule lands no page has a score
  under it — ~1.085M readings, hours of scoring — and decision 14 makes silence read as "no
  fault found". The dated rule's "one INSERT" is true of the cut and the floor, false of the
  lexicon, which is the operand that changes most.
- **Decision 15's suppression is unbuildable as written.** A `text_quality` human row cannot win
  the tie-break (its method is `human`, not the rule's instrument); a `document_text` human row
  does suppress, but only by a person ASSERTING the page's text — thousands of characters they
  did not transcribe — and it silently deletes the page's band sentence too. The record does not
  say which table it meant. Also `review_action_live` is keyed `(queue, target_table,
  target_key)`, so a "this text is misread" report and a "this warning is wrong" report are one
  live row and the second supersedes the first; a new `review_queue_vocab` member separates them
  without touching `search.PAGE_TABLES`.
- **The population is 1,085,292 rows, not ~931k** (judged 931,392 + blank 85,224 + short
  68,676), and no byte figure is given where ADR 0022 measured 365 B/row before accepting
  `document_text`. `/methodology`'s "3.5% flagged" is 3.4% of judged pages and 2.9% of the rows
  that would exist.
- **The owed as-of projection is the thing 0028 forbids.** An as-of view beside the current one
  IS a second copy of the display rule; the only non-duplicating construction redefines
  `document_text_display`, which is `page_fts`'s external content — a full page-index rebuild,
  measured at 27m26s over 1,104,935 rows, behind the wall.
- **No validator moves when a score or a rule lands.** `page_stamp` names `document_text`,
  `document_pagination` and `page_route`; migration 0032 added its terms for exactly this
  reason. Without a term, a rule change alters what every text page says behind unchanged ETags
  and a 300 s public cache.
- **The stored precision is cut-conditional and would sit on rows the cut never touched.**
  Precision 1.00/0.72 is measured over the flagged set; putting `score_row_id` on every score
  row stamps a page at 0.95 with a figure that says nothing about it. Leaving machine rows
  `unmeasured` and gating the sentence in the web tier is the alternative the draft refuses.
- **The lexicon in the blob tier contradicts ADR 0022 D2** ("one artefact goes to the blob tier:
  the engine payload"), and `prune_blobs.py` deletes a local blob 30 days after S3 holds it —
  against a writer that refuses to score without it. A 23,524-word list is small enough to live
  in the store.
- Smaller: the instrument is three repeated TEXT columns (a 64-char digest among them) on
  1.085M rows, where an `instrument` row would intern it; `quality_rule` has no stated
  `rule_id`, no `superseded_by` column and a unique index over no columns; `text_quality_run`
  has no key and no typed outcome vocabulary, which is ADR 0021 D5's own rule; no `run_id` on a
  score; and the § Validation line "nothing derived is published from a score" contradicts
  decision 13, which publishes one.

## From scoring the prose screen on its own population, 2026-09-18 (branch `text-layer-quality`)

The re-read's order is the operator's (prose first), and `text_quality.looks_like_prose` is what
obeys it. Its note claimed "on the 166 labelled pages, recall 0.92 and precision 0.92". Re-scored
read-only over production with the labels separated by who made them, that figure does not
reproduce and was measured mostly off-population; the note now carries the three rows below
instead. Nothing here blocks the prose pass — a queue order that is wrong costs reading order,
not a wrong assertion — but two things are owed if the screen is ever leaned on harder.

- **The screen is effectively unmeasured on the pages it orders.** Of the 166 labelled pages only
  32 are below the 0.5 cut, and only **5 of those are prose**: precision 0.80 (4/5), recall 0.80
  (4/5). The pooled 166-page figure is carried by the ≥0.7 band, which is 134 of the pages and
  where prose is most of the population and easy to spot (blind kinds there: precision 0.95,
  recall 1.00). His 95 checked kinds give 0.89/0.91. **Owed: ~40 kind labels drawn from the
  flagged set itself**, if the screen is to carry a stated rate. The indication it does give is
  worth having and is why the pass is still worth seeding: prose is 5 of 32 flagged pages (16%)
  and roughly 80% of what the screen selects, a fivefold lift in purity.
  **PAID 2026-09-19** — 40 drawn from the flagged set, stratified on the screen's own verdict and
  labelled by the operator on a blind sheet (`docs/research/text-quality/README.md` § The flagged
  set's own kinds). On-population: **precision 0.75 (0.53–0.89), recall 0.66 (0.42–1.00)**, prose
  23.3% of the flagged set (~7,400 pages). The screen may now carry a stated rate. Two figures
  above are corrected by it: the **fivefold lift is 3.2×** (both halves of that division moved),
  and the composition of the flagged set is **tables first at 37%**, not maps — the 32-page read
  came from a band × era draw and was never a population estimate. Recall still swings on two
  labels; a wider draw is the only thing that narrows it, and nothing needs it yet.
- **71 of the 166 kind labels are unchecked model labels**, which is the thing the operator's own
  rule forbids being turned into a rate ("model labels are a screen, never a measurement"). The
  quality labels in this directory were kept honest about this; the kind labels behind the screen
  were pooled without the distinction. The separation now lives in the module's note.
- Smaller, fixed in place rather than deferred: the precision/recall table printed a raw sample
  count inside a population-weighted precision cell, so `0.80 (42/48)` invited a division that
  gives 0.875; and the queue builder's docstring read as though 6,170 prose pages sat in 4,896
  documents, which is the count for all 31,798 flagged pages (the prose subset is 1,501).

## From building the text-layer re-read pass, 2026-09-18 (`reread`, schema-critic + `/code-review`)

The operator gave the go for the prose re-read and chose a page-list seed over routing the
documents. Building it found that routing is not optional, and both reviewers found it
independently. The pass is committed, guarded so it cannot be seeded, and the two things below
the first are owed before any reading from it is loaded. Acted on in the same commit: the
`ROOTS`/root-name mixup (a real `KeyError` waiting for `tabular`'s first partial re-seed), the
silent drop of newly-listed pages on re-seed, `seeded_from` separated from `class`, and the
backwards claim about `document_text_live` in the pass's own comment.

### Closed the same day

- **A re-read page had no routed class, and the store refuses such a reading.** `text/load.py`
  raises "an OCR reading names the class it was routed as (ADR 0021 D4)" and
  `CHECK (reading_channel <> 'ocr' OR route_class IS NOT NULL)` refuses the row; every page read
  would have been machine time thrown away. **The operator chose to route the pages first**
  (2026-09-18), so `ocr_wave.py route-list` routes a page list with the layout model alone, into
  the re-read's own route root, and the seed skips anything unrouted. The alternatives were
  worse: a new `route_class_vocab` member would overload a *tier* vocabulary with a *selection
  reason*, and relaxing the CHECK is a rebuild of a 1.4M-row table.
- **The disjointness guard the critic asked for is half-built**: the two passes now read
  different route roots, so a text-layer document cannot reach `dots` through a route document.
  Nothing still asserts that no document is both image-only and text-layer.

### Open — owed before a reading from this pass is loaded

- **Loading would change published text on every re-read page, with no dated rule.**
  `store/pages.py:band` LEFT JOINs the live `second` row whatever its channel, so a re-read row
  with no agreement turns "Read once; no second reading to compare it with, so no band." into
  "A second reading exists (dots.mocr 1.5); its distance from this one has not been computed, so
  no band." on `/text`, in search hits (`store/search.py`, `store/finder.py`) and through MCP
  (`web/mcp.py`). It contradicts ADR 0021 D8's "a text-layer page has no band and says so", and
  it is not replayable: `_SELECT` has no `superseded_at` term and `document_text_display` has no
  as-of form — the gap the withdrawn 0021 addendum already records.
- **The agreement distance is not a computation, it is a publishing decision.** Computing it
  makes `band()` print a number as a band on ~31,800 public pages using a **cross-channel**
  instrument: the measured AUC 0.93–0.97 was two *engine* readings at one tier, and the research
  README's own 0.59 against engine readings points the other way. A text-layer-versus-engine
  distance has been measured at nothing. Computing it later is also a supersede-and-reinsert of
  every row, not an UPDATE (`document_text.text` is immutable by trigger), and needs the reading
  documents re-collected, because the loader only writes an agreement the file quotes.
- **`second` spends the page's one `second` slot.** `document_text_one_second` is unique per
  live page, so the re-read takes the slot where the cheap second reading that catches invention
  would have gone — and dots.mocr is itself a VL model, so a re-read that invents is
  indistinguishable from one that repairs. Suggestion from the critic, worth weighing: run the
  ~6,170 prose pages, take the promotion decision with them in hand, and do **not** run the
  remaining ~25,600 until it is taken.
- **Promotion has a citator cost nobody has priced.** Under ADR 0026 a `citation_reading` names
  its `text_id` and staleness is detected over `document_text_display`. Promoting the re-read
  retires every text-layer primary on those pages at once, so every edge read off them goes
  stale in one step — a bounded but real re-walk.
- **The reading records no reason for its own existence.** `text_quality_queue.py` writes the
  scored `text_id` as the CSV's first column and the seed throws it away; `job` has no column
  for it and the reading document carries no trace of the score, the cut, the lexicon or the
  screen. Every other reading in `document_text` says why it was read that way (`route_class`
  with its method and version). Carrying `text_id` into `agreement_against` would make the
  binding a row rather than a note — and it is unrecoverable once a text-layer primary is
  superseded between seed and load, which a pymupdf bump through `repoint_producer` does.
- **Nothing asserts that no document is both image-only and text-layer**, which is the only
  thing keeping `dots` and `reread` off the same page. When it is violated the loader refuses
  the whole document's reading, not the one page. Cheap guard: have `seed_from_list` refuse a
  sha that has a route document.
- **`ocr_run` is published and has no `reading_role`** (`dump.py`, ADR 0022 D3), so the key
  `dots.mocr/1.5/200` now means two things — a primary reading of a degraded scan and a second
  reading of a suspect text layer — and a third party summing `pages_read` cannot tell them
  apart. Half the pages counted are displayed to nobody.
- ~~`fleet-up.sh` has no `reread` role~~ — built once the shape settled: a `reread-collect`
  service on the coordinator and a `reread` worker role sharing the `dots` server and key, with
  its own stop file (`.stop-reread`). The two workers share one card, so the role is opt-in and
  never part of `worker` or `all`, as `tabular` is.

## The fleet's blob mirrors are stale, not holed, 2026-09-18 (tabular pass, v2026.09.28)

Measured while reporting on the running pass. **728 pages across 310 documents had failed
`blob: missing on the node`** — after the page-owned `finish_reason length` failures (1,324),
essentially the entire remainder of the pass's 11.4% failure rate.

- **Nothing is lost.** None of the 310 are on the coordinator, but **all 310 are in S3**
  (`docketyard-prod`, `blobs/<aa>/<sha>`), 190.4 MB in total, checked by `head_object` on every
  one. The earlier reading of this — 434 documents "in NEITHER blob mirror, so no node reads
  them this seed" — was right about the mirrors and wrong about the record. S3 is the store and
  the mirrors are caches (`infra/deploy/README.md`); these caches simply lag.
- **The coordinator cannot refill its own mirror.** `rmi-nuc` holds the blob mirror the fleet
  reads through and has `boto3`, but no `~/.aws` credentials; `rmi-ai-machine` has the
  `docketyard-reader` profile and `pull_blobs.py`. So the box that owns the mirror cannot fill
  it, and the box that can fill it is the one we keep saying is stateless and replaceable. That
  asymmetry is the defect, not the missing bytes — and it bites harder once the card moves or
  the workstation is swapped for a 5090.
- **These pages cannot be recovered in the running seed.** `pagequeue` has `seed`, `collect`,
  `status`, `reap` and `fail` — there is no requeue verb, and a `blob:` failure that has spent
  its attempts is `failed`, which the design intends: re-read at a later seed. Resetting them
  would be hand-written SQL against a live queue. The designed path is a later seed, once the
  mirror is filled.
- **Cheap guard worth pricing: the seed does not check that it can read what it seeds.**
  `seed --dry-run` reports how many pages and documents it would queue, but nothing verifies
  the blobs are reachable from the nodes that will claim them. A presence check at seed time —
  local mirror, then S3 — would have surfaced 310 unreadable documents in seconds instead of
  728 spent attempts over two days. It is the same shape as the endpoint rule in `CLAUDE.md`:
  positively assert the precondition rather than infer it from a result that also has an
  innocent explanation.

## Two `series` shapes ride in one docket JSON, 2026-09-18 (v2026.09.28, shape 3)

Found while locking the docket-level JSON keys (the graders' I4). A sub-docket's response
carries **two keys named `series` with different shapes**:

- `series` at the body level is the full reference — `{raw_docket, printed, url}` — shaped
  deliberately by `sheet_json`, with `raw_docket` in the store's own spelling because
  `canonical()` renders a family as `FD_36873_0`, which no address resolves (code review,
  2026-09-01).
- `docket.series` is `{raw_docket}` alone, and nobody shaped it: it falls out of `asdict()`
  on `sheet.DocketSheet`, whose `series` field the route never pops the way it pops
  `parties`. A client reading the inner one gets `FD_36873` with no printed form and no
  address, and has no way to know the outer one is richer.

Locked as served rather than corrected — narrowing or dropping a published key is a shape
decision, not a test's to make, and `shape_version` 3 is live. The options when it is
chosen: pop `series` from the docket object (a removal, so a bump), or fill it to match the
body's three fields (additive, which the API page's promise allows without a bump). The
second costs nothing and makes the two agree; the first is cleaner and cannot be done
quietly. **The operator's call.**

## A pass cannot be declared deliberately down, 2026-09-18 (the 5090 swap)

The tabular pass was stopped cleanly for a card swap, and the fleet had no way to say so.
STALLED fired thirty minutes later — correct by its own rule (pages owed, none read) and
useless, because the condition was intended. `/health` served 503 for the whole window.

- **There is no quiet way to quiet it.** `monitor.py` only reports; the rules are evaluated
  off the box by design (ADR 0019 — "a dead box cannot report its own death"), so the silence
  belongs in the alerting side, outside this repo. Raising `--stall` hides the next real
  stall and needs somebody to remember to put it back. Stopping the monitor is worse than
  either: the off-box rules include *the series absent altogether*, so it swaps one alert for
  another and blinds the operator in between.
- **Production already has the concept and the fleet does not.** ADR 0020 gave the instance a
  maintenance mode; a pass has no equivalent. The shape that would fit: a `paused` marker
  beside the stop file that the monitor reads, exposed as its own series
  (`docket_yard_fleet_paused{pass}`) rather than by suppressing the stalled one — so the
  reason is published, dated, and visible, instead of an alert silently not firing. The
  stop file is nearly this already; it records the intent and nothing reads it.
- **Why it matters beyond tidiness:** an alarm that is right, unactionable and recurring is
  how an operator learns to ignore the alarm. The pass was down about an hour today and the
  fleet will be stopped and started far more often once the broker arbitrates it, which makes
  this more frequent, not less.

## Stats deferrals, graduated from TODO 2026-09-18 (v2026.09.28)

Parked in `TODO.md` and recorded here instead when the plan cap fired — they were the only
two items in that file held nowhere else.

- **One month walker for `home.py` and `stats.py`.** The two walk the record's months
  separately for their own figures; one walker would serve both and be measured once.
- **No index on `filing(filed_date)`.** Every date-ranged filing query — the coverage page,
  `count_filings`, `list_proceedings` — scans. Not felt at 54,422 filings; worth having before
  the backfill's later waves land, and worth measuring rather than assuming.

## From mapping the queue end to end, 2026-09-19 (the stopped tabular pass)

Found while mapping where every artefact of the pass lives, before deciding whether the
coordinator moves. Neither is a wrong assertion in the record today.

- **`dtype` is not in the producer declaration.** A worker declares the pass key, its host,
  the engine and version, the model and its weights revision, the max new tokens, the
  megapixel bound and the render (`hunyuan_worker.py` § producer) — but not the dtype.
  `ocr_run.load_hunyuan` hardcodes `bfloat16`, so every reader is bf16 today and the gap is
  latent, not live. It bites the moment a pre-Ampere card is added: Turing has no hardware
  bf16, and "fixing" that with float16 would declare an **identical reading key while reading
  differently** — the silent key split ADR 0023 exists to prevent, arriving from inside this
  project rather than from the broker. Live because the coordinator's own unused card is
  Turing. Adding dtype to the *declaration* is additive and forward-only; adding it to the
  *key* would invalidate every reading, so the two must not be confused.
- **The stale-mirror defect has a second remedy nobody had costed.** Measured 2026-09-19:
  the instance already holds 112 GB of blobs and already serves any document by hash, with an
  S3 refetch on a cache miss and the hash verified. So a reader could fetch document bytes
  without any mirror and without any credential on any fleet box, which would retire the
  `docketyard-reader` asymmetry recorded above rather than paper over it. **It is not free:**
  `docs/compute-fleet.md` says "Production never joins the fleet", and having the instance
  serve the fleet's bytes crosses that sentence, so it is an ADR amendment and not an
  implementation detail. Recorded as an option, not a plan.

## From the schema critic on the ADR 0025 addendum, 2026-09-19 (Proposed)

Folded into the addendum where it was wording; these two are code and are filed.

- **A restore whose queue is newer than its file tree silences documents, permanently.**
  `_decide` returns on `known == "whole"` (`pagequeue.py:639-641`) **without checking that the
  reading document exists** — while the `reread` branch just below it checks deliberately, with
  a comment saying the queue's verdict stands either way. So a coordinator restored from a
  queue snapshot taken after its file tree marks those documents whole, never re-queues them
  and never collects them: silent, per-document, and the 2026-09-06 shape again. The operator's
  procedure can avoid it — **restore files first, then the queue** — but a three-line fall-
  through to the `reread` verdict when `shard()` is absent would make the order not matter.
- **A worker's registration overwrites its own producer on every restart.**
  `register` is `ON CONFLICT (name) DO UPDATE SET producer = excluded.producer`
  (`pagequeue.py:240-245`) on a name defaulting to `<host>/<pass>`. The producer is published
  only in the root's `_manifest.json`, and `result.worker` — the page→worker link — is selected
  at collect and never used. So if the environment moves between restarts (a transformers
  upgrade, a re-pulled snapshot, a different card behind a pinned `--name`), the manifest names
  the **new** producer for pages read by the **old** one, which under ADR 0007 is a derived
  assertion whose method block was rewritten after the fact. Latent today because the fleet
  restarts rarely and by hand; **brokered placement makes restarts frequent and chosen by
  something else**, which is what moves this from tidy to load-bearing. The critic's shape:
  an append-only `worker_registration` row per distinct producer, `result.registration_id`, and
  `collect` writing the producers observed on that document's own pages.

## From reviewing the seed's missing-reading fix, 2026-09-19 (`/code-review` + stb-ingest-specialist)

Both passes called the change correct and shippable. Two findings are choices, not defects.

- **Re-reading is the expensive correct verdict, and a cheap one exists behind a guard.** When
  a restore leaves the queue newer than the file tree, the queue is by definition the surviving
  artefact — and it still holds every page's raw engine answer in `result`, written at `done()`
  before anything parses it. The fix throws those rows away at the next seed and spends GPU time
  re-reading pages already read; applied corpus-wide by a skewed restore that is up to 26,294
  pages for `tabular` alone. It also churns the store: a re-read is not bit-identical across
  kernels, so every page whose text differs retires a live row and inserts a replacement, with
  an FTS delete and insert, over text that was already correct. **The cheap verdict:** delete
  only the `collected` row, leave jobs and results, and let the next `collect` rebuild the
  identical file from `pages_of` with no machine time. **It is only safe under a guard** — the
  route document may have been re-run since, so the pages the queue holds may no longer be the
  pages the pass owes, and a naive recollect would rebuild over a stale page set and then report
  `whole` with the file present, silent again in the same class. `seed_from_list` already has
  the comparison (`pages_held`); `seed_pass` has `wanted` in hand but does not pass it to
  `_decide`. Recollect when the held page set equals what the pass now owes, re-read otherwise.
  Not taken today: the current behaviour is safe, and the restore order is the mitigation.
- **A narrowing list plus a missing reading document drops a held page.** The new branch reaches
  `seed_from_list` untested. Its top-up path queues `(held | wanted) & routed`, but `_decide`'s
  set-aside path leaves the caller queueing `sorted(wanted[sha])` alone — so under a *narrower*
  list the rebuilt reading document is narrower than the one that went missing, and the dropped
  pages' rows stay live in the store from the older run with no queue record. Confirmed in the
  review by running it: `pages_held` goes {1,2} → {1}. The store is not corrupted — page-level
  supersession makes it legal — and a narrowing list is the operator's own cut moving, so this
  is recorded rather than changed. Either queue `(held | wanted[sha]) & routed` on this path
  too, or say in `seed_from_list`'s docstring that a narrowing list is taken at its word.

## From the specialist on the stop signal, 2026-09-19 (ADR 0025 addendum proposal 1)

The two findings that could lose or misattribute a page were fixed in the same change. These
three are recorded rather than built.

- **`wait_for_server` ignores both the stop file and the signal**, and a document claims the
  opposite. `dots_worker.wait_for_server` loops up to `--server-wait` 1800 s with no stop
  check, so an operator's `touch .stop` does not stop a reader waiting on a dead server, and a
  preempted one is killed rather than exiting 0 with its marker. Nothing is lost — nothing is
  leased at that point — but `workstation-gate.ps1` states in its own header that the stop file
  is checked "before each page **and instead of waiting for a server**", which is behaviour the
  code does not have. Pre-existing; the fix is to pass the predicate into the sleep loop.
- **A brokered placement and `fleet-up.sh`'s restart loop must be mutually exclusive by
  construction, not by care.** The loop restarts a worker a minute after ANY exit, so a reader
  a broker just preempted goes back on the card sixty seconds later, overriding the placement
  the broker made. Written into `docs/compute-fleet.md` as a rule; nothing enforces it. Related:
  exit 0 now means three different things (queue drained, stop file, preempt) and only the
  third prints a marker — **the owed resubmitter must key off the broker's `preempted` state or
  the `jobd-checkpoint-complete` line, never the exit code.**
- **A forward hazard to record before anyone closes the grace gap.** The obvious next step for
  "a page that outruns the grace" is a transformers `StoppingCriteria` wired to the stop flag.
  If that is ever added, the generation ends with `ended_with_eos=False` and
  `new_tokens < max_new_tokens`, so `generation_failure` returns None and the **truncated**
  answer is posted as `done` — a silently short reading with no failure row, which is the
  2026-09-06 shape. An interrupted generation must be released unspent, never posted.

## The mirror is expendable; the results are not — the operator, 2026-09-19

**His decision, and it settles what a coordinator move has to carry.** The fleet's blob mirror
is a cache of a store that is always retrievable (ADR 0022 D2: S3 is the store, a mirror is a
cache), so the 109 GB does not travel and does not need refilling before a move — it warms, or
it is simply not there. What must be where it belongs is the **derived** half.

Where each result sits, measured 2026-09-19:

- **In the store, replicated:** the `dots` and `ppocr` readings. Safe; nothing owed.
- **On disk only, never loaded:** 2,578 collected `hunyuan-tabular` documents. Loading them is
  the operator's go (`docs/compute-fleet.md`), not yet given.
- **On disk only, and with no home in the store at all: the route roots** (27,269 documents).
  Seeding copies each route document's own method and method version into every page of every
  reading, so for a page that has been read AND loaded the classification survives in the
  store. For a page that has not, it exists nowhere else — and the tabular pass alone holds
  **9,019 unread pages** (6,799 pending, 2,220 failed). This is the artefact that wants an
  off-LAN copy permanently, not the queue and not the blobs.
- 16 raw answers in `queue.sqlite` belong to documents not yet written out.

**Resuming and making the backup routine are one decision.** The 2026-09-19 snapshot is valid
only because nothing has read since 2026-09-18 20:28Z. Once a pass runs, the coordinator
accumulates irreplaceable results continuously and a pre-resume copy decays by the hour.

## Correction: the route roots are expensive, not irreplaceable — 2026-09-19

Written the same day as the claim it corrects, because it reached an ADR, this file, `TODO.md`
and the fleet's private notes before anyone checked it against the code.

**The claim was that re-running the router "is not reproduction — it orphans the provenance
already quoted by every reading collected under the old one."** `_page_routes`
(`tools/fleet/pagequeue.py`) says the opposite in its own docstring: it carries "the route
document's OWN method and version rather than this module's constants — a document routed by an
earlier version must say so, which is what makes the reading scorable (ADR 0007)". **Mixed
router versions are a designed-for state, not a broken one.** And for a page already read and
loaded, the class and method are copied into the reading, so the route document is redundant
for it.

What is actually true, and what should be said instead:

- Re-running the router costs a layout-model pass over the corpus, and yields a **different
  method version**. That is recorded per page rather than hidden.
- A page reclassified on the way changes what each pass owes its document; the seed already
  handles that by re-reading, at the cost of the reading.
- The expensive artefact is the **readings**, not the routes: 17,275 tabular pages already read
  is roughly 43 hours of GPU at 9 s a page.
- **All of it together is 464 MB.** Keeping it across a rebuild is a tar file, not a
  constraint on how the machines are built.

I took a reviewer's framing and propagated it without checking the code, which is the failure
`claims-are-not-measurements` names. The figures in this file's 2026-09-19 entries stand; the
word "irreplaceable" does not.

## From the specialist on the coordinator backup, 2026-09-19 (ADR 0025 addendum proposal 3)

Fourteen findings; the ones that could let a wrong backup look right were fixed in the same
change. These are recorded instead.

- **The addendum contemplates two cadences and the tool has one.** Item 3 says "The route roots
  are copied **most often**", and `backup.py` copies everything on one rhythm because the whole
  archive is 636 MB and splitting it would buy little. Defensible, but it quietly collapses a
  distinction an Accepted record drew — **the operator's to settle**, either by adding a
  selector or by amending the item.
- **This is the second exception to decision 6's literal words, and only the first is written
  down.** D6 says "no node holds the store or a key"; the 2026-09-19 addendum sharpens that to
  "no node can **write to the store**" and sanctions a read-only `GetObject`+`ListBucket`
  credential. `fleet-backup-writer` is a *write-capable* key on the coordinator — scoped to one
  bucket that is not the store, with no delete action — which is consistent with that reading
  but is not stated anywhere. One sentence in the addendum would close it, so the next box is
  reasoned about rather than quietly excepted.
- **A restore procedure is owed**, beside `docs/compute-fleet.md`'s backup entry: extract order
  (the archive already carries it — the queue is the last member), `--no-same-owner`, and the
  fact that `fleet.token` and `fleet-node` are deliberately **not** in the archive and must be
  replaced by hand. A rebuilt coordinator needs that token from the password manager.
- Smaller, fixed in place rather than deferred: the queue snapshot is genuinely atomic
  (`Connection.backup` with the default `pages=-1` copies under one read transaction), so the
  docstring's earlier "a hash can never prove fidelity to a database that moved" was more
  pessimistic than the mechanism — the pessimism would have become TRUE had anyone later
  "improved" it into a chunked loop, which is why the reason is now written beside the call.
