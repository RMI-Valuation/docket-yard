# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## Now

- **The figures: 94.7% projected / 97.7% precision by the rule, 93.3% to a reader.** Three
  causes, each separated in migration 0016's header, which is the one to quote
- **The citator is in production at schema 17 and has never run a real load.** Nothing in
  the code blocks it; the first load is Cameron's to start
- **Owed with the pipeline**: ingest writing `decision_work`; the review queue and the "not
  in the record" display joining live `citation`; the veto's trigger. More in `deferred.md`
- **Drain closed**: 121 unfetched, every one a genuine refusal resting 7 days; the 3
  en-dash rows fetched on the deploy. **The class behind them is still open** — an
  unanswered attempt leaves no capture, so nothing rests it. Cameron's (`deferred.md`)
- **The O(docket) record page is fixed and deployed** (`sheet.one_entry`) — three outages
  2026-09-02, gap 1 recorded, nothing missed; the page now answers in 0.12 s where it cost
  21.5 s, and the Caddy containment is removed. Guards live (768 MB cap, 1-min webwatch).
  **The viewer is still O(docket)** and detection still took 6 h 13 m (`deferred.md`)
- **ADR 0019 and 0020 accepted and live.** Maintenance: `touch data/flags/maintenance`
  (used for the v2026.09.1 deploy — 2 m 50 s, no gap). Telemetry: `docket_yard_*` and the
  host's vitals reach Grafana Cloud. **The alert rules are Cameron's to write, and the
  no-data one is the point** — it replaces the heartbeat that took 6 h 13 m
- **Party types (F3)**: rules v2 at 83.3%, tuned on its own sheet — **a second unseen
  sample must confirm** before any type ships
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- No Anthropic key exists; any Claude-backed run needs a new one from Cameron
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **The router, measured** (§ Step 4): PP-DocLayoutV3 free at 0.05 s, graphic call safe,
  **blank call unsafe — "no regions" must never mean "skip"**. Preprocessing is closed
  (§ Step 5) but **200 DPI for the degraded tier is Cameron's call** (12.7% to 12.1%, +40 h)
- **More tabular and graphic ground truth** — 5 and 9 pages decide nothing; the tabular
  route, the router's figures and crop/masking's re-asks all wait on it. **Cameron's**
- **HunyuanOCR-1.5 is Cameron's call**: the only free engine that closes the table gap
  (86.2% cells), but its licence bars the EU/UK/Korea and forbids using outputs to improve
  any AI model, which the CC0 dump cannot absorb
- **OCR of the 13,604 image-only files** (M3's first slice): plan in `docs/ocr-plan.md`. The
  tiered read is not costed yet; the plan's ~$1,335 assumes one engine everywhere
- Deadline engine (C4): decision JSON carries no obligations (verified 2026-08-26); a
  hand-checked fixture of 8 for FD 36873 sits in `../up-ns-merger-tracker/briefs/2026-08-25.md`
  (read-only). Dates quoted, never computed
- JSON-LD (Cameron, 2026-08-26): none on any page; decide the vocabulary before adding any
- Cameron's idea: cadence switch from the alert email; a signed-link manage page per address
- **ADR 0012 addendum: the blob cache** (S3 the store, the instance a cache; sync + prune)
- **`docs/navigation-review.md`: Tiers 1–3 and A7 are built**, home keeps its rolling seven
  days (Cameron, 2026-09-01). Left is **his**: the masthead, and whether a place index is ripe
- When this list runs short or a decision makes one of them near-term, pull the next item
  from `docs/deferred.md` (review findings and known gaps, dated, with their context)

## Parked

- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
