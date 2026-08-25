# Contributing

Thanks for your interest. A few things to know before you start.

## Project status

**Pre-launch.** The design is settled (see [`docs/adr/`](docs/adr/)) and the pipeline is
being built. Until version one ships, the surface area for contribution is small and the
design is not open for re-litigation — decisions live in accepted ADRs, which are
append-only. If you think a decision is wrong, open an issue that makes the case; a change
means a new superseding record, never an edit to an old one.

## Before writing code

**Open an issue first and say what you intend to do.** Contributions by prior discussion
only — unsolicited pull requests are likely to be declined, not because they are unwelcome
but because unreviewed scope is how small projects drown. Issues are also the right channel
for **data corrections**: if the site publishes something wrong, we want to know, and
[`docs/corrections.md`](docs/corrections.md) describes how corrections propagate.

## The CLA

A signed contributor licence agreement — [`CLA.md`](CLA.md) — is **required before any
contribution is merged**. No exceptions, including trivial patches. Code is
AGPL-3.0-only; see [`LICENSE`](LICENSE) and [`docs/licensing.md`](docs/licensing.md).

## Development setup

```sh
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .[dev]
pre-commit install
pytest
```

Python 3.11+, standard library preferred — a dependency must earn its place. `ruff` for
lint and format, 100-column lines, UTF-8 and LF everywhere (pinned in `.gitattributes`).
Pre-commit runs ruff, hygiene checks, and secret scanning; CI runs the same plus tests.

## Rules that are not negotiable

They are listed in [`CLAUDE.md`](CLAUDE.md) and they bind humans too. The short version:
never infer a party's position from who filed a document; every derived assertion carries
provenance; dates are quoted from sources, never computed; `data/` is disposable and never
committed; secrets are never committed anywhere.
