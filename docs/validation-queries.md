# The five validation queries

Write each of these against the draft schema **on paper**, before any pipeline code exists. They
were chosen because between them they exercise geography, party succession, typed citation
edges, temporal grain, provenance, and service lists as data.

If one of them requires a migration that touches every row, that is the part of the design to
fix now — while it costs an afternoon.

---

## 1. Segment history through successor railroads

> Every proceeding touching this line segment since 1996, traversing corporate successors.

Exercises: geography as first-class rows, party succession as graph edges, proceeding-to-place
relationships. This is the query a valuation practice actually needs, and it is the one most
likely to expose a schema that treats parties as strings.

**Can the schema express it?** **Yes — after it broke the first draft twice.** As predicted,
the query exposed party handling: succession edges had no declared direction (half were
traversed backwards, silently), and party facts were anchored to document bytes, which lost
every no-attachment filing and cross-contaminated byte-identical boilerplate across dockets.
Fixed by declaring edge direction as data and giving filings their own identity. Query sketch
and the repair record: [`schema-draft.md`](schema-draft.md) (2026-08-25).

## 2. Negative treatment

> What has narrowed, distinguished, or superseded this decision?

Exercises: typed citation edges (not just "cites"), provenance on each edge, confidence.
A citation graph that cannot distinguish _followed_ from _overruled_ is a list, not a citator.

**Can the schema express it?** **Yes.** Typed treatment edges with per-edge provenance and
confidence, keyed to the _decision_ rather than one hash of one version — the first draft keyed
on a single content hash and would have returned half the edges the day an erratum split the
decision across two hashes. Sketch: [`schema-draft.md`](schema-draft.md) (2026-08-25).

## 3. Point-in-time docket state

> What did this docket look like on 18 August 2026, the day before Decision No. 30?

Exercises: event grain. If the store holds current state rather than the sequence of events,
this is unanswerable and cannot be retrofitted without reconstructing history.

**Can the schema express it?** **Yes.** The event ledger replays to any date; two timestamps
per event answer both "what the record said had happened by then" and "what we knew by then".
The first draft left corrections unjoinable and decision numbers in untyped JSON — both now
typed columns. Sketch: [`schema-draft.md`](schema-draft.md) (2026-08-25).

## 4. Trail-use notice lifecycle

> Every interim trail use notice with its full extension and expiration history.

Exercises: lifecycle modelling on a record that changes repeatedly over years. These dates are
dispositive in Court of Federal Claims takings litigation, so "the current state" is not enough
— the history is the product.

**Can the schema express it?** **Yes.** Instruments group a lifecycle without changing the
event grain; every date is quoted from a named document with provenance. The trap the query
caught: without natural keys and supersession pointers, the first improved re-extraction pass
silently doubles every NITU. Sketch: [`schema-draft.md`](schema-draft.md) (2026-08-25).

## 5. Service-list membership alert

> Alert me to anything filed in any proceeding where a given railroad appears on the service list.

Exercises: party as a resolved entity, service lists stored as structured data rather than
prose, and the join from a subscription to an event stream. STB publishes service lists and
nobody uses them.

**Can the schema express it?** **Yes — and the first paper projection was wrong.** "Latest row
per party" keeps removed parties on the list forever; membership is defined by the latest
_snapshot_ per docket, which the snapshot-event design expresses directly. The query also
surfaced the backfill/alert collision: without an ingest-mode flag, the first backfill wave
alerts every subscriber on thirty years of old filings.
Sketch: [`schema-draft.md`](schema-draft.md) (2026-08-25).
