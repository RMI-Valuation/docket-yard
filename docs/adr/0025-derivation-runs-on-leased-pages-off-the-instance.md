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

## Addendum (2026-09-19): a broker places the readers, and the coordinator is backed up

**Status: proposals 1–4 Accepted 2026-09-19 by the operator, on the decisions of 2026-09-18
they rest on. Proposals 5 and 6 are HELD, still Proposed** — they rest on a credential that has
not been placed and on a draft two reviews returned for rebuilding. Extends decision 1 — what a
reader's stop costs, and who may cause one.
It moves nothing in decisions 2 to 6, and it deliberately leaves one gap open: under decision 5
a broker's yield is indistinguishable from a stall, because STALLED is "pages owed and none
read", so every pause longer than the threshold pages the operator correctly and uselessly.
That a pass cannot be declared deliberately down is already filed (`docs/deferred.md`,
2026-09-18) and is not settled here.

A second project now wants the same cards, and nothing arbitrated between them: the only guard
was a VRAM floor inside a worker, so two workloads could load one card. The operator adopted a
self-hosted job broker on 2026-09-18, after a security pass and a fit pass, both clean. This
record said how a pass is read and watched. It never said **who decides which machine reads**.

Measured 2026-09-19, and separate from the broker: the coordinator holds the route roots
(27,269 documents), the collected readings not yet loaded (2,578 documents), and the queue —
64,113 answers, of which only 16 belong to a document not yet written out. Decision 1 makes
every *reader* disposable. Nothing ever made the coordinator so, and a pass stopped part-way is
when that matters most.

**The three are not equally expensive, and the difference decides what is copied how often.**
Everything here is reproducible; what varies is the price. The readings cost GPU time to read
again — about 43 hours for the tabular pages already read — and only while the engine build and
weights snapshot the producer names can still be fetched. The route roots cost a layout-model
run over the corpus, and re-running the router yields a **different method version**: seeding
copies each route document's own method and version into every page of every reading, expressly
so that a document routed by an earlier router says so, so a re-run is recorded honestly rather
than silently (ADR 0007) — but a pass then spans two router versions, and a page reclassified
on the way changes what that pass owes its document. For a page already read and loaded the
class and method are already in the store, so the route root is redundant for it.

*(An earlier draft of this addendum called the route roots "irreplaceable in the strict sense".
That was wrong — `_page_routes` exists precisely so an earlier router's work stays usable — and
it is corrected here rather than quietly dropped.)*

**Decided by the operator (2026-09-18):**

1. **A broker places readers on cards and may stop one**, deciding who gets a card, at what
   priority, and how one workload yields to another.
2. **The broker never learns what a pass is.** The submit line pins the pass; nothing on the
   broker side resolves an engine, a version or a render. A pass is a reading key (ADR 0023),
   so a broker free to resolve versions would split that key silently. The queue keeps owning
   pages, leases, the producer check and the key.

**Accepted by the operator, 2026-09-19 — proposals 1 to 4:**

1. **Preemption is the yield this record already has.** Decision 1 costs "the pages in hand and
   nothing else" when an operator sits down; a broker stopping a reader is that same case, not
   a new one. A reader must honour a stop *signal* as it honours the stop file — release what
   is unspent, exit 0 before the next page. It does not yet do so.
2. **A stopped job is terminal, so something must resubmit.** The broker does not requeue what
   it preempts. Resubmission belongs to this project's fleet tooling and never to the broker,
   because choosing to read again is choosing to spend the record's money.
3. **The coordinator is backed up; readers stay disposable.** Three paths, named rather than
   implied — `ocr/queue.sqlite`, the route roots `ocr/route*`, and each pass's collected root
   `ocr/<root>/` — **and never the data root wholesale, because `fleet.token` is its sibling**
   and decision 6 keeps keys off other machines. The route roots are copied most often, being
   the only strictly irreplaceable part. The queue is copied through SQLite's backup API, never
   `cp`, because it is served while it is read; what that can prove is the **transfer** — a hash
   matching between snapshot and copy — plus `PRAGMA integrity_check` and a row-count floor on
   the copy. It cannot prove fidelity to a database that moved while it was read, and no wording
   should claim it does. A reader keeps nothing worth copying, and that stays true by design.
