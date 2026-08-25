# Docket Yard — working context

A public record of proceedings before the **Surface Transportation Board** (STB), the federal
agency regulating freight rail. Docket sheets, alerts, and eventually a citator and a map.

Operated by RMI Valuation, LLC. Unaffiliated with the STB. Every record links to the agency's
own PDF.

**Status: pre-build.** Domains registered, design being settled, no pipeline code yet.
Read `docs/README.md` before proposing implementation work.

---

## Constraints that are already known — do not rediscover these

**STB has no API.** Its record search is a JavaScript front end over a WordPress AJAX endpoint.
The working route is a direct POST to `https://www.stb.gov/wp-admin/admin-ajax.php` with:

- `_ajax_nonce` — rotates; re-scrape from `/proceedings-actions/search-stb-records/` each run
- `action` — `stb_hook_table_decisions` | `stb_hook_table_filings` |
  `stb_hook_table_environmental_comments` | `stb_hook_table_dockets`
- `page`, `per-page`, `sort_by`, `sort_order`
- criteria as `search-criteria[i][name]` / `search-criteria[i][value]`

Plain `docketNum_two=36873` as a POST field is **silently ignored** — criteria must go through
`search-criteria`. A working reference implementation exists in the sibling project
`../up-ns-merger-tracker/tracker/stb_client.py`. **Do not modify that project.**

**The 10,000 in every result table is a display cap, not a total.** You cannot page past it, so
walking the archive requires date-slicing — a year at a time for decisions, a month at a time
for filings.

**Volume.** ~194 filings and ~53 decisions per month agency-wide; roughly 700 decisions/year
averaged over 30 years. The full record is on the order of 75,000–125,000 documents. This is
not a big-data problem.

**OCR burden is concentrated in the old archive.** Only about 1% of 2025–26 PDFs are image-only.
Sequence backfill waves from recent years first.

**Headless browsers cannot reach the internet from a sandboxed container** — the egress proxy
resets Chromium connections. curl and urllib work. Never plan a browser-based scrape.

---

## Decisions already made

Full reasoning lives in `docs/adr/`. Summary:

- **Scope v1 to a wedge:** agency-wide docket sheets + alerting, forward-only. No backfill, no
  citator, no map. Resist scope creep from enthusiasm.
- **Design the schema for the full product; implement only the wedge.** Adding attributes later
  is cheap; changing identity, grain, or provenance is not.
- **Six one-way doors** (ADRs 0002–0008): content-hash document identity; extraction captures
  layout not just text; party is an entity not a string; docket number is a composite key with
  parent/child; event grain over current state; provenance on every derived assertion.
- **Never infer a party's position.** It comes from the document's own words. A procedural
  filing takes no position regardless of who filed it. Dates are quoted, never computed from
  context.
- **Do not build** a citation-network visualisation, a comment-submission system, or anything
  duplicating STB's own Open Data Portal.

## Conventions

- Python 3.11+, standard library preferred; add a dependency only when it earns its place.
- `ruff` for lint and format, 100-column lines.
- ADRs are **append-only**. Superseding a decision means a new record, never editing an old one.
- Published pages (methodology, coverage, corrections) are generated from the same source as
  the internal specs. They must not be allowed to drift.
- `data/` is disposable and gitignored. Anything there must be reproducible from the pipeline.
- Never commit secrets. `CF_API_TOKEN` and friends come from the environment.

## What to ask about rather than assume

- Anything that would change the schema's grain or identity model.
- Anything that publishes a derived claim without provenance attached.
- Anything that commits the project to a public promise — an alert guarantee, a coverage claim,
  a correction policy.
