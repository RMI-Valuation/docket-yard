---
name: check-session-before-login
description: "Before starting `aws sso login`, check for a live session with `aws sts get-caller-identity --profile <p>` — Cameron may already be signed in"
metadata:
  type: feedback
---

Before asking Cameron to sign in (an `aws sso login` link, a Tailscale check), check whether a
session already exists: `aws sts get-caller-identity --profile docket-yard`. On 2026-10-18 I
started a device login and handed him the link while the profile was already signed in.

**Why:** a needless sign-in costs him a click and an interruption, and he noticed.
**How to apply:** probe first; only start a login when the probe fails with an expired/missing token.
