# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.
Pruned 2026-09-10: done items and facts that live elsewhere were removed; the nine operator
decisions were taken the same day and are recorded where each belongs.

## In motion

- **The `dots` OCR wave** reads on the fleet (`docs/compute-fleet.md`, ADR 0025): rmi-nuc
  coordinates, RMI-AI-MACHINE and the workstation's gate read, Grafana watches. When the
  queue empties: `second`, then `graphic`, on the NUC; rsync and `text load` each root on
  the instance IN THAT ORDER (`graphic` needs its own `ran_at` or the loader says `restart`)
- **The citator has never run a real load** (`citation`: 0 rows). The chain into a copy
  (2026-09-04) gave 15,164 distinct edges and 0 failures; `declare --scores` and reviewer 1
  are ready; 1,946 exposed keys are ~16 h of reading. The work card is judged (§ Next), so
  what is left is the operator's hours
- **Owed with the citator's pipeline**: the "not in the record" display joining live
  `citation`; the veto's trigger; a consumer for ADR 0023's pick rule (decided 2026-09-03:
  publish only when every live reading agrees — `cite.py` still sends `decided` unchanged)

## Next

- **The work card is judged and the plumbing shipped**: 106 of 106 (ADR 0017 addendum,
  `docs/research/benchmark/work-labels.csv`). What remains is the load itself — build the
  card on a production copy with `citation_dryrun.py --work`, then `citator declare`, as
  part of the first load below. A reader is shown no number; a shown edge names the sheet
- **Party types, the held-out sheet is drawn and WITH THE OPERATOR** (2026-09-10,
  `docs/research/party-types/held-out/`; blind queue `data/party-types-heldout-check.html`).
  When the Copy block (party_id, type, first, note) returns: apply both picks to its
  `labels.csv`, score with `party_types_rules.py --sheet`, 95% per type on the FIRST pick;
  then the assertion migration (schema-critic first) and the browse on `/parties`
- **v2026.09.13 is built and rehearsed, unreleased**: robots `/search` and JSON-LD, the
  no-answer fetch and truncated-download fix, migration 0026 (Owed 5), the admit-window fix.
  Deploy in MANUAL mode behind the wall by `infra/deploy/README.md` § Migration 0026; after
  it, check a sheet's JSON-LD block in Google's Rich Results test
- ADR 0024's stage is live and verified (2026-09-11: 75 read over three passes, none
  quarantined); still owed, a per-page failure record (Owed 2)
- **Held by the operator for rewording (2026-09-11)**: `/methodology`'s text-stage section
  (`848e366`) and the one-day-rest sentence (`3b538bc`); § Documents has his narrowed one
- **Pruned blobs are never read by the stage** (the parser has no network): 27 of 143 due
  (2026-09-11), a problems line every pass. Fetch them back from S3 before dispatch
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Deadline engine (C4): decision JSON carries no obligations (2026-08-26); a hand-checked
  fixture of 8 for FD 36873 is in `../up-ns-merger-tracker/briefs/2026-08-25.md` (read-only)
- The Mac's and the Jetson's passes, when a workload is chosen; two workers on the node,
  measured for the activation peak first

## Parked

- **Docket summaries (P6) and the AB status facet are specified, not chosen**
  (`docs/summaries.md`, 2026-09-10): the fifty-document sample is what a decision starts;
  the rule-only status slice (800 consummations, 714 trail-use filings) could go first
- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
