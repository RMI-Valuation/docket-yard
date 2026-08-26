# Alert reliability

> **Status: in progress.** The heartbeat is live (2026-08-26). The delivery promise,
> backfill-on-subscribe and failure-disclosure sections are decisions still to be taken and
> are written here only when taken — they are public promises (CLAUDE.md § Ask rather than
> assume).

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

A timestamp that is null — a store that has never done that thing — is reported as a
warning, not a failure, so a rebuilt store does not page every hour until its first fetch.

What the heartbeat does **not** cover yet: delivery ("events but no deliveries"), because
nothing is delivered yet. When alert delivery exists its own timestamp joins this table.

The check itself can fail silently — GitHub's scheduler skips runs on inactive repositories
after 60 days without a commit. A repository that goes quiet for two months should expect
the heartbeat to stop with it; `workflow_dispatch` re-arms it.

## Still to decide

- **Delivery promise** — cadence, expected lag, and what a subscriber should conclude from
  receiving nothing.
- **Backfill on subscribe** — whether a new subscriber sees recent history.
- **Failure disclosure** — how subscribers are told an alert was missed. Rare, and the moment
  that decides whether people trust the service.
