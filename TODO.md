# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## In motion

- **Retraction leaves its readings live** (v2026.09.16 deploy, 2026-09-13). `load`'s retraction
  supersedes only the `citation` row, so 903 `citation_reading` rows of keys v2026.09.15
  retracted are still live and `'pre-0026'` (finder 2026-09-01; none projects, since every
  consumer joins a live `citation`). He ACCEPTED them as residue and took the wall down. Owed:
  retire a reading with its citation, a method and `superseded_at` for the 903, and review
- **The citator is loaded** (v2026.09.18, rank v3): 19,393 rows, 16,766 edges, none shown; exposed
  505. **The review page, for a person**: docket, sub-docket and document in one look, linked to
  scan, text, both dockets and the match; same-docket filings citable (his); an ICC flag. GATED on
  the citations brief's 1-3; `panel_check_sheet.py`'s composition is its spec (untracked)
- **Owed with the citator's pipeline**: the "not in the record" display joining live
  `citation`; the veto's trigger; a consumer for ADR 0023's pick rule (`cite.py` sends `decided`)
- **The OCR walk** (1,022 documents; `load` refuses it, `Unscored`): his decisions of 2026-09-13
  in `docs/research/ocr-citation-benchmark/` — 98 documents drawn, 548 pages, drafted (813 rows),
  check pages built; truth = rows whose page PRINTS a docket. WAITS ON the long-form finder, then
  his check, `citation_dryrun.py` on `ocr` over the labelled pages, card, rank, load
- **The finder cannot read `Finance Docket No. N` / `Ex Parte No. N`** (2026-09-12's): 6,028
  (page, docket) held citations missing from the text layer, 4,078 from 1996-2005. **Closed
  before the OCR card (his decision)**: branch `finder-long-forms` (rank v4, card 226; 217/221),
  a ~100-citation gate at 87.5% (`docs/research/long-form-check/`), ADR 0017 addendum PROPOSED
  for him; then PR, text-layer re-load (ROADMAP § Chosen)
- **37 decision-carried documents hold no readable text** (43 pages): all PDFs, correctly read
  blank by pymupdf, **36 never OCR'd** — mostly AB 290 (12) and AB 33 (6), 1996-2019; one where
  `dots.mocr` failed and PP-OCRv6 read it blank. Why `image_only_documents` missed them: unknown

## Next

- **His 39 judged captions**: finder 2026-09-11 called 16 of them `citation`, so they stayed
  queued; not yet re-measured under the family closure (live since v2026.09.18)
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
