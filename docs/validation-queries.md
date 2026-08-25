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

**Can the schema express it?** _(unanswered)_

## 2. Negative treatment

> What has narrowed, distinguished, or superseded this decision?

Exercises: typed citation edges (not just "cites"), provenance on each edge, confidence.
A citation graph that cannot distinguish _followed_ from _overruled_ is a list, not a citator.

**Can the schema express it?** _(unanswered)_

## 3. Point-in-time docket state

> What did this docket look like on 18 August 2026, the day before Decision No. 30?

Exercises: event grain. If the store holds current state rather than the sequence of events,
this is unanswerable and cannot be retrofitted without reconstructing history.

**Can the schema express it?** _(unanswered)_

## 4. Trail-use notice lifecycle

> Every interim trail use notice with its full extension and expiration history.

Exercises: lifecycle modelling on a record that changes repeatedly over years. These dates are
dispositive in Court of Federal Claims takings litigation, so "the current state" is not enough
— the history is the product.

**Can the schema express it?** _(unanswered)_

## 5. Service-list membership alert

> Alert me to anything filed in any proceeding where a given railroad appears on the service list.

Exercises: party as a resolved entity, service lists stored as structured data rather than
prose, and the join from a subscription to an event stream. STB publishes service lists and
nobody uses them.

**Can the schema express it?** _(unanswered)_
