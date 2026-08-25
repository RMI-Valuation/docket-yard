# ADR 0011 — Reading is anonymous; accounts are an email address

- **Status:** Proposed
- **Date:** 2026-08-25

## Context

On a legal-research platform, attention is intelligence. A railroad's counsel subscribing to
a docket reveals litigation strategy; a reporter's watchlist reveals an unpublished story; a
landowner's bookmarks reveal a takings claim in preparation. A store of who-watches-what has
three predators: civil discovery (a subpoena for "everyone monitoring this docket" is
plausible in rail litigation), breach, and the market — this data is what commercial legal
analytics sells. The operator is itself a conflict to design against: RMI Valuation practises
in this industry, and parties would be rational to wonder whether the operator can see their
watchlists. Policy promises do not answer that; architecture does. Data never collected
cannot be subpoenaed, breached, sold, or misused — including by us. And the door only swings
one way: a paper trail cannot be un-collected later.

## Decision

**Can't-be-evil over won't-be-evil.** Concretely:

- **Reading is anonymous, always.** Every read path works with no account and no
  identity-linked logging. Server logs keep IPs briefly for abuse defence (days, not
  months) and are never joined to accounts.
- **Bookmarks default to the browser** (localStorage): no account, no server-side trail.
  Account-synced bookmarks are an explicit opt-in.
- **An account is an email address, full stop.** No name, no organisation, no profile.
- **Auth is passwordless magic link**: a single-use, short-lived link emailed on request.
  Inbox possession is the identity — the same trust anchor alert delivery already depends
  on. No password table exists to breach. Tokens are stored hashed; the sign-in flow
  responds identically whether an address is known or not (no account enumeration).
- **Subscriptions are confirmed opt-in.** A subscription fires nothing until the address
  owner clicks a confirmation link; unconfirmed subscriptions expire and are deleted.
  Confirmation and sign-in emails are rate-limited per address.
- **Alerts carry no tracking** — no open pixels, no per-user tokenised links — and every
  alert carries one-click unsubscribe that works without signing in (RFC 8058).
- **No watcher counts are ever published or stored beyond the subscription rows
  themselves.** Aggregate site analytics are cookieless, self-hosted, and coarse.
- **A published privacy page** joins the trust infrastructure (coverage, corrections,
  methodology): what is stored, what is never stored, what can and cannot be produced under
  subpoena — generated from the same source as the specs, and never claiming more than the
  architecture enforces. As a public promise, it ships only on explicit operator sign-off.

## Consequences

Trust becomes a feature competitors structurally cannot copy while they monetise attention
data. The build gets simpler: no password auth, no profiles, no analytics pipeline, no
consent banners — the subscription mechanism the wedge already needs is nearly the whole
account system. Confirmed opt-in doubles as sender-reputation hygiene. The costs: no
per-user product analytics to steer by (we will not know which pages a subscriber reads),
support flows must work without knowing much about the user, and some conveniences
(cross-device bookmarks by default) are deliberately forgone.

## Cost of reversing

Asymmetric by design. Loosening later (adding an opt-in feature that stores more, with
fresh consent) is possible and honest. The direction this record forbids is retroactive:
collecting first and minimising later is impossible — data collected under one promise
cannot be un-collected, and a privacy posture, once broken, does not recover.

---

*Proposed, not accepted. Accept only after this decision has been checked against
[`../validation-queries.md`](../validation-queries.md).*
