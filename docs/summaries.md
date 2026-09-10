# Docket summaries — the specification

**Status: specified 2026-09-10; not chosen, not built.** The operator called summaries a
good future feature, labelled as generated, and asked what one would look like before
anything was built. This document is that answer, with three dockets rendered by hand from
the record so the shape is settled before a model is asked. It is capability-map entry
P6 and waits for a decision; the fifty-docket sample in § What the sample measures
is the first thing the decision would start.

The mistake it prevents: **a summary that is the model's opinion of a proceeding.** A model
handed 1,174 filings and asked what happened will say what it thinks happened, and nothing
on the page can check it. The record does not publish claims that cannot be checked
(ADR 0007). So a summary here is a *composition of facts the record already holds and
sentences each grounded in one document*, and the generated part is as small as the record
allows — which, it turns out, is smaller than expected.

## What the record already says

Measured 2026-09-10 on production (schema 24):

| | median docket | FD 36447 | FD 36873 |
| --- | --- | --- | --- |
| Filings | 3 | 175 | 1,177 |
| Decisions | 1 | 33 | 37 |
| Decisions carrying the Board's own **Digest** | 0 | 11 (every Entire Board decision) | 6 |
| Span | 4½ months | 5 years 9 months | 13 months |
| Dockets with over 100 filings, whole record | | 70 | |
| Dockets with over 1,000 filings, whole record | | 3 | |

Two facts shape everything below.

