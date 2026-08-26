# 0015 — A party has an address, minted once and never reused

**Status:** Accepted, 2026-08-26 (drafted earlier the same day; accepted by the operator in a
later session, as the draft required). Supersedes the "parties are a facet, not an address"
addendum to ADR 0013; ADR 0013 itself stands, and now carries a note pointing here.

## Context

The party module (M6) resolves "filed for" strings to entities with aliases and successions,
and every sheet shows them; `/parties?name=…` searches them; a party has a feed and can be
followed. What it does not have is a page: a party cannot be linked, cited, bookmarked or
indexed. An outside review of the live site (2026-08-26) named this the highest-leverage
gap, and it is also validation query 5's natural home.

The addendum to ADR 0013 chose *facet, not address* deliberately, for a reason that still
holds: a party id is a **resolution artefact**. Two records that today are separate parties
may be found to be one; a same_as edge joins them and one becomes the component's
representative. A permanent URL built on an id that can stop being the representative is a
URL that changes — worse than none (ADR 0013).

## Decision

1. **The address is the party's own id**, `/p/<party_id>`, and **ids are never reused or
   renumbered.** A party row, once minted, is permanent (the ledger already never rewrites
   links — it supersedes them; the same discipline applies to the entity).
2. **Every id in a same_as component resolves.** A request for a member that is not the
   component's representative answers **301 to the representative's address**; the page
   itself lists every id that has been folded into it ("also known here as …"), with the
   provenance of the join. Nothing a reader ever bookmarked stops resolving.
3. **A split is a new party.** If a join is later found wrong, the edge is superseded and
   the members keep their own ids and addresses — no id ever changes meaning; only which
   address is the representative's does, and 301 follows the truth.
4. **No slug in the address.** A slug would encode a name that the party module treats as
   an assertion with provenance (names change; d/b/a's are added). The name belongs in the
   `<title>`, the page and the citation line, never in the key. `/p/<id>/<anything>` is
   accepted and 301s to `/p/<id>`, so a pasted "pretty" link still works.
5. **What the page carries** is what the search result carries today — names with type and
   provenance, successions and parents, the dockets filed in with counts, the feed and the
   follow form — plus a citation line. Never a position; never an inferred relationship.
6. **`/parties` stays** as the search; the sheet's Parties block links each party to its page.

## Consequences

- ADR 0013's promise ("a URL that resolves today resolves in ten years") extends to
  parties, with 301 as the mechanism for resolution changes — the same mechanism the docket
  address uses for case and spelling variants.
- The sitemap gains a `parties` section; `/feed/party/<id>` becomes `/p/<id>/feed` (the old
  path 301s, forever).
- Merges are visible on the page rather than hidden: a reader can see that two names were
  held to be one entity and why. That is a feature of ADR 0007, not a cost.
- Validation query 5 (subscribe by party / service list) is unaffected: it keys on party
  ids already.

## Validation (2026-08-26)

Checked against `docs/validation-queries.md` before acceptance:

- **Query 5 (service-list membership alert)** — unchanged. A party subscription keys on
  `subscription.party_id` and widens to the id's same_as component at delivery time
  (`alerts/build.py: party_events`); the page reads the same component through the same
  `Components` class, so what the page lists as "dockets filed in" is exactly what the
  subscription would alert on. No new table, column or grain: the address is the existing
  primary key.
- **Queries 1–4** — untouched; none reads the party tables.
- **ADR 0013's permanence promise** — extended to `/p/<id>` by decisions 1–4 above. The
  mechanism is the one the docket address already uses: any spelling of the same identity
  answers 301 to the one canonical address. The representative of a component is its
  smallest live id, so a join can only lower the target id; superseding a same_as edge
  re-splits the component and each id's target follows. A member's page never disappears
  and never changes meaning; only the redirect target moves, and always to a page that
  lists the id it was reached by.
- **ADR 0007** — the join command records method `human`, a version, the timestamp and the
  operator's note as `source_location`; the page shows that provenance beside every folded
  id, every name and every succession. A `human` row is never superseded by a model pass.
- **The tests that pin this** (`tests/test_party_pages.py`): every member id of a component
  301s to the representative; `/p/<id>/<anything>` 301s to `/p/<id>`; `/feed/party/<id>`
  301s to `/p/<id>/feed`; superseding the same_as edge changes only the redirect target,
  and both pages answer 200 afterwards; an id that never existed is 404, never reused.

What this changes in ADR 0013's boundary: parties now hold a permanent address; places,
labels and folds still do not.
