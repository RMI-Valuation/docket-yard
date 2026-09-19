# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## In motion

- **v2026.09.28 LIVE** (schema 33). **The fleet's checkout moved to `440118a` on 2026-09-19**
  after 12 commits at `67b1762` — deployed while the fleet was quiescent, backup first, counts
  identical after (dots 46,838/134; tabular 6,799 pending/17,275/2,220). `reread-collect` runs now
- **The citator is loaded** (v2026.09.19, rank v4): 25,777 rows, 22,547 edges, none shown;
  exposed 428. **The review page, for a person** — docket, sub-docket and document in one look,
  linked to scan, text, both dockets and the match; an ICC flag. GATED on the citations
  brief's 1-3; `panel_check_sheet.py`'s composition is its spec (untracked)
- **Tabular pass STOPPED CLEANLY mid-pass 2026-09-18 20:32Z** (`67b1762`): 17,275 done, 6,799
  pending, 2,220 failed, **nothing leased** — a resume loses and re-reads nothing. Key
  unchanged (HunyuanOCR `47644ecc`, transformers 5.16.1, render 150, mv 1.5); **do NOT raise
  the render to 200 mid-pass — two live keys**
- **ADR 0025 addendum: ALL SIX ACCEPTED, built, deployed and VERIFIED LIVE** 2026-09-19. A
  mirror miss now refetches: measured on the coordinator — a mirror hit 200, a miss fetched
  and hash-verified and the mirror filled, a sha in no store **404 not 503**, no spool left.
  New IAM user `docketyard-blobs-reader` (GetObject on `blobs/*`, ListBucket on the bucket,
  and it CANNOT read `litestream/`). Owed in `deferred.md`: the worker branches have no test,
  the corrupt-store alarm reaches nobody, `pull_blobs.py` still compares size not sha
- **THE FLEET REBUILD is his** (rmi-fleet `deploy/fleet-target-state.md`): steps 0–2 done,
  **step 3 unblocked** — rmi-nuc2 becomes the coordinator, rmi-nuc a CPU worker; copy
  `store.env` across with the rest
- **`JOBD_API_TOKEN` on the coordinator is still the ONE thing between here and a brokered
  resume** on today's topology. It needs no swap and no code: place it, then delete
  `/data/docketyard/ocr/.stop-tabular` on rmi-ai-machine
- **Decided dates, extraction pass only (his, 2026-09-16)**: ADR 0023 addendum Proposed on branch
  `decided-date-grain` (acbec23), schema-critic clean on pass 3 — page in the key, one live
  quotation per displayed reading, migration 0033. **His to accept; then migration + pass**

## Next

- **The prose re-read is BUILT and needs a GPU and one file copy** (`32345db`). To run: put
  `queue.csv.gz` (production `/tmp/tq/pages.csv.gz` is its source) on a fleet node — **auto
  mode refuses the scp** — then `route-list` and seed. Owed before ANY load, in `deferred.md`:
  loading changes what every re-read page publishes about itself with no dated rule
  (`pages.py:band`), and the agreement distance is a publishing decision, not a computation
- **2,578 collected readings await his load** (the mirror is expendable and backs up nightly)
- **Party types, the held-out sheet is WITH THE OPERATOR** (2026-09-10,
  `docs/research/party-types/held-out/`). When his Copy block returns: apply both picks, score
  `party_types_rules.py --sheet` at 95% per type on the FIRST pick, then the assertion
  migration (schema-critic first), then the browse on `/parties`
- **Held by the operator**: `/methodology`'s text-stage section (`848e366`) and the one-day-rest
  sentence (`3b538bc`); a sheet's JSON-LD in Rich Results. Gate's ONLOGON task unregistered
- Seed wave 2: unresolved spans; pre-2020 roads. Deadline engine (C4): fixture of 8 in
  `docs/deferred.md`

## Parked

- **Docket summaries (P6) and the AB status facet are specified, not chosen**
  (`docs/summaries.md`, 2026-09-10): the fifty-document sample is what a decision starts;
  the rule-only status slice (800 consummations, 714 trail-use filings) could go first
