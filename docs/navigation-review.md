# Navigation review — what the record holds and what a reader can reach

> **Status: analysis, 2026-08-31. Tiers 1–2 shipped 2026-09-01 (v2026.08.45), A6 the same
> day (v2026.08.46), and the first of Tier 3 after it (v2026.08.47)** — A1–A6, A8 and § B
> are fixed; of § C, the weeks index, the sub-docket breadcrumb and `/parties` as a page
> are built, and a docket index by prefix and year is not.
> A7, § D, § E and Tier 4 are unchanged and still the operator's to choose. Every measurement below
> is left as it was taken, because it is the evidence the fixes were made against; what
> shipped is recorded in `milestones.md` and in the commit, not by editing the numbers here.
>
> Requested by the operator after finding that search
> returns bare docket numbers, that the home page's "this week" is not the same week as
> `/week`, and that stepping back through weeks hits a wall at 10 Aug 2026. Nothing here is
> chosen work; `ROADMAP.md` § Chosen and `TODO.md` remain the record of what is being built.
> Six read-only passes over the live site, the templates and the production store, each
> measured. Every number below was taken on 2026-08-31 against `v2026.08.44`.

## The answer in one paragraph

The record is far larger and far better than the site lets anyone see. Three of the four
things the operator noticed are the same failure wearing different clothes: **the record
knows, and the page does not say.** The captions are in the search index and the template
never prints them. Three weeks of held filings are behind a sentence claiming they are not
covered. Thirty years of week pages render perfectly and are reachable only by clicking
"previous week" sixteen hundred times. The fourth — the masthead — is the reason none of it
is browsable: two entry points (this week, and a text box) into 32,623 proceedings. None of
this needs new data, and almost none of it needs new schema.

## The number that reframes the site

| | |
| --- | --- |
| Root families in the registry | 21,821 |
| …holding any filing | 3,483 |
| …holding any decision | 4,940 |
| …holding any environmental comment | 362 |
| …holding **any record at all** | 5,018 |
| **…holding only a caption** | **16,803 — 77.0%** |

For three quarters of the proceedings in this record, **the Board's caption is the entire
record**: no filing, no decision, no comment, no date, no party. It is also the one field
no search result, no suggest row and no index prints. `FD 30101` is the case in miniature —
zero filings, zero decisions, and a caption reading
`NORFOLK AND WESTERN RY CO.-ABANDONMENT EXEMPTION-WYOMING,WV`. The search row said
`FD 30101 — 0 filings`, which is accurate and useless, while the only thing the record knows
sat one field away in the same tuple.

That also settles a question worth settling: `0 filings` is *correct* for 91.6% of the rows
carrying it. It is not a counting bug. The page answers "how much is here" when the reader
is asking "what is this".

---

## A. Defects — these are wrong, not debatable

### A1. `covered()` reads the walk ledger with a key the ledger does not always use

**Fixed 2026-08-31.** `_walked_days()` expands each slice to the days it names — the whole
month for an unsuffixed key, `lo..hi` for a suffixed one — and `covered()` requires every
day of the window for both tables. It stops hiding what was walked without starting to
claim what was not. A test now carries a range-suffixed key.


`store/home.py:199` matches `slice_key = f"{action}:{month}"` exactly.
`capture/walk.py:427` appends `:{lo}..{hi}` whenever a wave walked part of a month. August
2026 is the only month that ever happened to — the wave stopped at the watch start. On
production, the **entire 368-month ledger contains exactly two range-suffixed slices**, both
August 2026, both `done`:

```text
stb_hook_table_filings:2026-08:2026-08-01..2026-08-26     done
stb_hook_table_decisions:2026-08:2026-08-01..2026-08-26   done
```

`store/coverage.py:137` reads the same ledger and strips the suffix correctly. Two modules,
one ledger, one of them right.

**Cost:** 91 filings and 16 decisions across three consecutive weeks, hidden behind
"Docket Yard's record does not yet cover this week". And because those three weeks sit
between the reader and everything older, the unbroken 1996–2026 archive is unreachable by
clicking. The wall is three weeks thick and thirty years deep.

