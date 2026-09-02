# ADR 0020 — Maintenance is a state the record does not share

- **Status:** Accepted
- **Date:** 2026-09-02
- **Accepted:** 2026-09-02 (the operator: "ADR 0019 and 0020 approved")
- **Addendum to:** [ADR 0012](0012-deployment-topology.md), which stands unchanged

## Context

ADR 0012 put four containers on one instance: `web` serves readers, `ingest` keeps the
record, `litestream` replicates it, `caddy` terminates TLS. The separation is real in the
compose file and has never been expressible as an operational state — the box is either
serving or it is not.

**2026-09-02 showed why that matters, three times in a day.** A crawler on a docket with
12,031 comments drove `web` to 850 MB and 167% of a two-core box; the site stopped answering
while `ingest` and `litestream` were entirely healthy and kept capturing whenever the machine
had CPU to give them. Readers saw a dead site. The record was never in danger. The only
thing missing was a way to say so.

The same gap runs the other way, and this is the sharper edge of it. **Production is four
migrations behind `main` (schema 13 against 17), and the deploy that closes the gap has been
held** — reasonably, because it is a migrating release whose rollback is a Litestream restore
rather than a tag change. The way that deploy runs today is: swap `DY_TAG`, `docker compose
up -d`, and find out. Readers are on the site while the migration runs; a fault is discovered
by the people least able to do anything about it; and the verification window is one in which
the store is simultaneously being read.

Two other pressures point the same way. The containment applied today — Caddy answering one
docket's comment pages with a 503 — is a hand-cut, single-path version of exactly this
mechanism, and it wants generalising rather than repeating. And ADR 0019 moves the
primary death detector to an alert on absent metrics; a planned outage that looks identical
to an unplanned one will page the operator about work the operator is doing.

## Decision

1. **Maintenance is served by `caddy`, not by `web`.** Caddy is a separate container that
   does not depend on the application being up, so `web` may be stopped outright and readers
   still get a courteous page rather than a connection refused. This is the whole reason the
   state is expressible at all, and it is why the toggle lives at the proxy.

2. **`ingest` and `litestream` do not observe maintenance.** Capture, ingest, alerting and
   replication continue. Maintenance is a statement about the *reading* surface; the record
   is kept throughout, and after 2026-09-02 that distinction is not theoretical. A release
   that must also stop the poller stops it explicitly and separately, and that is a different
   and rarer act.

3. **The status is 503 with `Retry-After`, never 200.** A 200 maintenance page tells every
   crawler that the content of every address is now an apology, and search engines will index
   it. 503 is the answer the web already has for this and costs nothing to give correctly.
   The permanence ADR 0013 promises is untouched: a 503 says *not now*, where a 404 would say
   *not here*.

4. **`/health` keeps answering, and answers honestly.** Maintenance must be distinguishable
   from an outage by a monitor, or ADR 0019's absent-metric alert fires on planned work and
   the operator learns to ignore it — which is worse than having no alert. `/health` therefore
   stays up, reports its freshness as it always does, and says that maintenance is on. What
   is silenced is the reader-facing alarm; the record-keeping alarm stays armed, because the
   record is still being kept.

5. **The toggle is a flag on the instance, read by the proxy — never a code path in the
   application.** Entering maintenance must not depend on the thing that may be broken. It is
   also then available when `web` will not start at all, which is the case that most needs it.

6. **A deploy of a migrating release enters maintenance first.** Maintenance on, deploy,
   migrate, verify against a live store with no readers touching it, maintenance off. If the
   migration is wrong it is discovered with nobody watching and the Litestream restore happens
   against a store nothing else is writing.

## Consequences

The held deploy becomes a materially smaller risk, which is this record's main purpose: the
verification step stops competing with readers, and a bad migration is found in a window
where the only cost is the window. Incidents gain an honest vocabulary — "the site is down"
and "the record stopped" become different sentences, and `/coverage` already distinguishes
them (gap 1, recorded today, says captures stopped for 6 h 52 m and no records were missed).
The Caddy block cut by hand today becomes an instance of a general mechanism rather than a
precedent for cutting more by hand.

The costs are small and worth naming. There is a new way to leave the site broken: a flag set
and forgotten, which the same monitoring that watches for outages should watch for. The
maintenance page is a fifth thing to keep in step with the site's design, and it is exactly
the sort of page that rots because nobody sees it — it should be reachable deliberately in
development. And maintenance is a state that must not become a habit: a site that is often
down for maintenance is a site that is often down.

## Cost of reversing

Cheap. Delete a matcher, a page and a flag; nothing in the store depends on it, no assertion
carries it, and no address changes meaning. It is written down because it changes how the
production topology ADR 0012 fixed is operated, not because it is hard to undo.

## Validation

Against `docs/validation-queries.md`: nothing. No table, no column, no assertion; the five
queries are untouched and no published figure moves.

Against **ADR 0012** this is an addendum in its own direction — the four-container split was
already the design, and this makes one consequence of it operable. The instance, the store,
the blob path and the pull-based deploy are all unchanged.

Against **ADR 0013**: permanence holds. Every address that answers 503 during maintenance
answers exactly as before afterwards, which is what 503 means and what 404 would not.

Against **ADR 0019** (accepted the same day): the two are complementary and slightly in tension, and the
tension is resolved here rather than left for the first incident to find. Maintenance must be
visible to the monitor — hence `/health` staying up and saying so — so that a planned window
does not fire an absent-metric alert and teach the operator to disregard it.

Against **ADR 0011**: the maintenance page has no reader data, no identifiers, and no
cookies; it is a static response from the proxy.
