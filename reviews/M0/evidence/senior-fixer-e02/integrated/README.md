# Integrated validation after production moved

During final remote-head verification, production advanced from 4781826184ec680582fac11e965582c5070b053f to 8dd96ab767c6d359728da2d64a49e47642c93b31. The diff changes only src/aios_core/storage/idempotency.py (52 insertions, 6 deletions): preserve typed refs during revalidation and classify serializer failures as DurableJSONError. It is a semantic change, not documentation.

Merged that production commit into the fixed session branch as 4846fba, resolving the one normalization conflict by retaining BOTH _persistence_snapshot and validated ObjectType dispatch. Prior 731a7503f3b99fa320d9220e74ed468d991c0cc0 green CI (run 34841598009/job 103967620071) is historical evidence only, not a substitute for integrated-head CI.

The earlier 11 failing E-B12/E-B13 probes are now formal tests/unit/test_m0_gate_sixth_followup.py (28 parameterized cases), not omitted from the passing suite. These cases were shown red in the prior evidence, then all passed after the production semantic repair was integrated. Original audit reports are immutable historical findings, not claims that the integrated version still has the same demonstrated bugs.

Local integrated validation A-H ran in the requested order: B10 17, B11 20, B6 5, B5 9, B7 5, R4 5, B1-B9 27, formal 485, Reference 15, prior audit probes 28. All passed. No skipped cases in formal or Reference. Architecture scanner and schema snapshot are part of formal suite. Existing reference/type/revision/time assertions retained (only canonical payload field traversal changed where the fixture shape changed).

Static follow-up: mypy (three touched production modules, follow-imports=silent), ruff E9/F63/F7/F82 (touched production and new tests), compileall src/tests, ruff format check (two new test files), git diff --check all passed. No whole-repository formatting/type policy invented; none is configured in the repository CI.

Correction to the earlier H-final-full.log: that one local invocation omitted PYTHONPATH in an environment without an editable install, so B8's subprocess could not import the src-layout package; 1 failed/456 passed. The failure log is retained. With explicit PYTHONPATH=src on the unchanged 731a750 source, 457 passed. Its remote CI installed the package under Python 3.12.14 and independently reported 457 passed + 15 Reference passed. This is not an xfail/skip or a production fix. Integrated H-full.log records the subsequent 485-case run with the explicit environment.

Current production branch-protection endpoint returned HTTP 403 Resource not accessible by integration. Workflow checks can be enumerated, but branch-protection-required-check policy cannot be certified with this integration. M0 FINAL PASS remains outside this agent's authority. Exact integrated remote SHA/run must be recorded in the final report/PR rather than inferred from these local logs.

## Remote integration canary and test-environment correction

Run 34841875486, job 103968506910, exact cc88209b50cff1b9005f6bd2a97ba15bb6cc508c was RED: 1 failed / 484 passed. Alternate raw-log fetch independently identified test_m0_gate_sixth_followup.py::test_nested_unordered_cross_process_and_ordered_separation, KeyError('PYTHONPATH'), <frozen os>:714. The promoted standalone audit probe wrongly assumed the variable exists; editable-install CI does not require it. Corrected only the subprocess import environment: explicitly use the path of the aios_core package actually imported by the parent, and preserve PYTHONPATH only when present. All seed/replay/order assertions remain. Parameterized present/absent environment paths adds one case (formal now 486). This correction is a real test portability fix, not xfail/skip/flaky reclassification; workflow remains unchanged.
