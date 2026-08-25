# ADR 0001 — Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

This project is expected to outlive its author's active interest in it, and to be inheritable
by a successor. Reasoning that lives only in one person's memory is lost the moment that person
stops paying attention. Several of the decisions ahead are expensive to reverse, and in eight
months the temptation will be to re-litigate them from scratch rather than recall why they were
made.

## Decision

Record every contested architectural decision as a numbered ADR in `docs/adr/`.

Records are **append-only**. Changing a decision means writing a new record that supersedes the
old one and marking the old one superseded — never editing history. The reasoning is the
artefact, not just the conclusion.

## Consequences

Arguing with recorded reasoning is much cheaper than re-deriving it. A successor inherits the
decisions and the arguments together. The cost is the discipline of writing one when a decision
is actually contested — and the discipline of *not* writing one when it isn't.

## Cost of reversing

Trivial. Stop writing them.
