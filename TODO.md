# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## In motion

- **The citator is loaded** (v2026.09.15): 15,535 edges, 9,863 naming a document, none shown;
  exposed 1,476. **Next the review page, for a person**: easy, explained, one look settling
  docket, sub-docket and document, linked to scan, text, both dockets and the matched document,
  over a queue of only what can publish, with an ICC flag for `(ICC served …)`. Same-docket
  filings and decisions must be citable (his). GATED on the citations brief's four questions.
  `panel_check_sheet.py`'s card composition is the spec to fold in (untracked, deliberately)
- **Owed with the citator's pipeline**: the "not in the record" display joining live
  `citation`; the veto's trigger; a consumer for ADR 0023's pick rule (`cite.py` sends `decided`)
- **THE CITATOR HAS NEVER READ THE OCR CHANNEL** (measured 2026-09-12). Both `extraction_run`
  passes are `text-layer` only (19,944 documents) while `ocr` text has been live since
  2026-09-05: 1,022 decision-carried documents / 7,386 pages had unfound citations, before
  today's loads superseded 4,297 more text-layer primaries — re-measure, then
  `citator walk --channel ocr` and load. No engine, no migration. **After ADR 0026 if he
  accepts it**, so those readings carry `text_id` from their first row
- **37 decision-carried documents hold no readable text** (43 pages): all PDFs, correctly read
  blank by pymupdf, **36 never OCR'd** — mostly AB 290 (12) and AB 33 (6), 1996-2019; one where
  `dots.mocr` failed and PP-OCRv6 read it blank. Why `image_only_documents` missed them: unknown

## Next

- **The panel clears 9.7% of the real 1,476, and 66.5% of the queue is CAPTIONS** (measured
  2026-09-11, `docs/extraction-benchmark.md`; he judged 40 — 39 captions, 0 citations). The
  QUEUE PREDICATE is the fix and not the finder: `citation_exposed` filters on the exposure
  judgement and not on `kind`, needs no schema change, and is what stands between him and a
  small queue. Switching panel clearing on is an ADR 0017 addendum, his
- **ADR 0026 is Proposed and WAITING ON HIM** (2026-09-12): a citation reading names the text
  it read — `text_id` FK plus `text_ref`, staleness over the display view, the live key held on
  a measured price, `{page, spans}` with a per-span raw, `superseded_at` on a forward-only
  trigger, a rebuild and a re-load behind a maintenance wall. Two schema-critic passes, nothing
  left to break. **On acceptance**: a branch and a PR (Copilot and Codex review), plus
  stb-ingest-specialist and `/code-review` on the loader path
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
