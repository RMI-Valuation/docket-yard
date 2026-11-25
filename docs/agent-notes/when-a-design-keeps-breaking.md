---
name: when-a-design-keeps-breaking
description: Repeated critic passes finding breaks — especially in the previous fix — is evidence about scope, and the scope question is Cameron's
metadata:
  type: feedback
---

When schema-critic keeps breaking a draft, stop drafting and take the scope question to him.
2026-09-17: three passes on an ADR 0021 addendum, each finding real breaks, and TWICE the break
was in the previous pass's own repair (a dated rule fixed the cut, then the lexicon reinstated
the same every-row cost; a read-time floor fixed that and pushed the row count to 1.085M). The
design had grown to 17 decisions and four tables to print ONE sentence on a page.

He withdrew it and took his own first answer — the score stays an internal routing list, the
re-read fixes the pages rather than labelling them.

**Why:** the accumulation is itself the finding. A fourth draft would have found a fourth break;
what was never re-asked was whether the published sentence justified the machinery.

**How to apply:** after two passes that each break the previous fix, write the cost plainly
(objects, rows, what a change costs) and bring it as a multiple-choice decision, with the
option he already leaned toward first. Withdraw rather than delete — the passes are what a
later attempt should start from. See [[adr-acceptance-is-camerons]] and [[adrs-stay-short]].
