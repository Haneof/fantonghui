"""CAM 闸门：宪法第 114 条验收项 ↔ schemas/constitution_acceptance.py 全量双向映射。

规则（对应 R4 修改案 R4-05 / 设计书 §1.4 "一矩阵"）：
1. 宪法第 114 条出现的每一个验收编号必须在账本中有映射 —— 缺一项 = 红灯；
2. 账本不得夹带宪法不认识的编号（R4-* 例外，且必须保持 proposed_pending_R4 待批准）；
3. status=contract_frozen 的条目，引用的测试文件必须真实存在 —— 防止"冻结了个寂寞"；
4. 模块编号只允许 C01–C15（以《工程重构设计书 R4》§2.1 为唯一账本）；
5. 宪法文本改动新增验收行而未入账本时，本测试随 CI 立即报警。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path



REPO_ROOT = Path(__file__).resolve().parents[2]
CHARTER = REPO_ROOT / "docs" / "constitution" / "AIOS核心系统宪法v3.0.md"
LEDGER_PATH = REPO_ROOT / "schemas" / "constitution_acceptance.py"

_ID_RE = re.compile(r"^\|\s*((?:A\d{2})|(?:R[123]-\d{2})|(?:V3-\d{2}))\s*\|", re.MULTILINE)


def _load_ledger():
    spec = importlib.util.spec_from_file_location("constitution_acceptance", LEDGER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _charter_acceptance_ids() -> list[str]:
    text = CHARTER.read_text(encoding="utf-8")
    start = text.index("### 第一百一十四条")
    end = text.index("## 第三十三章")
    return _ID_RE.findall(text[start:end])


def test_charter_section_is_parseable():
    """46 项硬校验：解析逻辑若被排版改动破坏，先在这里失败而不是静默放过。"""
    ids = set(_charter_acceptance_ids())
    assert len(ids) == 46, f"第 114 条应解析出 46 项验收，实际 {len(ids)} 项: {sorted(ids)}"


def test_every_charter_id_is_mapped():
    ledger = _load_ledger()
    mapped = {entry["id"] for entry in ledger.CONSTITUTION_ACCEPTANCE}
    missing = sorted(set(_charter_acceptance_ids()) - mapped)
    assert not missing, f"以下宪法验收项缺失 CAM 映射: {missing}"


def test_no_unauthorized_extra_ids():
    ledger = _load_ledger()
    charter = set(_charter_acceptance_ids())
    extras = {entry["id"] for entry in ledger.CONSTITUTION_ACCEPTANCE} - charter
    allowed = {f"R4-{i:02d}" for i in range(1, 10)}
    assert extras <= allowed and extras == allowed, (
        f"账本 R4 提案集必须恰为 R4-01..R4-09（修改案批准后转正），实际差异: {sorted(extras ^ allowed)}"
    )


def test_ledger_has_no_duplicate_ids():
    ledger = _load_ledger()
    ids = [entry["id"] for entry in ledger.CONSTITUTION_ACCEPTANCE]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    assert not dups, f"重复验收编号: {dups}"


def test_entry_schema_and_modules():
    ledger = _load_ledger()
    for entry in ledger.CONSTITUTION_ACCEPTANCE:
        for field in ("id", "title", "articles", "module", "milestone", "status"):
            assert entry.get(field), f"{entry.get('id', '?')} 缺字段 {field}"
        assert entry["title"].strip(), f"{entry['id']} 标题为空"
        assert entry["articles"], f"{entry['id']} 未引用宪法条款"
        bad = [m for m in entry["module"] if m not in ledger.LEDGER_MODULES]
        assert not bad, f"{entry['id']} 使用账本外模块编号 {bad}（唯一账本: C01–C15, 见设计书 §2.1）"
        assert entry["status"] in {
            "contract_frozen", "planned", "proposed_pending_R4"
        }, f"{entry['id']} 非法 status: {entry['status']}"


def test_contract_frozen_tests_actually_exist():
    ledger = _load_ledger()
    for entry in ledger.CONSTITUTION_ACCEPTANCE:
        if entry["status"] == "contract_frozen":
            assert entry["tests"], f"{entry['id']} 声称契约冻结但未引用任何真实测试"
            for rel in entry["tests"]:
                path = REPO_ROOT / rel
                assert path.is_file(), f"{entry['id']} 引用不存在的测试: {rel}"
        elif not entry["tests"]:
            assert entry.get("planned"), f"{entry['id']} 既无测试也未声明计划落点（禁止口号条目）"


def test_r4_items_are_pending_until_amendment_ratified():
    ledger = _load_ledger()
    for entry in ledger.CONSTITUTION_ACCEPTANCE:
        if entry["id"].startswith("R4-"):
            assert entry["status"] == "proposed_pending_R4", (
                f"{entry['id']} 提前转正：R4 修改案未经 architect/chief 签核，"
                "批准后将逐条转 planned 并把 planned 路径替换为真实 tests"
            )
