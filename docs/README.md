# Documents

## Reference — what to build, and what is known

| Document | What it is |
| --- | --- |
| [`capability-map.md`](capability-map.md) | 28 capabilities in five tiers, with effort and status. **A menu, not a roadmap.** |
| [`research/comparable-platforms.md`](research/comparable-platforms.md) | The evidence base — what CourtListener, FERC, the Federal Register and the paid products solved, what failed, and what sustains these projects. |
| [`stb-data-source.md`](stb-data-source.md) | The AJAX endpoint, its traps, and everything measured about the corpus. |
| [`validation-queries.md`](validation-queries.md) | The five queries the schema must answer on paper before pipeline code exists. |

## The document set

Twelve documents, and one test for each: **name the specific mistake it prevents.**
Documentation that isn't load-bearing is drag.

| # | Document | Purpose | Status |
| --- | --- | --- | --- |
| 01 | [`adr/`](adr/) | Schema and architecture decision records | 0001–0015 accepted (0015, party addresses, accepted 2026-08-26) |
| 02 | [`document-ir.md`](document-ir.md) | What the PDF→JSON layer captures | stub |
| 03 | [`methodology.md`](methodology.md) | Extraction rules; doubles as the published methodology page | page published 2026-08-26 (`web/templates/methodology.html`); extraction rules await extraction |
| 04 | [`licensing.md`](licensing.md) | Code, data and trademark terms | drafted |
| 05 | [`coverage.md`](coverage.md) | What's in the corpus and what isn't (published) | published 2026-08-26, numbers measured from the store |
| 00 | [`milestones.md`](milestones.md) | The record of what has shipped, milestone by milestone | append-only |
| 00b | [`deferred.md`](deferred.md) | Review findings and known gaps accepted as not-now, dated; `TODO.md` points here | started 2026-08-26 |
| 00c | [`upns-tracker-inheritance.md`](upns-tracker-inheritance.md) | What to take from the tabled UP–NS tracker (tiering, the calendar shape, a 988-document fixture) and what to refuse (stance by default, a daily brief) | written and verified 2026-08-26 |
| 12 | [`explainers.md`](explainers.md) | Docket-type explainers (P2): every prefix and suffix, graded by source | draft 2026-08-26, awaiting operator review |
| 05b | [`data.md`](data.md) | Bulk snapshot and JSON (published at `/data`) | published 2026-08-26, CC0 |
| 05a | [`stats.md`](stats.md) | The record in numbers (published at `/stats`) | published 2026-08-26, every number measured from the store |
| 06 | [`corrections.md`](corrections.md) | How errors are reported and propagated (published) | published 2026-08-26 |
| 07 | [`about.md`](about.md) | What this is and is not (published) | published 2026-08-26 |
| 08 | [`runbook.md`](runbook.md) | Failure modes and their fixes | DNS, repo, production, address key, mail, ingest |
| 09 | [`alerts.md`](alerts.md) | Delivery promise and silent-failure detection | decided and live 2026-08-26 |
| 10 | [`architecture.md`](architecture.md) | What runs where, storage layers, the rebuildable-store property | drafted |
| 11 | [`interface.md`](interface.md) | Design direction: trust-and-density, not-gov, HTML-first, the sheet is the product | drafted |
| 12 | [`ingest-design.md`](ingest-design.md) | M1 module layout and the rules ingest code is built around | drafted |
| 13 | [`contribute.md`](contribute.md) | The `/contribute` page: three lanes (ideas, code, money), what each may and may not promise | built and signed off 2026-08-26 (`/contribute`, v2026.08.26); silent on money by decision |
| 14 | [`search.md`](search.md) | One search box: docket number fast path, FTS5 over captions, party names and decisions, `/search` without JS, `/suggest` | built 2026-08-26 (`/search`, `/suggest`, migration 0010); schema-critic reviewed |
| 15 | [`traffic.md`](traffic.md) | Hourly request counts with no identifier; the privacy sentence the operator signs first | built 2026-08-26; the sentence signed and on `/privacy`; counts are the operator's only |

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
