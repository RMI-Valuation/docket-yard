# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## In motion

- **FIRST: ship PR #26** (ADR 0026, migration 0028), built and reviewed: merge, tag
  v2026.09.16, deploy behind the wall with the re-load in the same window; acceptance is zero
  live `text_ref = 'pre-0026'`. **Stop rule** (his, 2026-09-12): further P2 hardening against
  hand-built or damaged findings files goes to `docs/deferred.md`; a P1/P0, or anything `walk`
  can produce, is still fixed before the merge
- **The citator is loaded** (v2026.09.15): 15,535 edges, 9,863 naming a document, none shown;
  exposed 1,476. **The review page, for a person**: one look settling docket, sub-docket and
  document, linked to scan, text, both dockets and the match; same-docket filings and decisions
  citable (his); an ICC flag for `(ICC served …)`. GATED on the citations brief's 1-3.
  `panel_check_sheet.py`'s card composition is the spec to fold in (untracked, deliberately)
- **Owed with the citator's pipeline**: the "not in the record" display joining live
  `citation`; the veto's trigger; a consumer for ADR 0023's pick rule (`cite.py` sends `decided`)
- **THIRD: the citator has never read the OCR channel** (measured 2026-09-12). Both
  `extraction_run` passes are `text-layer` only (19,944 documents) while `ocr` text has been
  live since 2026-09-05: 1,022 decision-carried documents / 7,386 pages, widened by today's
  loads — **re-measure**, then `citator walk --channel ocr` and load. No engine, no migration.
  Third in his order (2026-09-12) so the readings carry `text_id` from their first row and the
  queue predicate is already fixed: OCR text is noisier, so it adds more noise per document
- **37 decision-carried documents hold no readable text** (43 pages): all PDFs, correctly read
  blank by pymupdf, **36 never OCR'd** — mostly AB 290 (12) and AB 33 (6), 1996-2019; one where
  `dots.mocr` failed and PP-OCRv6 read it blank. Why `image_only_documents` missed them: unknown

## Next

- **SECOND: fix the queue predicate** (his decision, 2026-09-12). `citation_exposed` filters on
  the exposure judgement and not on `kind`, so 66.5% of 1,476 are captions that can never
  publish (two models agree on 981; he judged 40 and found 39 captions, 0 citations). Fixing it
  takes the queue to roughly 495. No schema change, no ADR, no re-read — a query change plus
  `/code-review`. Switching panel clearing on is a separate ADR 0017 addendum, his
- **Party types, the held-out sheet is WITH THE OPERATOR** (2026-09-10,
  `docs/research/party-types/held-out/`). When his Copy block returns: apply both picks, score
  `party_types_rules.py --sheet` at 95% per type on the FIRST pick, then the assertion
  migration (schema-critic first) and the browse on `/parties`
- With the operator: a sheet's JSON-LD block in Google's Rich Results test, from a browser
- ADR 0024's stage: a per-page failure record is still owed (Owed 2)
- **Held by the operator for rewording (2026-09-11)**: `/methodology`'s text-stage section
  (`848e366`) and the one-day-rest sentence (`3b538bc`); § Documents has his narrowed one
- The workstation gate's ONLOGON task is still unregistered (`deferred.md`)
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Deadline engine (C4): no obligations in decision JSON; fixture of 8 in `docs/deferred.md`

## Parked

- **Docket summaries (P6) and the AB status facet are specified, not chosen**
  (`docs/summaries.md`, 2026-09-10): the fifty-document sample is what a decision starts;
  the rule-only status slice (800 consummations, 714 trail-use filings) could go first
- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
