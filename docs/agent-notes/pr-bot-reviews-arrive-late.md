---
name: pr-bot-reviews-arrive-late
description: "Copilot and Codex post reviews per commit and later than you expect — read the reviews list by commit and timestamp, never one comment fetch"
metadata:
  type: feedback
---

Before telling Cameron a PR's bot feedback is handled, list `pulls/<n>/reviews` with each review's
`commit_id` and `submitted_at`, and read every review on or after the last commit you replied to —
including its own inline comments (`reviews/<id>/comments`). A single fetch of `pulls/<n>/comments`
is a snapshot, not an inbox.

**Why:** on PR #26 (2026-09-12) I opened the PR and moved on without reading the bots at all; Cameron
asked "did you address the existing copilot and codex comments?" When I did fetch, it was comments
only, once. A SECOND Codex review on a later commit had landed minutes before my replies and held two
more findings, one real (spans not re-verified at the load boundary). I found it only by reading the
timeline for an unrelated reason.

**How to apply:**
- Codex reviews each new commit automatically (its summary comment's `headSha` and a 👀 reaction mean
  a run is in progress; 👍 means done with no findings). Copilot needs a re-request per commit.
- `gh pr edit --add-reviewer @copilot` works but a bot request never appears in
  `requested_reviewers` — confirm it in `issues/<n>/timeline` as a `review_requested` event.
- Before declaring review done, make sure every bot's latest review is on the head commit; if a fix
  was pushed after it, re-request and wait for the new one.

Related: [[narrow-the-command-before-escalating]] (don't trust a completion notice as proof),
[[code-review-verify-phase]].
