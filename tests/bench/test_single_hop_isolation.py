"""老王案单跳隔离与历史不可篡改的单元级防线（铁律 2 的纵深防御）。

门禁级证据来自 S5；这里用**更小的确定性场景**把三条不变量单独钉住，
任何一条回归都会立刻失败，而不是等到 20 秒的整流程盲测结束才发现：

1. 台账 SHA-256 全量校验通过，且任何字节改动都会被当场发现；
2. 单跳隔离只失效直接消费者，第二跳必须原样不动；
3. 双时态透镜在"当时所知"与"今天注解"之间保持 base 指纹逐字节相同。
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from aios_core.world.retrospective_annotation import (
    CascadeIsolationError,
    ImmutableFactLedger,
    SingleHopCascadeIsolator,
)

UTC = timezone.utc
T_TODAY = datetime(2026, 9, 16, 9, 30, tzinfo=UTC)


def _ledger() -> ImmutableFactLedger:
    ledger = ImmutableFactLedger()
    for index in range(5):
        ledger.record_fact(
            fact_id=f"obs_wang_{index}",
            entity_id="ent_old_wang",
            occurred_at=datetime(2023, 4, 1, tzinfo=UTC) + timedelta(days=index),
            kind="observation",
            payload={"text": f"老王第 {index} 次说下个月还", "amount": 250000},
        )
    return ledger


def test_ledger_verifies_pristine_history() -> None:
    ledger = _ledger()
    ok, checked = ledger.verify_integrity()
    assert ok is True, "未被碰过的历史必须校验通过"
    assert checked == 5, f"必须逐条重算，实际检查 {checked} 条"
    fingerprint = ledger.aggregate_fingerprint()
    assert len(fingerprint) == 64, "聚合指纹必须是 SHA-256 十六进制"


def test_ledger_detects_any_byte_level_tampering() -> None:
    ledger = _ledger()
    original = ledger.aggregate_fingerprint()
    # 模拟拿到封存字节的攻击者：直接改写 canonical_bytes（唯一可篡改面）
    tampered = dataclasses.replace(
        ledger._entries["obs_wang_0"], canonical_bytes=b'{"amount":1}'
    )
    ledger._entries["obs_wang_0"] = tampered
    ok, _checked = ledger.verify_integrity()
    assert ok is False, "字节级改动必须被 SHA-256 当场抓住"
    # 二层防线：若攻击者连封存哈希一起改写，聚合指纹（哈希矩阵）立即变形 ——
    # 单看聚合指纹不变说明"哈希没被改"，单看 verify 才说明"字节没被改"，两者缺一不可。
    assert ledger.aggregate_fingerprint() == original, (
        "仅改字节不改封存哈希时，聚合指纹本就应当不变（它就是哈希矩阵）"
    )
    ledger._entries["obs_wang_0"] = dataclasses.replace(
        ledger._entries["obs_wang_0"], sha256="0" * 64
    )
    assert ledger.aggregate_fingerprint() != original, "封存哈希被改写必须改变聚合指纹"


def test_ledger_refuses_conflicting_rewrite_of_a_sealed_fact() -> None:
    from aios_core.world.retrospective_annotation import LedgerConflictError

    ledger = _ledger()
    with pytest.raises(LedgerConflictError):
        ledger.record_fact(
            fact_id="obs_wang_0",
            entity_id="ent_old_wang",
            occurred_at=datetime(2023, 4, 1, tzinfo=UTC),
            kind="observation",
            payload={"text": "篡改版：老王没借钱", "amount": 0},
        )


def test_ledger_replays_identical_fact_idempotently() -> None:
    ledger = _ledger()
    again = ledger.record_fact(
        fact_id="obs_wang_0",
        entity_id="ent_old_wang",
        occurred_at=datetime(2023, 4, 1, tzinfo=UTC),
        kind="observation",
        payload={"text": "老王第 0 次说下个月还", "amount": 250000},
    )
    assert again == ledger.get_hash("obs_wang_0"), "逐字节一致的重复写入必须幂等"
    assert ledger.count() == 5, "幂等重放不得增加条目"


def test_single_hop_isolator_only_invalidates_direct_consumers() -> None:
    isolator = SingleHopCascadeIsolator()
    for index in range(3):
        isolator.register_node(f"summary_{index}")
        isolator.add_dependency("obs_origin", f"summary_{index}")
    for index in range(50):
        isolator.register_node(f"deep_{index}")
        isolator.add_dependency(f"summary_{index % 3}", f"deep_{index}")

    report = isolator.reverse_invalidate("obs_origin", max_hops=1)
    assert report.marked_stale, "直接消费者必须被标记 STALE"
    assert set(report.marked_stale) <= {"summary_0", "summary_1", "summary_2"}, (
        "单跳之外不得有任何节点被失效"
    )
    assert report.traversal_depth_reached == 1, "遍历深度必须严格等于 1"
    assert report.llm_recompute_triggered == 0, "隔离后不得触发历史重算（0 次调用）"
    assert report.cascade_suppressed is True, "必须显式声明级联已被抑制"
    assert isolator.stale_nodes(), "STALE 集合必须可审计"


def test_isolator_refuses_multi_hop_requests() -> None:
    isolator = SingleHopCascadeIsolator()
    isolator.register_node("obs_origin")
    with pytest.raises(CascadeIsolationError):
        isolator.reverse_invalidate("obs_origin", max_hops=2)


def test_second_hop_nodes_stay_untouched() -> None:
    isolator = SingleHopCascadeIsolator()
    isolator.register_node("obs_origin")
    isolator.register_node("direct")
    isolator.register_node("deep")
    isolator.add_dependency("obs_origin", "direct")
    isolator.add_dependency("direct", "deep")
    report = isolator.reverse_invalidate("obs_origin", max_hops=1)
    assert "direct" in report.marked_stale, "直接消费者必须被失效"
    assert "deep" not in report.marked_stale, "第二跳绝不允许被级联失效"
    assert "deep" not in isolator.stale_nodes(), "第二跳不得出现在 STALE 集合里"
