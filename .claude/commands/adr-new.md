---
description: Scaffold the next-numbered ADR from the template, status Proposed
argument-hint: <title of the decision>
---

Create a new architecture decision record titled "$ARGUMENTS".

1. List `docs/adr/` and find the highest existing number; the new record is that plus one,
   zero-padded to four digits.
2. Follow the structure of `docs/adr/TEMPLATE.md` exactly. Filename:
   `NNNN-<kebab-case-slug-of-title>.md`.
3. Status **Proposed**, today's date. Fill in Context, Decision, Consequences, and Cost of
   reversing from what is known - leave a clearly marked placeholder rather than inventing
   anything.
4. End the file with the standard footer: *Proposed, not accepted. Accept only after this
   decision has been checked against `../validation-queries.md`.*
5. If this record supersedes an earlier ADR, say so in the new record and remind me to update
   the old record's Status line to "Superseded by ADR-NNNN" - **never edit anything else in
   the old record**. ADRs are append-only.

Do not mark the new record Accepted in the same session it was drafted.
