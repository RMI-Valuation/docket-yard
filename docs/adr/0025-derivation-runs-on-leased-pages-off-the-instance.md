# ADR 0025 — Derivation runs on leased pages, on the operator's machines, never on the instance

- **Status:** Accepted 2026-09-10 (the operator)
- **Date:** 2026-09-09

## Context

The record's expensive derivations — OCR now, enrichment later — run on hardware the operator
owns: one Linux box with a 12 GB GPU today, a workstation, a Mac and a Jetson available. ADR
0024 settled the forward pass: the instance extracts a new document's *text layer* in a
container holding no store and no key. It said nothing about the batch work, which has run as
a hand-started script on one machine.

That script failed on 2026-09-06 in the way such scripts do. Its server died on one page; it
treated the refused connection as a page failure, walked the remaining 32,849 pages against a
closed port, recorded 9,915 documents as `failed`, printed progress throughout and exited 0.
Nothing alerted, because production's alerting watches the record, not the fleet. Three days
were lost before a login noticed. The same defect — one recorded `failed` silencing a document
for ever — is the one ADR 0024's review found in the loader's predicate.

Machines will differ: engines, versions, quantisation, numerics. ADR 0023 puts the engine and
the render in the reading's key for exactly this reason.

## Decision

1. **Derivation is a queue of pages under lease.** A worker claims pages, reads them, posts
   each result or failure, and extends its lease as it goes. A lease that expires returns the
   page. A dead process, a machine that goes away, or an operator sitting down at their
   workstation costs the pages in hand and nothing else.
2. **A pass is a reading key, and a worker declares its producer.** A worker is refused
   unless the key it declares is the pass's. Another engine, version or build on another
   machine is another pass — never a substitute inside this one.
3. **A failure's reason says whose it is, and the default is not the page's.** A page fails
   finally only for a named reason that belongs to the page. The server dying returns the
   page and makes the worker wait, claiming nothing, so the queue's ages tell the truth. A
   failure nobody named stops the worker rather than failing the page.
4. **A recorded failure is never a reason to skip.** Seeding re-queues every page of a
   document holding a failure that was not the page's own, and sets its file aside.
5. **The fleet is watched the way production is.** The queue's state is exposed in ADR 0019's
   grammar on the node, and detection is a rule evaluated off the box: no page *read* for
   ten minutes, more failed than read for an hour, or the series absent. A local status
   page is for reading, not for detection.
6. **No node holds the store or a key.** Workers read blobs and write reading documents;
   the loader on the instance is the only door into the store, as before.

## Consequences

Pages survive their processes. Adding a machine is a transport and a producer declaration,
not a redesign. Reading documents, the loader and the roots' order are unchanged. The queue
is one SQLite file on one node; a second node needs a small HTTP front on it, which is owed
when a second node is chosen. The off-box rules need the operator's Grafana credentials on
the node and are owed.

## Cost of reversing

Cheap. The output is the same file the old driver wrote; the queue can be deleted and the
driver restarted on any day. What is not cheap is running without it: measured, three days.
