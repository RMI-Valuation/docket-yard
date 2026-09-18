# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## In motion

- **v2026.09.28 LIVE** (a Search link in the masthead; v2026.09.27 built search out, PR #41,
  schema 33, `INDEX_FORMAT` 4). The fleet still runs `67b1762` until redeployed; the tabular
  root loads only with his go
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

- **The prose re-read: HIS GO, but it CANNOT BE SEEDED YET** (PR #42 merged as `b105b08`).
  Queue built — 6,170 prose pages, 1,501 docs, ~4.6 h — but (1) `pagequeue.seed_pass` reads only
  `ocr/route/*/*.json` and `ocr_wave.py` routes only `image_only_documents`, so none of these
  docs is routed: a pass entry and a seed-from-page-list path are owed; (2)
  `document_text_one_primary` is UNIQUE per live page and all 6,170 already hold a text-layer
  primary, so the pass must declare `primary` (superseding it, ADR 0023's pick rule) or `second`
  (undisplayed, ADR 0021 D8). **(2) IS HIS, before any seed.** Orientation still owed for the rest
- **~40 kind labels from the flagged set** (his, 2026-09-18, `deferred.md`): the prose screen is
  0.80/0.80 on 5 prose pages there, not the 0.92/0.92 that pooled blind labels off-population
- **MCP: list the proceedings behind a count** (`deferred.md`): asked for the 20 most recent, an
  assistant guessed one. CHOSEN 2026-09-18; the tool's shape is his
- **The graders' three open fix-now items** (`deferred.md` § The independent graders): the
  `coverage` tool matching `/coverage` is the ARDA demo item; the docket JSON key test; openapi
  hygiene
- **Party types, the held-out sheet is WITH THE OPERATOR** (2026-09-10,
  `docs/research/party-types/held-out/`). When his Copy block returns: apply both picks, score
  `party_types_rules.py --sheet` at 95% per type on the FIRST pick, then the assertion
  migration (schema-critic first) and the browse on `/parties`
- **Held by the operator**: `/methodology`'s text-stage section (`848e366`) and the one-day-rest
  sentence (`3b538bc`), 2026-09-11; a sheet's JSON-LD in Rich Results, from a browser
- The workstation gate's ONLOGON task is still unregistered (`deferred.md`)
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Deadline engine (C4): no obligations in decision JSON; fixture of 8 in `docs/deferred.md`

## Parked

- **Docket summaries (P6) and the AB status facet are specified, not chosen**
  (`docs/summaries.md`, 2026-09-10): the fifty-document sample is what a decision starts;
  the rule-only status slice (800 consummations, 714 trail-use filings) could go first
- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
