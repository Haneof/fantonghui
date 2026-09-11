"""Sprint 1 Task 1 —— 架构边界可追溯性测试。

目标:任何一条 02 契约都必须能在 core/ 找到归属模块,任何新增契约若没登记就立刻失败。
这条机制的用途是让 07 的"架构审查"有据可依:出问题能指到"违反 docs/02 §N"。
"""
from __future__ import annotations

import importlib
import re
import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import schema_check as sc  # noqa: E402


class TestRuntimeSkeleton(unittest.TestCase):
    def test_all_contract_modules_importable(self):
        for name, home in sc.CONTRACT_HOME.items():
            mod = home[: -len(".py")].replace("/", ".")
            with self.subTest(contract=name):
                importlib.import_module(mod)

    def test_sprint1_runtimes_are_live(self):
        """Sprint 1 Task 2-8 覆盖的 Runtime 必须已实现(可实例化,不再抛 NotImplementedError)。"""
        live = [("core.perception.perception_runtime", "PerceptionRuntime"),
                ("core.event.event_runtime", "EventRuntime"),
                ("core.world.world_runtime", "WorldRuntime"),
                ("core.world.state_runtime", "StateRuntime"),
                ("core.world.entity_runtime", "EntityRuntime")]
        for mod_name, cls_name in live:
            with self.subTest(cls=cls_name):
                cls = getattr(importlib.import_module(mod_name), cls_name)
                self.assertTrue(cls.contract, f"{cls_name} 未声明契约来源")
                cls(tempfile.mkdtemp(prefix="aios-live-")) if cls_name != "StateRuntime" else cls()

    def test_out_of_sprint_runtimes_are_still_skeleton(self):
        """Sprint 2/3/4 的 Runtime 必须仍然拒绝被调用(09 禁止事项 3)。"""
        from tools import forbidden_scan as fs

        self.assertEqual(fs.check_skeleton_intact(), [], "有 Sprint 2/3/4 的骨架被提前实装了")

    def test_every_runtime_method_is_guarded(self):
        cls = getattr(importlib.import_module("core.attention.wake"), "WakeRuntime")
        with self.assertRaises(NotImplementedError):
            cls().classify()


class TestSpecConformance(unittest.TestCase):
    def test_contracts_numbered_contiguously_and_homed(self):
        sc.check_contracts_have_home()

    def test_core_layout_equals_layout_doc(self):
        sc.check_layout_matches_spec()

    def test_new_contract_without_home_fails_loudly(self):
        """伪造一条 §14 契约,必须失败 —— 证明检查不是空转。"""
        fake = sc.contracts() + [(14, "Telepathy Runtime")]
        with mock.patch.object(sc, "contracts", return_value=fake):
            with self.assertRaises(AssertionError) as ctx:
                sc.check_contracts_have_home()
        self.assertIn("Telepathy Runtime", str(ctx.exception))

    def test_permitted_module_list_is_not_dangling(self):
        """登记了归属却没建文件,也要失败。"""
        with mock.patch.dict(sc.CONTRACT_HOME, {"AI Runtime": "core/ai/does_not_exist.py"}):
            with self.assertRaises(AssertionError):
                sc.check_contracts_have_home()


class TestLeaseBudgetConstants(unittest.TestCase):
    def test_budgets_match_contract_doc(self):
        src = sc.read("02_RUNTIME_CONTRACTS.md")
        table = dict(re.findall(r"`(\w+_WAKE)`: (\d+)ms", src))
        self.assertEqual(
            table, {"MICRO_WAKE": "2000", "AI_WAKE": "30000", "EMERGENCY_WAKE": "60000"},
            "02 §8 的租约时长与代码常量不一致",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
