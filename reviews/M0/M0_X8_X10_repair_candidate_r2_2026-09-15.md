# M0 X8-X10 Repair Candidate R2

Exact source repair prior to this evidence-only commit:

`c7ee1203b07650eaedc9a8120288371b8135b961`

This R2 preserves the existing frozen behavior that naive `knowledge_cutoff` values raise `ValueError`, while still mapping timezone-aware UTC conversion overflow at the public query boundary to `INVALID_ARGUMENT`.

The Chief 14-case X8/X9/X10 regression suite remains unchanged. No test expectations were weakened.

This evidence-only commit is the exact candidate trigger for canonical CI. It does not authorize production promotion or M1.
