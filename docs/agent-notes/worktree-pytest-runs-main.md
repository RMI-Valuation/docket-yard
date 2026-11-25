---
name: worktree-pytest-runs-main
description: "In an agent worktree, `uv run pytest` silently tests the MAIN checkout's code; use `env -u VIRTUAL_ENV uv run --extra dev python -m pytest` from the worktree"
metadata:
  type: feedback
---

In a git worktree under `.claude/worktrees/`, `uv run pytest` found pytest in the main checkout's
environment (my shell's `VIRTUAL_ENV` points at `e:\DevProjects\docket-yard\.venv`), which imports
`docketyard` from MAIN's `src`. On 2026-09-15 the veto-trigger branch's new trigger tests all reported
"DID NOT RAISE" and a 4-file run said "137 passed" — both were main's code, where migration 0030 did
not exist.

**Why:** a green or red run of the wrong code is worse than no run; it nearly sent correct triggers
back for rework.

**How to apply:** from the worktree, run
`env -u VIRTUAL_ENV uv run --extra dev python -m pytest ...` (pytest is in
`[project.optional-dependencies] dev`), and print `docketyard.__file__` once to confirm the import
path. Still one pytest run at a time. Related: [[claims-are-not-measurements]].
