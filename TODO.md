# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## In motion

- **v2026.09.28 LIVE** (schema 33). The fleet's checkout is pinned at `67b1762`; moving it is
  a deploy that changes what the collect loops run
- **The citator is loaded** (v2026.09.19, rank v4): 25,777 rows, 22,547 edges, none shown;
  exposed 428. **The review page, for a person** — docket, sub-docket and document in one look,
  linked to scan, text, both dockets and the match; an ICC flag. GATED on the citations
  brief's 1-3; `panel_check_sheet.py`'s composition is its spec (untracked)
- **Tabular pass STOPPED CLEANLY mid-pass 2026-09-18 20:32Z** (`67b1762`): 17,275 done, 6,799
  pending, 2,220 failed, **nothing leased** — a resume loses and re-reads nothing. Key
  unchanged (HunyuanOCR `47644ecc`, transformers 5.16.1, render 150, mv 1.5); **do NOT raise
  the render to 200 mid-pass — two live keys**. **To resume through jobd: he places
  `JOBD_API_TOKEN` on the coordinator, then delete `ocr/.stop-tabular`**
- **ADR 0025 addendum: proposals 1–4 ACCEPTED 2026-09-19, 5–6 HELD** (a blob miss as a fetch;
  what D6 means). 1 and 2 are BUILT (`stopping.py`, `resubmit.py`); 3 is RUNNING (nightly
  timer, 3 verified snapshots in `rmi-fleet-backups`). 5–6's draft is parked on
  `blob-refetch-held` — rebuild on `capture/s3.py`'s signed GET, streaming, structural error
  classes, worker half in both loops. Credential decided: `GetObject` + `ListBucket`
- **THE FLEET REBUILD is his, proposed 2026-09-19**: rmi-ai-machine, both NUCs and rmi-mac as
  fresh slates; target state per box in rmi-fleet `deploy/fleet-target-state.md`. Step 0 is
  DONE. Gated only on 5–6, which decide whether the reader can be stateless
- **Decided dates, extraction pass only (his, 2026-09-16)**: ADR 0023 addendum Proposed on branch
  `decided-date-grain` (acbec23), schema-critic clean on pass 3 — page in the key, one live
  quotation per displayed reading, migration 0033. **His to accept; then migration + pass**

## Next

- **The prose re-read is BUILT and needs a GPU and one file copy** (`32345db`). To run: put
  `queue.csv.gz` (production `/tmp/tq/pages.csv.gz` is its source) on a fleet node — **auto
  mode refuses the scp** — then `route-list` and seed. Owed before ANY load, in `deferred.md`:
  loading changes what every re-read page publishes about itself with no dated rule
  (`pages.py:band`), and the agreement distance is a publishing decision, not a computation
- **~40 kind labels: the BLIND sheet is BUILT and PUBLISHED, and is HIS to fill**
  (`kinds_check_sheet.py`, `fef1c30`; the link is outside the repo). 40 scans rendered whole at
  150 DPI beside the text the store serves; no score, no screen verdict, nothing drafted.
  **Next: his kinds, then precision off the prose stratum, recall on the weights (4.1 / 15.9)**
- **The mirror is EXPENDABLE (his, 2026-09-19)**: it never travels, so the rebuild carries no
  109 GB. Derived work backs up nightly; 2,578 collected readings still await his load
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
