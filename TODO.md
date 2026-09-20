# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## In motion

- **v2026.09.28 LIVE** (schema 33). The fleet runs `3629aa8` (coordinator moved forward
  2026-09-20; nothing it executes changed). dots 46,838/134
- **The citator is loaded** (v2026.09.19, rank v4): 25,777 rows, 22,547 edges, none shown;
  exposed 428. **The review page, for a person** — docket, sub-docket and document in one look,
  linked to scan, text, both dockets and the match; an ICC flag. GATED on the citations
  brief's 1-3; `panel_check_sheet.py`'s composition is its spec (untracked)
- **ADR 0025 addendum: ALL SIX ACCEPTED and VERIFIED LIVE**, re-proved on the new coordinator
  2026-09-20 — a miss fetches and hash-verifies, a hit serves from disk, a sha in no store
  **404 not 503**. Owed in `deferred.md`: the worker branches have no test, the corrupt-store
  alarm reaches nobody, `pull_blobs.py` still compares size not sha
- **rmi-nuc2 IS THE COORDINATOR** since 2026-09-20 (queue, roots, readings, credentials, backup
  and Alloy across; blob answers re-proved). **rmi-nuc is rmi-fleet's now** — wiped, no DY claim
- **THE TABULAR PASS READS THROUGH THE BROKER** since 2026-09-20 — job 40 (39 cancelled to drop
  `--blobs`, so a mirror miss is now a coordinator fetch), `dy-ocr`, preemptible. Key unchanged;
  **do NOT raise the render mid-pass**. **There was never a separate submit token**: one broker
  token, already on the box; what blocked it was ours (`3629aa8`). **Keep `--host` pinned until
  the fleet raises `dy-ocr`'s `vram_gb`** — 4 GiB on our own floor, and `cuda` matches the 2060
- **rmi-nuc's 2060 cannot read this pass — measured 2026-09-20**, answered in rmi-fleet
  `deploy/docket-yard-bf16-reply.md`. Not bf16 speed: a page asks one 4.13 GiB block against
  5.60 GiB usable, so 7 of 7 OOM'd. **Our own memory floor is half what a page needs**
- **HIS, and measured 2026-09-20 (`deferred.md`): `finish_reason length` is the MODEL LOOPING**,
  not a long page — 1,490 pages final-failed, 48 documents with nothing read. **Do not raise
  `max_new_tokens`.** Two decisions: is a loop the page's fault (it is filed as final) and is a
  degenerate answer's good prefix worth publishing. A repetition guard is separable and cheap
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
