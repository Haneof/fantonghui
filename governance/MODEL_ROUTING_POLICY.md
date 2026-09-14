# AIOS 2.0 Model Routing Policy

This file decides which model tier should do which kind of work. Model names may change over time; route primarily by capability class and escalation conditions.

## Routine implementation

Use a strong coding-capable model or agent when ALL are true:
- task scope is already frozen
- allowed files are explicit
- acceptance tests are explicit
- no previously FINAL PASS contract must change
- no cross-agent shared-interface conflict exists

Typical roles:
- Core Implementation Engineer
- Parallel Implementation Engineer after `PARALLEL_SAFE`

Preferred model class:
- GPT-5.6 Terra-class or comparable strong coding model
- Gemini strong coding/agent model
- existing repo-aware coding agent

The implementation model does not need to be the strongest model if the task is tightly specified and independently reviewed.

## Chief Engineer work

Use GPT-5.6 Sol-class or stronger for:
- task decomposition
- contract design
- code review
- adversarial test design
- scope decisions
- FINAL PASS
- integration decisions
- milestone planning

Use higher reasoning effort for tasks that span multiple contracts or contain temporal/revision/provenance semantics.

## Mandatory GPT-6-class escalation

Escalate to Principal Architect / Red Team when ANY of the following is true:

1. A proposed solution requires changing a previously FINAL PASS foundational contract.
2. Constitution/R1/R2/taskbook appear mutually inconsistent for the current implementation.
3. The same core mechanism receives 3 production-level PATCH cycles with different root causes, suggesting a deeper design flaw.
4. Two parallel implementation lines require incompatible changes to a shared frozen interface.
5. A change touches high-risk systemic behavior and the Chief Engineer cannot locally prove containment, especially:
   - correction/dependency propagation
   - anti-self-evidence
   - crash recovery
   - idempotency across failures
   - concurrent writers
   - schema/data migration
   - permission boundaries
   - AI Worker write isolation
   - long-term historical replay
   - security-sensitive mechanisms
6. A milestone is ready for Gate review. M0 Gate MUST receive an independent GPT-6-class architecture/red-team review before the milestone is considered fully closed.

## Optional GPT-6-class escalation

Use when one of these would materially reduce architectural risk:
- a large design choice has two plausible but incompatible approaches
- a novel invariant cannot be covered convincingly by local tests
- the Chief Engineer wants an independent fresh-context attack on assumptions

## Do NOT spend GPT-6 on

- routine schema additions with frozen requirements
- obvious test-only false-green fixes
- mechanical refactors
- documentation formatting
- simple CI failures
- ordinary bounded bug fixes whose root cause and containment are already clear

## Independence rule

For milestone red-team work, the GPT-6-class model should receive fresh source materials and an explicit adversarial charter. Do not prime it with conclusions like "the architecture is already correct". Its job is to try to falsify the current design.

## Routing summary

- Coding agent / Terra / Gemini-class: bounded implementation
- Sol-class: Chief Engineer, hard implementation, review, integration
- GPT-6-class: architectural court of appeal, independent red team, milestone Gate
- CI: mechanical verifier only
