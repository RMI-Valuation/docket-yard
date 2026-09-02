# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## Now

- **The figures: 94.7% projected / 97.7% precision by the rule, 93.3% to a reader.** Three
  causes, each separated in migration 0016's header, which is the one to quote
- **Nothing in the code blocks the citator from production** (migrations 0014-0017). Nobody
  has run the first real load, and production is four migrations behind at schema 13
- **Owed with the pipeline**: ingest writing `decision_work`; the review queue and the "not
  in the record" display joining live `citation`; the veto's trigger. More in `deferred.md`
- **Drain done**: 124 left — 121 resting refusals, 3 en-dash rows that fetch on the next
  deploy. **The class behind the 3 is open**, Cameron's (`docs/deferred.md`)
- **THE COMMENT PAGE IS O(DOCKET)** — three outages 2026-09-02. Every record page builds its
  whole docket sheet to read `sheet.title`; FD 35087 holds 12,031 comments, so each costs
  21.5 s and our sitemap invites the crawl. **Contained** by a Caddy 503 on that path (delete
  it with the fix); **the fix needs the deploy**. Top item in `docs/deferred.md`
- **Outage 2026-09-02, 03:26-10:18 UTC**, gap 1 recorded, nothing missed. **Detection took
  6 h 13 m**: GitHub runs the "hourly" heartbeat every 3-5 h. Guards still owed: a memory cap
  on `web` so it cannot take `ingest` down, and something acting on the healthcheck
- **ADR 0019 Proposed** — telemetry via Grafana Cloud + Alloy, primary detector an alert on
  absent metrics. **Cameron's: accept, and a Grafana Cloud credential**
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
