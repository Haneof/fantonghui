"""EntityRuntime —— 契约来源: 02 §2 World / 03 Entity+Relationship / Q4 裁决.

Entity 只保存 relationship_ids;Relationship 是一等对象,单独持久化。
实体系统只存客观身份线索,"AI 怎么理解这个实体"属于认知系统(宪法 6.2)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.mini_jsonschema import validate  # noqa: E402


def _load(name: str) -> dict:
    return json.loads((_ROOT / "schemas" / name).read_text(encoding="utf-8"))


class EntityRuntime:
    """实体与关系的持久化(02 §2)。"""

    contract = "02 §2 World / 03 Entity+Relationship"

    def __init__(self, var_dir) -> None:
        self.dir = Path(var_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.entities_path = self.dir / "entities.jsonl"
        self.relationships_path = self.dir / "relationships.jsonl"
        self._entities: dict[str, dict] = {e["id"]: e for e in self._read(self.entities_path)}
        self._relationships: dict[str, dict] = {r["id"]: r for r in self._read(self.relationships_path)}
        self._schema = _load("entity.json")
        self._rel_schema = _load("relationship.json")
        self._seq = len(self._relationships)

    @staticmethod
    def _read(path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    # ---------- Entity ----------

    def upsert(self, entity: dict) -> dict:
        errs = validate(entity, self._schema)
        if errs:
            raise ValueError(f"entity 不符合 schemas/entity.json: {errs}")
        old = self._entities.get(entity["id"], {})
        merged = {**old, **entity}
        merged["relationship_ids"] = sorted(set(old.get("relationship_ids", [])) | set(entity.get("relationship_ids", [])))
        merged["evidence"] = sorted(set(old.get("evidence", [])) | set(entity.get("evidence", [])))
        self._entities[entity["id"]] = merged
        with self.entities_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(merged, ensure_ascii=False, sort_keys=True) + "\n")
        return merged

    def ensure(self, entity_id: str, type_: str = "person") -> dict:
        if entity_id in self._entities:
            return self._entities[entity_id]
        return self.upsert(
            {"id": entity_id, "type": type_, "identity": {"name": None, "aliases": [], "confidence": 0.0},
             "relationship_ids": [], "evidence": []}
        )

    def get(self, entity_id: str) -> dict | None:
        return self._entities.get(entity_id)

    def all_entities(self) -> list[dict]:
        return list(self._entities.values())

    # ---------- Relationship ----------

    def link(self, entity_a: str, entity_b: str, type_: str, strength: float, evidence: list[str]) -> dict:
        """建立/更新关系。关系历史不嵌进 Entity(Q4 裁决)。"""
        self._seq += 1
        rel = {"id": f"rel_{self._seq:03d}", "entity_a": entity_a, "entity_b": entity_b,
               "type": type_, "strength": strength, "status": "ACTIVE", "evidence": sorted(set(evidence))}
        errs = validate(rel, self._rel_schema)
        if errs:
            raise ValueError(f"relationship 不符合 schemas/relationship.json: {errs}")
        prev = next((r for r in self._relationships.values()
                     if {r["entity_a"], r["entity_b"]} == {entity_a, entity_b} and r["type"] == type_), None)
        if prev:
            rel["id"] = prev["id"]
            rel["evidence"] = sorted(set(prev["evidence"]) | set(evidence))
            rel["strength"] = max(prev["strength"], strength)
        self._relationships[rel["id"]] = rel
        with self.relationships_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rel, ensure_ascii=False, sort_keys=True) + "\n")
        for eid in (entity_a, entity_b):
            ent = self._entities.get(eid)
            if ent is not None and rel["id"] not in ent["relationship_ids"]:
                self.upsert({**ent, "relationship_ids": [*ent["relationship_ids"], rel["id"]]})
        return rel

    def all_relationships(self) -> list[dict]:
        return list(self._relationships.values())
