from __future__ import annotations

import hashlib
import inspect
import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from aios_core.contracts import base, errors, models, operations, refs, time
from aios_core.contracts import enums
from aios_core.services import allowed_event_transitions, allowed_task_transitions


SNAPSHOT_PATH = Path("schemas/r2/m0_contract_snapshot.json")
MODEL_MODULES = (base, errors, models, operations, refs, time)


def _schema_hash(model: type[BaseModel]) -> str:
    schema = model.model_json_schema()
    canonical = json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _model_hashes() -> dict[str, str]:
    result: dict[str, str] = {}
    for module in MODEL_MODULES:
        for name, value in inspect.getmembers(module, inspect.isclass):
            if value.__module__ != module.__name__:
                continue
            if not issubclass(value, BaseModel):
                continue
            result[f"{module.__name__}.{name}"] = _schema_hash(value)
    return dict(sorted(result.items()))


def _enum_values() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for name, value in inspect.getmembers(enums, inspect.isclass):
        if value.__module__ != enums.__name__:
            continue
        if not issubclass(value, Enum):
            continue
        result[f"{enums.__name__}.{name}"] = [item.value for item in value]

    # TimePrecision is deliberately defined with the time contract, not enums.py.
    result[f"{time.__name__}.TimePrecision"] = [item.value for item in time.TimePrecision]
    return dict(sorted(result.items()))


def _task_transitions() -> dict[str, list[str]]:
    return {
        state.value: sorted(target.value for target in allowed_task_transitions(state))
        for state in enums.TaskState
    }


def _event_transitions() -> dict[str, list[str]]:
    return {
        state.value: sorted(target.value for target in allowed_event_transitions(state))
        for state in enums.EventStatus
    }


def build_current_snapshot() -> dict[str, object]:
    return {
        "gate_version": "M0-R2+R4-delta-candidate",
        "models": _model_hashes(),
        "enums": _enum_values(),
        "task_transitions": _task_transitions(),
        "event_transitions": _event_transitions(),
    }


def test_m0_schema_snapshot_matches_frozen_contract():
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    current = build_current_snapshot()
    assert current == expected, (
        "M0 frozen contract snapshot changed. Any change requires explicit approval.\n"
        "Current generated snapshot:\n"
        + json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True)
    )


def test_m0_snapshot_has_broad_contract_coverage():
    current = build_current_snapshot()
    assert len(current["models"]) >= 25
    assert len(current["enums"]) >= 12
    assert set(current["task_transitions"]) == {state.value for state in enums.TaskState}
    assert set(current["event_transitions"]) == {state.value for state in enums.EventStatus}
