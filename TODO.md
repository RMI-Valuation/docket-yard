# TODO

Open work only. Completed items are **deleted**, never checked off — git history is the
archive; shipped milestones are recorded in `docs/milestones.md`. `docs/deferred.md` is the
pool of accepted-later work: **pull an item from it into Next when capacity or a decision
makes it near-term**, and delete it there when it lands. Anything stale in Parked graduates
to `ROADMAP.md` or dies. Hard line cap enforced by pre-commit: when it fires, prune.

## Now

- **v2026.08.51 is live** (2026-09-01). Navigation review Tiers 1–3 (v45–v49), five from
  the deferred pool (v50), A7 + JSON shape 2 (v51). Delete
  `/srv/docketyard/pre-v45-backup.sqlite` (296 MB) once these have held a day
- **The comment-attachment drain is RUNNING** (started 2026-09-01 11:23 UTC, Cameron's go at
  the client's 2 s interval): `/srv/docketyard/drain.sh` under nohup, resumable, chunks of
  400 with a disk guard, logging to `drain.log`; `touch /srv/docketyard/drain.stop` ends it
  after the current chunk. **~2.5 days, not the 15 hours estimated** — the 2 s interval is
  not the constraint, the 1.46 MB downloads are (~7.6 s each). Disk holding at 20 GB
- **26,943 comment attachments unfetched, and the poller will never fetch them** (measured
  2026-08-31: all are `backfill`-mode observations and `poll` asks for `observed_in=
  "forward"`). Cameron's go given 2026-08-31, **throttled and after this release**:
  `fetch attachments --mode backfill` on the instance, resumable, watching disk (21 GB free
  against the pruner's 20 GB floor). ~27k requests to the Board — agree the rate first
- **ADR 0017 stays Proposed**, and `docs/citator-schema.md` now drafts its six open items
  into proposals so reviving it is a yes/no. Schema-critic found 24 defects in the first
  draft, including its headline: the honest precision after decision 5 is **98.2%**, not the
  100% first published. **Cameron's**: § G (a NULL confidence narrows ADR 0007 — 0018, drop
  the case, or a typed `confidence_state`), and whether 0017 is revived at all
- **Party types (F3)**: rules v2 at 83.3%, tuned on the sheet it is scored against, so
  **a second unseen sample must confirm** before any type ships
- No Anthropic key exists; any Claude-backed run needs a new one from Cameron
- Seed wave 2 (after wave 3 tables): unresolved spans; pre-2020 roads and successions
- Explainers' [?] rows await one email to the Board's records staff. Announcing: his call

## Next

- **ADR 0016** accepted 2026-08-28; `reviewer`/`review_action` drafted into
  `schema-draft.md` § 7. Build after 0017 settles
- `schema-draft.md`'s citation section is three revisions behind what 0017 proposes
  (`citation.treatment`, `cited_decision_id` FK, the superseded natural key); revise it on
  acceptance, not after
- **OCR of the 13,604 image-only files** (M3's first slice): plan in `docs/ocr-plan.md`,
  ~$700 for the backfill. Still blocked on 0017, and still needs the key
- Deadline engine (C4): decision JSON carries no extracted obligations (verified
  2026-08-26); a hand-checked fixture of 8 for FD 36873 is in
  `../up-ns-merger-tracker/briefs/2026-08-25.md` (read-only). Dates quoted, never computed
- JSON-LD (Cameron, 2026-08-26): none on any page; decide the vocabulary before adding any
- Cameron's idea: cadence switch from the alert email; a signed-link manage page per address
- **ADR 0012 addendum: the blob cache** (S3 the store, the instance a cache; sync + prune)
- **`docs/navigation-review.md`: Tiers 1–3 and A7 are built**, and the home window keeps its
  rolling seven days (Cameron, 2026-09-01). What is left is **Cameron's**: the masthead's
  shape, and whether a place index is ripe
- When this list runs short or a decision makes one of them near-term, pull the next item
  from `docs/deferred.md` (review findings and known gaps, dated, with their context)

## Parked

- A key held off the box (KMS), decrypting only at send time — ADR 0014's open forward step
- Stats deferrals: one month walker for `home.py`/`stats.py`; index `filing(filed_date)`
