# ADR 0010 — Versioning and releases

- **Status:** Accepted
- **Date:** 2026-08-25
- **Accepted:** 2026-08-25

## Context

Docket Yard is a service and a data product, not a library. "What version is this?" has four
different answers that must not be conflated: what code is deployed, what shape the store has,
what method extracted an assertion, and — eventually — what contract the public API promises.
A single version number pretending to answer all four is how "v1.4.2" ends up saying nothing
about whether the corpus was extracted with the old citation regex. Production will live in a
container pulled by its host, so "what is in production" must be answerable by one lookup.

## Decision

Four version axes, each with its own scheme:

1. **Service (releases): CalVer** — `vYYYY.MM.N`, where `N` counts releases within the month.
   Every release is a GitHub Release; **the git tag, the release tag, and the container image
   tag are the same string.** GitHub Releases is the production ledger: what is deployed is
   the latest release, by definition. Release notes live on the release, generated from the
   commit log; there is no `CHANGELOG.md`.
2. **Schema: monotonic migration numbers**, independent of service version. A release's notes
   state the schema version it expects.
3. **Extraction methods:** per-method `method_version` on every assertion, as already decided
   in ADR 0007. Model-based methods record model identity in the method name.
4. **Public API (future, capability F5):** its own explicitly versioned contract (`/v1/`),
   created when the API is, never inherited from the service version.

SemVer is deliberately not used for the service: nobody depends on its interfaces, so
major/minor compatibility semantics would be theater, while CalVer answers "how stale is
production?" from the tag alone.

## Consequences

Production state is one lookup. Deploys compose with pull-based hosting (a host pulls the
release-tagged image). Extraction provenance stays decoupled from deploy cadence — a re-run
is a method-version bump, not a release. The cost: four axes to keep straight, and the
`pyproject.toml` version field becomes ceremonial (pinned at `0.0.0`; the tag is the truth).

## Cost of reversing

Moderate, rising with time. Retagging conventions is cheap while releases are few; once
release tags are referenced by image registries, runbooks, and coverage pages, changing
schemes means a mapping table forever.

## Validation (2026-08-25)

Checked against [`../validation-queries.md`](../validation-queries.md): the five queries do
not exercise release or schema versioning directly. The one axis they do touch — extraction
method versions — was validated under ADR 0007, whose supersession discipline this decision
inherits unchanged. No query requires the axes to be unified, and query 2's
"re-typing is a higher-method-version pass, not a re-ingest" depends on them staying separate.
