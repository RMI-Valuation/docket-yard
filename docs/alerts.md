# Alert reliability

> **Status: live (2026-08-26).** The heartbeat, the delivery promise, no backfill, the
> failure-disclosure marking, encrypted addresses and bounce feedback are all decided and
> running; each section names its decision date. Changes to a promise here are changes
> to a public page and need the operator's sign-off (CLAUDE.md § Ask rather than assume).

## Purpose

What is promised about delivery, and how silent failure is detected.

## What this locks in

A monitoring requirement. Alerts are cheap to launch and expensive to keep correct — upstream
changes break them quietly.

## The heartbeat

**A dead box cannot report its own death** (ADR 0012), so the check runs off-box: the
`Heartbeat` GitHub Actions workflow (`.github/workflows/heartbeat.yml`) asks
`https://docketyard.org/health` every hour, as any reader would, and fails the run when a
threshold is crossed. A failed scheduled run emails the workflow file's last committer.

`/health` reports three timestamps and their ages, and always answers 200 — the monitor
judges, the box only reports, so a stale store is visible rather than hidden behind a 5xx
that a restart loop could mask. The three follow the silent-failure decomposition in
`schema-draft.md` § 6: every alert joins a subscription to an event and every event to a
capture, so "nothing since X" splits into three independently observable failures.

| Timestamp | Silence means | Threshold |
| --- | --- | --- |
| `last_forward_capture` — newest asserted forward capture of the filings or decisions table (document fetches are captures too and deliberately excluded: a draining attachment backlog must not make a refused poller look alive) | The poller is dead, or every pass is refused (nonce, WAF, criteria) | 3 hours: six missed 30-minute passes |
| `last_event` — newest ledger row | Captures arrive but nothing new is parsed from them: the parser broke, or the Board is genuinely quiet | 6 days: the Board serves something most business days; a long weekend must not page |
| `last_document` — newest fetched document | Records arrive but their files do not: the fetch broke, or the WAF began refusing GETs | 6 days |
| `oldest_pending_alert` — the oldest alert built but not yet sent | Events reach subscribers' queues but mail does not leave: SES, credentials, or the sender | 3 hours; null means the queue is empty, which is the normal state |

A timestamp that is null — a store that has never done that thing — is reported as a
warning, not a failure, so a rebuilt store does not page every hour until its first fetch.

The check itself can fail silently — GitHub's scheduler skips runs on inactive repositories
after 60 days without a commit. A repository that goes quiet for two months should expect
the heartbeat to stop with it; `workflow_dispatch` re-arms it.

## The delivery promise (decided 2026-08-26)

A subscription is to **one docket** (its family: the parent and its sub-dockets fold into
one sheet and one subscription) **or, from M6, to one party** — filings whose "Filed For"
cell resolves to that party, in any docket; decisions carry no filer and never reach a
party subscription — at **one of two cadences the subscriber chooses**:

- **As it happens** — one email per docket per poll pass that observed something new on
  it. The poller runs every 30 minutes, so an entry the Board posts is usually in the
  subscriber's inbox within the hour. A pass that finds three new entries on a docket
  sends one email listing all three, never three emails.
- **Daily** — one email per subscriber per day, listing everything new across all their
  daily-cadence dockets, sent after the last pass of the day (23:00 Eastern; the Board's
  own clock). Nothing new, no email.

**No backfill.** Alerts are strictly forward from the moment a subscription is confirmed;
the confirmation email links to the sheet, which already shows the whole record. An alert
never carries an entry the record observed before the confirmation — "observed" meaning
recorded in the ledger, so a filing the Board back-dates but posts after confirmation *is*
alerted, and one the record only caught up on later is alerted and marked late (below).

**Confirmation is a button, not a link.** The confirmation email links to a page whose
button does the confirming, because corporate mail gateways fetch links on delivery and a
fetch is not consent. The same holds for unsubscribing from a page; the RFC 8058 one-click
POST from a mail client's own button is honoured directly.

**Addresses are never readable at rest** (decided 2026-08-26, migration 0005): the store
holds an HMAC of the address for matching and a Fernet ciphertext for sending, under a
key (`DY_EMAIL_KEY`) that lives only in the instance environment and the operator's
password manager — never in the store, S3, or a backup. Every copy of the store is
ciphertext. The operator can decrypt, because sending requires it; the privacy page says
so. Losing the key loses every subscription; people subscribe again.

**A mailbox that bounces or complains is never mailed again.** SES reports permanent
bounces and complaints to an SNS topic that POSTs to the site; each report is verified by
signature and puts the address's HMAC on the suppression list, which every subscribe and
every send consults. This matters because SES's own account-level suppression accepts a
message and drops it silently — without the feedback, a bounced subscriber would be
"sent to" forever (runbook § Mail).

