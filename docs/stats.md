# Statistics page

**Status:** published 2026-08-26 at `/stats`. Every number is measured from the store by
`src/docketyard/store/stats.py`; this document says what those numbers mean so that the
page and the code cannot drift apart. Nothing typed appears on the page.

## What is counted, and how

| Number | Unit | Source |
|---|---|---|
| Filings, decisions | The Board's own identifier, counted once — a filing entered under a parent and a sub-docket is one filing. `coverage` uses the same unit. | `filing.stb_filing_id`, `decision_record.stb_decision_id` |
| Documents held | Distinct content hashes, with total bytes | `document` |
| Dockets in the registry | Every docket the registry walk or a later observation has seen | `docket` |
| Parties on record | Every entity the party module has minted or seeded (ADR 0004) | `party` |
| Over time | Filings by *filed date*, decisions by *service date* — the Board's dates, never the date we observed the entry. Drawn as two column charts (the last 24 months; every calendar year), server-rendered SVG with no script, from the same rows the month-by-month table shows; the current year is drawn lighter because it is unfinished. Every month from the earliest dated record to the current month is present, empty months included. | `filed_date`, `service_date` |
| Most active proceedings | Filings dated in the current calendar year, folded into the docket family's root (ADR 0005), top ten | `filing`, `docket.parent_docket_id` |
| Decisions by deciding body | As printed on the Board's entry; a blank cell is shown as blank, not guessed | `decision_record.deciding_body` |
| Registry by prefix | Dockets and filings held per docket-type prefix | `docket.prefix` |

## What the page does not claim

- A month's number is what **this record holds** dated in that month — not what the Board
  posted. Until the backfill reaches a month it under-counts, and the page says so.
- Dates are shape-checked at ingest, not range-checked. A Board-side typo (a filing dated
  2062, or month 13) still counts in the headline total but is left out of the month table
  rather than stretching it; the table stops at the current month.
- Nothing about readers, subscribers, or traffic (ADR 0011).

## Caching

The numbers move at most once per poll, so the response carries `Cache-Control: public,
max-age=1800`. Everything else on the page is read-only and cookie-free like the other trust
pages.
