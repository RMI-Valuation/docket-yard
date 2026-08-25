# Documents

Nine documents. Four close doors that are expensive to reopen, three exist because the site is
public, two exist because future-you will be debugging at eleven at night.

The test for each: **name the specific mistake it prevents.** Documentation that isn't
load-bearing is drag.

| # | Document | Purpose | Status |
|---|---|---|---|
| 01 | [`adr/`](adr/) | Schema and architecture decision records | drafted, unaccepted |
| 02 | [`document-ir.md`](document-ir.md) | What the PDF→JSON layer captures | stub |
| 03 | [`methodology.md`](methodology.md) | Extraction rules; doubles as the published methodology page | stub |
| 04 | [`licensing.md`](licensing.md) | Code, data, and trademark terms | drafted |
| 05 | [`coverage.md`](coverage.md) | What's in the corpus and what isn't (published) | stub |
| 06 | [`corrections.md`](corrections.md) | How errors are reported and propagated (published) | stub |
| 07 | [`about.md`](about.md) | What this is and is not (published) | stub |
| 08 | [`runbook.md`](runbook.md) | Failure modes and their fixes | stub |
| 09 | [`alerts.md`](alerts.md) | Delivery promise and silent-failure detection | stub |

Plus [`validation-queries.md`](validation-queries.md) — the five queries the schema must answer
on paper before any pipeline code is written.

## Order

**Phase 1, before pipeline code:** 01–04. These are the one-way doors.
**Phase 2, before launch:** 05–07. Trust infrastructure; writing them forces design decisions.
**Phase 3, as you build:** 08–09.

## Deliberately not written yet

A roadmap past the wedge, pricing, brand guidelines, a full API specification, and any ontology
beyond what the five validation queries require. Each backfill wave will surface relation types
nobody anticipated; freezing the model early is how this becomes a modelling exercise that ships
nothing.
