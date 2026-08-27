# Registers

**Status:** court actions and protective orders published 2026-08-27 (chosen by delegation;
capability map D4 and D7, first slices). `src/docketyard/store/registers.py` is what this
document describes; `/methodology#registers` is generated from the same rule.

A register is a page over every entry of a **type the Board itself printed**, grouped by
docket, newest first, linking each record and its parties. It is a projection of held rows —
rebuildable, never a source of truth (ADR 0006) — and it infers nothing:

| Register | Address | Rows | Rule |
| --- | --- | --- | --- |
| Court actions | `/court` | `decision_record` | `LOWER(decision_type) = 'notice of court action'` |
| Protective orders | `/protective` | `filing` | `LOWER(filing_type) LIKE '%protective order%'` |

Measured 2026-08-27 on the whole record: 491 court-action notices (12 distinct decision
types in all); 695 filings typed `Motion For Protective Order` (the only filing type naming
one, of 122). The sheet marks a protective-order entry with a link to the register.

What a register does **not** say, and its page says so: what the court did (D4's status,
"vacated or withdrawn", is human coding on the document); whether the Board granted the
motion or what was then filed under seal (D7's remainder waits for extraction). Trail-use
(D1) has no register because no decision type names it: notices of interim trail use are
inside `Decision` bodies.

## The citation resolver (F2's second half)

`/d?q=<citation>` answers 303 to the permanent address a citation names; `/cite?q=` answers
the same as JSON (`web/cite.py`). Forms: every docket spelling `urls.lookup` already took,
plus the Board's long names (`STB Finance Docket No. 36873`, `Ex Parte No. 711`, `Docket
No. NOR 42130`), a decision as docket + service date (`FD 36873 (STB served Aug. 25,
2026)`, `… decided 8/25/2026`), and the Board's record ids (`Decision 53210`, `Filing
311981`). A date that two held decisions share resolves to the sheet (which lists both), a date not
held to the sheet — `/cite` carries the reason as `note`, `/d` just lands there; a number the record does not hold resolves to the
sheet address anyway (which says it is not held). The Board's reporter form (`N S.T.B. n`)
and `Decision No. n` are not resolvable until extraction fills `decision_number`. The search
box tries the resolver before the index, so a pasted citation never becomes a word search.
