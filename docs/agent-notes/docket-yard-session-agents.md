---
name: docket-yard-session-agents
description: Custom subagents schema-critic and source-verifier exist in .claude/agents; stb-ingest-specialist was deliberately deferred
metadata:
  type: project
---

`.claude/agents/` holds **schema-critic** (adversarial review of schema/ADRs against
docs/validation-queries.md), **source-verifier** (re-checks docs/ claims against primary
sources via WebFetch), and **stb-ingest-specialist** (created 2026-08-25 with M1 design;
reviews ingest code against the ten endpoint traps listed in its file and
docs/ingest-design.md). All read-only reviewers. Slash commands: `/adr-new`, `/schema-check`,
`/verify-sources`.

**Why:** CLAUDE.md's review-before-commit policy routes schema changes through schema-critic
and ingest/network code through stb-ingest-specialist — these reviews are mandatory, not
optional.

**How to apply:** run the matching reviewer before committing code in its domain. Agents
created mid-session are not registered until the next session — spawn general-purpose with
the agent file's prompt inlined as a fallback.

Related: [[docket-yard-github-home]]
