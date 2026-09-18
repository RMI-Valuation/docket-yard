# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## In motion

- **v2026.09.28 LIVE** (tag change: a Search link in the masthead). **v2026.09.27** 2026-09-17 15:25 UTC (schema 33, `INDEX_FORMAT` 4; behind the wall
  15:20:10-15:25:34, restore point 15:20:10Z): search built out (PR #41). On the instance `the`
  unfiltered also reaches the 1.5 s budget and leaves page text out. The fleet still runs `67b1762`
  until redeployed; the tabular root loads only with his go
- **The citator is loaded** (v2026.09.19, rank v4): 25,777 rows, 22,547 edges, none shown; exposed
  428. **The review page, for a person**: docket, sub-docket and document in one look, linked to
  scan, text, both dockets and the match; same-docket filings citable (his); an ICC flag. GATED on
  the citations brief's 1-3; `panel_check_sheet.py`'s composition is its spec (untracked)
- **Tabular pass RUNNING** since 2026-09-16 11:46Z (coordinator and workstation on `67b1762`; PR #34
  merged 2026-09-17). First 16 min: 67 read, 9 page-owned `finish_reason length` (~12%, final), 4 blob misses;
  **~12.6 s/page, so ~88 h, not the 36-48 h scoped**. 434 of 3,385 documents (1,051 pages, 0.24 GB)
  are in NEITHER blob mirror, so no node reads them this seed. Stop: `touch
  /data/docketyard/ocr/.stop-tabular` on rmi-ai-machine. Nothing collected is loaded
- **Decided dates, extraction pass only (his, 2026-09-16)**: ADR 0023 addendum Proposed on branch
  `decided-date-grain` (acbec23), schema-critic clean on pass 3 — page in the key, one live
  quotation per displayed reading, migration 0033. **His to accept; then migration + pass**

## Next

- **Text-layer quality, HIS 95 LABELS AND HIS TWO DECISIONS, 2026-09-17**
  (`docs/research/text-quality/`, branch `text-layer-quality`): **~110,500 of 931,392
  text-layer pages are faulty (1 in 8), ~25k garbage**; the <0.5 cut catches 68% of garbage,
  2/3 of what it flags are maps. The quality ADDENDUM IS WITHDRAWN (his, after three critic
  passes): the score stays an internal routing list, nothing published, no schema change.
  Owed: (1) **measure orientation** before the re-read — 9 of 64 pages need rotating, all with
  `/Rotate = 0`, and the wave runs PP-OCRv6 with the toggles off; (2) then re-read the <0.5
  pages, prose first, on dots.mocr
- **MCP: list the proceedings behind a count** (`deferred.md` § From using the live MCP server):
  asked for the 20 most recent, an assistant had to guess one. His to choose; small
- **The graders' three open fix-now items** (`deferred.md` § The independent graders): the
  `coverage` tool matching `/coverage` is the ARDA demo item; the docket JSON key test; openapi
  hygiene
- **Party types, the held-out sheet is WITH THE OPERATOR** (2026-09-10,
  `docs/research/party-types/held-out/`). When his Copy block returns: apply both picks, score
  `party_types_rules.py --sheet` at 95% per type on the FIRST pick, then the assertion
  migration (schema-critic first) and the browse on `/parties`
- **Held by the operator**: `/methodology`'s text-stage section (`848e366`) and the one-day-rest
  sentence (`3b538bc`), 2026-09-11; a sheet's JSON-LD in Google's Rich Results test, from a browser
- The workstation gate's ONLOGON task is still unregistered (`deferred.md`)
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Deadline engine (C4): no obligations in decision JSON; fixture of 8 in `docs/deferred.md`

## Parked

- **Docket summaries (P6) and the AB status facet are specified, not chosen**
  (`docs/summaries.md`, 2026-09-10): the fifty-document sample is what a decision starts;
  the rule-only status slice (800 consummations, 714 trail-use filings) could go first
- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
