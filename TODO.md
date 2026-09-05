# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## Now

- **The figures: 94.7% projected / 97.7% precision, 93.3% to a reader.** Three causes,
  separated in migration 0016's header, which is the one to quote
- **The citator has never run a real load** (`citation`: 0 rows). The whole chain ran into a
  COPY 2026-09-04: 73,101 findings, **15,164 distinct edges**, 0 failures. `citator declare
  --scores` exists and **reviewer 1 is granted**, so the steps are runnable; what is left is
  **capacity** — 1,946 exposed keys, ~16 h of reading, one reviewer. **Cameron's to start**
- **Owed with the pipeline**: the "not in the record" display joining live `citation`; the
  veto's trigger; `Resolution.decision_id` is never assigned, so `cited_decision_id` is
  always NULL — **the next code item, and the only one of the three that is mine**
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
- No Anthropic key exists; any Claude-backed run needs a new one from Cameron
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **ADR 0024 is Proposed and the code is the next finder.** Two review rounds (schema
  critic, then the ingest specialist reading it as a pass change) broke nine of its ten
  decisions between them; it is stamped Accepted only when an implementation has proved it.
  Seven owed items in § Owed, headed by `extraction_dispatch` past the schema critic
- **The OCR wave: Paddle is done and loaded, `dots` is running.** Paddle 2026-09-05 —
  15,085 documents, 247,923 pages, 0 failures; `ppocr-primary` loaded (169,516 pages,
  1:1 displacement of empty text-layer rows). `dots` started 2026-09-05 10:59 CDT in tmux
  `ocr-dots` with vLLM in tmux `vllm` on port 8120, ~132 h over 41,688 degraded pages; log
  `/data/docketyard/ocr/logs/dots.log`. Then `second`, then `graphic` — load each root in
  that order, and `graphic` needs its own `ran_at` or the loader answers `restart`
- Deadline engine (C4): decision JSON carries no obligations (verified 2026-08-26); a
  hand-checked fixture of 8 for FD 36873 sits in `../up-ns-merger-tracker/briefs/2026-08-25.md`
  (read-only). Dates quoted, never computed
- JSON-LD (Cameron, 2026-08-26): none on any page; decide the vocabulary before adding any
- **`docs/navigation-review.md`: Tiers 1–3 and A7 are built**, home keeps its rolling seven
  days (Cameron, 2026-09-01). Left is **his**: the masthead, and whether a place index is ripe
- When this list runs short or a decision makes one of them near-term, pull the next item
  from `docs/deferred.md` (review findings and known gaps, dated, with their context)

## Parked

- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
