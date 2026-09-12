# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## In motion

- **The citator is loaded, and re-loaded with the line wrap** (v2026.09.15, 2026-09-11 20:16
  UTC): 15,535 edges, 9,863 naming a document, none shown; exposed 1,476. **Next the review
  page, for a person** (the measurement is in): easy, explained, one look settling docket,
  sub-docket and document, linked to scan, text, both dockets and the matched document, over a
  queue of only what can publish, with an ICC flag for `(ICC served …)`. Same-docket filings
  and decisions must be citable (his requirement). GATED on the citations brief's four
  questions
- **Owed with the citator's pipeline**: the "not in the record" display joining live
  `citation`; the veto's trigger; a consumer for ADR 0023's pick rule (decided 2026-09-03:
  publish only when every live reading agrees — `cite.py` still sends `decided` unchanged)

- **Comment scans: `dots` is DONE** — 46,838 pages read, 134 failed, 16,632 documents
  collected 2026-09-12 04:17 UTC. `second` and `graphic` launched on the NUC 13:55 UTC
  (`second` owed 6,710 documents). **Then rsync and `docketyard text load` each root in
  order: dots, second, graphic.** The workstation gate's ONLOGON task is still unregistered

## Next

- **The panel clears 9.7% of the real 1,476, and 66.5% of the queue is CAPTIONS** (measured
  2026-09-11, `docs/extraction-benchmark.md`; he judged 40 — 39 captions, 0 citations). The
  QUEUE PREDICATE is the fix and not the finder: `citation_exposed` filters on the exposure
  judgement and not on `kind`, needs no schema change, and is what stands between him and a
  small queue. Switching panel clearing on is an ADR 0017 addendum, his
- **Offsets in the finder, on PROVENANCE and not recall** (his decision 2026-09-12, and his
  re-decision the same day on the measurement): `find` reports each match's offset, `load`
  writes a real `source_location`. Offsets uniquely recover 12 of 506 lost rows — 0.016% of
  readings — while the per-line split is 421 (`docs/citation-grain.md` § The one number
  nobody had). The walk reads flat `document_text.text`, so the honest shape is
  `{page, char_start, char_end}` and NOT migration 0014's declared `{page, block_id, bbox}`:
  schema-critic on that, then stb-ingest-specialist and `/code-review`

- **Party types, the held-out sheet is WITH THE OPERATOR** (2026-09-10,
  `docs/research/party-types/held-out/`). When his Copy block returns: apply both picks, score
  `party_types_rules.py --sheet` at 95% per type on the FIRST pick, then the assertion
  migration (schema-critic first) and the browse on `/parties`
- With the operator: a sheet's JSON-LD block in Google's Rich Results test, from a browser
- ADR 0024's stage: a per-page failure record is still owed (Owed 2)
- **Held by the operator for rewording (2026-09-11)**: `/methodology`'s text-stage section
  (`848e366`) and the one-day-rest sentence (`3b538bc`); § Documents has his narrowed one
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Deadline engine (C4): no obligations in decision JSON; fixture of 8 in `docs/deferred.md`

## Parked

- **Docket summaries (P6) and the AB status facet are specified, not chosen**
  (`docs/summaries.md`, 2026-09-10): the fifty-document sample is what a decision starts;
  the rule-only status slice (800 consummations, 714 trail-use filings) could go first
- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
