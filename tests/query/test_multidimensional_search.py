"""AIOS 3.0 多维心智搜索底座与操作总线集成测试 (Multidimensional Search Tests).

贯彻最高宪法第二十章与第二十四章：
1. 验证按多维属性（dim_health, dim_finance, dim_social）精准过滤；
2. 验证今天外挂注记（RetrospectiveAnnotation）自动同步并高权重置顶召回；
3. 验证毫秒级延迟 (<= 20ms) 与极简 Token 封套 (<= 150 tokens)；
4. 验证 WorldOperatorSuite.search 原语的原生无缝驱动。
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
import pytest

from aios_core.contracts.enums import ObjectType, SourceClass
from aios_core.contracts.ids import new_object_id, new_operation_id
from aios_core.contracts.models import (
    Entity,
    Observation,
    TemporalExtent,
)
from aios_core.contracts.operations import OperationRequest
from aios_core.operations.world_operator import WorldOperatorSuite
from aios_core.query.search import MultidimensionalSearchEngine
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc
T0 = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)


@pytest.fixture
def test_world():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = SQLiteWorldStore(path)

    # 1. 实体
    ent_me = Entity(
        object_id="ent_me",
        subject_id="user_1",
        revision=1,
        entity_kind="person",
        canonical_name="用户本人",
        occurred=TemporalExtent.point(T0),
        learned_at=T0,
        recorded_at=T0,
        created_by="test",
    )
    ent_wang = Entity(
        object_id="ent_wang",
        subject_id="user_1",
        revision=1,
        entity_kind="person",
        canonical_name="老王",
        aliases=["王哥", "王建国"],
        occurred=TemporalExtent.point(T0),
        learned_at=T0,
        recorded_at=T0,
        created_by="test",
    )

    # 2. 多维观测数据流
    # 健康维
    obs_hr = Observation(
        object_id="obs_heart_rate_1",
        subject_id="user_1",
        revision=1,
        source_kind="biometrics",
        modality="text",
        value="早晨静息心率115次/分，频发室性早搏，体感心慌胸闷。",
        occurred=TemporalExtent.point(T0),
        learned_at=T0,
        recorded_at=T0,
        created_by="test",
    )
    # 财务维
    obs_loan = Observation(
        object_id="obs_wang_loan_contract",
        subject_id="user_1",
        revision=1,
        source_kind="transaction",
        modality="text",
        value="转账借款给老王50万元，约定半年后归还本金并支付利息。",
        occurred=TemporalExtent.point(T0),
        learned_at=T0,
        recorded_at=T0,
        created_by="test",
    )
    # 工作维
    obs_work = Observation(
        object_id="obs_code_overtime",
        subject_id="user_1",
        revision=1,
        source_kind="work_log",
        modality="text",
        value="在公司通宵加班编写分布式调度器，凌晨02:30提交代码。",
        occurred=TemporalExtent.point(T0),
        learned_at=T0,
        recorded_at=T0,
        created_by="test",
    )

    op = OperationRequest(
        operation_id=new_operation_id(),
        operation_name="init.test",
        expected_world_revision=store.current_world_revision(),
        reason="Init multidimensional fixtures",
        idempotency_key="init_key",
        source_class=SourceClass.AI_COGNITION,
    )
    store.commit([ent_me, ent_wang, obs_hr, obs_loan, obs_work], op)

    suite = WorldOperatorSuite(store)
    yield suite, store

    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


def test_multidimensional_search_by_dimension(test_world):
    suite, store = test_world

    # 1. 仅按 dim_health 维度过滤
    t0 = time.perf_counter()
    health_hits = suite.search.query(dimension="dim_health")
    lat_ms = (time.perf_counter() - t0) * 1000.0

    assert len(health_hits) >= 1
    assert health_hits[0]["object_id"] == "obs_heart_rate_1"
    assert health_hits[0]["dimension"] == "dim_health"
    assert lat_ms <= 20.0  # 毫秒级极速响应

    # 2. 仅按 dim_finance 维度过滤
    finance_hits = suite.search.query(dimension="dim_finance")
    assert len(finance_hits) >= 1
    assert finance_hits[0]["object_id"] == "obs_wang_loan_contract"
    assert finance_hits[0]["dimension"] == "dim_finance"


def test_search_with_today_retrospective_annotation(test_world):
    suite, store = test_world

    # 今天在 T_now 发现老王是骗子，挂载外挂解释注记
    t_today = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    anno = suite.cognition.record_realization_today(
        target_object_id="obs_wang_loan_contract",
        target_object_type=ObjectType.OBSERVATION,
        reinterpretation_claim="北京市朝阳区法院判决生效：老王犯合同诈骗罪，定性为诈骗款！",
        is_invalidating=True,
        now=t_today,
    )

    # 搜索 "老王 诈骗"
    t0 = time.perf_counter()
    page = suite.search.search_mind(keywords=["老王", "诈骗"])
    lat_ms = (time.perf_counter() - t0) * 1000.0

    assert page.status == "ok"
    assert len(page.hits) >= 1
    # 注记自动被检索召回并置顶
    top_hit = page.hits[0]
    assert top_hit.is_annotation is True
    assert "合同诈骗罪" in top_hit.excerpt
    assert top_hit.score >= 10
    assert lat_ms <= 20.0

    # 验证 Token 封套极简性 (<= 150 Tokens)
    assert page.total_estimated_tokens <= 150


def test_entity_alias_disambiguation_in_mind_search(test_world):
    suite, store = test_world

    # 别名 "王建国" 在实体表中注册为 "老王" 的别名
    hits = suite.search.query(keywords=["王建国", "借款"])
    assert len(hits) >= 1
    assert hits[0]["object_id"] == "obs_wang_loan_contract"


def test_idle_catch_up_still_syncs_today_annotation(test_world):
    """M5-001 验收：索引追平世界后新挂的注记，catch_up() 必须独立同步。

    注记是「今天挂的解释图层」，不产生 world_revision。若注记同步被绑在
    「有新 revision 才执行」的路径上，稳态下今天挂的标签要等下一次世界提交
    才能召回——这条用例把该退化钉死。
    """

    suite, store = test_world
    engine = suite.search.index
    assert engine.catch_up() >= 1, "首次追平应索引到世界本体对象"
    rev_before = store.current_world_revision()

    t_today = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    anno = suite.cognition.record_realization_today(
        target_object_id="obs_wang_loan_contract",
        target_object_type=ObjectType.OBSERVATION,
        reinterpretation_claim="北京市朝阳区法院判决生效：老王犯合同诈骗罪，定性为诈骗款，可依法追偿。",
        is_invalidating=True,
        now=t_today,
    )
    assert store.current_world_revision() == rev_before, "挂注记不得改写历史与世界版本"

    # 世界无新 revision：catch_up 行数为 0，但注记必须已经进投影
    assert suite.search.catch_up() == 0
    assert suite.search.sync_annotations() == 0, "注记指纹未变化时严禁重复写投影"

    page = suite.search.search_mind(keywords=["老王", "诈骗"])
    assert page.status == "ok"
    assert anno.annotation_id in [h.object_id for h in page.hits], "今天挂的注记必须今天可召回"
    assert page.hits[0].is_annotation is True
    assert "合同诈骗罪" in page.hits[0].excerpt
    assert page.total_estimated_tokens <= 150

    by_anno = suite.search.search_by_annotation(anno.annotation_id)
    assert anno.annotation_id in [h.object_id for h in by_anno.hits]

    # 注记在时空面上必须带维度（dimension 列落值，供按维度正交检索）
    with sqlite3.connect(store.db_path) as conn:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(search_occurred)")]
        assert "dimension" in cols
        row = conn.execute(
            "SELECT dimension, subject_id FROM search_occurred WHERE object_id=?",
            (anno.annotation_id,),
        ).fetchone()
    assert row is not None and row[0], "注记必须带维度落 search_occurred"


def test_annotation_recall_is_complete_and_co_search_stays_compatible(test_world):
    """M5-001 验收：注记 100% 召回，且 co_search（共现）接口保持兼容。"""

    suite, store = test_world
    t_today = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    plan = [
        ("obs_wang_loan_contract", "老王借款合同定性为诈骗款，进入资产追偿程序。"),
        ("obs_heart_rate_1", "连续通宵加班与频发室性早搏存在因果关联，须停工复查。"),
        ("obs_code_overtime", "该次通宵加班是早搏诱因，工时记录可作证据指针。"),
    ]
    annos = [
        suite.cognition.record_realization_today(
            target_object_id=target,
            target_object_type=ObjectType.OBSERVATION,
            reinterpretation_claim=claim,
            now=t_today,
        )
        for target, claim in plan
    ]
    suite.search.catch_up()

    recalled = 0
    for anno in annos:
        page = suite.search.search_by_annotation(anno.annotation_id)
        if anno.annotation_id in [h.object_id for h in page.hits]:
            recalled += 1
    assert recalled == len(annos), f"注记召回必须 100%，实测 {recalled}/{len(annos)}"

    # co_search 兼容：共现检索仍按原语义返回，且诚实携带水位
    page = suite.search.co_search(["老王", "借款"])
    assert page.status in {"ok", "stale_index"}
    assert page.world_revision >= page.index_watermark
    assert "obs_wang_loan_contract" in [h.object_id for h in page.hits]

    # 检索入口一致：search_mind 与 query 摘要切片同源
    rows = suite.search.query(keywords=["老王", "诈骗"])
    assert rows and rows[0]["dimension"] == "dim_finance"
    assert rows[0]["estimated_tokens"] <= 150
