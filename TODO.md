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
- **The citator is loaded** (v2026.09.15): 15,535 edges, 9,863 naming a document, none shown;
  exposed 1,476. **The review page, for a person**: one look settling docket, sub-docket and
  document, linked to scan, text, both dockets and the match; same-docket filings and decisions
  citable (his); an ICC flag for `(ICC served …)`. GATED on the citations brief's 1-3.
  `panel_check_sheet.py`'s card composition is the spec to fold in (untracked, deliberately)
- **Owed with the citator's pipeline**: the "not in the record" display joining live
  `citation`; the veto's trigger; a consumer for ADR 0023's pick rule (`cite.py` sends `decided`)
- **The OCR walk waits on the family closure** (his decision, 2026-09-13). Re-measured from the
  shipped `find` (00:40 UTC): 1,022 documents, 7,430 pages, 683 citations + 937 captions. NO
  OCR-channel measurement exists, so `load` refuses it (`Unscored`) and OCR needs its own
  `rank_version`. Order: land the family closure (branch `finder-family-closure`, built and
  reviewed; card `data/card-2026-09-12.json` = 224/255, 218/246, 216/220, work 140/140 against
  the old finder's 257/248 on the same registry; rehearsal, runbook section, PR owed), THEN an
  OCR citation sample he judges, measure, rank, load
- **37 decision-carried documents hold no readable text** (43 pages): all PDFs, correctly read
  blank by pymupdf, **36 never OCR'd** — mostly AB 290 (12) and AB 33 (6), 1996-2019; one where
  `dots.mocr` failed and PP-OCRv6 read it blank. Why `image_only_documents` missed them: unknown

## Next

- **The queue predicate SHIPPED in v2026.09.17** (2026-09-13, verified live: 854 / 1 / 502).
  Left: of his 39 judged captions the finder calls 16 `citation`, so they stay queued — the
  family closure in `stash@{0}` is the likely lever. And finder 2026-09-01's 73,212 `kind`
  judgements are still live beside 2026-09-11's, the supersession keyed by version
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
