# M0-014 Review Packet

- Task: M0-014 Task / Wake / Session / Action / Outcome 基础契约
- Base: `2a096d7e67d2cd590bdfc68d98f77bb1044e70b0`
- Frozen semantic HEAD: `af49c27c95527ca1d2b28cddd88115b0264b48c4`
- Compare: ahead-only, 3 commits, behind 0
- Production file changed: `src/aios_core/contracts/models.py`
- Test file added: `tests/unit/test_active_system_contracts.py`
- No `sqlite_store.py`, scheduler, Worker, database schema or unrelated frozen contract changes.

## Frozen invariants

1. Future work is a durable Task, not model-context memory.
2. Task remains distinct from Goal.
3. Wake is a separate durable object carrying source/hits/evidence/priority/dedupe.
4. Session preserves wake origin, world snapshot, operation IDs and checkpoint for recovery.
5. Action has stable execution_id and remains separate from Outcome.
6. Action completion / message delivery does not imply user acceptance, goal improvement, or learning success.
7. Outcome may remain `unknown`.
8. Historical reason/execution/outcome/wake/action/evidence refs are pinned; navigation refs are not globally forced pinned.
9. M0-009 persistence-boundary revalidation applies to post-validation list mutation.
10. Scheduling/runtime behavior remains out of M0-014 scope and is deferred to M2.

## CI

- Run: `34807928978`
- Job: `103863350345`
- Python: 3.12.14
- pytest: 8.4.2
- Formal: 315 passed, 1 accepted adversarial EvidenceSet serializer warning
- Reference: 15 passed
- Conclusion: SUCCESS

## Known failed attempt

Run for `48423e911626aa07ac7e31617c19927eca8b0e83` failed during test collection because the new test imported `StoreError` from the wrong module and referenced a nonexistent `store.world_revision` property. Production code was unchanged by the correction. Commit `af49c27...` fixes only those test defects and is the accepted exact HEAD.
