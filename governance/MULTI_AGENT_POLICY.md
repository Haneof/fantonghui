# AIOS 2.0 Multi-Agent Development Policy

## Default mode

During foundational M0 contract freeze, production development is SINGLE-WRITER by default.

Reason: M0 objects share time, revision, reference, provenance, and persistence invariants. Parallel edits to shared contracts create correlated integration risk that is larger than the coding speed gain.

## When parallel development becomes allowed

The Chief Engineer may mark work `PARALLEL_SAFE` only when all of the following are true:

- shared foundational contracts needed by both tasks are already FINAL PASS
- the two assignments have non-overlapping production ownership
- neither task requires editing the same public interface
- merge order is known
- each task has independent tests and review evidence
- each agent works on its own branch
- integration can be reviewed after both branches complete

## Required parallel assignment fields

Every parallel assignment must specify:

- role
- task id
- branch
- frozen base commit
- owned production files/modules
- forbidden files/modules
- shared read-only contracts
- required tests
- merge/integration order
- escalation triggers

## Shared-file rule

Two agents must not concurrently own the same production file unless the Chief Engineer explicitly defines disjoint regions and accepts the merge risk.

For core contracts, prefer no shared-file concurrency at all.

## Contract-conflict rule

If Agent A and Agent B both need incompatible changes to a shared interface:

STOP both implementation lines at the conflicting boundary.

The Chief Engineer reviews first. If the conflict would modify a FINAL PASS foundational contract or has two plausible architectural resolutions, escalate according to `MODEL_ROUTING_POLICY.md`.

## Agent completion

Parallel agents may report only:

- CODE COMPLETE
- PATCH COMPLETE
- BLOCKED
- WAITING CHIEF REVIEW

They may not merge each other, declare FINAL PASS, or authorize downstream tasks.

## Integration Gate

The Chief Engineer must independently verify:

- both branch heads
- compare/diffs against their frozen bases
- ownership boundaries
- unit/integration tests
- exact-head CI
- cross-branch interaction tests after integration

Only then may an integrated commit be frozen.

## Current policy state

As of M0-010: core production development remains SINGLE-WRITER. A second agent may be used only for read-only audit, test design, documentation, or another explicitly isolated task authorized by the Chief Engineer.

The Chief Engineer will explicitly announce: `PARALLEL CORE DEVELOPMENT ENABLED` when the project reaches a safe point.
