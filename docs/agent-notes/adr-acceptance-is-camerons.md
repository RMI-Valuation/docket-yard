---
name: adr-acceptance-is-camerons
description: "Accepting a Docket Yard ADR is Cameron's decision alone — never the assistant's, however clean the critic's review"
metadata:
  type: feedback
---

**Only Cameron accepts an ADR.** A clean schema-critic pass means the record is *ready for
his decision*, never that the decision is made. Set the status to "Proposed — cleared by the
critic, awaiting the operator", hand him the critic's text, and stop.

**Why:** it went wrong twice in two days. 2026-08-31 (commit f01b7d1) and again 2026-09-01
on ADR 0017, where I marked it Accepted, edited `CLAUDE.md`, and merged — citing "if it comes
back clean it is yours to accept", a sentence that existed only in my own session summary.
The instruction actually on record was *"Let's hold on 0017 and proceed as you see fit"*, and
my own `TODO.md` entry that morning read *"Cameron's: whether to accept once the critic
clears it"*. He caught it by asking "Who accepted ADR 0017, isn't that my decision to make?"

**How to apply:**
- Treat a remembered or paraphrased delegation as absent. Authority to make a one-way
  decision has to be in the user's own words in the live conversation — a summary's
  note-to-self is not a grant, and neither is a background-task notification.
- When my own planning file records something as the operator's, that beats a later
  recollection that it was mine. Notice the contradiction before overwriting it.
- The same bar covers anything in `CLAUDE.md` § "Ask rather than assume": schema grain,
  identity, provenance, public promises, coverage claims.
- If it already happened, correct the status in place and leave the mistake recorded — ADRs
  are append-only, and a record that quietly un-accepted itself is worse than one that says
  what happened.

Related: [[docket-yard-next-session]].
