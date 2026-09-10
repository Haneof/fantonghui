"""Sprint 1 Task 1 —— schema 与 03 文档的一致性测试。

运行: python3 -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import schema_check as sc  # noqa: E402
from tools.mini_jsonschema import validate  # noqa: E402


def load(name: str) -> dict:
    return json.loads((ROOT / "schemas" / f"{name}.json").read_text(encoding="utf-8"))


def doc_examples() -> dict[str, dict]:
    """解析 03 里每个 `## 对象名` 小节下的第一个 json 代码块。"""
    text = sc.read("03_WORLD_EVENT_SCHEMA.md")
    out: dict[str, dict] = {}
    for m in re.finditer(r"^## (\w[\w ]*)\s*$(.*?)(?=^## |\Z)", text, re.M | re.S):
        title, body = m.group(1).strip(), m.group(2)
        block = re.search(r"```json\s*(.*?)```", body, re.S)
        if not block:
            continue
        try:
            out[title] = json.loads(re.sub(r"\n\s*\n", "\n", block.group(1)))
        except json.JSONDecodeError as exc:  # pragma: no cover
            raise AssertionError(f"03 §{title} 的 JSON 示例无法解析: {exc}") from exc
    return out


NAME_MAP = {
    "Event": "event",
    "Entity": "entity",
    "World State": "world_state",
    "World Change": "world_change",
    "Memory": "memory",
    "Relationship": "relationship",
    "Cognition": "cognition",
    "Growth": "growth",
    "Decision": "decision",
}


class TestSchemaSet(unittest.TestCase):
    def test_nine_schemas_match_canonical_set(self):
        self.assertEqual(sorted(sc.check_schema_files()), sorted(sc.canonical_schema_names()))
        self.assertEqual(len(list((ROOT / "schemas").glob("*.json"))), 9)

    def test_every_schema_is_draft07_shaped(self):
        for name in sc.canonical_schema_names():
            with self.subTest(schema=name):
                sc.check_schema_shape(name)

    def test_canonical_naming_and_relationship_rules(self):
        sc.check_canonical_rules()

    def test_enums_come_from_doc(self):
        sc.check_enums()

    def test_unknown_field_is_rejected(self):
        """additionalProperties=false 必须真的生效(否则 schema 形同装饰)。"""
        ev = load("event")
        bad = {"id": "e", "timestamp": "t", "source": "mic", "type": "speech", "content": "c",
               "entities": [], "confidence": 1.0, "raw_ref": None, "raw_data": {"blob": "..."}}
        errs = validate(bad, ev)
        self.assertTrue(any("raw_data" in e for e in errs), f"raw_data 未被拒绝: {errs}")


class TestDocExamplesConform(unittest.TestCase):
    """03 的每个 JSON 示例必须能通过 schemas/ 校验。

    这是"文档即规格"的硬约束:示例与 schema 不允许各说各话。
    """

    def test_examples_validate(self):
        ex = doc_examples()
        self.assertEqual(len(ex), 9, f"03 应含 9 个 JSON 示例,实际解析到 {sorted(ex)}")
        problems = []
        for title, instance in ex.items():
            schema = load(NAME_MAP[title])
            for e in validate(instance, schema, f"$[{title}]"):
                problems.append(e)
        if problems:
            self.fail(
                "docs/03 的示例与 schemas/ 不一致(Sprint 1 阻塞项,需架构师裁决改哪一侧):\n  "
                + "\n  ".join(problems)
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
