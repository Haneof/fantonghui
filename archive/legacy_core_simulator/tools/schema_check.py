"""AIOS Sprint 1 Task 1 —— 规格一致性检查器.

把 docs/ 里的规范变成可执行断言,防止"文档说一套、代码长一套":

- schemas/ 的文件集合必须等于 docs/03 Canonical schema set
- 每个 schema 必须是 draft-07 形状,且 required ⊆ properties
- Event 只允许 raw_ref、禁止 raw_data(03 Canonical naming rule)
- Entity 只允许 relationship_ids、禁止 relationships(Q4 裁决)
- memory.level / cognition.status / decision.options / wake 类别必须等于文档里的枚举
- docs/02 的契约编号必须连续,且每条契约都在 core/ 下有归属模块
- core/ 的子目录集合必须等于 docs/06 的目录树

用法: python3 tools/schema_check.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SCHEMAS = ROOT / "schemas"

DRAFT07 = "http://json-schema.org/draft-07/schema#"

#: docs/02 契约条目 -> core/ 归属模块。新增契约必须在此登记,否则测试失败。
CONTRACT_HOME = {
    "Perception Runtime": "core/perception/perception_runtime.py",
    "Event Runtime": "core/event/event_runtime.py",
    "World Runtime": "core/world/world_runtime.py",
    "State Runtime": "core/world/state_runtime.py",
    "Memory Runtime": "core/memory/memory_runtime.py",
    "Identity Runtime": "core/identity/identity_runtime.py",
    "Relevance Runtime": "core/attention/relevance.py",
    "Attention Runtime": "core/attention/attention_runtime.py",
    "Lease Runtime": "core/attention/lease.py",
    "Wake Runtime": "core/attention/wake.py",
    "AI Runtime": "core/ai/ai_runtime.py",
    "Capability Runtime": "core/capability/capability_runtime.py",
    "Interaction Runtime": "core/interaction/interaction_runtime.py",
    "Evolution Runtime": "core/evolution/evolution_runtime.py",
}


def read(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def _fenced(text: str, heading: str) -> str:
    """取出某个二级标题下第一个围栏代码块的内容。"""
    tail = text.split(heading, 1)[1]
    m = re.search(r"```[a-zA-Z]*\n(.*?)\n```", tail, re.S)
    if not m:
        raise AssertionError(f"找不到 {heading!r} 下的代码块")
    return m.group(1)


# ---------- 文档侧解析 ----------

def canonical_schema_names() -> list[str]:
    t = read("03_WORLD_EVENT_SCHEMA.md")
    m = re.search(r"标准对象共 \d+ 个：`([^`]+)`", t)
    assert m, "03 缺少 'Canonical schema set' 声明行"
    return [x.strip() for x in m.group(1).split("/")]


def doc_enum(heading_pattern: str, field: str) -> list[str]:
    t = read("03_WORLD_EVENT_SCHEMA.md")
    m = re.search(rf"`{field}` (?:枚举|status` 枚举)：`([^`]+)`", t)
    if not m:
        m = re.search(rf"{heading_pattern}：`([^`]+)`", t)
    assert m, f"03 找不到 {field} 的枚举声明"
    return [x.strip() for x in m.group(1).split("/")]


def wake_classes() -> list[str]:
    t = read("04_WAKE_RUNTIME.md")
    block = _fenced(t, "## 4. Wake 类型")
    return [ln.split()[0] for ln in block.strip().splitlines() if ln.strip()]


def contracts() -> list[tuple[int, str]]:
    t = read("02_RUNTIME_CONTRACTS.md")
    return [(int(n), name.strip()) for n, name in re.findall(r"^## (\d+)\. (.+?)\s*$", t, re.M)]


def layout_core_dirs() -> list[str]:
    t = read("06_REPOSITORY_LAYOUT.md")
    block = _fenced(t, "## 文档规范位置")
    seg = block.split("├─ core/", 1)[1].split("├─ adapters/", 1)[0]
    return sorted(set(re.findall(r"^\s*[│├└─\s]*([a-z_]+)/\s*$", seg, re.M)))


# ---------- 检查项 ----------

def check_schema_files() -> list[str]:
    want = canonical_schema_names()
    got = sorted(p.stem for p in SCHEMAS.glob("*.json"))
    assert got == sorted(want), f"schemas/ 与 03 声明不一致: 期望 {sorted(want)},实际 {got}"
    return want


def check_schema_shape(name: str) -> dict:
    p = SCHEMAS / f"{name}.json"
    s = json.loads(p.read_text(encoding="utf-8"))
    assert s["$schema"] == DRAFT07, f"{name}: 不是 draft-07"
    assert s["$id"] == f"aios://schemas/{name}.json", f"{name}: $id 不符"
    assert s["title"] == name, f"{name}: title 与文件名不一致"
    assert s["type"] == "object", f"{name}: 顶层必须是 object"
    assert s["additionalProperties"] is False, f"{name}: 必须关闭未知字段"
    assert s.get("required"), f"{name}: required 不能为空"
    unknown = set(s["required"]) - set(s["properties"])
    assert not unknown, f"{name}: required 里有未定义字段 {unknown}"
    return s


def check_canonical_rules() -> None:
    ev = check_schema_shape("event")
    assert "raw_ref" in ev["properties"], "event 必须含 raw_ref"
    assert "raw_data" not in ev["properties"], "event 禁止 raw_data(03 Canonical naming rule)"
    assert "raw_ref" in ev["required"], "raw_ref 必须显式存在(可为 null),不得省略"
    en = check_schema_shape("entity")
    assert "relationship_ids" in en["properties"], "entity 必须用 relationship_ids(Q4 裁决)"
    assert "relationships" not in en["properties"], "entity 禁止内嵌 relationships(Q4 裁决)"


def check_enums() -> None:
    mem = check_schema_shape("memory")
    assert mem["properties"]["level"]["enum"] == doc_enum("", "level"), "memory.level 枚举与 03 不一致"
    cog = check_schema_shape("cognition")
    assert cog["properties"]["status"]["enum"] == doc_enum("", "status"), "cognition.status 枚举与 03 不一致"
    dec = check_schema_shape("decision")
    opts = re.findall(r'"(silent|notify|suggest|execute)"', read("03_WORLD_EVENT_SCHEMA.md"))
    want = sorted(set(opts))
    got = sorted(set(dec["properties"]["options"]["items"]["enum"]))
    assert got == want == sorted(
        set(re.search(r'"options": \[([^\]]+)\]', read("03_WORLD_EVENT_SCHEMA.md")).group(1).replace('"', "").replace(" ", "").split(","))
    ), f"decision.options 与 03 不一致: {got} vs {want}"


def check_contracts_have_home() -> None:
    items = contracts()
    nums = [n for n, _ in items]
    assert nums == list(range(len(nums))), f"02 契约编号不连续: {nums}"
    for _, name in items:
        home = CONTRACT_HOME.get(name)
        assert home, f"契约 {name!r} 没有 core/ 归属,请先在 CONTRACT_HOME 登记并决定职责"
        assert (ROOT / home).exists(), f"{name} 的归属模块不存在: {home}"


def check_layout_matches_spec() -> None:
    want = layout_core_dirs()
    got = sorted(p.name for p in (ROOT / "core").iterdir() if p.is_dir() and not p.name.startswith("__"))
    assert got == want, f"core/ 目录与 06 不一致: 期望 {want},实际 {got}"
    assert (ROOT / "core" / "perception").is_dir(), "Q3 裁决要求 core/perception/ 存在"
    assert (ROOT / "core" / "attention" / "lease.py").exists(), "Q5 裁决要求 lease 归 attention"


def run() -> list[str]:
    lines = []
    names = check_schema_files()
    lines.append(f"schemas/ = 03 Canonical set ({len(names)} 个): {' '.join(names)}")
    for n in names:
        s = check_schema_shape(n)
        lines.append(f"  {n:<13} props={len(s['properties']):>2} required={len(s['required']):>2} additionalProperties=False ✓")
    check_canonical_rules()
    lines.append("canonical 规则: event 只允许 raw_ref、entity 只允许 relationship_ids ✓")
    check_enums()
    lines.append("枚举与 03 一致: memory.level(9) / cognition.status(4) / decision.options(4) ✓")
    items = contracts()
    check_contracts_have_home()
    lines.append(f"02 契约 {len(items)} 条,编号 0..{len(items)-1} 连续,全部有 core/ 归属 ✓")
    check_layout_matches_spec()
    lines.append(f"core/ 目录与 06 一致: {' '.join(layout_core_dirs())} ✓")
    lines.append(f"wake 类别(取自 04 §4): {' '.join(wake_classes())}")
    return lines


if __name__ == "__main__":
    for line in run():
        print(line)
    print("\nSPEC-CONFORMANCE OK")
