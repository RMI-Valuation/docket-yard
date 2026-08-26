# Docket Yard - working context

A public record of proceedings before the **Surface Transportation Board** (STB), the federal
agency regulating freight rail. Docket sheets, alerts, and eventually a citator and a map.

Operated by RMI Valuation, LLC. Unaffiliated with the STB. Every record links to the agency's
own PDF.

**Status: the wedge is live.** <https://docketyard.org> serves the sheets, alerts and the
trust pages from one Lightsail instance (ADR 0012), polling forward every 30 minutes since
2026-08-26; M1–M5 done, unannounced. What comes next is chosen from the capability map, not
assumed. Production operations: `infra/deploy/README.md`.

## Read these before proposing implementation work

| File | Why |
|---|---|
| `docs/README.md` | Index of the whole document set, with status per document |
| `docs/validation-queries.md` | **The five queries the schema must answer.** All five answered on paper 2026-08-25. |
| `docs/schema-draft.md` | The paper schema the queries were validated against; revision history included |
| `docs/adr/` | **0001-0014 all Accepted** (0002-0008 and 0010-0014 carry Validation sections) |
| `docs/stb-data-source.md` | Endpoint mechanics, its silent-failure traps, and every measurement taken |
| `docs/capability-map.md` | The 28 capabilities. A menu, not a roadmap. |
| `docs/research/comparable-platforms.md` | What CourtListener, FERC and others solved; what failed and why |

## Scope

**Version one is a wedge:** agency-wide docket sheets plus alerting, forward-only. No historical
backfill, no citator, no map. Those are real and they are later. Resist scope creep - including
your own enthusiasm for the capability map.

## Constraints already established - do not rediscover

**STB has no API.** The route is a direct POST to a WordPress AJAX endpoint. Full mechanics in
`docs/stb-data-source.md`. Two traps worth repeating here because they fail silently:

- Search criteria **must** go through `search-criteria[i][name]/[value]`. Passing
  `docketNum_two=36873` as a plain POST field is ignored and returns a full unfiltered result
  set with a 200. Ingest code must positively assert the filter applied.
- Filings filter on `filingStartDate`/`filingEndDate`, **not** `officialFilingStartDate`,
  despite the column being labelled "Official Filing Date". The wrong pair returns a
  `success: false` "There are no filings available" envelope — the same one a page past the
  end returns, so it cannot be trusted as "empty" on a first page.

**The 10,000 in every result table is a display cap, not a count.** Walking the archive requires
date-slicing. Backfill waves are forced by the API.

**Volume is modest** - roughly 250 documents a month agency-wide, 75,000-125,000 for the whole
record. This is not a big-data problem. Do not over-engineer for scale.

**A working reference implementation** of the endpoint client exists in the sibling project
`../up-ns-merger-tracker/tracker/stb_client.py`. **Do not modify that project.** Read it if
useful, but write ingest code fresh against this project's schema rather than copying - the
sibling is docket-scoped and has no entity model.

**Headless browsers cannot reach the internet from a sandboxed container** - the egress proxy
resets Chromium connections. curl and urllib work. Never plan a browser-based scrape.

## Design decisions

Reasoning lives in `docs/adr/`. The one-way doors, **all Accepted 2026-08-25** after paper
validation against the five queries (see each record's Validation section):

- **0002** content-hash document identity
- **0003** extraction captures layout, not just text
- **0004** party is an entity, not a string (91 of 605 "Filed For" cells are *lists* of parties)
- **0005** docket number is a composite key with parent/child
- **0006** event grain over current state
- **0007** provenance on every derived assertion
- **0008** geography as structured rows before there is a map

**Do not accept an ADR without first checking it against `docs/validation-queries.md`.** ADRs
are append-only: superseding one means a new record, never editing the old.

Also accepted: **0001** (record architecture decisions), **0009** (name and domain topology),
**0010** (CalVer releases), **0011** (reading is anonymous; an account is an email address),
**0012** (deployment topology), **0013** (permanent URLs), **0014** (subscriber addresses are
ciphertext at rest under an operator-held key).

## Rules that are not negotiable

- **Never infer a party's position.** It comes from the document's own words. A procedural
  filing takes no position regardless of who filed it. Dates are quoted, never computed from
  context.
- **Every derived assertion carries provenance** - source document, location, method, method
  version, timestamp, confidence.
- **Published pages are generated from the same source as the internal specs.** Methodology,
  coverage, and corrections must not be allowed to drift from what the code actually does.
- **Do not build** a citation-network visualisation (CourtListener deprecated theirs for lack of
  traction - build the graph, not the picture), a comment-submission system, or anything
  duplicating STB's own Open Data Portal.

## Working rhythm

- **Start every session by reading `TODO.md`; end it by updating `TODO.md`.**
- Completed items are deleted, never checked off — git history is the archive.
- `ROADMAP.md` is milestone-level only and covers the wedge; detail belongs in `docs/`, and
  everything past the wedge belongs in the capability map, not the roadmap.
- Both files have hard line caps enforced by pre-commit (`tools/check_plan_caps.py`). When a
  cap fires, prune or graduate items; never raise the cap as a side effect.
- Internal planning never moves to GitHub Issues — Issues are reserved for outside intake
  (bug reports, data corrections).

### Review before commit (no PRs for internal work, so this replaces them)

- **Docs-only or trivial changes:** commit after hooks pass; no model review required.
- **Any substantive code change:** run `/code-review` on the diff before committing
  (low/medium for small diffs, high for anything structural) and triage the findings
  in-session. Deferred findings go to `TODO.md`, never silently dropped.
- **Schema-touching changes:** schema-critic reviews before commit, always.
- **Ingest/parser/network code:** the stb-ingest-specialist agent reviews for the endpoint
  traps and invariants (create it at M1 if it does not exist yet); `/security-review` on
  anything handling external input before it first ships.
- **Milestone-scale work:** do it on a branch and open a PR — that tier gets
  `/code-review ultra` and any PR bots (CodeRabbit OSS tier) before merging to `main`.

## Conventions

- Python 3.11+, standard library preferred; add a dependency only when it earns its place.
- `ruff` for lint and format, 100-column lines.
- UTF-8, LF endings everywhere - pinned in `.gitattributes` and `.vscode/settings.json`.
- `data/` is disposable and gitignored. Anything there must be reproducible from the pipeline.
- Never commit secrets. Tokens come from the environment, are short-lived, and are revoked
  after use. See `docs/runbook.md`.

## Ask rather than assume

- Anything that changes the schema's grain, identity model, or provenance.
- Anything that publishes a derived claim without provenance attached.
- Anything committing the project to a public promise - an alert guarantee, a coverage claim,
  a correction policy.
- Anything that would make a decision recorded in an accepted ADR obsolete.
