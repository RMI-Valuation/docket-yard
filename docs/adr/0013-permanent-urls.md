# ADR 0013 — Permanent URLs

- **Status:** Accepted
- **Date:** 2026-08-25
- **Accepted:** 2026-08-25

## Context

A stable address for every docket, decision and filing is capability F2 and the reason a
site becomes citable in a brief (GovInfo proved the pattern). Once published, an address is
a promise for the life of the site: it can never be reused, repointed, or allowed to rot.
That makes the scheme a public promise and a one-way door. The identifiers the Board itself
prints — prefix, sequence, sub-number, suffix (ADR 0005), filing id, decision id — are the
only material the scheme may be built from, because anything else could change.

## Decision

- **Dockets:** `/d/{PREFIX}-{SEQUENCE}` for a parent, e.g. `/d/FD-36873`;
  `/d/{PREFIX}-{SEQUENCE}/sub/{SUB}` for a sub-docket, e.g. `/d/FD-36873/sub/1`. A suffix
  attaches to the level it belongs to: `/d/S5M-1-A` (suffix on a parent),
  `/d/AB-55/sub/785X` (suffix on a sub). Prefix and suffix are upper-case in the canonical
  address; any case resolves and redirects to canonical.
- **Records:** `/decision/{STB-DECISION-ID}` and `/filing/{STB-FILING-ID}`, e.g.
  `/decision/53210`, `/filing/311981` — the Board's own record ids, which its search form
  and links already expose.
- **Both parent spellings the source uses** (`FD_36873`, `FD_36873_0`) resolve to the one
  canonical address; the site never mints an address from a synthesised spelling.
- **Permanence rules:** an address, once served, is never reused for a different identity
  and never removed; a superseded record (an erratum, ADR 0002) keeps its address and
  points at its replacement; a corrected identity redirects with a 301 and keeps redirecting.
- **Cite-this** on every page emits exactly the canonical address, and the printed short
  form ("STB Finance Docket No. 36873") beside it.

## Consequences

Addresses are short, guessable and derivable by anyone who knows STB's numbering, so a
practitioner can type one without a search step. Routing needs the same parser the ingest
uses (`parse_docket_id`) — one definition of identity. The cost is the discipline: the URL
table is append-only forever, and a redesign that removes a path is forbidden by this record.

## Cost of reversing

Effectively impossible after launch. Every citation in a brief, every bookmark and every
inbound link is a promise this record made; changing the scheme means keeping the old one
alive forever anyway.

## Validation (2026-08-25)

Checked against [`../validation-queries.md`](../validation-queries.md): addresses are built
only from the identity ADR 0005 keys on (prefix, sequence, sub, suffix) and the record ids
the source prints, so every query's join path is unchanged. Query 3's "the day before
Decision No. 30" resolves through `/decision/{id}` once the printed decision number is
extracted — an addition, not a re-keying. Implemented the same day in `web/urls.py`, which
delegates to the ingest parser so there is one definition of identity; the review of that
code caught a second grammar creeping in and it was removed.

## Addendum (2026-08-26): weeks

A fourth address class, decided by the operator: **`/week/{Monday}`** — a fixed Monday to
Sunday calendar week (ISO), addressed by the ISO date of its Monday, e.g. `/week/2026-08-17`.
Any day of the week resolves to its Monday with a 301; `/week` redirects to the most
recent complete week. The home page's "this week" stays a rolling seven days ending at the
latest activity and is not an address. A week the record does not yet cover exists at its
address and says so, filling in when a backfill wave reaches it. The permanence rules
above apply unchanged: a week address, once served, is never removed or repointed.

## Addendum (2026-08-26): the boundary of the promise

Decided by the operator: the promise covers addresses built from what the Board itself
identifies — dockets, filings, decisions — and calendar weeks, which are dates. It does
**not** extend to anything the pipeline derives: parties, places, labels, folds. Those are
reading aids reached by query, may be re-minted or re-resolved as methods improve, and are
never offered in a "cite this" box. A derived thing earns a permanent address only by a
further record here, never by being served once.

