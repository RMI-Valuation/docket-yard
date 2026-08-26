# ADR 0014 — Subscriber addresses are ciphertext at rest

- **Status:** Accepted
- **Date:** 2026-08-26
- **Accepted:** 2026-08-26 (operator sign-off in the drafting session, by explicit decision)

## Context

ADR 0011 made reading anonymous and reduced an account to an email address, on the
principle that data never collected cannot be subpoenaed, breached, sold or misused. The
one datum the wedge must collect is the address an alert is sent to. Migration 0004 stored
it in plain text. Reviewing that, the operator asked the direct question — who could ever
get at these rows? — and the honest answer was: civil discovery (rare), a breach of the
instance or its keys (the likeliest path), and every *copy* of the store: the Litestream
replica and snapshots in S3, the hourly backups, a developer's `litestream restore` on a
laptop. The last of these is the ordinary, non-adversarial way a plaintext table travels.

Hashing alone cannot serve a system whose job is to send mail. The standard library has no
authenticated cipher.

## Decision

- **Every stored address is two derived values under one operator-held key:** an
  HMAC-SHA256 (`email_hash`) that all matching uses — one live subscription per address
  and docket, the suppression list, rate limits, unsubscribe — and a Fernet ciphertext
  (`email_enc`) that only the sender decrypts, at the moment of sending. The suppression
  list keeps a ciphertext too, so a key rotation can re-derive its hashes.
- **The key (`DY_EMAIL_KEY`) lives in the serving instance's environment and the
  operator's password manager, and nowhere else** — never in the store, S3, a backup, or
  the repository. Every copy of the store is therefore unreadable as addresses.
- **Fail closed.** Without the key the subscribe form answers 503 and the poller builds
  no alerts. A malformed key closes the vault and says so; it does not stop capture.
- **Normalisation is the vault's job**, not the caller's: an address is hashed in exactly
  one form, so no caller can mint a second identity for one person.
- **The public privacy page states the limit plainly:** the operator can decrypt, because
  sending requires it, so a lawful and specific demand can still produce the addresses of
  people currently following a docket. Encryption at rest is not a legal shield and is not
  presented as one.
- **One dependency earns its place:** `cryptography` (Fernet). Rolling a cipher from the
  standard library was rejected.

## Consequences

The threat the wedge is most exposed to — a copy of the store leaving the box — no longer
carries addresses. The operator's own access is unchanged and is disclosed. Costs: the key
is a single point of loss (losing it loses every subscription; people subscribe again),
rotation is an all-rows pass over three tables that is not yet written, and migration 0005
is the one migration in the set that dropped rows (two test subscriptions, documented in
its header). The `CHECK (email = lower(trim(email)))` that 0004 carried cannot be
expressed over a hash; the invariant moved into the vault and its test.

## Cost of reversing

Low in mechanics — decrypt every row with the key and write plaintext — but it is the
wrong direction under ADR 0011 (loosening is possible; collecting more readably later is
the door that record forbids swinging back). A stronger posture (a key held off the box,
e.g. in a KMS with the box able to decrypt only at send time) is a forward step this record
does not preclude.

## Validation (2026-08-26)

Checked against [`../validation-queries.md`](../validation-queries.md): only query 5 touches
subscriptions, and its join (`schema-draft.md` § 6, `alerts/build.py`) never needs the
address — it projects `email_hash` and the sender decrypts one row at send time. Queries
1–4 touch no subscription table. The schema-critic's review (2026-08-26) found the join,
uniqueness, suppression, digest grouping and unsubscribe semantics intact on the hash, and
the one finding it raised — a suppression list that could not survive key rotation — was
fixed before the migration shipped (`email_suppression.email_enc`). Production ran on this
schema (v2026.08.10–11) with a real subscription and a real bounce before acceptance.
