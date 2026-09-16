# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## In motion

- **The citator is loaded** (v2026.09.19, rank v4): 25,777 rows, 22,547 edges, none shown; exposed
  428. **The review page, for a person**: docket, sub-docket and document in one look, linked to
  scan, text, both dockets and the match; same-docket filings citable (his); an ICC flag. GATED on
  the citations brief's 1-3; `panel_check_sheet.py`'s composition is its spec (untracked)
- **Three schema PRs (2026-09-15), all findings fixed, ALL THREE REHEARSED** in production's image
  (v2026.09.24, SQLite 3.46.1) on a restore, in number order: #35 `veto-trigger` (0030, ee7e2ac,
  precheck 0 rows, 4.4 s), #37 `ocr-page-failure` (0031, ebf7cc5, 3.7 s), #36 `page-route` (0032,
  71a4278, 3.6 s). Additive throughout: no row moved, fk clean, no temp left; figures on each PR.
  Merge in number order; each addendum is Proposed, his to accept
- **HunyuanOCR tabular pass, PR #34** (67b1762): parity probe PASSED, 4070 empty (9 MiB), dots
  sessions stopped. Seed measured from the coordinator's route root: **26,294 pages in 3,385
  documents** (1,616 one-page, 104 over fifty, largest 536). At the probe's 3.3-10.3 s/page that
  is **roughly 36-48 h** on one 4070. **Starting it is his** (a seed with no worker reading pages
  the monitor as STALLED from the first scrape)
- **Claude batch for the 134 pages dots refused: COLLECTED and the load REHEARSED** on a restore —
  98 documents, `loaded: 98`, +134 `document_text` (ocr/claude-sonnet-5/200-max2576-grey primary,
  unmeasured), +98 `ocr_run`, 98 blobs (1.35 MB); it supersedes 134 `text-layer`/pymupdf primaries,
  121 of them empty and the other 13 holding only the STB's 9-char e-filing stamp, which the new
  reading keeps. 554,016 characters where 121 pages showed nothing. No pin needed (the OCR channel
  is unpinned by design), no human row touched, no migration. **Loading waits for his go**
- **Decided dates: measured** (`deferred.md` § 2026-09-15) — his call what to build

## Next

- **Party types, the held-out sheet is WITH THE OPERATOR** (2026-09-10,
  `docs/research/party-types/held-out/`). When his Copy block returns: apply both picks, score
  `party_types_rules.py --sheet` at 95% per type on the FIRST pick, then the assertion
  migration (schema-critic first) and the browse on `/parties`
- With the operator: a sheet's JSON-LD block in Google's Rich Results test, from a browser
- ADR 0024 Owed 2, the per-page failure record — HIS CHOICE to build (2026-09-15): addendum
  draft for the shape, schema-critic, his acceptance, then a branch
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