**An Entire Board decision carries a Digest** — one paragraph, written by the Board, stating
what the decision does ("The Board waives a regulatory limitation … and conditionally
accepts an otherwise complete feeder line application, contingent upon applicant's
submission of a valuation estimate by December 28, 2020"). It is the Board's own summary of
its own act. For those decisions nothing is generated: the Digest is quoted, with the
footnote the Board attaches to it ("The digest constitutes no part of the decision of the
Board but has been prepared for the convenience of the reader"). Decisions of the Director
of Proceedings, the Chief Counsel, the Office of Environmental Analysis and the
administrative law judge carry no Digest; they are the majority (22 of 33 in FD 36447) and
they are procedural — schedules, extensions, discovery rulings, subpoenas.

**A filing's type and filer are recorded facts.** The Board's filing type ("Application",
"Reply", "Motion To Compel", "Notice Of Intent To Participate (Without Comment)") and the
"Filed For" cell are in the record, and the party module resolves the filer to an entity.
So who filed what kind of thing, when, needs no model. What a filing *asks for* is in its
text, and that is where a generated sentence is needed.

## The shape

A summary opens with **where the proceeding stands** — the latest decision's entry and a
status line quoted from it — then a dated list, decisions and selected filings interleaved,
each entry one sentence, each sentence standing on exactly one document; then a count of
what the list left out. The newest act is the first thing on the page, because on a
six-year docket it is what a reader most likely came for; the list below runs in date order,
because a proceeding reads as a story that way. Long dockets get long lists, and the length
is the record's, not the model's.

```
  AI-generated summary · from the documents listed · <model> <version> · prompt v<N> ·
  generated <date> · not reviewed · [how this was made]

  Where it stands — decision served 2026-05-27, Entire Board:
              "<the Board's Digest, quoted>"
  Before the Board: "<the deadline or step that decision sets, quoted>"

  2020-11-12  Application       Lake Providence Port Commission, …
              <one sentence: what the filing asks for, in its words>
  2020-12-02  Reply             Delta Southern Railroad, Inc.
              <one sentence>
  2020-12-11  Decision          Entire Board
              "<the Board's Digest, quoted>"
  2021-01-15  Decision          Director of Proceedings
              <one generated sentence>
  …
  2026-09-02  Decision          Entire Board
              <one sentence>
  Not listed: 25 letters, 5 errata, … — the full list is the docket sheet
```

Every sentence links to its document and carries the provenance block beside it (§ Each
sentence is an assertion). A reader who doubts a sentence is one click from the page it
came from.

### Rule 1 — which documents get a sentence

Mechanical, stated on `/methodology`, and never the model's judgement of what matters:

1. **The opening filing**, always: the earliest filing whose type is Application, Petition,
   Notice of Exemption, Notice of Intent to Initiate Case, Complaint, or the docket's first
   filing if none of those. It defines what the proceeding is.
2. **Every decision.** A Digest where the Board wrote one; a generated sentence where it did
   not.
3. **Every filing a decision cites.** The Board's own acts say which filings mattered. Once
   the citation graph (C2) is on, this is an edge lookup; until then, the decision's text
   names them and the sentence for the decision links them.
4. **Filings by type**: Application, Petition, Motion (every kind), Reply, Appeal, Status
   Report, Brief, Verified Statement, Rebuttal, and Modify/Supplement Prior Filing. Not:
   Letter, Comment, Comments, Notice Of Intent To Participate, Support Statement, Errata,
   Certificate Of Service, Exhibit(s), Substitution Of Counsel, Miscellaneous. The line is
   *pleadings that ask the Board for something* against *correspondence and the public's
   comments*. The list is a constant in the code, rendered on `/methodology` from the
   constant, and a change to it is a version bump of the method (§ Each sentence is an
   assertion).
5. **A cap with a visible remainder, and recency wins under it.** Above N entries (N a
   constant; 60 to start) the list keeps the opening filing, every decision and every
   decision-cited filing unconditionally, and admits pleadings by type **newest first**
   until N is reached; the remainder line counts what was left out by type, and the docket
   sheet is the full list. So when the cap binds, this summer's motions are on the page and
   the first winter's replies are in the count — never the reverse. FD 36873 hits the cap;
   FD 36447, at about 130 entries, does not, and shows all of them.

Everything not listed is **counted, by type and by filer**, in the remainder line — a
count is a fact, and a proceeding with 533 notices of intent to participate and 208 comments
is described by those numbers better than by any sentence about them.

### Rule 2 — what a sentence may say

A generated sentence says **what the document asks for or states, in the document's own
words, attributed to the filer the record holds.** "Delta Southern Railroad's motion asks the
Board to reject the amended application as incomplete and terminate the proceeding" is a
sentence about a document. "Delta Southern opposes the sale" is a sentence about a party,
and the rule that a party's position is never inferred (CLAUDE.md) forbids it — not because
it is false, but because it was not read off a document; it was concluded. The difference is
that the first sentence can be wrong in a way a reader can check, and the second cannot.

Concretely, the prompt for a filing sentence is given the filing's first pages and asked for
one sentence beginning with the filer's name and a verb of asking or stating (asks, moves,
requests, notifies, reports, replies that, states that), naming the relief sought or the
fact stated, and nothing about motive, merit, likelihood or outcome. For a decision without
a Digest, the same with the deciding body as subject and a verb of deciding (grants, denies,
sets, extends, orders, directs, holds in abeyance). Dates inside a sentence are the
document's printed dates, never computed (CLAUDE.md).

The sentence is checked before it is stored: it must name the filer (or body) the record
holds; every proper noun in it must appear in the document's text; every date in it must
appear in the document's text; it must be one sentence under a length bound. A sentence that
fails is not stored, and the entry shows the recorded facts alone — date, type, filer, link —
which is the fallback for the whole summary too (§ When the model is not there).

### Rule 3 — where it stands

The first thing on the page, above the list: the latest decision's entry (its Digest, or its
generated sentence), and a status line quoting what that decision says is before the Board
— the sentence in its text that sets the next deadline or procedural step — with the
decision's service date. It never computes a deadline from a rule; it prints the one the
Board printed. When the latest document is a filing rather than a decision (a consummation
notice closing an abandonment, a notice of withdrawal), the entry shown is still the latest
*decision's*, and the filing sits at the foot of the list where its date puts it; the
reader sees both, and the page does not decide what the filing means.

### Rule 4 — the label

Above the list, always, in one line: that the summary is generated; from which documents
(the list itself); by which model at which version, which prompt version, on which date;
that it is not reviewed (or: reviewed by a named reviewer on a date, when it has been);
and a link to the method on `/methodology`. Beside each generated sentence: a mark that it
is generated, distinct from the mark on a quoted Digest. A summary that a reviewer has
corrected shows the correction as the review path does everywhere (ADR 0016).

## Each sentence is an assertion

Under ADR 0007 a generated sentence is a derived assertion and carries: the source document
(sha256), the location (the pages given to the model), the method (`docket-summary`),
the method version (which encodes the model identifier, its version or quantisation, the
engine, and the prompt version — one string, so two configurations never share it, the
same discipline ADR 0023 applies to a reading), the time, and a confidence. It lives in
its own table with the store's `superseded_by` idiom, a live index per (document, method),
and a review path. It is *not* stored in `document_text`: a summary is not a reading of the
document, it is a claim about it.

The composed summary is not stored at all. It is rendered from the record's facts and the
live sentences, the way every page is rendered from the store, so it cannot drift from what
the sentences say, and re-running the model for one document replaces one sentence.

A Digest is stored as an assertion too, with method `board-digest` and a version, so the
page can say which decisions the Board summarised itself and the citator can find the
Digest's span; its confidence is 1.0 and its text is the Board's.