> **Note (2026-08-26):** the paragraph above is superseded for **parties** by
> [ADR 0015](0015-a-party-has-an-address.md), accepted the same day: a party's id is its
> permanent address (`/p/<id>`), never reused or renumbered, with 301 from any id folded
> into a same_as component to its representative. The boundary stands unchanged for
> places, labels and folds. This record is not edited; the note is appended (ADR 0001).

## Addendum (2026-08-27): documents by content hash

Decided by the operator: a fifth address class, **`/document/{sha256}.{ext}`** — the bytes of a
document the record holds, addressed by their SHA-256 (ADR 0002); the suffix names what the
bytes are (`pdf`, `jpg`, `zip`, `xlsx`, `docx`; `bin` when nothing sniffed) and any other
suffix at the same hash answers 301 to it. A PDF or image is served inline so a browser shows
it rather than downloads it, with the Board's own file linked beside. The hash is
the identity, so the address is permanent by construction: the same bytes always answer at
the same address, and a replaced file (an erratum) is a different address, with the chain
kept in `document_source`. The address is offered in the cite box and listed in the sitemap.
It carries no derived claim; it is the primary source itself. The viewer page a reader opens
from a sheet — `/filing/{id}/view`, `/decision/{id}/view` — is a sub-address of a record
that already exists and adds no class.

## Addendum (2026-09-03): the record's text

`/filing/{id}/text` and `/decision/{id}/text` show what a machine read from the record's
file, page by page (ADR 0021 D7). **One address per record, not per page** — the operator's
decision, 2026-09-03: `?file=N` picks among several files as the viewer's does, and `#p<n>`
anchors a page. 1.1M page addresses against 74k records would be a crawler's address space,
and a crawler walking one is this site's one real outage (2026-09-02). Like the viewer it is
a sub-address of a record that already exists and adds no class; unlike the viewer it is
**held** from the CC0 dedication with the party module (`robots.txt` names it for the agents
named there) and is not listed in the sitemap. Its validator is the document's own
(`page_stamp`), so a corrected page moves that page and nothing else. What the page says
about a misreading and `/corrections` is `docs/ocr-migration.md` item 26, undecided.

## Addendum (2026-09-03): the viewer address retires into the record

Decided by the operator, put as a question once the O(docket) read behind the viewer was
gone: **the record page carries the frame.** `/filing/{id}` and `/decision/{id}` show the
record's file beside the record, with `?file=N` picking among several and `#file` landing on
the frame; `/filing/{id}/view` and `/decision/{id}/view` answer **301** to that, carrying
`?file=N`, because a permanent address never dies. What the viewer showed and the record
page does not — the neighbours on the sheet, the follow form — is the sheet's; the text page
keeps its scan link, which now lands on the record.

## Addendum (2026-09-04): the rail comes back with the record

The addendum above sent the neighbours and the follow form back to the sheet. In use that
was wrong, and the operator said so: a reader who reaches a decision from a search result or
an alert is on the record page, not the sheet, and the record page had stopped showing the
files it holds, the parties it was filed for, the records either side of it, and its
citation. Nothing had replaced them — they were the viewer's rail, and the rail did not come
across when `/view` folded in.

**The record page carries a rail beside the frame**, in the `.viewer` grid the text page
already uses: the parties resolved from the "Filed For" cell and linked to `/p/<id>`, the
files with the hash that is each one's identity and a link to the Board's own copy, the
neighbours in sheet order, the citation with its copy button, and the follow form. No new
address, no new class of page — this addendum changes what a record page *shows*, not where
anything lives, so nothing in the Decision above moves.

The read behind it is `sheet.entry_and_neighbours`, restored rather than rebuilt: it orders
the family from three small queries and never assembles an entry it will discard. Measured
2026-09-04 on a production copy, FD 35087 (12,031 comments, the worst docket in the record):
`docket_sheet` 235.3 ms, `one_entry` 8.5 ms, this 22.6 ms — 2.7x the cheap read where it
hurts most, and 10x under the read that caused the 2026-09-02 outage. Over 40 ordinary
records, which is what a crawler meets, 1.09 ms against 1.28 ms.

A comment's page has no frame, so it has no rail, and its caption keeps the file addresses
the framed pages moved into Cite. The caption still quotes the "Filed For" cell as the Board
printed it; the rail's links are that same cell resolved by rule, and both are shown on
purpose — the quote is the record, the links are derived from it (ADR 0004, ADR 0007).
