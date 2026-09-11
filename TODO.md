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
- **Built, unreleased**: `Disallow: /search` for the named AI agents, site-level JSON-LD
  (`web/jsonld.py`), and `/llms.txt` no longer linking what robots refuses — ride the next
  release; after deploy, check a sheet's block in Google's Rich Results test
- **ADR 0024's stage is LIVE** (v2026.09.12, pinned `pymupdf@1.26.0` 2026-09-10 23:19 UTC).
  First pass 23:45: 25 dispatched, all 25 read in 3.7 s. Owed 5 DECIDED 2026-09-11:
  `ocr_run.dispatch_id`, echoed by the container, checked at admit (ADR 0024 addendum) —
  migration 0026 + extract image + `/security-review`, deployed UN-PINNED. Still owed: a
  per-page failure record (2); the `/methodology` queue table (6) rides the next release
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- A no-answer fetch is a status-0 capture on every path, resting one day (decided
  2026-09-10, `deferred.md` § 2026-09-02); stb-ingest-specialist and schema-critic first
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
