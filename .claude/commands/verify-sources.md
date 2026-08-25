---
description: Re-verify a document's claims against primary sources
argument-hint: <doc path, or a specific claim to check>
---

Launch the **source-verifier** subagent against: $ARGUMENTS

If a document was named, have it extract the load-bearing factual claims (legal specifics
first, then measurements, then platform facts) and verify each against a primary source. If a
single claim was given, verify just that claim.

When it reports back, give me the verdict table with quotes and URLs. Where a claim is
**Contradicted** or **Stale**, propose the correction to the document but do not apply it
until I confirm - and remember corrections to ADRs are new records, never edits.