**Unsubscribing forgets you.** The subscription row and everything about it is deleted,
not flagged (ADR 0011). One-click unsubscribe from any old alert still answers "you are
unsubscribed", because that is true.

**What receiving nothing means:** the Board posted nothing to that docket since the last
email — or the record is behind, in which case the heartbeat has already paged the
operator and the coverage page records the gap (below).

**Alerts fire off the event ledger and nothing else** (`schema-draft.md` § 6): an alert
row joins a subscription to an event whose capture is `forward`. Backfill never alerts.
Each alert carries the same provenance the sheet does: the Board's own file, linked.

## Feeds and webhooks (M8, decided 2026-08-26)

Email is one channel of three. All three render the same `EventSummary`
(`alerts/summary.py`) for the same events — record-bearing event types from forward
captures, never a backfill wave — so a feed reader, a webhook receiver and an inbox see the
same entry.

**Atom feeds** (`web/feeds.py`) are stateless: `/feed` (agency-wide), `/d/<docket>/feed`
(family) and `/feed/party/<id>` return the latest 100 entries, `Cache-Control: max-age=1800`.
Nothing is stored about the reader (ADR 0011). A party feed is addressed by party id the
way a party subscription is — a delivery channel, not a page (ADR 0013 addendum still holds).

**Webhooks** (`alerts/webhooks.py`, migration 0008) are subscriptions whose recipient is
an https URL. Everything about addresses applies unchanged: the URL is hashed and sealed
under the vault key, confirmed before anything is sent, rate-limited on confirmation
attempts, deleted on unsubscribe, and the alert ledger's claim-before-send discipline and
three-attempt limit are the same. What differs:

- **Confirmation is a ping**, not a mail: a signed POST (3-second budget, no store handle
  held while it waits) carrying the confirmation link and the signing secret. Only
  whoever reads the endpoint's traffic can confirm, and the secret is never shown on a
  page. A ping the endpoint does not accept still counts against the three-an-hour
  limit and its token expires unused — withdrawing it would let a URL that never answers
  be pinged without limit. The page says the same thing whatever happened.
- **One secret per endpoint.** A URL following two dockets holds one secret, so a daily
  digest across both verifies. The host is resolved once, every address checked, and the
  checked address is the one dialled (certificate verified against the name), so a name
  that answers differently on a second lookup cannot steer a request inward.
- **Every delivery is signed**: `X-DocketYard-Signature: sha256=<HMAC-SHA256(secret, body)>`
  over the exact bytes, `X-DocketYard-Delivery: <alert id>`. The body is
  `build.payload()`: `events[]` (the summary fields plus `late`), `party` when the alert
  is for one, `unsubscribe_url`.
- **Outbound connections are the one place this service connects where a stranger
  chose.** https only, no credentials in the URL, no redirects followed, ten-second
  timeout, and the host is resolved and refused unless every address is public unicast — a
  name pointing into the instance's own network never gets a connection.
- **Suppression applies by hash**, so an operator can stop an endpoint the way a bounced
  address is stopped. Nothing suppresses automatically yet: an endpoint that fails three
  attempts fails that alert and is tried again on the next, and a permanently dead one
  accumulates failed alerts in the log (TODO.md carries the follow-up).
- Webhooks go out whether or not mail is configured; email alerts wait, pending, for a
  sender, and the heartbeat's `oldest_pending_alert` leg reports the wait.
- The heartbeat leg `oldest_pending_alert` covers both channels: a pending webhook alert
  ages the same way.

## Failure disclosure (decided 2026-08-26)

When the heartbeat catches a gap — a window in which the record was not being kept —
two things happen:

1. **The coverage page records the window.** The heartbeat runs off-box and cannot write
   the store, so the operator, once paged, records the gap (start, end, what failed in the
   decomposition's terms) as a `coverage_gap` row; the coverage page is generated from
   those rows and from the capture ledger, so it can never claim more than was recorded.
2. **The catch-up is marked, automatically.** Lateness is derived from the capture ledger
   itself — an entry is late when the forward captures around it are further apart than
   the heartbeat threshold — so it does not wait on the operator. Once the poller
   recovers, entries observed late are still alerted (they are new events), and the alert
   that carries them says so:
   *"These entries were posted by the Board between (start) and (end), while Docket Yard
   was not keeping the record. They are delivered late."* Sent normally otherwise — no
   separate apology mail, no silence.

What is **not** promised: that every entry is caught (the Board's endpoint fails silently
in measured ways; see `stb-data-source.md`), or any lag figure tighter than "usually
within the hour". Promises appear on the public coverage and privacy pages only after the
operator signs off on that page (ADR 0011).
