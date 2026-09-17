# Docket Yard

A public record of proceedings before the **Surface Transportation Board** - every filing,
decision and environmental comment, organized into docket sheets you can actually follow, with
alerts when something moves.

Not affiliated with the Surface Transportation Board. Every record links to the agency's own PDF.

## Status

Live at <https://docketyard.org> since 2026-08-26 and under active development. The Board's
docket search is captured every thirty minutes; the archive is walked back to January 1996.
What the record holds, and what it does not, is measured on
[`/coverage`](https://docketyard.org/coverage).

What is there today:

- **Docket sheets** at permanent addresses (`/d/FD-36873`), one chronological page per
  proceeding across filings, decisions and environmental comments
- **Alerts** by email, Atom feeds and signed webhooks, per docket, per party or agency-wide
- **Parties** resolved to entities with their aliases and successions (`/p/<id>`)
- **Data**: JSON at every record address (append `.json`), a nightly SQLite snapshot under
  CC0 at [`/data`](https://docketyard.org/data), and [`/api`](https://docketyard.org/api)
  describing both
- **Document text**: the Board's files read page by page, labelled with who read them, and
  searchable
- **A read-only MCP server** for AI assistants, described at
  [`/.well-known/mcp.json`](https://docketyard.org/.well-known/mcp.json)

## Where to read

- **Why each thing is built the way it is** - [`docs/adr/`](docs/adr/), one record per
  contested decision, append-only
- **The whole document set, with status** - [`docs/README.md`](docs/README.md)
- **How the Board's search actually works, traps included** -
  [`docs/stb-data-source.md`](docs/stb-data-source.md)
- **The menu of what could come next** - [`docs/capability-map.md`](docs/capability-map.md)
- **Known gaps and review findings not yet fixed** - [`docs/deferred.md`](docs/deferred.md)

## Running it

Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --extra dev
uv run pytest                                  # the test suite
uv run docketyard --help                       # capture, ingest, poll, text, citator, dump, serve, ...
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
