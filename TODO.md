# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.
Pruned 2026-09-10: done items and facts that live elsewhere were removed; the nine operator
decisions were taken the same day and are recorded where each belongs.

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

- **Comment scans to the fleet** (the operator's decision, 2026-09-11): 12,184 image-only
  attachments, 51,000 pages. Paddle done 20:51 UTC (0 failed); **primary LOADED** 20:55 (8,211
  documents); `dots` reading, 13,013 pending at 23:55 UTC. The workstation's gate died with his
  reboot and rejoined 2026-09-11 23:45 UTC — register its ONLOGON task (`deferred.md`).
  `second` and `graphic` are NOT queue passes: they follow as `ocr_wave.py` documents when the
  queue empties (`compute-fleet.md`), then rsync and `text load` each root in that order

## Next

- **A PANEL of local models CLEARS about half the review queue — MEASURED, 2026-09-11**
  (`docs/extraction-benchmark.md`). Two models agreeing on both the citation and the document
  settle 70 of 148 with 0 wrong. **Over the REAL 1,476 the panel clears only 9.7%, not 47.3%.**
  The finding is elsewhere: both models agree **981 (66.5%) are CAPTIONS, not citations**, 649
  of them the citing decision's own docket. `find.py:190` has the mechanism — the own-docket
  rule is a disjunct `DOC_WORDS` defeats, and a caption block holds those words. **WITH HIM: 40
  drawn to judge** (`data/caption-check.html`). If it holds, the finder is the bug and the queue
  is two-thirds noise. Precision is measured through the review page (his decision); no
  threshold — ADR 0017 thresholds on nothing; switching clearing on is an 0017 addendum, his

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
