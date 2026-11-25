---
name: copilot-review-request-login
description: "Re-requesting a Copilot PR review takes the login `Copilot`; `copilot-pull-request-reviewer` is refused as a non-collaborator"
metadata:
  type: reference
---

To ask Copilot for a fresh review after pushing a new head:

```
gh api -X POST repos/RMI-Valuation/docket-yard/pulls/<n>/requested_reviewers \
    -f "reviewers[]=Copilot" --jq .number
```

`-f "reviewers[]=copilot-pull-request-reviewer"` — the login its reviews are POSTED under — returns
422 "Reviews may only be requested from collaborators" (2026-09-15, PR #36). Copilot also reviews a
newly opened PR unasked, so a re-request is only needed after a later push.

**BUT ON 2026-09-17 (PR #42) THAT CALL SILENTLY DID NOTHING**: it returned 200 with the whole PR
object, `requested_reviewers` stayed `[]`, no `review_requested` timeline event was written, and
no review arrived within 20 minutes of the PR opening — so the "reviews a new PR unasked"
behaviour did not fire either. Three forms were tried (`-f`, `-F`, a JSON body). Do not report a
Copilot review as requested without checking
`gh api …/pulls/<n> --jq '[.requested_reviewers[].login]'` afterwards; when it comes back empty,
the recovery is Cameron adding Copilot from the PR page's Reviewers panel, which the API will not
do. See [[pr-bot-reviews-arrive-late]].

**The GraphQL route is a dead end too** (2026-09-18, PR #42): `suggestedActors` offers only
`copilot-swe-agent` (`BOT_kgDOC9w8XZ`-shaped id), which is the CODING agent, not the reviewer, and
`requestReviews(userIds: [...])` rejects a Bot id — "Could not resolve to User node". Do not spend
the calls; go straight to asking Cameron for the click.

Always pass `--jq` on `gh api`: the bare call prints the whole pull-request object, which is
thousands of tokens of context for one status line. See [[pr-bot-reviews-arrive-late]].
