---
name: code-review-verify-phase
description: "In this environment /code-review's forked run launches the eight finders and ends; no verify pass consolidates them — verify candidates yourself"
metadata:
  type: feedback
---

`/code-review medium` here returns "waiting on the eight finders before the verify pass" and
then never runs it: the forked skill ends its turn after dispatching, and the finder results
arrive as task notifications with no consolidation. `/code-review low` does run inline and
reports directly.

**Why:** Cameron's standing rule is to verify every review finding against the data before
taking it (eleven of eleven reproduced last time; two were errors in an ADR's own drafting).
Waiting for a verify pass that will not come wastes the session; acting on unverified
candidates breaks the rule.

**How to apply:** after the eighth finder notification, reproduce each candidate against
the code or the store (a reading, a query, a short script), take what holds, record what is
deferred in docs/deferred.md dated, and say in the summary which were not reproducible. A
low pass after the fixes is cheap and has caught real things each time. Related:
[[docket-yard-next-session]].
