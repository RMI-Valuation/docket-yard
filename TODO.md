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
- **Tabular pass STOPPED CLEANLY mid-pass 2026-09-18 20:32Z** (`67b1762`): 17,275 done, 6,799
  pending, 2,220 failed, **nothing leased** — a resume loses and re-reads nothing. Key
  unchanged (HunyuanOCR `47644ecc`, transformers 5.16.1, render 150, mv 1.5); **do NOT raise
  the render to 200 mid-pass — two live keys**. **BACKED UP 2026-09-19** to two boxes: routes
  (27,269, the only strictly irreplaceable part), collected-unloaded (2,578), the queue
  (64,113 answers, 16 uncollected). Resume = the placement decision; NAS target chosen next
- **ADR 0025 addendum Proposed 2026-09-19** — a broker places readers; the coordinator is
  backed up. **His to accept.** Open with it: which box coordinates, whether the freed box
  reads (its card is Turing, so bf16 is unmeasured), and where a reader gets blob bytes
- **Decided dates, extraction pass only (his, 2026-09-16)**: ADR 0023 addendum Proposed on branch
  `decided-date-grain` (acbec23), schema-critic clean on pass 3 — page in the key, one live
  quotation per displayed reading, migration 0033. **His to accept; then migration + pass**

## Next

- **The prose re-read is BUILT and needs a GPU and one file copy** (`32345db`; `route-list`,
  `seed --from`, `dots_worker --pass`, `fleet-up.sh reread`, 48 fleet tests, schema-critic and
  two `/code-review` rounds acted on). To run: put `queue.csv.gz` (production `/tmp/tq/`, also
  in this session's scratchpad) on a fleet node — **auto mode refuses the scp** — then
  `route-list` and seed; no card is committed elsewhere now. Owed before ANY load, in
  `deferred.md`: loading changes what every re-read page publishes about itself with no dated
  rule (`pages.py:band`), and the agreement distance is a publishing decision, not a computation
- **~40 kind labels from the flagged set** (his, 2026-09-18, `deferred.md`): the prose screen is
  0.80/0.80 on 5 prose pages there, not the 0.92/0.92 that pooled blind labels off-population
- **The blob mirror** (his, 2026-09-18): the 310 failed documents are all in S3 (190.4 MB);
  the coordinator owns the mirror the fleet reads through but holds no credential to refill it.
  Second remedy found 2026-09-19 — the instance already serves any blob by hash — but it
  crosses "production never joins the fleet", so it is an ADR, not a fix (`deferred.md`)
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
