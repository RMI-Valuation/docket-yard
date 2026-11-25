# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## In motion

- **Every decision waiting on him is listed in `docs/deferred.md` § Waiting on the operator**
  (64, gathered 2026-10-03); an answer moves an item here or closes it there.
- **v2026.10.6 LIVE** (2026-10-26, schema 34; first deploy on the new host). The fleet runs `3629aa8` (coordinator moved forward
  2026-09-20; nothing it executes changed). dots 46,838/134
- **The citator is loaded** (rank v7, finder 2026-09-14b, since v2026.09.24): 26,205 rows,
  22,547 edges, none shown; exposed 428. **The review page, for a person** — docket, sub-docket and document in one look,
  linked to scan, text, both dockets and the match; an ICC flag. GATED on the citations
  brief's 1-3; `panel_check_sheet.py`'s composition is its spec (untracked)
- **ADR 0025 addendum: ALL SIX ACCEPTED and VERIFIED LIVE**, re-proved on the new coordinator
  2026-09-20 — a miss fetches and hash-verifies, a hit serves from disk, a sha in no store
  **404 not 503**. Owed in `deferred.md`: the worker branches have no test, the corrupt-store
  alarm reaches nobody, `pull_blobs.py` still compares size not sha
- **THE TABULAR PASS IS HELD since 2026-09-20; his, 2026-11-25: the infrastructure has changed
  since it last ran** — work out what it needs adjusting first, and that waits on the fleet project
  moving into Orca. Where it stopped: job 40 exited 5 on the breaker, 25 pages in a row of
  `d3d06d3de4f2` looped, and that document is first in claim order (62 pages pending). 18,775
  done, 5,134 pending (578 docs), 2,385 failed (1,586 loops, 798 blob-missing). `finish_reason
  length` is the MODEL LOOPING (measured 2026-09-20, `deferred.md`): **do not raise
  `max_new_tokens`**; the loop decisions (page's fault? publish a good prefix?) and a cheap
  repetition guard come with the restart. **The 2,578 collected readings load with the pass**,
  under its rule (his, 2026-11-25). Key unchanged; do NOT raise the render mid-pass

## Next

- **The account move is DONE (2026-10-18, 37-min gap); the old host is deleted.** Mail runs
  through the bridge until the new account's SES production access, then four `.env` lines
  end it. Alerts through the bridge VERIFIED 2026-10-26 (22 sent since 10-18, 0 failed);
  `traffic.sqlite` in Litestream since 2026-10-26, restore proved. S3 LIST cost ESTIMATED
  ~$4/mo (276k blobs; sync + prune each list all of `blobs/` every 30 min); Cost Explorer
  is denied to `docket-yard` — a measured bill needs an amended request
- **The prose re-read is BUILT and HELD** (`32345db`; his, 2026-11-25). To run: put
  `queue.csv.gz` (production `/tmp/tq/pages.csv.gz` is its source) on a fleet node — **auto
  mode refuses the scp** — then `route-list` and seed. Owed before ANY load, in `deferred.md`:
  loading changes what every re-read page publishes about itself with no dated rule
  (`pages.py:band`), and the agreement distance is a publishing decision, not a computation
- **Held by the operator**: `/methodology`'s text-stage section (`848e366`) and the one-day-rest
  sentence (`3b538bc`); a sheet's JSON-LD in Rich Results. Gate's ONLOGON task unregistered
- Seed wave 2 (unresolved spans; pre-2020 roads); deadline engine (C4) fixture in deferred.md
- **Internal names out of the current tree** (his, 2026-11-25: do it soon; the three decisions
  were taken 2026-11-13; the measured plan is kept outside the repo). Four PRs, the first a
  mechanical rename of `tools/rmi-ai-machine/` to `tools/derive/`. History is not rewritten

## Parked

- **Docket summaries (P6) and the AB status facet are specified, not chosen**
  (`docs/summaries.md`, 2026-09-10): the fifty-document sample is what a decision starts;
  the rule-only status slice (800 consummations, 714 trail-use filings) could go first
- **Party types, parked 2026-11-25 (his)**: the held-out sheet (`docs/research/party-types/
  held-out/`) went to him 2026-09-10; on its return, score `party_types_rules.py --sheet` at
  95% per type, the assertion migration (schema-critic first), then the browse on `/parties`
