# M0-012 Review Packet

Task: EventAnchor（事件锚点）契约与生命周期
Date: 2026-09-14
Chief verdict: FINAL PASS
Frozen semantic commit: `5ab6ed1c21f2c3f2664104faff3494113bdd5bc1`
Pre-task base: `ab5c789faf758644a25d3c1fbc8a4d9a79b03bd4`

## Authoritative requirements checked

- Event is an interpretation/anchor, not a raw Observation fact.
- Lifecycle supports CANDIDATE / ACTIVE / RESOLVED / REVISED / REJECTED / MERGED / SPLIT.
- candidate->active, candidate->rejected, active->revised tested.
- MERGED terminal tested; SPLIT terminal also guarded.
- REVISED uses a new append-only object revision; old versions remain replayable.
- merge/split/revision retain explicit versioned links.
- Event does not copy raw Observation payloads.
- create does not require confidence=1.
- changing title/interpretation cannot erase old revisions.

## Production delta

Only production file changed from pre-task base:

`src/aios_core/contracts/models.py`

EventAnchor additions/freeze:

- support/counter EvidenceSet refs separated while preserving legacy generic `evidence_set_refs`.
- provenance refs pinned.
- `split_from_ref` and `revision_reason` added.
- structural lifecycle invariants for REVISED/MERGED/SPLIT and revision reasons.

`src/aios_core/services/state_machines.py` was inspected and not changed because its existing transition table already satisfies the M0-012 required transition tests.

## Test files

- `tests/unit/test_event_anchor.py`: 15 EventAnchor contract/lifecycle/replay tests.
- `tests/unit/test_event_anchor_legacy_evidence_ref.py`: exact + pinned compatibility guard for legacy generic evidence refs.

## CI history

Initial test commit `98372478a39ad85d0653d30e03b8d7d24370ba70`:
- 282 passed / 1 failed.
- failure: existing M0-006 regression expected `EventAnchor.evidence_set_refs`.
- verdict at that point: NOT PASS.

Compatibility repair `eb8ab749cb561b6b64701e7f1ddbadf932f28284`:
- restored generic `evidence_set_refs` while keeping explicit support/counter refs.
- CI SUCCESS: 283 passed + reference 15.

Final semantic/test freeze `5ab6ed1c21f2c3f2664104faff3494113bdd5bc1`:
- GitHub Actions run `34806790239`
- job `103860118133`
- CPython 3.12.14 / pytest 8.4.2
- 284 passed, 1 expected pre-existing serializer warning
- Reference suite: 15 passed
- SUCCESS

## Adversarial conclusions

1. Low-confidence candidate is legal.
2. Confidence outside [0,1] is rejected.
3. Invalid lifecycle transition candidate->resolved is rejected.
4. REVISED without historical link/reason is rejected.
5. MERGED/SPLIT without required traceability links are rejected.
6. Floating Claim/Evidence/history provenance is rejected.
7. Post-validation in-place mutation to floating provenance is rejected again at the durable store boundary.
8. Participant navigation remains allowed to use stable Entity ID with floating revision; this is navigation, not evidence provenance.
9. Sports-day -> track-test revision history survives exact historical replay.
10. Raw Observation contents do not appear in Event payload.

## Deferred intentionally

Not part of M0-012:
- event.create/expand/revise/reject/merge/split service implementation;
- reverse dependency index;
- downstream stale propagation;
- correction-generated review Tasks/Wakes;
- M3 R2-11 propagation behavior.

These remain future milestones and were not pulled forward.
