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
- **The viewer is still O(docket)**: `/filing|/decision/<id>/view` needs the entry's
  neighbours and the Parties block, so it cannot use `sheet.one_entry`. One click from every
  record page and not disallowed in `robots.txt`; detection took 6 h 13 m (`deferred.md`)
- **The alert rules are Cameron's, and the no-data one is the point** — it replaces the
  heartbeat that took 6 h 13 m. Telemetry live; maintenance is `touch data/flags/maintenance`
- **`methods.stamp()` has no channel term** — the first OCR-channel citator load would stamp
  text-layer measurements onto OCR rows and publish them. A live ADR 0017 D3 violation
  waiting for a load that has not happened; fix before any OCR pass runs
- **ADR 0021 (the grain) and 0022 (where the text lives) are Proposed**, cut by half to the
  four answers: finding aid always shown, assertion gated; cheap second reading, escalation
  operator-triggered; maps last, tables a later pass. **Cameron's** (`ocr-migration.md`)
- **Party types (F3)**: rules v2 at 83.3%, tuned on its own sheet — **a second unseen
  sample must confirm** before any type ships
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- No Anthropic key exists; any Claude-backed run needs a new one from Cameron
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **The router**: free at 0.05 s, graphic call safe, **blank call unsafe — "no regions"
  must never mean "skip"**. **Cameron's**: 200 DPI for the degraded tier (+40 h), and the
  ground-truth top-up the tabular route waits on (tables are now read last, not never)
- **HunyuanOCR-1.5 deferred with the tabular tier**: closes the table gap (86.2% cells), but
  its licence bars the EU/UK/Korea and forbids using outputs to improve any model
- **OCR of the 15,085 image-only files** (M3's first slice): **247,923 pages**, censused
  2026-09-02 — 42% over the plan's estimate, so ~187 h of box time and not 132
- Deadline engine (C4): decision JSON carries no obligations (verified 2026-08-26); a
  hand-checked fixture of 8 for FD 36873 sits in `../up-ns-merger-tracker/briefs/2026-08-25.md`
  (read-only). Dates quoted, never computed
- JSON-LD (Cameron, 2026-08-26): none on any page; decide the vocabulary before adding any
- Cameron's idea: cadence switch from the alert email; a signed-link manage page per address
- **ADR 0012 addendum: the blob cache** (S3 store, instance cache) — ADR 0021 D14 leans on it
- **`docs/navigation-review.md`: Tiers 1–3 and A7 are built**, home keeps its rolling seven
  days (Cameron, 2026-09-01). Left is **his**: the masthead, and whether a place index is ripe
- When this list runs short or a decision makes one of them near-term, pull the next item
  from `docs/deferred.md` (review findings and known gaps, dated, with their context)

## Parked

- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
