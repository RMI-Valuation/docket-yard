---
name: adrs-stay-short
description: "ADRs must be succinct — state the decision, not the history of drafts that got it wrong"
metadata:
  type: feedback
---

Keep ADRs short and to the point of what they decide. Cameron, 2026-09-05: "we don't want
long ADRs that no one can understand, we have fallen into that trap before."

**Why:** an ADR is read to find out what was decided. Narrative about earlier drafts,
per-decision post-mortems and kept lineage bury that, and a record nobody can read is a
record nobody consults — which is the whole point of writing one. Recent ADRs run 226–409
lines and that is already too long, not a target.

**How to apply:** state each decision in the active voice with a one-line reason where the
reason is non-obvious, and stop. The account of what an earlier draft got wrong belongs in
the COMMIT MESSAGE, and owed work in a short § Owed section — never as inline history in
the decisions. ADR 0022's kept three-draft lineage is the exception that earned it (the same
mistake repeated); do not generalise from it. 0024 was rewritten from ~200 lines of
half-archaeology to 142 for exactly this.

Related: [[adr-acceptance-is-camerons]].
