---
description: Run the schema critic against the draft schema and the five validation queries
argument-hint: [adr number(s), a schema file, or blank for the full draft]
---

Launch the **schema-critic** subagent.

Target: $ARGUMENTS (if blank: `docs/schema-draft.md` and every Proposed ADR in `docs/adr/`).

Tell it to check the target against all five queries in `docs/validation-queries.md`, using
the measured facts in `docs/stb-data-source.md`, and to return per-query verdicts plus a
ranked defect list.

When it reports back, relay the verdicts and defects to me faithfully - including the ones
that are inconvenient for the current design. Do not change any ADR's status or edit the
schema in response without asking me first.
