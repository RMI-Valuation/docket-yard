---
name: venv-locked-by-vscode
description: "uv sync fails \"Access is denied\" on .venv\\Scripts when VS Code's Ruff/Black servers run from the venv, leaving it half-wiped (no pytest, pre-commit hook fails)"
metadata:
  type: reference
---

VS Code's Ruff server (`.venv\Scripts\ruff.exe server`) and Black formatter LSP run out of the
project `.venv` and lock `Scripts`. A `uv sync` then removes the packages and fails on
`Scripts` — the venv is left with no pytest/ruff/pre_commit, and the git pre-commit hook dies
with "No module named pre_commit". Fixed 2026-10-18: find the PIDs (processes whose Path is
under `.venv`), stop them, `uv sync --extra dev`; VS Code restarts the servers.
