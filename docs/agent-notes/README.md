# Agent working notes

Lessons a coding agent's sessions on this project wrote down for the next session: how the
operator wants decisions brought to him, how to measure before claiming, how reviews are read.
They were the agent's private memory on one workstation until 2026-11-25, when they were
moved here so that a session started in any checkout or worktree has them.

Each note is one fact with its date, why it holds, and how to apply it. They are
point-in-time observations, not specifications: where a note names a file, a command or a
number, check it against the repository before relying on it. `CLAUDE.md` and the ADRs win
over a note that disagrees with them.

A `[[name]]` link that matches no file here points at a note kept off the public record
because it names machines or operations. On the workstation those are in the gitignored
`.claude/memory-local/` of the main checkout; a fresh worktree does not have them.

New lessons are added here as a file of the same shape and a line below.

## The notes

- [`adr-acceptance-is-camerons`](adr-acceptance-is-camerons.md) — Accepting a Docket Yard ADR is Cameron's decision alone — never the assistant's, however clean the critic's review
- [`adrs-stay-short`](adrs-stay-short.md) — ADRs must be succinct — state the decision, not the history of drafts that got it wrong
- [`audience-after-arda-talk`](audience-after-arda-talk.md) — Docket Yard stopped being unannounced on 2026-09-17 — ARDA AI Spotlight talk, and a Class I railroad colleague is sharing it internally
- [`check-session-before-login`](check-session-before-login.md) — Before starting `aws sso login`, check for a live session with `aws sts get-caller-identity --profile <p>` — Cameron may already be signed in
- [`code-review-verify-phase`](code-review-verify-phase.md) — In this environment /code-review's forked run launches the eight finders and ends; no verify pass consolidates them — verify candidates yourself
- [`continual-improvement-role`](continual-improvement-role.md) — Cameron's standing charge (2026-09-16): Claude's job is to continually improve Docket Yard, working through filed findings
- [`copilot-review-request-login`](copilot-review-request-login.md) — Re-requesting a Copilot PR review takes the login `Copilot`; `copilot-pull-request-reviewer` is refused as a non-collaborator
- [`docket-yard-session-agents`](docket-yard-session-agents.md) — Custom subagents schema-critic and source-verifier exist in .claude/agents; stb-ingest-specialist was deliberately deferred
- [`docket-yard-topology-decisions`](docket-yard-topology-decisions.md) — Hosting, URL scheme and web-dependency decisions made 2026-08-25 (ADR 0012/0013, FastAPI+Jinja2+uvicorn)
- [`model-labels-are-a-screen`](model-labels-are-a-screen.md) — Blind model label passes miscalibrate in BOTH directions; a rate is only publishable after Cameron checks a subsample
- [`pr-bot-reviews-arrive-late`](pr-bot-reviews-arrive-late.md) — Copilot and Codex post reviews per commit and later than you expect — read the reviews list by commit and timestamp, never one comment fetch
- [`questions-with-context-multiple-choice`](questions-with-context-multiple-choice.md) — When a decision is Cameron's, pose it as multiple-choice questions, each carrying enough context to decide
- [`rehearse-in-productions-image`](rehearse-in-productions-image.md) — Run a migration's tests and rehearsal inside production's image (its SQLite), not on this workstation's newer engine
- [`state-the-question-before-measuring`](state-the-question-before-measuring.md) — Write down the question and its grain BEFORE measuring; run the shipped code rather than re-implementing it; look for what breaks a conclusion, not what supports it
- [`ultra-review-only-when-needed`](ultra-review-only-when-needed.md) — Cameron prefers not to run /code-review ultra on milestone PRs unless it is really needed; Copilot + Codex + local reviews are the default gate
- [`venv-locked-by-vscode`](venv-locked-by-vscode.md) — uv sync fails "Access is denied" on .venv\Scripts when VS Code's Ruff/Black servers run from the venv, leaving it half-wiped (no pytest, pre-commit hook fails)
- [`when-a-design-keeps-breaking`](when-a-design-keeps-breaking.md) — Repeated critic passes finding breaks — especially in the previous fix — is evidence about scope, and the scope question is Cameron's
- [`worktree-pytest-runs-main`](worktree-pytest-runs-main.md) — In an agent worktree, `uv run pytest` silently tests the MAIN checkout's code; use `env -u VIRTUAL_ENV uv run --extra dev python -m pytest` from the worktree
