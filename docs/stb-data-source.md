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

**The search page is cached, and a cached page carries a dead nonce** (measured 2026-08-26,
first production pass from AWS us-east-2). The page came back `x-cache: HIT` from stb.gov's
nginx cache with a nonce that WordPress rejected on every POST: **403 with body `-1`** — the
`check_ajax_referer` failure, not a WAF block, and not User-Agent dependent (a browser UA got
the same `-1`). `Cache-Control: no-cache` on the GET did nothing; a query string the cache had
not seen (`?dy=<epoch>`) returned `x-cache: MISS`, a different nonce, and a 200 on the POST.
The client cache-busts every nonce fetch. Home and rmi-ai-machine never hit this, presumably
because they reached a different cache node or an uncached copy; do not read a working nonce
from one network as proof it works from another.

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
the raw.

**The default row order is not repeatable** (measured 2026-08-25): two unsorted requests for
page 1 of the dockets table returned different rows. Multi-page walks MUST pin a sort. The
dockets table's sortable keys are in the search-page markup as `data-stb-sort`:
`docketNum` and `docketTitle.keyword` (the `.keyword` suffix is Elasticsearch idiom — and the
10,000 cap is ES's `max_result_window`, which is why no sort lifts it). An unknown `sort_by`
value returns the "There are no dockets available" envelope, not an error. **`sort_by=docketNum`
is repeatable and pages without overlap** (measured: page 1 twice identical, page 1 ∩ page 2
empty) — the walk order. `sort_by=officialFilingDate` (filings) and `sort_by=serviceDate`
(decisions) both return rows (measured in the same session); their page stability is assumed
from the dockets result, not separately measured.

**Docket census by prefix** (2026-08-25, `docketNum_one` filter, `total` per prefix): AB 6054,
AM 3, ARB 0, ASC 0, CNO 1, CU 16, DOP 4, DSO 0, EP 429, EPM 146, FD 8646, FSA 14, IS 267,
ISM 1944, MC 97, MCC 724, MCF 6006, MXC 13, NOM 1446, NOR 3431, PTO 6, RER 0, RR 5, S5A 0,
S5M 190, SAI 11, SDM 570, SO 22, STA 7, SUB 18, SUS 0, WB 106, WC 1, WCC 5 — **about 30,200
dockets, and no prefix reaches the 10,000 cap**, so prefix slicing alone walks the whole
registry in ~640 requests. **Walked in full 2026-08-25:** 627 requests, 32,604 docket rows in
the registry — the census rows plus ~2,400 parents minted for sub-dockets whose parent never
prints in the table (e.g. `AB_1_0`, implied by `AB_1_6`); exactly the six census-empty
prefixes quarantined. Id forms seen: `S5M_1_0_A` and `SUB_300_0_L` (suffix on a parent),
`CU_349` (bare parent), `WC_1548_1_C` (suffix on a sub); prefixes can contain digits.

**`per-page` is clamped to 50 server-side** (measured 2026-08-25): a request for
`per-page=100` returns 50 rows per page, and page 2 continues from row 51 (66 rows arrived as
50 + 16), so the server pages by its own clamp, not the requested size. Whether `total` counts
rows or records on the multi-row-per-filing tables is unmeasured; the safe stop condition is
"the first short page", never `seen >= total`. Visible columns:
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
wrong pair returns `{"success": false, "data": {"error": "<p>There are no filings available at
this time.</p>"}}` — and (measured 2026-08-25) **that is the identical envelope a page past the
end of a result set returns.** On a first page it is indistinguishable from a genuinely empty
slice, so ingest treats it as the trap; only after a page that passed the filter assertion
does it mean end-of-results.

**The date pair is inclusive at both ends** (measured 2026-08-26): `filingStartDate =
filingEndDate = 08/25/2026` returned exactly the rows dated 08/25; `08/24..08/25` returned
both days; `08/25..08/26` returned only 08/25 (nothing yet on the 26th). Month slices can
therefore meet edge to edge — last day of one, first day of the next — with no gap and no
double count.

**October 2025 has no filings** (measured 2026-08-26): every filings slice inside
`10/01/2025..10/31/2025` returns the no-results envelope; filings run to 2025-09-30 and
resume 2025-11-13 — the federal shutdown, during which the Board's e-filing was closed. Two
decisions were served on 2025-10-01. It is the one month in the record where the page-1
envelope is the truth rather than the trap; `walk.EXPECTED_EMPTY_MONTHS` records it, so a
wave marks the slice `empty` with this measurement as its reason instead of `partial`.

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

**Measured 2026-08-31** (the operator found the record holds none of them: AB 55 (Sub-No. 794X)
shows 70 records on our sheet where the Board's own search shows 6 environmental comments too):

- `action = stb_hook_table_environmental_comments` answers on the same nonce and the same
  `search-criteria[i][name]/[value]` vocabulary as the other tables. `docketNum_one/two/three`
  filter it, and the envelope echoes what it understood — "Search Criteria: Docket Prefix = AB,
  Sequence Number = 55, Sub Seque…". AB 55 (Sub-No. 794X) answers `total: 6`, matching the
  Board's own count exactly, including `EO-3243` of 10/4/2019.
- **The unfiltered table answers `total: 10000` — the display cap**, so the whole set needs
  slicing to walk, exactly as the dockets registry did.
- Default sort is "Date Received or Sent Desc."; `sort_by=""` is accepted.
- The columns, from one row: date; comment number (`EI-34280`); docket (`FD_36873`); submitter
  (`David Gertsch`); organisation (`Albany County Planning Department`); **the comment's own
  words**; **a location string** (`Laramie, WY`); and an attachment on the same S3 host
  (`EI-34280.pdf`).
- Row ids are composite: `AB_55_794_X|39772|753808`, alongside the comment number and the
  docket as separate anchors.
- **The date pair is `startDate`/`endDate`** — generic, and a third spelling of the same
  idea after filings' `filingStartDate` and decisions' `serviceStartDate`. Measured
  2026-08-31 by reading the search form (which declares `startDate`/`endDate` alongside
  the other pairs) and confirming against the endpoint, which echoes "Start Date =
  2026-01-01, End Date = 2026-08-31". **The filings trap applies here too**: the three
  wrong pairs (`filingStartDate`, `officialFilingStartDate`, `serviceStartDate`) each
  answer an empty envelope with a 200, not an error.
- **Volume, measured the same day by date slice**: 1996–2005 holds **2,057**; 2006–2015 and
  2016–2026 each answer the 10,000 display cap, so the whole set is **well over 22,000** —
  the order of the decisions table. A backfill therefore slices by year or month, as the
  record waves do; 2026 to date is 151, and a recent week held 5, so the forward rate is
  a handful a week agency-wide.
- The search page also declares an action this record does not use:
  `stb_hook_search_by_date`.

**Measured the same day by reading the rows themselves**, because the schema's natural key
turned on a fact the column list above did not settle. It corrects that list, which was taken
from a single row:

- The row is **nine cells, not eight**: `[0]` a folder button carrying the row's own
  `data-stb-id` and a `data-stb-record` label (`#EI-34280 | David Gertsch`); `[1]` date;
  `[2]` comment number; `[3]` docket; `[4]` submitter; `[5]` organisation; `[6]` the comment's
  words; `[7]` location; `[8]` attachment.
- **No cell prints the middle part of the composite id.** `FD_36873|203738|830758` prints
  neither `203738` nor `830758` anywhere in the row — so the corroboration check that guards
  filings and decisions (the printed id cell must agree with the id) cannot be written against
  it. What *is* printed is the comment number, which is also the `data-stb-id` of cell 2's own
  detail link. **Identity corroborates on the comment number and the docket.**
- Across **150 rows** of 2026 (three pages): comment number blank in 0, colliding with a
  different middle id in 0, repeated across different dockets in 0. `(docket, comment number)`
  is the identity the source will corroborate.
- **One comment spans several rows, one per attachment**, exactly as filings do — FD 36854's
  `EI-34249` occupies four. Folding by (docket, record) is required, not optional.
- **The table is not only comments.** Numbers carry two prefixes: `EI` for a submitted comment
  (42 of 50 on FD 36873) and `EO` for the Board's own environmental documents (8 of 50), whose
  submitter and organisation cells hold a document title — "Final Environmental Assessment" in
  both — rather than a person and an employer.
- **Half the rows carry no comment text at all**: 76 of the 150 print `--`, as do 10 of FD
  36873's 50. Location is absent in 37 of 150.
- **The comment text is not truncated.** The longest cell observed is 1,549 characters and
  ends on a complete signature; the lengths cluster at no round number.
- **The location format varies**: `Laramie, WY` and `Towson, Maryland` both occur — the state
  is not reliably a two-letter code, so parsing it is a judgement, not a split.
- **`per-page` is clamped to 50** here as elsewhere: `per_page=100` returns 50 rows and the
  envelope says "Records 1-50".
- `startDate`/`endDate` confirmed against a second slice: 2026-01-01 to 2026-08-31 answers
  `total: 151`, and the envelope echoes "Start Date = 2026-01-01, End Date = 2026-08-31".
  **Both spellings of a date are accepted**, and both echo back as ISO: `01/01/2026` and
  `2026-01-01` answer the same `total: 151`, so the walk's own `%m/%d/%Y` form needs no
  special case here. A single month (June 2026) answers 15 — comfortably inside one page.
- A per-comment detail modal exists — `stb_hook_modal_environmental_comment_details`, with its
  own nonce carried on the cell — but `id` is not its criterion name; it answers "The
  requested environmental comment could not be loaded." Nothing needs it: the table cell holds
  the whole comment.

**The sort, measured 2026-08-31 when the walk needed one to pin.** This table is the
exception to "every multi-page walk pins a sort", and both halves of why are traps:

- **Any non-empty `sort_by` answers the empty envelope with a 200.** `date`,
  `receivedDate`, `dateReceived`, `receivedOrSentDate`, `commentDate`, `receivedSentDate`,
  `dateReceivedOrSent` and `commentNum` were each tried: every one returns
  `success: false`, "There are no environmental comments available" — indistinguishable
  from a genuinely empty slice and from a page past the end. This is the **fourth**
  instance of the same silent-failure shape, after the criteria format, the filings date
  pair and the decisions date pair. `sort_by=""` is the only accepted value.
- **`sort_order` is echoed but not applied.** The envelope dutifully says "Sort by Date
  Received or Sent Asc." for `asc`, and returns byte-identical rows to `desc` — newest
  first either way. The order is not ours to choose.

**The default order is nonetheless stable enough to page, which was measured rather than
assumed.** The 2026 slice (`total: 151`) walked in four pages of 50 returned **151 rows
carrying 151 distinct `data-stb-id`s** — no overlap, no omission — and page 1 was
byte-identical on an immediate repeat. The last page returned 1 row, so a short page still
means end-of-results. Those same 151 rows carry only **143 distinct (docket, comment
number) pairs**: six comments occupy more than one row, one per attachment, exactly as
filings do.

## Measured 2026-08-26: document sizes

Attachments are served from S3 (`dcms-external.s3.amazonaws.com`) with `Content-Length`;
most are under a megabyte, but the record holds files of 22 MB, 56 MB and **1.07 GB**
(`303143.pdf`, the CP–KCS merger application in FD 36500, filed 2021-10-29). Reading a
body whole (`resp.read()`) took the wave process to 1.4 GB RSS and the kernel killed it on
the 2 GB instance, twice. Documents are therefore streamed to disk in 1 MB chunks
(`StbClient.download`) and hashed by chunks; nothing about a file's size is assumed.

## Measured 2026-08-27: the 41 "partial" months of 1996–2000 are empty

Waves 2–3 left 41 month slices `partial` (33 filings, 8 decisions, all 1996-01 → 2000-07):
each answered the no-results envelope on its first page, which the walker refuses to trust
as empty because the same envelope is what a wrong criterion returns. A month slice has no
census (only docket-prefix slices carry `expected_empty`), so the note "the census says
non-empty" over-states it — the walker simply cannot tell.

Neighbour-window reconciliation settles it: a window spanning a `done` month and the
doubted month returns exactly the done month's total, so the doubted month adds nothing.
`filingStartDate` 09/01–10/31/1996 → total 1 = September alone; 06/01–07/31/2000 → 56 =
June alone, while 06/01–08/31 → 70; `serviceStartDate` 01/01–08/31/1996 → 38 = August
alone. Both date-criteria pairs answer the envelope for the doubted months. The earliest
record the endpoint returns is dated 25 Jan 1996; 1995 answers the envelope outright.

What follows: the walker now runs this proof itself (`walk.reconcile_empty_month`):
a month that answers the envelope on its first page is walked outward to the nearest `done`
month and one window is asked across the doubted run; equal totals record the month
`empty` with the proof in its captures, anything else leaves it `partial` and says so. A
wrong criterion cannot pass — the window would answer the envelope too. The table below is
the measurement the mechanism was checked against.

| Table | Doubted months | Done neighbour | Neighbour total | Window total |
|---|---|---|---|---|
| decisions | 1996-01 → 1996-07 (7) | 1996-08 | 38 | 38 |
| decisions | 1996-09 (1) | 1996-10 | 1 | 1 |
| filings | 1996-02 → 1996-08 (7) | 1996-09 | 1 | 1 |
| filings | 1996-10 → 1996-11 (2) | 1996-12 | 2 | 2 |
| filings | 1997-02 → 1997-04 (3) | 1997-05 | 1 | 1 |
| filings | 1997-07 → 1998-02 (8) | 1998-03 | 101 | 101 |
| filings | 1998-08 (1) | 1998-09 | 7 | 7 |
| filings | 1998-10 (1) | 1998-11 | 2 | 2 |
| filings | 1998-12 → 1999-01 (2) | 1999-02 | 1 | 1 |
| filings | 1999-06 → 2000-01 (8) | 2000-02 | 655 | 655 |
| filings | 2000-07 (1) | 2000-08 | 14 | 14 |

Eleven windows, 22 requests, 41 months: every window equals its neighbour alone.
