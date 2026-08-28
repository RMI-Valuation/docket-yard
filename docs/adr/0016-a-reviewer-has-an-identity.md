# ADR 0016 — A reviewer has an identity; reading stays anonymous

- **Status:** Proposed
- **Date:** 2026-08-28

## Context

Two accepted decisions meet here. ADR 0007 says every derived assertion carries provenance —
source, location, method, method version, timestamp, confidence. ADR 0011 says reading is
anonymous and an account is an email address, nothing more. Until now the only humans who
asserted anything into the record were the operator (the party seed, joins, corrections,
gap records, all recorded as method `human` under the operator's own hand). The OCR plan
(`docs/ocr-plan.md`, chosen 2026-08-28) adds a review queue, and the citation graph and the
extraction benchmark will add more: a person accepts one engine's reading over another,
types a correction, confirms or rejects a citation edge, checks a label. The operator's
instruction, the same day: *reviewers should have a login; we should be able to track who
reviewed.*

The forces: a human review is a **derived assertion** and must carry *who* as its method
detail, or ADR 0007 is not met; a reviewer who cannot be told apart from another cannot be
trusted, corrected or thanked; and yet nothing about ADR 0011's promise to *readers* may be
weakened by it — the door that must stay shut is the one between reading and identity.

## Decision

**Reviewing is writing to the record, and writing has a name. Reading does not.**

- **A reviewer is an account with a role.** The account is the one ADR 0011 already
  defines — an email address, passwordless magic-link sign-in, address ciphertext at rest
  (ADR 0014) — plus a `reviewer` grant the operator gives by hand and can withdraw. No
  self-service sign-up as a reviewer; no profile beyond a **credit name** the reviewer
  chooses (how they wish to be shown, or "anonymous reviewer").
- **Every review action is a provenance row.** Method `human`, method detail the reviewer's
  id, the timestamp, what was reviewed and what was decided (accepted reading A, typed a
  correction, rejected edge, confirmed label). It is append-only: a later review supersedes,
  never overwrites; a withdrawn grant leaves past rows intact and attributed.
- **What is published:** the credit name beside a reviewed assertion where the page shows
  provenance; counts of reviews per reviewer only if the reviewer opts in. Never the email.
- **What is not stored:** nothing about what a reviewer *reads*. The review surfaces log
  the actions above and nothing else; no page views, no timing beyond the action's own
  timestamp, no IP joined to the account (ADR 0011's log rule stands). Signing in as a
  reviewer does not make any read page identity-linked.
- **The operator is reviewer zero**, with the same rows as anyone else; the seed and joins
  already recorded as `human` are re-attributed to the operator's reviewer id when the
  table exists, so one rule covers all human assertions.
- **The surfaces:** one review area, `/review`, reachable only signed in with the grant,
  with a queue per kind (OCR pages, citation edges, benchmark labels, corrections). The
  queue shows the evidence beside the question (page image beside text; the citing passage
  beside the candidate target) and records one decision per item. Anything without a
  queue is not reviewable through the site; nothing there can subscribe, spend or alter
  the ledger.

## Consequences

Human assertions become as traceable as machine ones, which the OCR review layer and the
citator both require. The account system stays the one that exists — a reviewer is a
subscription-style account with a grant, not a new identity model — so no password table,
no profile, no analytics appear. `/contribute` gains one sentence (how to become a
reviewer: ask the operator) and `/privacy` gains one paragraph (what a reviewer account
stores, and that reading is unchanged). The costs: a small table for grants and credit
names, a `review_action` table (schema-critic before it exists; ADR 0007's shape), the
sign-in flow must be built out beyond confirmation links (magic-link sign-in exists in
ADR 0011's decision but not yet in code), and a role that can be withdrawn needs a way to
be withdrawn.

## Cost of reversing

Low for the tables; high for the record. Rows attributed to a reviewer are provenance and
stay: removing identity later would strip method detail from every human assertion, which
ADR 0007 forbids. The reverse direction — collecting more about reviewers than their
actions — is what ADR 0011 forbids, and this record keeps that door shut.

## Validation

Against `docs/validation-queries.md` this changes no query; it adds detail to the answer
of "who says so, and how" for human assertions, which query 4 (provenance) already asks.
Against ADR 0011: reading paths are untouched; a reviewer's reads are not logged; the
account is still an email address. Against ADR 0007: the review row is a full provenance
row, with the reviewer id as method detail.
