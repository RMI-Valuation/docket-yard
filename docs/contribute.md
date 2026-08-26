# `/contribute` — design note

> **Status: planning only, 2026-08-26.** Chosen by the operator as the ask after party pages;
> not started. The page copy is a draft for the operator's review, and ships only on his
> sign-off (a public promise; ADR 0011's rule applies). This note records what the page must
> decide and where each decision already stands, so the draft is written once.

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
| **Money** | `hello@docketyard.org`, for now | Operator's decision 2026-08-26: no payment channel yet; say what money pays for and that it buys nothing | Whether to name the running cost (the instance, S3, SES — roughly the $12 plan plus cents) so "what it pays for" is a number; the entity question (`licensing.md` § Open) must be settled before any formal channel |

## What the page must say, in this order

1. What the project is and is not, in one line, with the operator named as RMI Valuation,
   LLC (as `/about` does; no named person, per the M5 decision).
2. **Ideas** — link to the idea template; say that reports are public; say that the
   capability map is the menu and a decision is the operator's (so an idea is not a queue).
3. **Data errors are not ideas** — one line pointing at `/corrections`.
4. **Code** — the repository link; the CLA, and why (single copyright ownership keeps
   relicensing possible: `licensing.md` § Contributions); "open an issue before a pull request".
5. **Money** — what it pays for (hosting, mail, the backfill's storage; nothing else); that it
   **buys nothing**: no priority, no influence over what is built, no access, no listing; that
   there is no channel yet beyond an email; that the project may never take money at all.
6. What contributing does **not** get anyone: their name on the site, a say in the record's
   content, early access to anything.

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

- [ ] Approve the three-lane structure and the order above.
- [ ] Decide whether the money paragraph names the monthly cost.
- [ ] Confirm the code lane's wording is "discussion first, CLA applies" until the attorney
      review, and that the review is the gate for merging any outside pull request.
- [ ] Review the draft copy (written next, in `web/templates/contribute.html`, with this note
      as the source) before it is linked from the footer.