4. **A reader does not also coordinate.** The machine that runs another project's jobs must not
   be the machine holding this project's ledger. The token is not the reason — it is on every
   joining machine by design — the ledger is.
**HELD, still Proposed — proposals 5 and 6, the operator's to accept or refuse.** Two reviews
returned the first draft of proposal 5 on 2026-09-19: it must be built on this project's own
standard-library signed GET and stream a document rather than buffer it, classify the store's
answers structurally rather than by matching their text, and land the worker half in the same
change — without which a 502 or 503 spends no attempt, records nothing, and loops the fleet.
**One part of it the operator did settle that day:** were the credential ever placed, it carries
`s3:GetObject` **and `s3:ListBucket`** on the blob prefix, so that a document genuinely absent
from the store answers 404 and is charged to the document, while a broken credential answers 403
and is charged to the environment. Without `ListBucket` the two are the same answer, and the
distinction the queue's whole failure grammar rests on cannot be made.

5. **A blob miss is a fetch, not a failure.** The coordinator refetches a document the mirror
   does not hold from the store itself, the way the instance's document route already does, and
   the mirror becomes a cache that may be cold, pruned or absent. Today a miss is a 404, and
   that 404 is what failed **728 pages across 310 documents** on 2026-09-18 — every one of them
   in the store the whole time. What this buys is not the bytes: it is that no box must hold
   109 GB to serve them, and that the box owning the mirror can refill it, which until now only
   a *different* box could do. The sha is the identity (ADR 0002), so fetched bytes are hashed
   before they are cached or served, and a mismatch is loud and never written — that would be a
   corrupt object in the store of record. Whose fault a miss is keeps the queue's own grammar:
   absent from the store is the document's, an unusable credential is the environment's, a
   wrong hash is the store's.
6. **What decision 6 means, said plainly.** "No node holds the store or a key" is **already not
   literally true** — the reading box has held a read-only S3 profile since 2026-08-26, which is
   how the blobs got there. What D6 means, and what item 5 keeps, is that **no node can write to
   the store**: the loader on the instance stays the only door in. A `GetObject`-only credential
   scoped to the blob prefix is not a door. Stating this is not a widening; it is admitting what
   has been true since the fleet was built, so that the next box is reasoned about rather than
   quietly excepted. It does sharpen item 4: a job placed by the broker on the coordinator could
   read that credential, so the coordinator is the one box that must not take other work.

**Consequences.** Placement stops being a matter of which script was started where. Item 5 costs
one read-only credential on the coordinator and makes the mirror movable by not moving it: a
coordinator can change machines without carrying 109 GB, warming instead on demand. It also
retires the recorded asymmetry — the box that owns the mirror could not refill it — rather than
routing around it, and it is why item 5 is worth settling **before** the coordinator moves.
Items 3 and 4 cost one machine's spare capacity and a scheduled copy, and item 4 retires
`fleet-up.sh`'s
`all` role — reader and coordinator on one box — to development only. Item 1 is a change to both
workers, whose lease loops are deliberately duplicated, so it lands in both; the signal must set
the same flag the stop file sets and **must not latch**, since the stop files are latches a
person clears and a broker stop that latched would keep a reader dead until someone noticed.
Item 2's resubmitter owns every exit, not only a preempt: today a restart loop covers queue-
empty and four failure exits, and a broker that displaces it inherits all five.

Nothing here moves the loader, the roots, the reading key, or what a reading says about itself
— but two things the critic found are *adjacent* to that claim and are filed rather than
decided: a worker's registration overwrites its own producer on every restart, which frequent
brokered restarts make load-bearing; and a restore whose queue is newer than its file tree can
mark a document whole while its reading document is absent.

**Cost of reversing.** Cheap, and per item: the broker can be stopped and readers started by
hand on any day, and a backup is a copy nobody has to read. What is not cheap is item 3 left
undone — at the time of writing, 17,275 pages of reading on one disk.
