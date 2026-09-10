# AIOS adapters

This directory contains adapters that are part of the AIOS mainline boundary.

The simulator adapter is intentionally kept below `aios/01_os`: it emits Raw
Signals only. It does not call Event Runtime or World Runtime, so simulator
replay still passes through the Perception boundary.

Migrated from the repository's validated adapter fixtures without deleting the
original paths. The original files remain available as compatibility/reference
copies until a separate migration decision is made.
