# Documents

## Reference — what to build, and what is known

| Document | What it is |
| --- | --- |
| [`capability-map.md`](capability-map.md) | 28 capabilities in five tiers, with effort and status. **A menu, not a roadmap.** |
| [`research/comparable-platforms.md`](research/comparable-platforms.md) | The evidence base — what CourtListener, FERC, the Federal Register and the paid products solved, what failed, and what sustains these projects. |
| [`stb-data-source.md`](stb-data-source.md) | The AJAX endpoint, its traps, and everything measured about the corpus. |
| [`validation-queries.md`](validation-queries.md) | The five queries the schema must answer on paper before pipeline code exists. |

## The document set

Nine documents. Four close doors that are expensive to reopen, three exist because the site is
public, two exist because future-you will be debugging at eleven at night.

The test for each: **name the specific mistake it prevents.** Documentation that isn't
load-bearing is drag.

| # | Document | Purpose | Status |
| --- | --- | --- | --- |
| 01 | [`adr/`](adr/) | Schema and architecture decision records | 0001–0009 all accepted |
| 02 | [`document-ir.md`](document-ir.md) | What the PDF→JSON layer captures | stub |
| 03 | [`methodology.md`](methodology.md) | Extraction rules; doubles as the published methodology page | stub |
| 04 | [`licensing.md`](licensing.md) | Code, data and trademark terms | drafted |
| 05 | [`coverage.md`](coverage.md) | What's in the corpus and what isn't (published) | stub |
| 06 | [`corrections.md`](corrections.md) | How errors are reported and propagated (published) | stub |
| 07 | [`about.md`](about.md) | What this is and is not (published) | stub |
| 08 | [`runbook.md`](runbook.md) | Failure modes and their fixes | DNS and repo sections written |
| 09 | [`alerts.md`](alerts.md) | Delivery promise and silent-failure detection | stub |

## Order

**Phase 1, before pipeline code:** 01–04. These are the one-way doors.
**Phase 2, before launch:** 05–07. Trust infrastructure; writing them forces design decisions.
**Phase 3, as you build:** 08–09.

## Deliberately not written yet

A roadmap past the wedge, pricing, brand guidelines, a full API specification, and any ontology
beyond what the five validation queries require. Each backfill wave will surface relation types
nobody anticipated; freezing the model early is how this becomes a modelling exercise that ships
nothing.

## Provenance

Everything in this folder came out of a design session on 2026-08-25 and is unvalidated to
varying degrees. The measured facts in `stb-data-source.md` were verified directly against
stb.gov that day. The material in `research/` is secondary research with sources cited —
**re-verify anything load-bearing before it drives a decision**, particularly legal specifics.
