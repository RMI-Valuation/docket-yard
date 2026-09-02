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
  in the record" display joining live `citation`; the veto's trigger the day it stops being
  inert. Twelve smaller findings in `docs/deferred.md`
- **Drain stopped at its floor 2026-09-02**, 26,940 down to 124 unfetched — 121 genuine
  refusals resting 7 days, and **3** the en-dash rows, which fetch on the next deploy
  carrying `_wire_url`. **The class behind the 3 is open**: Cameron's, in `docs/deferred.md`
- **OCR bench done, 2026-09-01** — 13 runs, 10 engines; **three free local engines beat
  Textract**, so the ~$260 line goes to ~$0. **dots.mocr** is the one to build on (8.2% CER,
  MIT, nothing invented, 100% dockets). No engine wins every tier: § Step 3 of the bench
- **Party types (F3)**: rules v2 at 83.3%, tuned on its own sheet — **a second unseen
  sample must confirm** before any type ships
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- No Anthropic key exists; any Claude-backed run needs a new one from Cameron
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **The router, measured 2026-09-02** (§ Step 4): PP-DocLayoutV3 free at 0.05 s a page,
  graphic call safe, **blank call unsafe — "no regions" must never mean "skip"**; plus an
  unconfirmed clean-vs-degraded signal (AUC 0.843) it was assumed blind to. dots.mocr
  layout-only is 75x dearer for no net gain. Left: **the second unseen sample**
- **Preprocessing measured, 2026-09-02** (§ Step 5): no image operation earns its place —
  crop cuts CER but invents, masking does not invent but loses 5 dates. **Cameron's call:
  the degraded tier at 200 DPI** (dots 12.7% to 12.1%, dockets held, +40 h); 300 OOMs
- **More tabular and graphic ground truth** — 5 and 9 pages decide nothing. The tabular
  routing, the router's figures and preprocessing's re-asks all wait on it. **Cameron's**
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
