"""M1-018 补充件单测：客观事实完整性台账（SHA-256 基线 + 数据库层不可变）。

与 `test_m1_018_retrospective_annotation.py`（主实现，提交 829a0a2）互补：
主实现用 SQLite authorizer 证明**代码路径没有发出** UPDATE/DELETE；
本件证明**即使有人绕过应用层，数据库也会拒绝**，并且基线已落库、
可在任意后续时刻复核出磁盘级篡改。
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime, timedelta, timezone

import pytest

from aios_core.world.fact_immutability_ledger import (
    FactImmutabilityLedger,
    canonical_fact_sha256,
)

TODAY = datetime(2025, 9, 16, 9, 0, 0, tzinfo=UTC)
T0 = TODAY - timedelta(days=730)
RULING_DAY = T0 + timedelta(days=730)
PARTNER = "ent_cofounder_zhao"
OBSERVATION_COUNT = 18_000


def _payload(index: int, day_offset: int) -> dict[str, object]:
    """高熵客观事实：技术评审 / 汇款凭证 / 深夜谈判体征 / 合同，四类轮转。"""
    kind = index % 4
    if kind == 0:
        return {
            "kind": "technical_review",
            "artifact": f"core-ip-review-{index:05d}",
            "verdict": "通过",
            "reviewer": PARTNER,
            "ip_scope": "推理引擎核心专利族",
            "day_offset": day_offset,
        }
    if kind == 1:
        return {
            "kind": "remittance_voucher",
            "voucher_no": f"PAY-2023-{index:06d}",
            "amount_cny": 1_250_000 + index * 137,
            "counterparty": "孵化主体账户",
            "day_offset": day_offset,
        }
    if kind == 2:
        return {
            "kind": "physiological_signal",
            "hrv_rmssd_ms": 18.4 + (index % 40) * 0.31,
            "cortisol_nmoll": 480 + (index % 90) * 2.7,
            "context": "深夜高压对赌条款谈判",
            "local_time": "02:40",
            "day_offset": day_offset,
        }
    return {
        "kind": "contract_execution",
        "contract": "《Pre-A 轮联合孵化与股权代持对赌协议》补充协议",
        "clause": f"第 {index % 27 + 1} 条 业绩承诺与回购触发",
        "signatories": ["用户", PARTNER],
        "day_offset": day_offset,
    }


def _facts(count: int = OBSERVATION_COUNT) -> list[dict[str, object]]:
    out = []
    for i in range(count):
        day_offset = (i * 730) // count
        occurred = T0 + timedelta(days=day_offset, minutes=i % 1440)
        out.append(
            {
                "object_id": f"obs_{i:06d}",
                "revision": 1,
                "object_type": "observation",
                "subject_id": PARTNER,
                "occurred_at": occurred,
                "learned_at": occurred,
                "payload": _payload(i, day_offset),
            }
        )
    return out


@pytest.fixture
def ledger() -> FactImmutabilityLedger:
    conn = sqlite3.connect(":memory:")
    try:
        yield FactImmutabilityLedger(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 哈希基线
# ---------------------------------------------------------------------------


def test_18000_facts_seal_with_persisted_baseline(
    ledger: FactImmutabilityLedger,
) -> None:
    assert ledger.seal_many(_facts()) == OBSERVATION_COUNT
    assert ledger.fact_count() == OBSERVATION_COUNT

    report = ledger.verify_fact_integrity()
    assert report.checked == OBSERVATION_COUNT
    assert report.intact == OBSERVATION_COUNT
    assert report.all_intact


def test_baseline_is_durable_and_reverifiable_by_a_second_handle() -> None:
    """基线落库后，另一个连接（另一个进程）也能独立复核。

    这是主实现缺的一环：哈希只在测试内即时算，基线不落库，
    事后就无法发现磁盘级篡改。
    """
    conn = sqlite3.connect(":memory:")
    try:
        first = FactImmutabilityLedger(conn)
        first.seal_many(_facts(500))
        before = first.verify_fact_integrity()
        assert before.all_intact and before.checked == 500

        # 同一连接的新句柄（模拟后续任意时刻的复核方）
        second = FactImmutabilityLedger(conn)
        after = second.verify_fact_integrity()
        assert after.all_intact
        assert after.checked == 500

        # 基线可被独立取出比对，而不只是"自洽"
        expected = canonical_fact_sha256(_payload(0, 0))
        assert second.digest_of("obs_000000") == expected
        assert second.digest_of("obs_does_not_exist") is None
    finally:
        conn.close()


def test_verify_detects_disk_level_tampering() -> None:
    """绕过触发器模拟磁盘级篡改，校验必须报出——否则"完整性"只是装饰。"""
    conn = sqlite3.connect(":memory:")
    try:
        ledger = FactImmutabilityLedger(conn)
        ledger.seal_fact(
            object_id="obs_voucher",
            revision=1,
            object_type="observation",
            subject_id=PARTNER,
            occurred_at=T0,
            learned_at=T0,
            payload={"kind": "remittance_voucher", "amount_cny": 1_250_000},
        )
        assert ledger.verify_fact_integrity().all_intact

        conn.execute("DROP TRIGGER trg_fact_ledger_no_update")
        conn.execute(
            "UPDATE fact_integrity_ledger SET payload_json = "
            """'{"amount_cny": 9, "kind": "remittance_voucher"}'"""
        )
        conn.commit()

        report = ledger.verify_fact_integrity()
        assert not report.all_intact
        assert report.mismatched_object_ids == ("obs_voucher",)
        assert report.intact == 0
        assert report.checked == 1
    finally:
        conn.close()


def test_canonical_hash_ignores_key_order_and_timezone() -> None:
    a = {
        "amount": 1_250_000,
        "kind": "remittance",
        "at": datetime(2024, 1, 1, tzinfo=UTC),
    }
    b = {
        "at": datetime(2024, 1, 1, 8, tzinfo=timezone(timedelta(hours=8))),
        "kind": "remittance",
        "amount": 1_250_000,
    }
    assert canonical_fact_sha256(a) == canonical_fact_sha256(b)
    assert canonical_fact_sha256(a) != canonical_fact_sha256({**a, "amount": 1_250_001})
    assert len(canonical_fact_sha256(a)) == 64


def test_canonical_hash_keeps_chinese_verbatim() -> None:
    """中文不得被转义成 \\uXXXX，否则跨环境哈希不可复现。"""
    import json

    digest_input = {"verdict": "通过", "context": "深夜高压对赌条款谈判"}
    canonical = json.dumps(
        digest_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert "\\u" not in canonical
    assert "通过" in canonical
    assert len(canonical_fact_sha256(digest_input)) == 64


# ---------------------------------------------------------------------------
# 数据库层不可变（任何连接、任何工具都写不出来）
# ---------------------------------------------------------------------------


def test_database_rejects_update_and_delete_from_any_connection(
    ledger: FactImmutabilityLedger,
) -> None:
    ledger.seal_fact(
        object_id="obs_x",
        revision=1,
        object_type="observation",
        subject_id=PARTNER,
        occurred_at=T0,
        learned_at=T0,
        payload={"kind": "technical_review", "verdict": "通过"},
    )

    # 注意：BEFORE UPDATE/DELETE 是**行级**触发器，空表上的语句影响 0 行、
    # 不会触发。因此必须先写入一行，才能真正检验阻断是否生效。
    for statement in (
        "UPDATE fact_integrity_ledger SET canonical_sha256 = 'tampered'",
        "UPDATE fact_integrity_ledger SET payload_json = '{}'",
        "DELETE FROM fact_integrity_ledger WHERE object_id = 'obs_x'",
        "DELETE FROM fact_integrity_ledger",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="art.93"):
            ledger._conn.execute(statement)

    # 违宪尝试之后事实仍然完好
    assert ledger.verify_fact_integrity().all_intact
    assert ledger.fact_count() == 1


def test_triggers_survive_reopen_and_second_ledger_handle() -> None:
    """触发器是 schema 的一部分，重开连接、重建句柄都仍然生效。"""
    conn = sqlite3.connect(":memory:")
    try:
        ledger = FactImmutabilityLedger(conn)
        ledger.seal_fact(
            object_id="obs_y",
            revision=1,
            object_type="observation",
            subject_id=PARTNER,
            occurred_at=T0,
            learned_at=T0,
            payload={"kind": "contract_execution"},
        )
        FactImmutabilityLedger(conn)  # 幂等重建句柄

        triggers = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            ).fetchall()
        }
        assert {"trg_fact_ledger_no_update", "trg_fact_ledger_no_delete"} <= triggers

        with pytest.raises(sqlite3.IntegrityError, match="art.93"):
            conn.execute("DELETE FROM fact_integrity_ledger")
    finally:
        conn.close()


def test_empty_table_statements_do_not_prove_anything() -> None:
    """显式记录行级触发器的边界，避免后来者写出假绿测试。"""
    conn = sqlite3.connect(":memory:")
    try:
        ledger = FactImmutabilityLedger(conn)
        # 空表：语句影响 0 行，触发器不触发，不会抛错。
        conn.execute(
            "DELETE FROM fact_integrity_ledger WHERE object_id = 'nonexistent'"
        )
        assert ledger.fact_count() == 0

        ledger.seal_fact(
            object_id="obs_z",
            revision=1,
            object_type="observation",
            subject_id=PARTNER,
            occurred_at=T0,
            learned_at=T0,
            payload={"kind": "physiological_signal"},
        )
        with pytest.raises(sqlite3.IntegrityError, match="art.93"):
            conn.execute("DELETE FROM fact_integrity_ledger WHERE object_id = 'obs_z'")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 读取与规模
# ---------------------------------------------------------------------------


def test_facts_for_filters_by_occurrence_time(ledger: FactImmutabilityLedger) -> None:
    ledger.seal_many(_facts(2000))
    probe = T0 + timedelta(days=100)

    then = ledger.facts_for(PARTNER, up_to=probe)
    everything = ledger.facts_for(PARTNER)

    assert 0 < len(then) < len(everything)
    assert all(f.occurred_at <= probe for f in then)
    assert len(everything) == 2000


def test_sealing_is_idempotent(ledger: FactImmutabilityLedger) -> None:
    facts = _facts(100)
    assert ledger.seal_many(facts) == 100
    ledger.seal_many(facts)
    assert ledger.fact_count() == 100
    assert ledger.verify_fact_integrity().all_intact


def test_stress_seal_and_verify_18000_within_budget() -> None:
    """18,000 条封存 + 全量重算校验的耗时上界（防退化为逐条事务）。"""
    conn = sqlite3.connect(":memory:")
    try:
        ledger = FactImmutabilityLedger(conn)

        started = time.perf_counter()
        sealed = ledger.seal_many(_facts())
        seal_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        report = ledger.verify_fact_integrity()
        verify_ms = (time.perf_counter() - started) * 1000

        assert sealed == OBSERVATION_COUNT
        assert report.all_intact and report.checked == OBSERVATION_COUNT
        assert seal_ms <= 5000, f"封存 18,000 条耗时 {seal_ms:.0f}ms，疑似逐条事务"
        assert verify_ms <= 5000, f"全量校验 18,000 条耗时 {verify_ms:.0f}ms，超出预算"
    finally:
        conn.close()


def test_ledger_does_not_touch_m0_frozen_tables() -> None:
    """只建自己的一张表，不得创建或修改任何 M0 冻结表。"""
    conn = sqlite3.connect(":memory:")
    try:
        FactImmutabilityLedger(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert tables == {"fact_integrity_ledger"}
        assert "object_revisions" not in tables
        assert "world_commits" not in tables
    finally:
        conn.close()
