# M0 X8-X10 Repair Candidate

Status: GREEN CANDIDATE PENDING EXACT-HEAD CI AND FROZEN REVIEW REPLAYS

Rejected predecessor:

`b9b5921c3e31a40528b0b96e689ae721c334bd7c`

Chief reproducer / adjudication:

- probe commit: `125ff791c8bbdd0ac72343070789d0dece968eeb`
- adjudication commit: `f3e2fcfd538a49ca4578ed80f903b66e9e5559b9`
- finding groups: X8 dataclass-contained typed refs; X9 datetime/query numeric protocol boundaries; X10 corrupt durable-state protocol mapping

Repair source commit:

`9928c66d2aba1b51b1270ca5502afa9d6d3f5073`

Repair scope:

- persistence snapshot recursively preserves dataclass fields so actual `ObjectRef` / `SourceRef` values remain visible to M0-019 validation instead of being silently flattened;
- UTC conversion overflow is normalized to validation failure;
- public historical query integer/timestamp bounds are validated before SQLite binding;
- corrupt world revision, object payload JSON, idempotency result JSON, and legacy replay state fail closed through `STORAGE_FAILURE` rather than raw runtime/parser exceptions.

The one-shot patch workflow/script used only to apply this repair were deleted by the repair commit and are not part of the resulting candidate tree.

This file exists to create an immutable user-authored exact HEAD for canonical CI. It does not declare M0 FINAL PASS. Production remains unchanged and M1 remains frozen.
