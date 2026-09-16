from __future__ import annotations

import uuid

from .enums import ObjectType


_PREFIXES: dict[ObjectType, str] = {
    ObjectType.OBSERVATION: "obs",
    ObjectType.ENTITY: "ent",
    ObjectType.RELATION: "rel",
    ObjectType.DIMENSION_DEFINITION: "dim",
    ObjectType.DIMENSION_MEMBERSHIP: "dmem",
    ObjectType.DIMENSION_DERIVATION: "dder",
    ObjectType.CLAIM: "clm",
    ObjectType.EVIDENCE_SET: "evs",
    ObjectType.EVENT: "evt",
    ObjectType.SUMMARY: "sum",
    ObjectType.GOAL: "gol",
    ObjectType.DEPENDENCY: "dep",
    ObjectType.TASK: "tsk",
    ObjectType.WAKE: "wak",
    ObjectType.SESSION: "ses",
    ObjectType.ACTION: "act",
    ObjectType.OUTCOME: "out",
    ObjectType.OPERATION_EXPERIENCE: "exp",
    ObjectType.TOOL_PROPOSAL: "tlp",
    # --- R4 修改案（M0-023~028）候选契约 ---
    ObjectType.PREDICTION: "prd",
    ObjectType.LIFE_CHAPTER: "lfc",
    ObjectType.REINTERPRETATION: "rip",
    ObjectType.COMMUNICATION_EXPERIENCE: "cxp",
    ObjectType.BUDGET_POLICY: "bgp",
    ObjectType.ASSEMBLY_POLICY: "asp",
}


def new_object_id(object_type: ObjectType) -> str:
    """Generate a stable opaque object id.

    The id is intentionally independent of labels/names. Renaming an entity or
    revising an event must never change its identity.
    """
    return f"{_PREFIXES[object_type]}_{uuid.uuid4().hex}"


def new_operation_id() -> str:
    return f"op_{uuid.uuid4().hex}"


def new_execution_id() -> str:
    return f"exec_{uuid.uuid4().hex}"
