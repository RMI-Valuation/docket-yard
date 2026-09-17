# Docket Yard

A public record of proceedings before the **Surface Transportation Board** - every filing,
decision and environmental comment, organized into docket sheets you can actually follow, with
alerts when something moves.

Not affiliated with the Surface Transportation Board. Every record links to the agency's own PDF.

## Why it exists

The Board publishes its dockets through a records search page built for a person looking up
one case. There is no API for them, result lists stop at a 10,000-row display cap, a filter
passed the wrong way is silently ignored, and much of the older record is scanned paper with
no text in it. Docket Yard reads that record the hard way - sliced by date, every filter
asserted, scans read by OCR - so people, programs and AI assistants can use it.

## Status

Live at <https://docketyard.org> since 2026-08-26, free to use, and under active development.
The Board's docket search is captured every thirty minutes; the archive is walked back to
January 1996. What the record holds, and what it does not, is measured on
[`/coverage`](https://docketyard.org/coverage). Releases are CalVer
([ADR 0010](docs/adr/0010-versioning-and-releases.md)), listed under
[Releases](https://github.com/RMI-Valuation/docket-yard/releases); the one serving the site is
named in its footer and at [`/health`](https://docketyard.org/health).

What is there today:

- **Docket sheets** at permanent addresses (`/d/FD-36873`), one chronological page per
  proceeding across filings, decisions and environmental comments
- **Search** across dockets, captions, party names, the Board's decision summaries and the
  text of documents; a citation in any of the Board's printed forms (`Ex Parte No. 711`,
  `AB 55 (Sub-No. 785X)`) resolves to its address at `/d?q=` or as JSON at `/cite?q=`
- **Document text**: the Board's files read page by page - born-digital files from their own
  text layer, scans by OCR - each page labelled with who read it and the scan one click away
- **Alerts** by email, Atom feeds and signed webhooks, per docket, per party or agency-wide
- **Parties** resolved to entities with their aliases and successions (`/p/<id>`)
- **Browsing**: the week's activity ([`/weeks`](https://docketyard.org/weeks)),
  [statistics](https://docketyard.org/stats), and registers of
  [court actions](https://docketyard.org/court) and
  [protective orders](https://docketyard.org/protective)
- **Data**: JSON at every record address (append `.json`), a nightly SQLite snapshot of the
  index under CC0 at [`/data`](https://docketyard.org/data), and
  [`/api`](https://docketyard.org/api) describing both
- **A read-only MCP server** for AI assistants at `/mcp`, described at
  [`/.well-known/mcp.json`](https://docketyard.org/.well-known/mcp.json): search the record,
  read a docket sheet, an environmental comment or a page of a document's text, count filings
  by the Board's own type, and check coverage. Every answer carries what the record does not
  hold and links the Board's own file

## Where to read

- **Why each thing is built the way it is** - [`docs/adr/`](docs/adr/), one record per
  contested decision, append-only
- **The whole document set, with status** - [`docs/README.md`](docs/README.md)
- **How the Board's search actually works, traps included** -
  [`docs/stb-data-source.md`](docs/stb-data-source.md)
- **The menu of what could come next** - [`docs/capability-map.md`](docs/capability-map.md)
- **Known gaps and review findings not yet fixed** - [`docs/deferred.md`](docs/deferred.md)

## How it is built

Most of the code is written with AI - [Claude Code](https://claude.com/claude-code) - under the
rules in [`CLAUDE.md`](CLAUDE.md): decisions recorded before they are built, tests on every
change, model code review before commit, schema and ingest reviewers for the parts that fail
silently, and bot reviewers on every pull request. Whoever writes the code, the published
record follows the same rules: never infer a party's position, quote dates rather than compute
them, and carry provenance on every derived claim.

## Running it

Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --extra dev
uv run pytest                                  # the test suite
uv run docketyard --help                       # capture, walk, poll, text, search, dump, serve, ...
uv run docketyard poll                          # one forward pass into data/ (talks to stb.gov)
uv run docketyard serve                         # the site over that store, read-only
```

`data/` is disposable and gitignored; everything in it is reproducible from the pipeline.
Production runs on one instance: [`infra/deploy/README.md`](infra/deploy/README.md).

## Layout

```text
src/docketyard/capture  the Board's endpoint: slices, asserted filters, the walk
src/docketyard/ingest   captures into the event ledger; dockets, filings, decisions, comments
src/docketyard/store    SQLite schema and migrations, sheets, search, coverage, the snapshot
src/docketyard/alerts   subscriptions, email, feeds, webhooks
src/docketyard/parties  "filed for" strings resolved to entities, with provenance
src/docketyard/text     page text: pagination, readings, loading
src/docketyard/citator  citations between the Board's documents (built, not yet displayed)
src/docketyard/web      the site, the JSON twins and the MCP server
tests/                  the test suite
tools/                  operator tools: the derivation fleet, benchmarks, checks
docs/                   decisions, specifications and research
infra/                  deployment, DNS, monitoring
```

## Contributing and licence

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) first: contributions are by prior discussion in an
issue, and data corrections are welcome there. Code is **AGPL-3.0-only** - see
[`LICENSE`](LICENSE). Contributions require the agreement in [`CLA.md`](CLA.md). The data
layers carry different terms; see [`docs/licensing.md`](docs/licensing.md).
