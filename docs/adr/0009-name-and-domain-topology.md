# ADR 0009 — Name and domain topology

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

The project needed a name that is findable by people searching for STB records, ownable as a
trademark, and comfortable for a constituency that includes STB staff themselves. Those pull in
different directions: descriptive names are findable but unprotectable, and the trademark was
identified as real leverage if the project ever needs a commercial path.

Two candidates were rejected for specific reasons worth recording.

**"STB Watch"** was the original instinct and reads naturally, but "watch" carries a watchdog
connotation. Board and staff are a target audience rather than an adversary, and a name framing
the project as oversight works against adoption by exactly the people whose participation makes
it authoritative. It is also descriptive, so weak as a mark, and it welds the project to one
agency permanently.

**"Milepost"** was preferred on merit — rail's own unit of location, and the place-to-proceeding
lookup is the project's most distinctive capability. It was dropped on availability: the bare
word is taken on both `.com` (1999) and `.org` (2007), the workaround domains were clunky, and
*The Milepost* is an established publication.

Also rejected on availability, all taken on both TLDs: Clearboard, Interlocking, Openrail,
Docketry, Dispatcher, Interchange, Rail Register.

## Decision

**Docket Yard** is the name and the mark. A rail yard is where loose cars are received,
classified, and assembled into something that moves — which is what the platform does with a
scattered corpus. It is rail-native, immediately legible to a lawyer, and spellable from hearing.

Known minor flaw: audibly close to "dockyard" (shipbuilding). Accepted.

**"Watch" survives as the interface verb** — "Watch this docket" — where it describes an action
the user takes rather than a stance the project takes.

**Domain topology.** `docketyard.org` is canonical. `.org` over `.io` deliberately: `.io` is a
ccTLD with long-term uncertainty, and this project is meant to be inheritable.

| Domain | Role |
| --- | --- |
| `docketyard.org` | Canonical |
| `docketyard.com`, `docketyard.net` | Defensive |
| `docketcommons.org`, `docketcommons.com` | Umbrella name, held |
| `stbdocket.org`, `stbdocket.com` | Descriptive doorway → 301 |
| `stbwatch.org`, `stbwatch.com` | Descriptive doorway → 301 |

This resolves the findable-versus-ownable tension by doing both: a distinctive mark, with
descriptive domains redirecting into it so search traffic still lands.

**The STB-prefixed names are never registered as trademarks.** A mark built on a federal
agency's initials risks refusal for falsely suggesting a connection, and undercuts the
unaffiliated posture. They are redirect domains only. The Board may be named descriptively in
copy; never in the logo, never as a source identifier.

Registered under **RMI Valuation, LLC** — liability shield, clean expense treatment, and
continuity that does not depend on one person. Revisit before the trademark filing, since the
applicant must be the party that will own and control the mark.

## Consequences

Search traffic for "STB docket" reaches a name that can be defended. Sixteen redirect hostnames
need certificates and rules maintained, which `infra/cf_redirects.py` handles. Once published
URLs are cited, the canonical choice is permanent.

## Cost of reversing

Renaming after launch means abandoning accumulated citations, search ranking, and recognition.
Changing the canonical host is cheaper but still leaks. Both are expensive after any real
adoption; both are nearly free today.
