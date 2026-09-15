"""M1-012R 实体拓扑超链接四级网络穿透检索器 —— 单元测试。

验收对照（云端工单 / 4号 Agent 任务书）：
- [硬验收 1] 遍历深度达到 4 级时，检索耗时 <= 25ms（规模化图谱：60 锚点
  / 240 证据集 / 2880 观测）；
- [硬验收 2] 别名必须 100% 正确归一链接到主实体档案（含大小写、全角、
  空白污染、别名入口遍历），同名歧义绝不静默合并（V3 §36）；
- [红线探针] 查询层无 sqlite3 依赖、无模糊扫描语义（废除单表 LIKE 遍历）；
- [确定性] 同输入同输出（幂等重放）；指针索引不复制载荷（V3 §18）。
"""

from __future__ import annotations

import concurrent.futures
import pathlib

import pytest
from pydantic import ValidationError

from aios_core.query import (
    AliasAmbiguousError,
    EntityHyperlinkGraphTraverser,
    EntityNotRegisteredError,
    HyperlinkTraversalResult,
    InvalidTraversalDepthError,
    MalformedIdentifierError,
    normalize_alias,
)

MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "aios_core"
    / "query"
    / "hyperlink_traverser.py"
)


# ----------------------------------------------------------------------
# 测试图谱工厂
# ----------------------------------------------------------------------

def build_graph(
    traverser: EntityHyperlinkGraphTraverser,
    *,
    n_anchors: int = 3,
    evidence_per_anchor: int = 2,
    observations_per_evidence: int = 3,
    root_id: str = "ent_laowang_root",
    aliases: tuple[str, ...] = ("老王", "王叔", "隔壁老王"),
) -> dict[str, list[str]]:
    """构建 Entity→Anchor→EvidenceSet→Observation 四级指针图并返回层级清单。"""
    all_anchors: list[str] = []
    all_evidence: list[str] = []
    all_observations: list[str] = []
    for a in range(n_anchors):
        anchor_id = f"evt_{root_id}_{a:03d}"
        evidence_ids = [f"evs_{root_id}_{a:03d}_{e:03d}" for e in range(evidence_per_anchor)]
        for ev_index, evidence_id in enumerate(evidence_ids):
            observation_ids = [
                f"obs_{root_id}_{a:03d}_{ev_index:03d}_{o:03d}"
                for o in range(observations_per_evidence)
            ]
            traverser.register_evidence_links(evidence_id, observation_ids)
            all_observations.extend(observation_ids)
        traverser.register_anchor_links(anchor_id, evidence_ids)
        all_evidence.extend(evidence_ids)
        all_anchors.append(anchor_id)
    traverser.register_entity_link(root_id, list(aliases), all_anchors)
    return {
        "anchors": all_anchors,
        "evidence_sets": all_evidence,
        "observations": all_observations,
    }


# ----------------------------------------------------------------------
# 硬验收 1：深度 4 级穿透 <= 25ms
# ----------------------------------------------------------------------

def test_depth4_traversal_within_25ms_on_sized_graph() -> None:
    traverser = EntityHyperlinkGraphTraverser()
    levels = build_graph(
        traverser,
        n_anchors=60,
        evidence_per_anchor=4,
        observations_per_evidence=12,
    )
    assert len(levels["anchors"]) == 60
    assert len(levels["evidence_sets"]) == 240
    assert len(levels["observations"]) == 2880

    # 预热一次（解释器缓存/分支预测达标后的稳态查询时延才是用户时延）
    traverser.traverse_entity_network("ent_laowang_root", depth=4)

    runs = [
        traverser.traverse_entity_network("老王", depth=4) for _ in range(5)
    ]
    for result in runs:
        assert result.traversal_depth == 4
        assert result.traversal_ms <= 25.0, (
            f"depth-4 traversal took {result.traversal_ms}ms (> 25ms budget)"
        )
    # 稳态下远低于预算是设计预期：断言数量级余量，防止退化到临界值
    assert runs[-1].traversal_ms < 12.5
    # 幂等重放：同一输入五次穿透的拓扑内容逐字节一致（计时字段除外）
    for result in runs[1:]:
        assert result.model_dump(exclude={"traversal_ms"}) == (
            runs[0].model_dump(exclude={"traversal_ms"})
        )


def test_depth4_result_completeness() -> None:
    traverser = EntityHyperlinkGraphTraverser()
    levels = build_graph(traverser)
    result = traverser.traverse_entity_network("ent_laowang_root", depth=4)
    assert result.root_entity_id == "ent_laowang_root"
    assert list(result.anchors) == sorted(levels["anchors"])
    assert list(result.evidence_sets) == sorted(levels["evidence_sets"])
    assert list(result.observations) == sorted(levels["observations"])
    assert result.matched_level == "entity_id"


