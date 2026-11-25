---
name: ultra-review-only-when-needed
description: Cameron prefers not to run /code-review ultra on milestone PRs unless it is really needed; Copilot + Codex + local reviews are the default gate
metadata:
  type: feedback
---

On PR #27 (finder family closure, 2026-09-13) Cameron said: "I'd prefer not to do review ultras
unless they are really needed." CLAUDE.md still lists ultra for milestone-scale PRs; his
stated preference narrows that.

**Why:** ultra is billed and user-launched; the local /code-review high + low, the
schema-critic / stb-ingest-specialist agents, Copilot and Codex already cover most PRs.

**How to apply:** don't ask him to launch ultra by default. Propose it only when a change is
unusually risky and the other reviews leave a real gap — say why it is needed. When Codex is
blocked (it hit its usage limit on PR #27 and likely #26's last commit), tell him; he can
re-request it with `@codex review`. See [[pr-bot-reviews-arrive-late]].