Fix: match on the month prefix, as `coverage.py` already does. Add a test with a
range-suffixed key — none exists.

### A2. The "not covered" sentence can be printed over records the page is holding

**Fixed 2026-08-31.** `coverage_state()` is the only thing a week page asks, and it returns
`uncovered` — the one state that may print the sentence — only when the window's filing and
decision counts are both zero. A short ledger over held records is `partial`: the records
render, with a line saying how far the walk reached.


Independent of A1, nothing prevents recurrence. The sentence asserts three things and
measures one: that the ledger is short (measured), that nothing is here (never checked), and
— by its absence elsewhere — that a covered week is complete (a claim the record cannot make
anywhere). The invariant is cheap: **the sentence renders only when the window's counts are
zero.** Otherwise render what is held, with a line saying how far the walk reached.

### A3. `/coverage` blames filings and decisions for the comment walk's gaps

**Fixed 2026-08-31**, wording approved by the operator. `records_incomplete` and
`comments_incomplete` are separate, the comment clause sits outside the backfill branch
because the two walks are independent, and consecutive months collapse to a range so 56 of
them read as one. `/mcp`'s coverage answer was unioned the same way and is split too.


`store/coverage.py:134` unions all three record tables into one `backfill_incomplete` list,
and the template prints it inside a sentence whose subject is filings and decisions. The
live page therefore tells readers that **1996-01 through 2000-08 — 56 months — are not yet
complete for filings and decisions.** They are complete. Those 56 partial slices are every
one of them `stb_hook_table_environmental_comments`, because the Board's comment table does
not begin until September 2000. The page is wrong in both directions: it names four and a
half years that are fine and omits the one month that is genuinely partial.

This is a coverage claim on a trust page, so the corrected wording is the operator's to
approve, not just a code change.

The three pages currently contradict each other about August 2026: `/stats` publishes 254
filings for the month, `/week` hides 91 of them as uncovered, and `/coverage` says the month
is fine and 1996 is not.

### A4. Future weeks claim to be empty; year 1 is a 500

**Fixed 2026-08-31.** A week outside `[1990-01-01, today + 366 days]` is a 404, which ends
both corridors and both overflows; both bounds are fixed constants, never read from the
record, so an address that answers 200 cannot later answer 404. A week that has not
happened yet says so, and is `noindex`.


`/week/2030-01-07` renders "0 decisions served, 0 filings observed, in 0 proceedings" — the
record affirmatively asserting an empty week four years out, because `covered()`'s
watch-start test has no upper bound. The honest page says the week has not happened yet.
`/week/0001-01-01` returns **HTTP 500** (date arithmetic overflow in the prev/next links),
and `/week/1900-01-01` answers 200 with a link to `/week/1899-12-25` — an unbounded backward
corridor of pages on a single-process box.

### A5. Every archive week page is headed "this week"

