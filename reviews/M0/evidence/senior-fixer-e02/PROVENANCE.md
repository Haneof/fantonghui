# B10/B11 repair provenance (2026-09-14)

Production base and original failing run SHA: `4781826184ec680582fac11e965582c5070b053f`.
Original run 34837086293 / job 103953253641.

The ordinary gh logs download failed on the external storage hop. The alternate web fetch tool successfully read the signed raw job-log URL. The URL signature is intentionally not persisted here. Raw-log excerpts inspected: chunks 0, 2, 48 and 49 (50 total); not a claim to have archived all raw log bytes.

Verified raw-log lines:

```
2026-09-14T11:13:24.1847660Z platform linux -- Python 3.12.14, pytest-8.4.2, pluggy-1.6.0
2026-09-14T11:13:24.1850068Z collected 433 items
2026-09-14T11:13:34.5955965Z tests/unit/test_world_object_revision.py:680: AssertionError
2026-09-14T11:13:34.5961471Z tests/unit/test_world_object_revision.py:732: AssertionError
2026-09-14T11:13:34.5975106Z ================== 24 failed, 409 passed, 1 warning in 11.27s ==================
```

The two named tests are `test_w15_object_type_cannot_change_across_revisions` and `test_w16_type_conflict_atomic_rollback_multi`: expected VERSION_CONFLICT, got INVALID_ARGUMENT. DummyClaim is not a canonical Claim; canonical revalidation rejects it before type-continuity validation. Stack boundary: sqlite_store.py:461 -> idempotency.py:103 -> canonical Claim.model_validate; StoreError is raised at sqlite_store.py:464. Other original failures: test_errors E12/E13/E15/S02/S03; test_refs R04-R17; test_time T27/T28/knowledge_cutoff_uses_learned_at_not_occurred. These are the same canonical-fixture incompatibility, not 24 independently discovered runtime bugs. Existing assertions remain; one payload assertion follows the equivalent canonical EventAnchor participant_refs[0] instead of the removed custom field ref.

The GitHub UI's two annotations are one Node warning and one exit-code error, NOT two pytest failures. Installed remote Pydantic was 2.13.5. Prior audit local full traceback archive remains under governance/agent_reports/m0-parallel-audits/evidence/auditor-e-02/head-baseline.log.

Local runs: Python 3.11.2, pytest 8.4.2, Pydantic 2.13.5. Remote 3.12 exact-SHA CI is required separately. pytest targeted deselections are deliberate scope selection, not skipped blockers. No workflow modification.

`edges-red.log` was produced on merge baseline 7a796a8 (src/tests inherited from production) with new tests committed as ea1a12b before implementation. 6 failed / 18 passed. Unknown string/None discriminator escaped as KeyError; registry replacement did not raise. The unhashable discriminator existing-key case already mapped to IDEMPOTENCY_CONFLICT and is retained as a control.

`B11-historical-red.log` runs the fifth-followup B11 tests with both PYTHONPATH and pytest pythonpath explicitly pointing at an archived 659157b849a0dbaad241c3e316dcd98eb7c72df7 tree: 4 failed / 1 passed. Existing production B11 repair is retained; no weakening of key rejection.

All local A-H phase logs precede two semantics-neutral static adjustments (local variable rename and explicit TypeAdapter[Any] annotation). Final full-suite rerun and remote exact-SHA result must supersede them. Scoped static checks: ruff fatal/syntax rules on changed implementation/new probe, mypy on three modified source modules with silent imports, compileall src/tests, full architecture tests, ruff format on new probe only, git diff --check. The repository has no declared lint/typecheck/format CI jobs or configurations, and no whole-repository style cleanup was performed.

## Known remaining blockers outside this minimal repair

Prior E-B12/E-B13 audit probe was re-run with pytest pythonpath explicitly forced to the repair tree: 11 failed / 17 passed. Typed refs under Any still lose type before collection; non-UTF8 Any bytes still escape as UnicodeDecodeError. No assertion is disabled; these audit probes remain standalone evidence rather than being silently called part of the passing formal suite. Consequently a green B10/B11 CI cannot authorize M0 FINAL PASS. M0 REMAINS BLOCKED pending the independent adjudication/repair of those separately reported findings.

Only the fixed session branch is changed/pushed. Production source was merged into it (unrelated histories) without switching branches; production branch itself was not pushed. Original audit reports and unrelated HTML are not repaired or overwritten.
