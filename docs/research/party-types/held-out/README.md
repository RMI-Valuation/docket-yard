# The held-out party-type sheet

`labels.csv` here is the **second** sample (decided 2026-09-10): 300 parties the rules have
never seen, drawn to turn rules v2's figures on the first sheet — tuned there, and so an
upper bound — into a measurement. A type ships on rule confidence when its precision on
this sheet clears **95%** (`docs/party-types.md` § The page).

## How it was drawn

`tools/party_types_sample.py --rules v2 --exclude ../labels.csv --seed 20260910 --blank`,
from the live store (schema 25) exported read-only by `tools/party_types_export.py` at
2026-09-10 23:40 UTC: 10,171 live `as_filed` names, one per party, less the first sheet's
300, leaves 9,871. Stratified over what rules v2 (`rule:party-type/2026-08-30b`) **emits**,
because the bar is precision — of the names v2 calls a type, how many the operator agrees
with. `sample.json` holds the strata and the population behind each.

**The allocation — the operator's choice, 2026-09-10: weight the candidates.** The four
types v2 scored at 97% or better on the first sheet — government, elected-official,
labor-union, port — are the only ones that could plausibly clear 95%, and take 40 rows
each: at 40, 95% allows two misses. Law-firm takes all 5 names left (the first draw took
the rest). The other seven take 19–20 each, enough to see whether their tuned figures held
and no more. Weighed and set aside: an even ~27 per type (the candidates on a one-miss
edge), and a census of port and labor-union at the others' expense.

The `type` column is **blank** until the operator judges a row, so an unjudged row can
never score as agreement; the scorer counts blanks apart.

## How it is judged

**Blind, then revealed — the operator's choice, 2026-09-10.** The check queue
(`tools/party_types_check_page.py --blind`) hides v2's draft until the first pick, then
shows it boxed; the first pick is kept beside the final one. This is the sheet that
decides what ships, and a boxed draft pulls toward agreeing with it; the first pick is
the unanchored reading, and a change made after seeing the draft is recorded rather than
lost. (On the first sheet, drafts shown, the operator overturned 42% of v1's drafts —
anchoring was not overwhelming, but this is the number that gates publication.) The
conventions are the first sheet's: a role is never a type, a joined pair is a span
artefact, carrier status and class are quoted attributes (`docs/party-types.md`).
