# Corrections

> **Status: stub.** Published page, and an engineering requirement in disguise. Depends on ADR 0007 being honoured.

## Purpose

How an error is reported, what happens next, and how a correction propagates to every page displaying the affected data.

## What this locks in

Whether errors can be fixed at scale. Retrofitting propagation means knowing which derived assertions came from which source.

## Skeleton

- **How to report** — one link on every page carrying a derived claim.
- **What is promised** — response window, and what happens on disagreement.
- **Propagation** — how a corrected extraction invalidates everything derived from it.
- **Hand corrections survive re-extraction.** State the mechanism, or a better model will
  silently overwrite human work.
- **A public correction log.** Costs nothing, signals a great deal.
