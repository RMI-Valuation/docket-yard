# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## Now

- **The figures: 94.7% projected / 97.7% precision, 93.3% to a reader.** Three causes,
  separated in migration 0016's header, which is the one to quote
- **The citator has never run a real load** (`citation`: 0 rows). The chain ran into a COPY
  2026-09-04: 73,101 findings, **15,164 distinct edges**, 0 failures; `declare --scores` and
  reviewer 1 are ready. What is left is **capacity** — 1,946 exposed keys, ~16 h of reading,
  one reviewer. **Cameron's to start**
- **Owed with the pipeline**: the "not in the record" display joining live `citation`; the
  veto's trigger. `Resolution.decision_id` is assigned (2026-09-05): **16,051 of 217,352
  landed resolutions reach a work**, measured over all 976,058 live pages
- **The work grain refuses until scored** — `cited-by --work` raises `Unscored`; opening it is
  one `class_measurement` on `('citation_resolution', 'work')`. **Cameron's, with the capacity**
- **Drain closed**: 121 unfetched, every one a genuine refusal resting 7 days. **The class
  behind them is open** — an unanswered attempt leaves no capture. Cameron's (`deferred.md`)
- **The alert rules are Cameron's, and the no-data one is the point** — it replaces the
  heartbeat that took 6 h 13 m. Telemetry live; maintenance is `touch data/flags/maintenance`
- **Cameron's**: revisit noindex now that search reaches the text, and whether `/search`
  joins the named AI agents' disallow list — it prints the held page text they may not fetch
  at `/text`. A mask pattern change is a new migration
- **ADR 0023's pick rule is decided (2026-09-03): compare values** — publish only when every
  live reading agrees. No consumer built yet; `cite.py` sends `decided` to the sheet unchanged
- **Party types (F3)**: rules v2 at 83.3%, tuned on its own sheet — **a second unseen
  sample must confirm** before any type ships
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Cameron's: a new Anthropic key before any Claude-backed run; the explainers' [?] rows
  (one email to the Board's records staff); announcing

## Next

- **ADR 0024 amended; migrations 0023 (`extraction_dispatch`) and 0024 (`producer_declaration`,
  § Owed 1) committed, yours to accept.** Six critic passes and the ingest specialist found
  silent mass exhaustion, the 1.07 GB PDF dispatched, one `failed` silencing a document for
  ever, a halt that never releases, and a pin that could never move. **The gate is the DEPLOY,
  not the apply** — shipping either table freezes its shape under CC0. Nothing declares a pin
- **`dots` died 2026-09-06 (CUDA OOM, a 12 MP sheet); the driver walked 32,849 pages against
  a closed port, exited 0, and nobody knew for three days. Restarted 2026-09-09 through the
  page queue** (`tools/fleet/`, `docs/compute-fleet.md`, ADR 0025 Proposed): 33,147 pages
  re-queued, 2,560 documents whole, `fleet-up.sh` on RMI-AI-MACHINE, monitor :8130, ~5 days.
  Alloy writes from the node since 2026-09-09. **Cameron's: the three Grafana rules (stalled,
  failing, absent; 10 min)**, and ADR 0025. Then `second`, `graphic`; rsync + `text load` IN ORDER
- Deadline engine (C4): decision JSON carries no obligations (2026-08-26); a hand-checked
  fixture of 8 for FD 36873 is in `../up-ns-merger-tracker/briefs/2026-08-25.md` (read-only)
- JSON-LD (Cameron, 2026-08-26): none on any page; decide the vocabulary before adding any
- **`docs/navigation-review.md`: Tiers 1–3 and A7 are built**, home keeps its rolling seven
  days (Cameron, 2026-09-01). Left is **his**: the masthead, and whether a place index is ripe

## Parked

- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
