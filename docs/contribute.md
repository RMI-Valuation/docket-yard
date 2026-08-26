# `/contribute` — design note

> **Status: built 2026-08-26 (`web/templates/contribute.html`, `/contribute`), awaiting the
> operator's sign-off before it is deployed** (a public promise; ADR 0011's rule applies).
> **Decided 2026-08-26: two lanes, ideas and code. The money lane is tabled** — the page says
> the project does not take money at present and will say what it pays for and buys if that
> changes; the entity question (`licensing.md` § Open) comes first. This note is the source
> the page is generated from; the two must not drift.

## What it is for

One page that answers "how do I help?" in three lanes, without creating any obligation the
project cannot keep. It is not a fundraising page and not a community page; it is the
routing table for outside input, the same way `/corrections` is the routing table for data
errors.

## The three lanes

| Lane | Route | Already decided | Still to decide |
| --- | --- | --- | --- |
| **Ideas** | GitHub Issues, a new `idea.yml` template | Issues are for outside intake only (`CLAUDE.md`); `data-correction.yml` is the model | Template fields (below); whether ideas are triaged publicly (label + a one-line reply) or silently |
| **Code** | The repository, under the CLA | CLA exists from the first commit (`CLA.md`, `licensing.md` § Contributions); AGPL-3.0 | Nothing on the page until the attorney has reviewed the CLA (`licensing.md` § Open) — until then the page says code contributions are welcome *by discussion first*, and links the CLA as what will apply |
| **Money** | none — tabled | Operator's decision 2026-08-26: the page says the project does not take money at present, and that if that changes the page will say what it pays for and what it does not buy | The entity question (`licensing.md` § Open) and whether to name the running cost, before any channel exists |

## What the page must say, in this order

1. What the project is and is not, in one line, with the operator named as RMI Valuation,
   LLC (as `/about` does; no named person, per the M5 decision).
2. **Ideas** — link to the idea template; say that reports are public; say that the
   capability map is the menu and a decision is the operator's (so an idea is not a queue).
3. **Data errors are not ideas** — one line pointing at `/corrections`.
4. **Code** — the repository link; the CLA, and why (single copyright ownership keeps
   relicensing possible: `licensing.md` § Contributions); "open an issue before a pull request".
5. What contributing does **not** get anyone: their name on the site, a say in the record's
   content, early access to anything, a private line to the operator.
6. **Money** — one paragraph: the project does not take money at present; if that changes the
   page will say what it pays for and what it does not buy; nothing to send, nowhere to send it.

## The idea template (`.github/ISSUE_TEMPLATE/idea.yml`)

Modelled on `data-correction.yml`. Fields: *What you were trying to do* (required); *What
would have helped* (required); *Which capability this is nearest to* (optional dropdown of
the capability-map ids, so the operator can file it against the menu); *Are you a
practitioner, a carrier, a shipper, a reporter, a researcher, other* (optional, single
choice — no free text about the person). Label `idea`. The config's blank-issue setting stays
off.

## Rules the page inherits

- Never a promise of delivery, timing, or reply. "Reports are public and so is what is done
  about them" is the corrections page's promise and is the strongest wording available here.
- Nothing about readers: no counter of contributors, no thanks list, no tiers.
- The page is generated from this note's decisions, not the other way round (`CLAUDE.md`:
  published pages do not drift from the specs). When the draft is approved, this note becomes
  the source and the template renders it.

## Needs the operator

- [x] Two lanes; money tabled (2026-08-26).
- [ ] Sign off the page copy (`web/templates/contribute.html`) before it is deployed and
      linked from the footer.
- [ ] Confirm the code lane's wording — "discussion first; pull requests held until the CLA
      review" — and that the review is the gate for merging any outside pull request.
- [ ] Later: the entity question, and whether a money paragraph ever names the running cost.