## When the model is not there

The summary degrades to facts. With no sentence stored for a document, its entry is the
date, the type, the filer and the link — which is the docket sheet's row. A docket with no
sentences at all shows the list under Rule 1 with no generated text, the remainder line and
no status line. That is a worse page than the sheet and a better one than a blank, and it
is what every docket shows between the decision to build this and the first pass over it.

## Where it runs

A `summary` pass on the fleet (ADR 0025): a job per document under Rule 1, a worker that
claims documents instead of pages, the same lease, the same monitor. The backfill runs on
the GPU boxes; the forward trickle — a handful of documents a day — on the Jetson, which is
always on and idle. Two producers means two method versions and the page saying which; a
later fleet pass re-reads the trickle's documents under the backfill's version, so the
difference is temporary (`docs/compute-fleet.md`). The API route (a frontier model through
the batch endpoint) is a third producer and a spend decision; the sample decides whether
it is worth it.

## Three dockets, rendered by hand

Each rendering below was written from the documents' text as the record holds it,
following the rules above, on 2026-09-10. Sentences marked **[gen]** are the ones a model
would write; the author wrote them from the document, which is what the model is asked to
do. Sentences marked **[digest]** are the Board's. Everything else is a recorded fact.

### AB 55 (Sub-No. 822X) — the median docket

CSX Transportation, Inc. — Discontinuance of Service Exemption — in Robeson and Bladen
Counties, N.C. Three filings, one decision, 2025-11-24 to 2026-04-09.

> **AI-generated summary** · from the 4 documents listed · not reviewed
>
> **Where it stands** — decision served 2025-12-12, Chief Counsel: "this exemption will be
> effective on January 12, 2026, unless stayed pending reconsideration."
>
> **2025-11-24 · Notice of Exemption · CSX Transportation, Inc.**
> [gen] CSX Transportation files a verified notice of exemption to discontinue service over
> an approximately 21.72-mile line on its Wilmington Subdivision between milepost SEA 297.61
> and milepost SEB 319.33 in Robeson and Bladen Counties, N.C.
>
> **2025-12-12 · Decision · Chief Counsel, Office of Chief Counsel**
> [gen] The Chief Counsel's notice states that CSXT has certified that no local traffic has
> moved over the line for at least two years, that the exemption will be effective on
> January 12, 2026 unless stayed, and that petitions to stay and formal expressions of
> intent to file an offer of financial assistance must be filed by December 22, 2025.
>
> **2026-04-09 · Consummation Notice · CSX Transportation, Inc.**
> [gen] CSX Transportation notifies the Board that on April 9, 2026 it consummated the
> discontinuance of service over the line.
>
> Not listed: 1 errata/correction (CSX Transportation, Inc., 2025-12-05).

Three sentences. The consummation notice is listed under Rule 1.4 as a Notice; the errata is
counted. The status line at the top quotes the latest *decision* and this docket ended with
a filing, so the top says "effective January 12, 2026 unless stayed" and the foot says the
discontinuance was consummated on April 9, 2026 — both true, both the documents' words, and
the page does not say the second closes the first, because that is an inference about what
a consummation means (Rule 3).

### FD 36447 — the contested docket

Lake Providence Port Commission — Feeder Line Application — Line of Delta Southern Railroad
Located in East Carroll and Madison Parishes, La. 175 filings, 33 decisions, 2020-11-12 to
2026-09-02. Filers: Delta Southern Railroad, Inc. (63 filings under three spellings); Lake
Providence Port Commission alone or with the Southeast Arkansas Economic Development
District, the Madison Parish Port Commission and North Louisiana & Arkansas Railroad (about
70); the Board itself (6). Under Rule 1 the list holds the application, 33 decisions, and
about 95 pleadings by type, so it is 130-odd entries long and **a reader sees all of them**:
the docket is under the cap. **What follows is abbreviated by the author, not by the
design** — the first fourteen months are rendered in full to show the shape, and the
remaining four and a half years are described in one italic paragraph so this document
stays readable. On the page, every one of those entries is rendered the same way.

