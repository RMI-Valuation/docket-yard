# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## In motion

- **Retraction leaves its readings live — DECIDED 2026-09-13, drafting.** Measured on a restore
  taken after the OCR load: 903 live readings on keys with no live `citation` (all text-layer,
  `pre-0026`, finder 2026-09-01; 0 decided; 779 docs; 768 to a successor, 135 at itself), plus 903
  resolutions and 2,709 judgements; 0 pages changed channel. ADR 0018 D2 says a retraction retires
  `citation` alone, so this is an addendum. His picks: retire READINGS with the citation (the rest
  later, `deferred.md`); a per-reading RETIREMENT ROW (method, version, date, reason); the 903 in
  the MIGRATION, behind the wall. Next: addendum draft, schema-critic, migration, rehearsal
- **The citator is loaded** (v2026.09.19, rank v4): 25,777 rows, 22,547 edges, none shown; exposed
  428. **The review page, for a person**: docket, sub-docket and document in one look, linked to
  scan, text, both dockets and the match; same-docket filings citable (his); an ICC flag. GATED on
  the citations brief's 1-3; `panel_check_sheet.py`'s composition is its spec (untracked)
- **Owed with the citator's pipeline**: the "not in the record" display joining live
  `citation`; the veto's trigger; a consumer for ADR 0023's pick rule (`cite.py` sends `decided`)
- **37 decision-carried documents hold no readable text** (43 pages): all PDFs, correctly read
  blank by pymupdf, **36 never OCR'd** — mostly AB 290 (12) and AB 33 (6), 1996-2019; one where
  `dots.mocr` failed and PP-OCRv6 read it blank. Why `image_only_documents` missed them: unknown

## Next

- **His 39 judged captions**: finder 2026-09-11 called 16 of them `citation`, so they stayed
  queued; not yet re-measured under the family closure (live since v2026.09.18)
- **Next finder version (his decisions of 2026-09-13, `docs/deferred.md`)**: the resolver's
  FALLBACK anchor (strict key first, the family only when that finds no date: FD 34554 gains 35093,
  EP 575 keeps 36758) and a fused-footnote rule keying a six-digit number to the document's own
  docket (346 of 352 are own captions). Branch + PR, card, rehearsal, re-load
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
