# M0-021 Review Packet

## Frozen semantic head

`8818dba83d97f73e3e48df97df9a18e3c450ba9d`

## Base

`5e570f94d79de1d42b11113639c9d8da612a697f`

## Production files changed

- `src/aios_core/services/state_machines.py`
- `src/aios_core/services/__init__.py`

## Test files added

- `tests/unit/test_state_machines_m021.py`

## Semantic assertions

- exact TaskState transition matrix frozen
- exact EventStatus transition matrix frozen
- RUNNING -> WAITING_RESULT allowed
- COMPLETED -> RUNNING rejected
- CANDIDATE -> REJECTED allowed
- MERGED -> ACTIVE rejected
- terminal Task states have no outgoing transitions
- MERGED and SPLIT Event states have no outgoing transitions
- transition inspection returns immutable frozensets
- state changes validated on same object_id
- state changes require exactly next object revision
- illegal state transition remains illegal even when caller presents a new revision

## Exact-head CI

- run: `34813790092`
- job: `103880165317`
- CPython 3.12.14
- pytest 8.4.2
- formal: 385 passed, 1 warning
- reference: 15 passed
- conclusion: SUCCESS

## Diff boundary

Compare `5e570f94...` -> `8818dba...` is ahead-only by 3 commits. Changed files are limited to the state-machine service/export and M0-021 tests. No contracts, storage, query, scheduler, Worker, or persistence schema were modified.
