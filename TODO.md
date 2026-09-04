# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## Now

- **The figures: 94.7% projected / 97.7% precision, 93.3% to a reader.** Three causes,
  separated in migration 0016's header, which is the one to quote
- **The citator is in production at schema 19 and has never run a real load.** Nothing in
  the code blocks it; the first load is Cameron's to start
- **Owed with the pipeline**: ingest writing `decision_work`; the review queue and the "not in
  the record" display joining live `citation`; the veto's trigger. More in `deferred.md`
- **Drain closed**: 121 unfetched, every one a genuine refusal resting 7 days. **The class
  behind them is open** — an unanswered attempt leaves no capture. Cameron's (`deferred.md`)
- **The alert rules are Cameron's, and the no-data one is the point** — it replaces the
  heartbeat that took 6 h 13 m. Telemetry live; maintenance is `touch data/flags/maintenance`
- **Migration A is done** (77,567 documents, 1,104,935 pages, store 3.7 GB) and both write-lock
  findings shipped in v2026.09.7. Left: the batched rebuild is unverified at 1.1M rows — the
  next real rebuild proves it (Cameron, 2026-09-04) — and `deferred.md` holds the one residual
- **v2026.09.3–8 shipped 2026-09-04** (noindex text pages, contact details omitted at
  display, the page search path). **Cameron's**: revisit noindex now that search reaches the
  text, and whether `/search` joins the named AI agents' disallow list — it prints the held
  page text they may not fetch at `/text`. A mask pattern change is a new migration
- **ADR 0023's pick rule is decided (2026-09-03): compare values** — publish only when every
  live reading agrees. No consumer built yet; `cite.py` sends `decided` to the sheet unchanged
- **Party types (F3)**: rules v2 at 83.3%, tuned on its own sheet — **a second unseen
  sample must confirm** before any type ships
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- No Anthropic key exists; any Claude-backed run needs a new one from Cameron
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **The OCR wave is running on rmi-ai-machine** (decided 2026-09-04: 200 DPI for degraded,
  HunyuanOCR for tabular LAST, the provisional region-count split at 13). `ocr_wave.py`,
  tmux `ocr-paddle`, log `/data/docketyard/ocr/logs/paddle.log`: router + PP-OCRv6 over
  247,923 pages (~24 h), then `dots` behind vLLM (~200 h), `second`, `graphic`; rsync each
  root and `text load` it in that order. Tabular pages stay "not yet read" until the
  HunyuanOCR pass; the top-up sample that confirms the split is still Cameron's
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
