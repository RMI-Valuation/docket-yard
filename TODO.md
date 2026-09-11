# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.
Pruned 2026-09-10: done items and facts that live elsewhere were removed; the nine operator
decisions were taken the same day and are recorded where each belongs.

## In motion

- **The citator is LOADED** (2026-09-11 16:55 UTC): 15,198 edges, none shown. **The finder's
  line wrap is PR #25** (his decisions: before any review, both wraps in one change); card
  built (work 140/140). It waits on Copilot and Codex, silent since #22: he checks the settings.
  Then the review page — easy, explained, one look settling docket, sub-docket and document,
  linked to scan, text, both dockets and the matched document, over a queue of only what can
  publish — with an ICC flag for `(ICC served …)`. Same-docket filings and decisions citable
- **Owed with the citator's pipeline**: the "not in the record" display joining live
  `citation`; the veto's trigger; a consumer for ADR 0023's pick rule (decided 2026-09-03:
  publish only when every live reading agrees — `cite.py` still sends `decided` unchanged)

- **Comment scans to the fleet** (the operator's decision, 2026-09-11): the 12,184 image-only
  comment attachments, 51,000 pages, through the record's wave under its keys — Paddle route
  and primary on RMI-AI-MACHINE (`comment-pass/ocr`), `dots` on the degraded pages through the
  queue, `second` and `graphic` on the NUC; load primary, dots, second, graphic, in order

## Next

- **Local models as the first reviewers: MEASURE FIRST** (his decision, 2026-09-11, the
  citations brief's avenue J). Step 1 done: the stored role runs agree at 95.9%, no better than
  qwen3 alone. Step 2: 2–3 models over the 225 checked targets, asked the review question with
  the record's candidates and the own-docket fact. Nothing ships; clearing a key on agreement
  is an ADR 0017 addendum, his. The review page is designed after it

- **Party types, the held-out sheet is drawn and WITH THE OPERATOR** (2026-09-10,
  `docs/research/party-types/held-out/`; blind queue `data/party-types-heldout-check.html`).
  When the Copy block (party_id, type, first, note) returns: apply both picks to its
  `labels.csv`, score with `party_types_rules.py --sheet`, 95% per type on the FIRST pick;
  then the assertion migration (schema-critic first) and the browse on `/parties`
- v2026.09.13 is deployed (2026-09-11 10:17 UTC): the operator checks a sheet's JSON-LD
  block in Google's Rich Results test, from a browser
- ADR 0024's stage is live, the dispatch stamp with it: 345 of 375 read by 10:18 UTC, the
  first quoted stamp landed at deploy. Still owed, a per-page failure record (Owed 2)
- **Held by the operator for rewording (2026-09-11)**: `/methodology`'s text-stage section
  (`848e366`) and the one-day-rest sentence (`3b538bc`); § Documents has his narrowed one
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Deadline engine (C4): decision JSON carries no obligations (2026-08-26); a hand-checked
  fixture of 8 for FD 36873 is in `../up-ns-merger-tracker/briefs/2026-08-25.md` (read-only)
- **The review measurement across the fleet** (his decision, 2026-09-11): llama3.1:8b over the
  768 mentions on the Mac, RMI and NUC (niced), qwen3:14b where it fits; the Jetson (8B won't
  fit) and the Mac run qwen3:4b. Pace, agreement with the Mac. Two workers: activation peak first

## Parked

- **Docket summaries (P6) and the AB status facet are specified, not chosen**
  (`docs/summaries.md`, 2026-09-10): the fifty-document sample is what a decision starts;
  the rule-only status slice (800 consummations, 714 trail-use filings) could go first
- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