> **AI-generated summary** · from the documents listed · not reviewed
>
> **Where it stands** — decision served 2026-05-27, Entire Board: "The Board directs Lake
> Providence Port Commission to submit any revisions to its valuation calculations and
> supporting evidence deemed warranted by the updated information Delta Southern Railroad,
> Inc., recently produced in discovery and sets a deadline for the completion of discovery."
> *(The decision of 2026-09-02 is later, and its text had not reached the record when this
> was written; on the page it would be the one quoted.)*
>
> **2020-11-12 · Application · Lake Providence Port Commission, Southeast Arkansas Economic
> Development District, Madison Parish Port Commission, and North Louisiana & Arkansas
> Railroad**
> [gen] The Lake Providence Port Commission applies under 49 U.S.C. § 10907 to acquire a
> 20-mile line of Delta Southern Railroad between milepost 471 and milepost 491 in East
> Carroll and Madison Parishes, Louisiana, for operation by North Louisiana & Arkansas
> Railroad.
>
> **2020-11-12 · Motion/Petition/Request · the same applicants**
> [gen] The applicants petition for expedited consideration of the feeder line application
> and its acceptance before the constitutional minimum value of the property is determined.
>
> **2020-12-02 · Reply · Delta Southern Railroad, Inc.**
> [gen] Delta Southern Railroad replies in opposition to the petition for expedited
> consideration and acceptance of the application before the valuation is determined.
>
> **2020-12-04 · Reply · Lake Providence Port Commission and others**
> [gen] The Port Commission moves for permission to respond to Delta Southern's reply, to
> clarify the record and answer what it calls misleading comments in that reply.
>
> **2020-12-11 · Decision · Entire Board**
> [digest] "The Board waives a regulatory limitation relating to the acceptance of
> incomplete applications and conditionally accepts an otherwise complete feeder line
> application, contingent upon applicant's submission of a valuation estimate by
> December 28, 2020."
>
> **2021-01-15 · Decision · Director of Proceedings**
> *(no sentence: the entry shows its recorded facts and the link. The author had only the
> decision's recital of the application, not the page where it acts, and a sentence
> written from a later decision's account of this one — "accepted the application and set
> a schedule" — is precisely what Rule 2 forbids. This is the fallback, as a reader sees it.)*
>
> **2021-03-09 · Decision · Director of Proceedings**
> [gen] The Director suspends the procedural schedule pending further Board order, in light
> of filings made by NLA, DSR and LPPC shortly before the deadline for verified statements
> and comments.
>
> **2021-06-01 · Decision · Entire Board**
> [digest] "The Board denies a motion for protective order, denies as moot a related
> petition for issuance of a subpoena, and directs the parties to confer and report to the
> Board on any remaining discovery issues. The Board also denies two motions to strike and
> directs the parties to inform the Board whether they are interested in pursuing
> Board-sponsored mediation."
>
> **2021-10-21 · Decision · Entire Board**
> [digest] "The Board acknowledges the parties' reports that discovery issues have been
> resolved and orders Board-sponsored mediation in an effort to resolve disputes relating
> to the line at issue."
>
> **2022-02-09 · Decision · Director of Proceedings**
> *(no sentence, for the same reason: the author read the recital and not the order.)*
>
> **2022-08-23 · Decision · Entire Board**
> [digest] "This decision allows the Lake Providence Port Commission to file an amended
> feeder line application that involves a longer line than originally proposed. The Board
> also denies as moot three motions pertaining to the initial application, grants a motion
> to strike a rebuttal filing in support of the motion to file a supplemental application,
> and orders the current owner to provide specified information about the line …"
>
> **2022-10-14 · Decision · Director of Proceedings**
> [gen] The Director's decision addresses Patriot Rail Company's verified notice of
> exemption in Docket No. FD 36642 to acquire control of Delta Southern Railroad, and its
> effect on this proceeding.
>
> **2023-01-04 · Modify/Supplement Prior Filing · Lake Providence Port Commission**
> [gen] The Port Commission files an expanded feeder line application seeking to force the
> sale of Delta Southern's track from milepost 471.0 at Lake Providence over a longer
> segment than the original application.
>
> **2023-01-13 · Motion/Petition/Request · Delta Southern Railroad, Inc.**
> [gen] Delta Southern Railroad moves to reject the Port Commission's amended feeder line
> application as incomplete and for action terminating the proceeding.
>
> **2023-02-02 · Decision · Entire Board**
> [digest] "The Board waives the 30-day regulatory deadline for accepting or rejecting the
> amended feeder line application filed on January 4, 2023."
>
> *[Author's abbreviation — on the page, roughly 115 more entries follow here, rendered
> exactly as above: 2023-02 to 2026-09 holds 19 further decisions (5 with a Digest — the
> denial of the motion to reject, 2023-11-20; abeyance in light of state court actions,
> 2024-08-02; removal from abeyance and denial of motions to dismiss, 2025-09-25;
> assignment of an administrative law judge for discovery, 2025-12-12; denial of an appeal
> of the judge's subpoena ruling, 2026-03-25; a discovery deadline, 2026-05-27) and the
> judge's discovery rulings of 2025-12 to 2026-07; among the pleadings, seven motions to
> compel, two motions to dismiss, two appeals, six status reports, and 58 replies — each an
> entry under Rule 1, most recent last.]*
>
> Not listed: 25 letters, 5 errata, 2 comments, 2 certificates of service, 2 substitutions
> of counsel, 1 exhibit, 1 support statement, 1 notice of intent to participate — the full
> list is the docket sheet.

What this shows. Two entries fell back to facts because the author, reading as the model
would, had the document's recital and not its order — the rendering keeps them that way
rather than filling them from a later decision, and that is the discipline in miniature.
The dispute is visible without a word of characterisation: the application,
the petition to skip valuation, the reply opposing it, the conditional acceptance, the
expanded application, the motion to reject it, the state court actions, the motions to
dismiss, their denial, the discovery fights before a judge. A reader who knows the
proceeding will find nothing here that was concluded rather than read. What is lost is
any sense of *why* — and that is the loss the rule accepts, because the why is where a model
guesses.

Two things the rendering found that the specification must carry:

- **A decision's attachment is not always the decision.** Four of FD 36447's 33 decision
  records attach a party's letter or motion — the Board's listing links the pleading acted
  on (decisions 50834, 52017, 52090, 52130). A sentence generated from that text would
  describe the wrong document. The check in Rule 2 (the subject must be the deciding body)
  catches it, and the entry falls back to facts; the record's own quality gap is logged.
- **The 22 procedural decisions are where the model earns its place.** The Entire Board
  writes a Digest; the Director and the judge do not, and their decisions are what moves a
  proceeding month to month. If the sample shows the model cannot write "The Director
  suspends the procedural schedule pending further Board order" reliably from a page, the
  feature is a Digest reader with a filing list, which is still worth having.

### FD 36873 — the scale docket

Union Pacific Corporation and Union Pacific Railroad Company — Control — Norfolk Southern
Corporation and Norfolk Southern Railway Company. 1,177 filings, 37 decisions (6 with a
Digest; the rest from the Chief Counsel, the Office of Environmental Analysis and a judge),
2025-07-30 to 2026-09-09. Filing types: 533 notices of intent to participate without
comment, 208 comments, 147 letters, 54 replies, 41 miscellaneous, 38 notices of intent with
comment, 25 motions, 21 notices, 21 supplements, 13 support statements, 10 motions to compel.

Under Rule 1: the opening filing (the Notice of Intent to Initiate Case, 2025-07-30, and the
Application of 2025-12-19 — both, since the first opened the docket and the second is the
application); 37 decisions; every decision-cited filing; and by type 54 replies, 25 motions,
10 motions to compel, 21 supplements, notices, status reports. That is about 190 entries,
over the cap of 60, so the list holds the two opening filings, the 37 decisions, the cited
filings, and the **most recent** pleadings by type until the cap — the first winter's
replies are what the cap drops, not this summer's motions — and the remainder line reads:

> Not listed: 533 notices of intent to participate (without comment), 208 comments, 147
> letters, 41 miscellaneous, 38 notices of intent (with comment), 13 support statements, 10
> errata, and 110 further pleadings — the full list is the docket sheet, and every comment
> is on the environmental comments page.

The page is 60 entries and a remainder line. It is long, and it is exactly as long as the
Board's own acts plus the pleadings the cap admits; a reader wanting the merger story reads
37 decisions in date order, six of them in the Board's own summary, and knows what was
asked and decided without the summary having decided anything. The comments — the volume of
this docket — are a number and a link, which is honest: 741 expressions of interest and
comment are not summarisable without inferring what their authors mean.

## What the sample measures

Fifty documents drawn under Rule 1 from dockets of the three sizes, stratified so the
procedural decisions are half of them, each sentence written by three producers — the
fleet's local model, the Jetson's smaller one, and a frontier model through the API — and
by the operator as the reference. Scored on: does the sentence pass the Rule 2 check
(mechanical); does it say what the document asks for (the operator, three grades: right,
incomplete, wrong); does it infer anything (the operator; any inference fails the sentence).
The producer with the fewest failures at the lowest cost is the backfill's; the Jetson's is
the trickle's if its failure rate is within a stated margin. The figures go on
`/methodology` beside the label, and they are what the label's "not reviewed" is measured
against.

## What this is not

Not a narrative. Not an outcome ("the Board approved the merger"): that is a Digest, quoted.
Not a party's position, ever. Not a deadline computed from a rule. Not a replacement for the
docket sheet, which stays the record of everything filed. Not built until chosen.
