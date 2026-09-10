# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.
Pruned 2026-09-10: done items and facts that live elsewhere were removed; the operator's
decisions have their own section.

## In motion

- **The `dots` OCR wave** reads on the fleet (`docs/compute-fleet.md`, ADR 0025): rmi-nuc
  coordinates, RMI-AI-MACHINE and the workstation's gate read, Grafana watches. When the
  queue empties: `second`, then `graphic`, on the NUC; rsync and `text load` each root on
  the instance IN THAT ORDER (`graphic` needs its own `ran_at` or the loader says `restart`)
- **The citator has never run a real load** (`citation`: 0 rows). The chain into a copy
  (2026-09-04) gave 15,164 distinct edges and 0 failures; `declare --scores` and reviewer 1
  are ready; 1,946 exposed keys are ~16 h of reading. Waits for the work card (§ Next,
  decided 2026-09-10), then starts when the operator has the hours
- **Owed with the citator's pipeline**: the "not in the record" display joining live
  `citation`; the veto's trigger; a consumer for ADR 0023's pick rule (decided 2026-09-03:
  publish only when every live reading agrees — `cite.py` still sends `decided` unchanged)

## The operator's decisions

- Whether the second ChatGPT seat becomes a second code reviewer on pull requests

## Next

- **The work card before the first load** (decided 2026-09-10, `docs/runbook.md` Blocker 4):
  draft a cited-document column for the 240 served-date spans on the sixty-decision sheet
  for the operator's check; `citation_dryrun.py`, `scorecard` and `declare` gain a work
  stage; the loader stamps document-bearing rows from `('citation_resolution', 'work')`
- **Party types, the held-out sheet** (decided 2026-09-10): draw 300 disjoint from the first
  sample, rules v2 drafts, a check queue for the operator; the bar is 95% per type; then
  the assertion migration (schema-critic first) and the browse on `/parties`
- `Disallow: /search` for the named AI agents in the robots route, and site-level JSON-LD
  (`WebSite`, `Dataset`, `BreadcrumbList`, from the page's own reads) — both decided
  2026-09-10, `docs/machine-surface.md`)
- ADR 0024's dispatcher — the container that reads new material's text layer on the
  instance — is unwritten; `/security-review` before it ships (§ Owed 8), and `text load`
  should declare the producer from the root's `_manifest.json` (`deferred.md`)
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