# ----------------------------------------------------------------------
# 硬验收 2：别名 100% 归一到主实体档案
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw_alias",
    [
        "老王",
        "王叔",
        "隔壁老王",
        "  隔壁老王  ",          # 首尾空白污染
        "Ｌａｏ　Ｗａｎｇ",        # 全角字符 + 全角空格（NFKC 折叠）
        "LAO WANG",             # 大小写折叠
        "lao   wang",           # 内部空白压缩
    ],
)
def test_alias_100_percent_normalized_to_primary_entity(raw_alias: str) -> None:
    traverser = EntityHyperlinkGraphTraverser()
    levels = build_graph(
        traverser, aliases=("老王", "王叔", "隔壁老王", "Lao Wang")
    )
    resolved = traverser.resolve_alias(raw_alias)
    assert resolved == "ent_laowang_root"

    result = traverser.traverse_entity_network(raw_alias, depth=4)
    assert result.root_entity_id == "ent_laowang_root"
    assert result.matched_level == "alias"
    # 归一后的别名集合精确等于注册集合（无多余、无遗漏）
    assert list(result.matched_aliases) == sorted(
        normalize_alias(a) for a in ("老王", "王叔", "隔壁老王", "Lao Wang")
    )
    # 别名入口与 ID 入口的穿透结果（除 matched_level 外）完全一致
    via_id = traverser.traverse_entity_network("ent_laowang_root", depth=4)
    assert result.anchors == via_id.anchors
    assert result.evidence_sets == via_id.evidence_sets
    assert result.observations == via_id.observations


def test_alias_topology_does_not_leak_near_miss_entity() -> None:
    traverser = EntityHyperlinkGraphTraverser()
    build_graph(traverser, aliases=("老王", "王叔", "隔壁老王"))
    # 近形但不同的实体：王师傅 ≠ 老王
    traverser.register_entity_link(
        "ent_wang_shifu", ["王师傅", "老王头"], ["evt_wang_shifu_001"]
    )
    traverser.register_anchor_links("evt_wang_shifu_001", [])
    traverser.register_entity_link("ent_other", ["隔壁老张"], [])

    result = traverser.traverse_entity_network("隔壁老王", depth=4)
    assert result.root_entity_id == "ent_laowang_root"
    assert "王师傅" not in [normalize_alias(a) for a in result.matched_aliases]
    assert "evt_wang_shifu_001" not in result.anchors
    other = traverser.traverse_entity_network("隔壁老张", depth=2)
    assert other.root_entity_id == "ent_other"
    assert other.anchors == ()


def test_ambiguous_alias_never_silently_merges() -> None:
    """同一别名声称属于两个实体：解析必须显式失败并列出全部候选（V3 §36）。"""
    traverser = EntityHyperlinkGraphTraverser()
    traverser.register_entity_link("ent_laowang_root", ["老王", "王叔"], [])
    traverser.register_entity_link("ent_xiaowang", ["小王", "王叔"], [])
    traverser.register_entity_link("ent_xiaoer", ["小王"], [])

    with pytest.raises(AliasAmbiguousError) as excinfo:
        traverser.resolve_alias("王叔")
    assert "ent_laowang_root" in excinfo.value.context["candidate_entity_ids"]
    assert "ent_xiaowang" in excinfo.value.context["candidate_entity_ids"]

    with pytest.raises(AliasAmbiguousError):
        traverser.traverse_entity_network("小王", depth=4)
    # 歧义不影响无冲突别名：100% 正确归一的其余部分必须继续可用
    assert traverser.resolve_alias("老王") == "ent_laowang_root"
    stats = traverser.stats()
    assert stats["alias_conflicts"] == 2  # 王叔 与 小王 两条冲突记录


# ----------------------------------------------------------------------
# 深度语义与契约校验
# ----------------------------------------------------------------------

def test_depth_semantics_level_by_level() -> None:
    traverser = EntityHyperlinkGraphTraverser()
    levels = build_graph(traverser)

    d1 = traverser.traverse_entity_network("ent_laowang_root", depth=1)
    assert d1.anchors == ()
    assert d1.traversal_depth == 1

    d2 = traverser.traverse_entity_network("ent_laowang_root", depth=2)
    assert list(d2.anchors) == sorted(levels["anchors"])
    assert d2.evidence_sets == ()
    assert d2.observations == ()

    d3 = traverser.traverse_entity_network("ent_laowang_root", depth=3)
    assert list(d3.evidence_sets) == sorted(levels["evidence_sets"])
    assert d3.observations == ()

    d4 = traverser.traverse_entity_network("ent_laowang_root", depth=4)
    assert list(d4.observations) == sorted(levels["observations"])


@pytest.mark.parametrize("bad_depth", [0, 5, -1, True, 2.5, "4", None])
def test_invalid_depth_rejected_with_protocol_error(bad_depth: object) -> None:
    traverser = EntityHyperlinkGraphTraverser()
    build_graph(traverser)
    with pytest.raises(InvalidTraversalDepthError):
        traverser.traverse_entity_network("ent_laowang_root", depth=bad_depth)  # type: ignore[arg-type]


def test_unregistered_entity_raises_not_found() -> None:
    traverser = EntityHyperlinkGraphTraverser()
    with pytest.raises(EntityNotRegisteredError):
        traverser.traverse_entity_network("ent_ghost", depth=4)
    with pytest.raises(EntityNotRegisteredError):
        traverser.resolve_alias("查无此人")


