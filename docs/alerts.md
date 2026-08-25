# Alert reliability

> **Status: stub.** Write alongside the alerting code, not after the first silent failure.

## Purpose

What is promised about delivery, and how silent failure is detected.

## What this locks in

A monitoring requirement. Alerts are cheap to launch and expensive to keep correct — upstream changes break them quietly.

## Skeleton

- **The canary.** Zero new documents for N business days is far more likely a broken scraper
  than a quiet agency. Alert *yourself* on silence.
- **Delivery promise** — cadence, expected lag, and what a subscriber should conclude from
  receiving nothing.
- **Backfill on subscribe** — decide deliberately whether a new subscriber sees recent history.
- **Failure disclosure** — how subscribers are told an alert was missed. Rare, and the moment
  that decides whether people trust the service.