**Fixed 2026-08-31.** The heading is passed into `_week_body.html`; the home page's window
is "The latest seven days at the Board" (operator's wording), so "this week" no longer
names two different units. The home page's `<title>` and `og:title` named the rolling
window too, and now name the record.


`_week_body.html` is shared by the home page and the ~1,590 dated week pages, and the
heading is a constant. `/week/2010-03-01` is titled "Week of 1 Mar 2010" and then, below it,
"Proceedings that moved **this week**". The wording problem the operator found on the home
page is stamped across thirty years of archive.

### A6. The follow controls on a sub-docket sheet subscribe to two different things

**Decided 2026-08-31, not built.** The operator's call: an AB sub-docket subscription stops
folding to its family; FD and every other prefix keep folding. It changes what a
subscription means, so it is its own change with its own review, not part of a corrective
release. In `TODO.md`.


`web/app.py:1105` — `family = identity.parent() or identity` — silently rewrites any
sub-docket subscription to its family. The form on `/d/AB-55/sub/794X` says **"Follow this
docket"**; what it subscribes to is all 766 of AB 55's proceedings. The reader finds out
from the confirmation email, which names AB 55.

Two lines away, the Atom link on the same page is `/d/AB-55/feed` — also the family — while
`/d/AB-55/sub/794X/feed` returns **404**.

For FD, where a sub-docket is a phase of one proceeding, the fold is right. For AB, where a
sub-docket **is** the abandonment of one line in one county, it is exactly wrong — and AB is
where the lay reader is. This is the one item in this review that is arguably a broken
promise rather than a missing feature.

### A7. A series sheet and its own JSON twin disagree about what the proceeding is

`/d/AB-167` is 399,160 bytes and renders **zero** entries — the template substitutes prose —
while advertising "602 filings, 258 decisions and 1,768 environmental comments observed
here". `/d/AB-167.json` is **2,075,728 bytes** and publishes all 2,628 of them. The page
builds that list, discards it, and gives the reader no way to reach the counts it quotes.
`docs/deferred.md` frames this as a performance question; it is now also a
correctness-of-presentation one.

Two tables on that same page also disagree with each other: the "most recently active" table
totals filings + decisions + comments, the full index has no Comments column, so
AB 167 (Sub-No. 1189X) reads as "1861 held" in one and "282 filings, 46 decisions" in the
other, with 1,533 comments vanishing between them.

### A8. Small and stale

All four fixed or decided 2026-08-31, except the two marked below.

- `/stats` does not mention environmental comments anywhere — 34,257 records, a third of the
  search index, absent from the statistics page. `store/stats.py` contains no reference to
  `enviro_comment`.
- The 404 page still says "a corrections page is being written for exactly that".
  `/corrections` shipped and is in the footer.
- `sheet.html:115` puts an "in the protective-order register" badge on any entry whose type
  names a protective order. There is **no equivalent badge for court actions**: the register
  holds 341 notices across 290 dockets and no sheet entry points at it. Same machinery, one
  of the two wired up. (The footer link on every page makes this easy to miss — inside
  `<main>`, FD 36873 carries three links to `/protective` and none to `/court`.)
- `/about`, `/llms.txt` and the snapshot manifest describe a record without comments.
- `<title>` and `og:title` on the home page are "Docket Yard — this week at the Surface
  Transportation Board", so every search result and link unfurl of the bare domain is titled
  by a rolling seven-day window rather than by a record running 1996 to today.

---

## B. The withheld record — everything matched, nothing shown

**Fixed 2026-08-31.** `search_doc.caption` (migration 0013) carries the row's own printed
name and the template leads with it, the identifier beside it; every row can carry a
highlighted `snippet()` of the body saying why it matched, dropped when it would only repeat
the caption. `/suggest` carries the caption too — the promise `search.md` had made since M4
— and deliberately not the snippet, whose markers are control characters. The caption is a
column rather than the title because `title` is weighted 8.0 in the ranking and holds the
number a reader types.

`store/search.py` yields `(kind, ref, path, title, body, fact)` per row.
`templates/search.html:21` renders `kind`, `title` and `fact`. **It never renders `body`** —
and `body` is where every generator but one puts the words:

| Row kind | `title` yielded | what sits in `body`, unprinted |
| --- | --- | --- |
| docket (sub) | `AB 307 (Sub-No. 5X)` | `WYOMING AND COLORADO RAILROAD COMPANY, INC.--ABANDONMENT EXEMPTION--IN CARBON COUNTY, WY` |
| docket (family) | `FD 30101` | the caption, the spellings, every sub-caption |
| decision | `Decision 52435` | **the Board's own printed summary** |
| comment | `EI-1041` | submitter, organisation, location, the commenter's own words |
| party | *a name* | the component's other names |

**86,069 of 96,225 index rows (89.4%) have an identifier-only title.** 29,542 of 31,979
docket rows (92.4%) carry their own caption in `body`. All 19,833 decision rows carry a
summary by construction — the generator filters out the ones without. Parties are the one
kind that works, and they are the one kind whose title is a name.

So "search returns docket numbers but doesn't tell you what they are" is not a data gap and
not the Board's missing captions. It is three lines of template.

Two consequences worth stating separately:

- **A result list looks homogeneous when it is not.** In the operator's Wyoming search,
  `FD 30101` matched because it is in Wyoming, *West Virginia*; `AB 307 (Sub-No. 5X)` matched
  the railroad company's name, not the state. Nothing on the page distinguishes them, because
  the matched term appears nowhere — not bolded, not snippeted, not in the fact column.
- **FTS5 `snippet()` and `highlight()` already work against the live index**, with no schema
  change, no rebuild and no migration. Showing why a row matched is available today.

The same defect runs through `/suggest`, which `docs/search.md` promises "answers
as-you-type with captions" and which returns `{"title": "AB 3", "fact": "the docket sheet"}`.

---

## C. No way in

Two entry points into the whole record: **this week, and a text box.** Everything else needs
you to already know what you are looking for.

The masthead is `This week | Parties | Statistics` — and `/parties`, one of the three, is a
heading, a sentence and an empty search box: 10,156 parties, not one of them named, no list,
no alphabet. **Fixed 2026-09-01**: the fifty busiest are named with their counts, and an
alphabet leads to a page per initial over all 10,108 components. Counting them exposed a
second defect — `/stats` counted `party` ROWS where `/parties` counts components, so two of
the three masthead pages published different numbers under one sentence; a party is the
entity (ADR 0015), so `/stats` now counts components too. Thirteen further surfaces are footer-only.

| Surface | Clicks from home | How a reader finds it today |
| --- | --- | --- |
| ~32,000 of 32,623 dockets | ∞ | the search box, or nothing |
| ~10,150 of 10,156 parties | ∞ | type a name you already know — **`/parties` since 2026-09-01: the 50 busiest named, and an A–Z over all 10,108** |
| ~34,250 of 34,257 comments | ∞ | a sheet you already found, or a search hit |
| ~1,540 of ~1,550 active weeks | ∞ | "← previous week", one at a time — **`/weeks` since 2026-09-01: 1,550 weeks, 31 years, one page, in the sitemap** |
| `/about/prefixes` (the page) | 3 | Statistics → an explainer → "Every docket prefix" |

**Crawlers get seven indexes; readers get none.** `sitemaps.py` publishes pages, dockets,
decisions, filings, comments, parties and documents. `llms.txt` hands a machine a curated
four-item map of the record. That map is better than anything a reader is offered — and the
weeks are in neither, so no search engine can be the index the site lacks.

The trust pages are terminal: `/coverage`, `/methodology`, `/privacy` and `/parties` contain
zero outbound internal links. `/coverage` states the record holds 32,623 dockets back to
1996 and offers no way to look at any of them. It is the most-linked page in the templates
and the emptiest exit.

The deep pages are where strangers actually land — roughly 107,000 of ~130,000 indexable
addresses are filings, decisions and comments — and none of them carries the "About this
record" block that the docket sheet carries. A filing page's entire link set is its docket
and the PDF. All ~130,000 pages share one identical `meta description`.

The long tail is a field of cul-de-sacs: 952 of AB 167's 995 proceedings hold nothing, and
each is a page with no link to its parent, no siblings, no `/coverage`, and filter chips that
filter an empty list. A sub-docket sheet never links up to its series — `store/sheet.py:88`
matches `docket_id = ? OR parent_docket_id = ?` against the page's own id, so on a child the
family query returns only itself. **The way up shipped 2026-09-01** (`sheet.Series`): every
sub-docket page now names its series and links to it, which is also the way to its siblings,
since the series page indexes them. The filter chips are unchanged.

---

## D. Weight and shape

| Page | Bytes | Entries |
| --- | --- | --- |
| `/d/AB-167/sub/1189X` | **2,641,718** | 1,861 — of which 1,533 comments |
| `/d/FD-36873` | 2,164,447 | 1,142 |
| `/d/AB-167.json` | 2,075,728 | 2,628 |
| `/d/AB-167` | 399,160 | 0 rendered |
| `/protective` | 443,239 | unpaginated |

The heaviest page on the site is not the merger — it is a 1990s abandonment carrying 1,533
environmental comments. `docs/deferred.md` records "FD 36873 is 1.1 MB / 908 entries",
which is stale in both the number and the page it names.

The cost is DOM, not bandwidth: Caddy gzips FD 36873 to ~120 KB, but the page carries 27,537
elements and 2,233 inline SVG icons — one per entry link, repeated. Two cheaper moves than
pagination should be priced first: replacing the repeated SVGs with `<symbol>`/`<use>`, and
windowing by year. The measurement `docs/deferred.md` asks for — a real low-end phone — has
still not been taken.

Every sheet filter is client-side JavaScript with no URL state, so "the decisions in
FD 36873" is not a linkable address, is not crawlable, and does not exist at all without
JavaScript. The follow form sits at roughly line 24,496 of ~24,600.

Structurally: **there is no index on `filing(filed_date)` or `decision_record(service_date)`.**
Every date-window query on the home page, the week pages and `/stats` is a full scan. It is
cheap at 62,000 rows behind a 300-second cache, and it is the thing that would have to change
before a year-by-year browse.

---

## E. What the record could serve and does not

- **Place.** 3,730 of 30,184 held captions name a county, parish or borough — concentrated
  exactly where the lay reader is: **52.1% of AB captions (3,158 of 6,056)**, against 6.1% of
  FD and under 1% of MCF, NOR, ISM and NOM. Alongside them sit 11,821 environmental comments
  carrying a location as the commenter wrote it. A place index built from those two string
  sets is quotation, not inference — ADR 0008's "structured rows before there is a map",
  which is what this would be. Note that `ROADMAP.md`'s "maps and geography: not ripe"
  measurement is dated 2026-08-27 and predates the comment wave by four days.
- **The Board's own summaries.** 19,833 decisions arrive with a summary written by the
  agency. `docs/research/comparable-platforms.md` records that CourtListener built extraction
  and clustering to obtain the equivalent; here they arrive pre-written and the results page
  discards them.
- **Replacements.** ADR 0002's `supersedes_sha256` and the `document_replaced` event exist,
  `/coverage` says a replaced file is noticed, and no reader surface shows one. A register
  over corrected decisions and notices is the same rule shape as `/court`.
- **A human page for `/cite`.** The resolver works and answers JSON only.

---

## F. A sequence, if the operator wants one

Cheap and strictly corrective first; nothing here is chosen work.

**Tier 1 — say what is true (hours, no schema, no new address).**
A1 the slice-key match, A2 the invariant, A5 the shared heading, A4 the two week bounds,
A3 the `/coverage` sentence (wording needs sign-off), A8's stale strings, and the comments
count on `/stats`. This alone reopens the whole 1996–2026 archive to navigation.

**Tier 2 — print what is already indexed (small, one template and one query).**
Render `body` as a highlighted snippet on every search row; make the caption a docket row's
title with the number beside it. One change, and T1, T4, T5 and T6 all improve at once.

**Tier 3 — a front door (a day or two each).** *The weeks index and the breadcrumb shipped
2026-09-01; the aggregate measured 35 ms, not 120.*
A weeks index built from the ~120 ms full-record aggregate; a docket index by prefix and
year, linked from the explainers that currently dead-end after saying "the registry holds
6,643 AB dockets"; `/parties` as a page before it is a search; and the sub-docket → series
breadcrumb.

**Tier 4 — decisions, not tasks.** The masthead's shape. Whether the home window stays
rolling or becomes the calendar week. Whether the alert unit follows the sub-docket. What a
series sheet is. Whether a place index is ripe.

## G. What remains unmeasured

- **What readers do.** By design there is no query log and no per-page counter (ADR 0011).
  Over five days of traffic, human-classified requests to `/search` total 47, to `/parties`
  70, to `/week` 135, against 70,632 bot requests to record pages. The site is unannounced;
  there is no audience to measure yet, so this review reasons from tasks and comparables, not
  from analytics.
- **A real phone against a 2.6 MB sheet.** Still the open question in `docs/deferred.md`.
- **`snippet()` cost over 50 rows on the instance.** Verified working on two; the worst case
  re-reads a 79 KB body.
- **Whether the published snapshot carries the comment tables.** `dump.py` allowlists them;
  the live manifest still reports `schema_version: 10`.
- **Whether the August 2026 range slice was excluded deliberately.** `walk.py`'s comment
  explains why the suffix exists for the *walker*; nothing records whether `covered()` was
  meant to inherit that strictness. Either way A2 must hold.