@pytest.mark.parametrize(
    "bad_alias", ["", "   ", "\u3000", 123, None]
)
def test_malformed_alias_rejected(bad_alias: object) -> None:
    traverser = EntityHyperlinkGraphTraverser()
    with pytest.raises(MalformedIdentifierError):
        traverser.register_entity_link("ent_x", [bad_alias], [])  # type: ignore[list-item]


# ----------------------------------------------------------------------
# 工程性红线：确定性、指针语义、并发、废除模糊扫描
# ----------------------------------------------------------------------

def test_registration_is_idempotent_replay_identity() -> None:
    traverser = EntityHyperlinkGraphTraverser()
    build_graph(traverser)
    first = traverser.traverse_entity_network("ent_laowang_root", depth=4)
    # 重复登记同一条链：集合并集语义，绝不产生重复边/重复结果
    build_graph(traverser)
    second = traverser.traverse_entity_network("ent_laowang_root", depth=4)
    assert first.model_dump(exclude={"traversal_ms"}) == (
        second.model_dump(exclude={"traversal_ms"})
    )
    stats = traverser.stats()
    assert stats["entity_anchor_edges"] == 3
    assert stats["anchor_evidence_edges"] == 6
    assert stats["evidence_observation_edges"] == 18


def test_index_stores_pointers_only_no_payload_aliasing() -> None:
    """只存指针：注册后外部修改传入序列不得影响索引（防引用别名泄漏）。"""
    traverser = EntityHyperlinkGraphTraverser()
    aliases = ["老王", "王叔"]
    anchors = ["evt_a1"]
    traverser.register_entity_link("ent_laowang_root", aliases, anchors)
    aliases.append("Injected After Registration")
    anchors.append("evt_injected")
    result = traverser.traverse_entity_network("ent_laowang_root", depth=2)
    assert result.matched_aliases == ("王叔", "老王")  # 按码点排序
    assert result.anchors == ("evt_a1",)


def test_self_reference_edge_terminates_gracefully() -> None:
    """构造自环/前向环指针：逐级 BFS 只沿分层表前进，必须安全终止。"""
    traverser = EntityHyperlinkGraphTraverser()
    traverser.register_entity_link("ent_loop", ["环形者"], ["evt_loop_self"])
    traverser.register_anchor_links("evt_loop_self", ["evs_loop_self"])
    traverser.register_evidence_links("evs_loop_self", ["obs_loop_self"])
    traverser.register_anchor_links("evt_loop_self", ["evt_loop_self"])  # 自环
    result = traverser.traverse_entity_network("ent_loop", depth=4)
    # 自环指针只是模型噪音：BFS 沿分层表单向前进，安全终止且不放大
    assert result.anchors == ("evt_loop_self",)
    assert result.evidence_sets == ("evs_loop_self", "evt_loop_self")
    assert result.observations == ("obs_loop_self",)


def test_concurrent_registration_and_traversal_is_safe() -> None:
    traverser = EntityHyperlinkGraphTraverser()
    build_graph(traverser, n_anchors=10)

    def register_worker(worker: int) -> None:
        for i in range(50):
            traverser.register_entity_link(
                f"ent_w{worker}", [f"别名{worker}_{i}"], []
            )
            traverser.register_anchor_links(
                f"evt_w{worker}_{i}", [f"evs_w{worker}_{i}"]
            )

    def traverse_worker() -> None:
        for _ in range(50):
            result = traverser.traverse_entity_network("老王", depth=4)
            assert result.root_entity_id == "ent_laowang_root"

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(register_worker, w) for w in range(4)]
        futures += [pool.submit(traverse_worker) for _ in range(4)]
        for future in futures:
            future.result(timeout=30)
    stats = traverser.stats()
    assert stats["entities"] == 1 + 4  # 根实体 + 4 个注册线程实体


def test_result_contract_is_frozen_and_closed() -> None:
    traverser = EntityHyperlinkGraphTraverser()
    build_graph(traverser)
    result = traverser.traverse_entity_network("ent_laowang_root", depth=4)
    with pytest.raises(ValidationError):
        result.root_entity_id = "ent_hacked"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        HyperlinkTraversalResult(
            root_entity_id="ent_x",
            matched_aliases=(),
            anchors=(),
            evidence_sets=(),
            observations=(),
            traversal_depth=4,
            traversal_ms=0.0,
            undocumented_field="must be forbidden",
        )


def test_redline_no_sql_and_no_fuzzy_scan_in_query_module() -> None:
    """废除单表模糊遍历的 CI 级红线：查询模块不得引入嵌入式 SQL 依赖
    （AST 级 import 检查），不得出现模糊扫描/SQL 拼接语义。"""
    import ast

    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(
                alias.name.split(".")[0] != "sqlite3" for alias in node.names
            ), "query layer must not import sqlite3"
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "sqlite3", (
                "query layer must not import sqlite3"
            )
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    assert "like" not in source, "fuzzy-scan semantics are forbidden"
    assert "select " not in source
    assert "execute(" not in source
