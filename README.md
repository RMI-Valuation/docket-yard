# Docket Yard

A public record of proceedings before the **Surface Transportation Board** - every filing and
decision, organized into docket sheets you can actually follow, with alerts when something moves.

Not affiliated with the Surface Transportation Board. Every record links to the agency's own PDF.

## Status

Pre-build. Domains are registered and redirecting; the repository is scaffolded; the design is
documented. No pipeline code yet.

- **What to build, and why** - [`docs/capability-map.md`](docs/capability-map.md)
- **The evidence under it** - [`docs/research/comparable-platforms.md`](docs/research/comparable-platforms.md)
- **How the data source actually works** - [`docs/stb-data-source.md`](docs/stb-data-source.md)
- **What to settle first** - [`docs/README.md`](docs/README.md)
- **The test the schema has to pass** - [`docs/validation-queries.md`](docs/validation-queries.md)

## Scope of the first release

Agency-wide docket sheets plus alerting, forward-only. No historical backfill, no citator, no
map. Those are real and they are later. The capability map is a menu, not a roadmap.

## Layout

```
docs/           decisions and specifications; adr/ is append-only
docs/adr/       one architecture decision record per contested choice
docs/research/  secondary research with sources cited
infra/          DNS, redirects, deployment
src/docketyard  pipeline (empty - nothing built yet)
tests/          (empty)
data/           local store; gitignored and always reproducible
```

## Licence

Code is **AGPL-3.0-only** - see [`LICENSE`](LICENSE). Contributions require the agreement in
[`CLA.md`](CLA.md). The data layers carry different terms; see
[`docs/licensing.md`](docs/licensing.md).
