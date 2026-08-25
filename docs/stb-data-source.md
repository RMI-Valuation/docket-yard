# The STB record: endpoint mechanics and measured facts

Everything here was verified against stb.gov on 2026-08-25. Re-verify before relying on it —
the nonce rotates by design and the rest could change without notice.

## There is no API

STB's record search is a JavaScript front end over a WordPress AJAX endpoint. There is no
documented API, no RSS, no bulk export, and no webhook. The working route is a direct POST.

```text
POST https://www.stb.gov/wp-admin/admin-ajax.php
Content-Type: application/x-www-form-urlencoded

_ajax_nonce   = <scraped per run>
action        = stb_hook_table_decisions
                | stb_hook_table_filings
                | stb_hook_table_environmental_comments
                | stb_hook_table_dockets
                | stb_hook_table_rail_recordations
page          = 1
per-page      = 100
sort_by       = serviceDate | officialFilingDate | ''
sort_order    = asc | desc
search-criteria[0][name]  = docketNum_one
search-criteria[0][value] = FD
search-criteria[1][name]  = docketNum_two
search-criteria[1][value] = 36873
```

**Search criteria must go through `search-criteria[i][name]/[value]`.** Passing
`docketNum_two=36873` as a plain POST field is *silently ignored* — the endpoint returns a full
unfiltered result set and a 200, which is the worst possible failure mode. Any ingest code needs
a positive assertion that the filter was actually applied, not just that the call succeeded.

**The nonce rotates.** Scrape it per run from
`https://www.stb.gov/proceedings-actions/search-stb-records/`, where each results table carries
`data-stb-action="stb_hook_table_*"` and `data-stb-nonce="<hex>"`.

**The endpoint rejects non-browser User-Agents** (measured 2026-08-25): a POST with UA
`DocketYard/0.0 (+https://docketyard.org)` returns **403 Forbidden**; the same request with
`Mozilla/5.0 (compatible; DocketYard/0.0; +https://docketyard.org)` succeeds. A `Mozilla/5.0`
prefix satisfies the WAF while keeping the client honestly identified. GETs of the search page
are not filtered this way.

**The dockets table decomposes docket identity for you** (measured 2026-08-25): each row's
`data-stb-id` carries `PREFIX_SEQUENCE_SUB[_SUFFIX]` — `EP_749_0`, `FD_36339_0`,
`AB_55_785_X`, `AB_32_98_x`. `_0` in the sub position means the parent docket — but the parent
also appears **without** the `_0` (`FD_36873` and `FD_36339_0` are both parent spellings, both
observed live) — and suffix case varies (`X` and `x` both appear). Normalise for identity, keep
the raw. Visible columns:
Docket Number, Docket Title, Service List (a generate control, not data). The unfiltered
dockets table reports `total: 10000` — the display cap — so the full registry walk requires
slicing by `docketNum_one` (prefix), and capped prefixes need further slicing by sequence.

**Available criteria field names** (from the search form): `docketNum_one` through
`docketNum_four`, `docketTitle`, `decisionNumber`, `decisionType`, `decidingBody`,
`decisionSummary`, `serviceStartDate`, `serviceEndDate`, `filingName`, `filingType`, `filedFor`,
`party`, `organization`, `filingStartDate`, `filingEndDate`, `officialFilingStartDate`,
`officialFilingEndDate`, `submitterRecipient`, `enviroCommentNumber`, `enviroCommentTypeId`,
`documentSearchAll`, `documentSearchAny`, `documentSearchExact`, `documentSearchNone`,
`recordationNumber`, `recordationCategory`, `equipmentDescription`, `typeOfAgreement`.

Note the inconsistency: filings filter on `filingStartDate`/`filingEndDate`, **not**
`officialFilingStartDate`, despite the column being labelled "Official Filing Date". Using the
wrong pair returns zero rows with no error.

## The 10,000 cap

Every table reports `total: 10000` when the unfiltered result set is large. **This is a display
cap, not a count**, and you cannot page past it. Walking the archive therefore *requires*
date-slicing — a year at a time for decisions, a month at a time for filings in busy periods.
Backfill waves are forced by the API, not merely good practice.

## Measured volumes

| Measure | Value |
| --- | --- |
| Decisions, agency-wide | ~53/month (Jul 2026); 586 in 1996, 1,126 in 2005, 406 in 2024 |
| Filings, agency-wide | ~194/month (Jul 2026) |
| Decisions, 30-year estimate | ~21,000 |
| Full record, order of magnitude | 75,000–125,000 documents |

Not a big-data problem. The 2025–26 filing rate is inflated by FD 36873, which alone ran ~70
filings/month.

## Document characteristics

Sampled across 602 documents filed 2025-07 → 2026-08:

- **~1% are image-only** with no text layer; roughly another 1% have a mangled text layer. Modern
  STB PDFs are born-digital. **OCR burden concentrates entirely in the pre-2000 archive.**
- Median extracted text ~4,300 characters; 90th percentile ~26,000; maximum ~142,000.
- A single filing can appear on **several rows, one per attachment**, and the same document can
  appear under both a docket and its sub-docket. Deduplicate by document ID and fold attachments
  together, preferring a PDF as the primary link.
- Attachments are served from `dcms-external.s3.amazonaws.com`. Not all are PDFs — `.xlsx`,
  `.zip`, `.jpg`, and `.docx` all appear, and some rows have no attachment at all.

## Citation density

22% of documents in FD 36873 cite at least one other docket; 98 distinct dockets are referenced
from that one proceeding. The most-cited is **FD 36500** (CPKC/Kansas City Southern control) at
52 mentions — the precedent everyone argues from.

A naive regex over docket-shaped strings produces false positives: waybill letter `WB25-53`
parses as docket `WB 25`, and `FD 36873 (Sub-No. 1)` can mangle into `FD 368731`. **Validate
every extracted citation against the dockets table** before storing it. Ingesting
`stb_hook_table_dockets` first is what makes the citation graph trustworthy.

## Party names

Measured on FD 36873's 605 distinct "Filed For" values:

- Naive normalisation (stripping corporate suffixes, casefolding) collapsed them to 597. **Name
  variants are not the problem within a proceeding.**
- **91 of 605 cells are lists of parties, not one party** — e.g. "Norfolk Southern Corporation
  and Norfolk Southern Railway Company, Union Pacific Corporation and Union Pacific Railroad
  Company" in a single field.
- Some cells repeat the same party several times over.

The implication is the opposite of the obvious one: the first job is **splitting**, not merging.
The merge problem is real but lives across decades, not within a docket.

## What is not on stb.gov

- **Federal Register**: STB has 6,400+ FR documents, and every one returns an **empty
  `docket_ids` array**. There is no join key from an FR notice to the docket it belongs to.
- **regulations.gov**: STB documents exist there as orphans with `docketId: null`. There are
  **zero STB dockets** in the docket index and **zero STB comments** — the agency takes comments
  only through its own e-filing.

The record is split across three federal systems with no shared key. Building that join is
original work.

## Environmental comments

The environmental comments table carries the commenter's own submitted text in a field, plus a
location string. On FD 36873, 40 of 51 carried a clean "City, ST" — directly geocodable, and the
cheapest possible first map layer.
