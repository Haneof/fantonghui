"""M1-012R 实体拓扑超链接网络穿透检索器验收测试。

验收标准（工单 TASK-M1-012R）：
1. 深度为 4 的穿透检索耗时 <= 25ms；
2. 别名必须 100% 正确归一链接到主实体档案；
3. 返回完整的实体、锚点与观察事实拓扑链
   （Entity -> EventAnchor -> EvidenceSet -> Observation）。
"""

from __future__ import annotations

import time

import pytest

from aios_core.query.hyperlink_traverser import (
    AliasConflictError,
    EntityHyperlinkGraphTraverser,
    HyperlinkTraversalResult,
    UnknownEntityError,
)

PERFORMANCE_BUDGET_MS = 25.0


def build_lao_wang_graph() -> EntityHyperlinkGraphTraverser:
    """构造工单示例图谱：老王/王叔/隔壁老王 四级因果穿透链。"""

    t = EntityHyperlinkGraphTraverser()
    t.register_observation(
        "obs-tea-001", payload={"raw": "老王说：今晚茶馆见。", "source": "chat"}
    )
    t.register_observation(
        "obs-tea-002", payload={"raw": "王叔拍桌：就这么定了。", "source": "audio"}
    )
    t.register_evidence_set(
        "es-tea-001",
        purpose="support",
        observation_ids=["obs-tea-001", "obs-tea-002"],
    )
    t.register_anchor(
        "anchor-lao-wang-tea",
        title="老王茶馆议事",
        evidence_set_ids=["es-tea-001"],
        participant_entity_ids=["老王", "小李"],
    )
    t.register_entity_link(
        "老王",
        aliases=["王叔", "隔壁老王"],
        anchor_ids=["anchor-lao-wang-tea"],
    )
    t.register_entity_link("小李", aliases=["李子"], anchor_ids=["anchor-lao-wang-tea"])
    return t


# ---------------------------------------------------------------------------
# 验收标准 2：别名 100% 归一到主实体档案
# ---------------------------------------------------------------------------


def test_aliases_unify_to_primary_entity_one_hundred_percent() -> None:
    t = build_lao_wang_graph()

    # 全部已登记别名（含主实体 ID 本身、带空白噪声的变体）逐一检索，
    # 必须 100% 归一到同一主实体档案 "老王"，无一漏网。
    probe_names = [
        "老王",
        "王叔",
        "隔壁老王",
        "  王叔  ",
        "\t隔壁老王\n",
        "老王 ",
    ]
    for name in probe_names:
        result = t.traverse_entity_network(name)
        assert result.root_entity_id == "老王", f"别名 {name!r} 未归一到主实体"
        assert set(result.matched_aliases) == {"老王", "王叔", "隔壁老王"}
        assert result.matched_aliases[0] == "老王"  # 首位恒为主实体档案


def test_alias_resolution_is_exact_not_fuzzy() -> None:
    """废除 LIKE '%xxx%'：子串 / 近似名不得误命中，必须精确抛错。"""

    t = build_lao_wang_graph()
    for wrong in ("老", "王", "隔壁", "老王八蛋", "老王小王"):
        with pytest.raises(UnknownEntityError):
            t.traverse_entity_network(wrong)


def test_alias_conflict_between_entities_is_rejected() -> None:
    t = EntityHyperlinkGraphTraverser()
    t.register_entity_link("老王", aliases=["王叔"], anchor_ids=[])
    with pytest.raises(AliasConflictError):
        t.register_entity_link("另一个王", aliases=["王叔"], anchor_ids=[])


def test_alias_cannot_be_promoted_to_second_primary_entity() -> None:
    t = EntityHyperlinkGraphTraverser()
    t.register_entity_link("老王", aliases=["王叔"], anchor_ids=[])
    with pytest.raises(AliasConflictError):
        t.register_entity_link("王叔", aliases=[], anchor_ids=[])


def test_reregistration_merges_links_idempotently() -> None:
    t = build_lao_wang_graph()
    t.register_anchor("anchor-2", title="老王的第二件事")
    t.register_entity_link("老王", aliases=["王叔", "神秘邻居"], anchor_ids=["anchor-lao-wang-tea", "anchor-2"])

    result = t.traverse_entity_network("神秘邻居")
    assert result.root_entity_id == "老王"
    assert result.matched_aliases == ["老王", "王叔", "隔壁老王", "神秘邻居"]
    assert [a["anchor_id"] for a in result.anchors] == [
        "anchor-lao-wang-tea",
        "anchor-2",
    ]


def test_unknown_entity_raises_lookup_error() -> None:
    t = build_lao_wang_graph()
    with pytest.raises(UnknownEntityError):
        t.traverse_entity_network("查无此人")
    # UnknownEntityError 同时是 LookupError，便于上层按查找失败分支处理。
    with pytest.raises(LookupError):
        t.traverse_entity_network("查无此人")


# ---------------------------------------------------------------------------
# 验收标准 3：完整四级因果拓扑链
# ---------------------------------------------------------------------------


def test_depth4_returns_full_four_level_causal_chain() -> None:
    t = build_lao_wang_graph()

    result = t.traverse_entity_network("隔壁老王", depth=4)
    assert isinstance(result, HyperlinkTraversalResult)
    assert result.traversal_depth == 4

    # Level 1: EventAnchor
    assert [a["anchor_id"] for a in result.anchors] == ["anchor-lao-wang-tea"]
    anchor = result.anchors[0]
    assert anchor["title"] == "老王茶馆议事"
    assert anchor["depth"] == 1
    assert anchor["via_entity_id"] == "老王"

    # Level 2: EvidenceSet
    assert [e["evidence_set_id"] for e in result.evidence_sets] == ["es-tea-001"]
    evidence = result.evidence_sets[0]
    assert evidence["depth"] == 2
    assert evidence["anchor_id"] == "anchor-lao-wang-tea"
    assert evidence["purpose"] == "support"

    # Level 3: Observation（原始言论）
    assert [o["observation_id"] for o in result.observations] == [
        "obs-tea-001",
        "obs-tea-002",
    ]
    for obs in result.observations:
        assert obs["depth"] == 3
        assert obs["evidence_set_id"] == "es-tea-001"
        assert obs["anchor_id"] == "anchor-lao-wang-tea"
    assert result.observations[0]["payload"]["raw"] == "老王说：今晚茶馆见。"

    # 网络横向穿透：共享锚点的对等实体（hop 2 起即可达）
    assert result.linked_entity_ids == ["小李"]

    # 结果契约为不可变快照
    with pytest.raises((TypeError, ValueError)):
        result.root_entity_id = "篡改者"


def test_depth_budget_controls_penetration_layers() -> None:
    t = build_lao_wang_graph()

    d0 = t.traverse_entity_network("老王", depth=0)
    assert d0.traversal_depth == 0
    assert d0.anchors == d0.evidence_sets == d0.observations == []
    assert d0.linked_entity_ids == []
    assert d0.matched_aliases == ["老王", "王叔", "隔壁老王"]

    # hop 1：仅事件锚点层
    d1 = t.traverse_entity_network("老王", depth=1)
    assert len(d1.anchors) == 1
    assert d1.evidence_sets == [] and d1.observations == []
    assert d1.linked_entity_ids == []

    # hop 2：+证据组 +共享锚点的对等实体（网络横向穿透启动）
    d2 = t.traverse_entity_network("老王", depth=2)
    assert len(d2.evidence_sets) == 1
    assert d2.linked_entity_ids == ["小李"]
    assert d2.observations == []

    # hop 3：+原始观察 +对等实体自身的锚点（本图中小李无新增锚点）
    d3 = t.traverse_entity_network("老王", depth=3)
    assert len(d3.observations) == 2
    assert [a["anchor_id"] for a in d3.anchors] == ["anchor-lao-wang-tea"]

    # hop 4：完整四级因果链 + 对等实体的证据组 + 二度对等实体
    d4 = t.traverse_entity_network("老王", depth=4)
    assert d4.linked_entity_ids == ["小李"]
    assert len(d4.observations) == 2
    assert [a["anchor_id"] for a in d4.anchors] == ["anchor-lao-wang-tea"]


def test_deeper_budget_expands_peer_entity_hyperlinks() -> None:
    t = EntityHyperlinkGraphTraverser()
    # 小李另有独立锚点：随着预算加深逐步穿透。
    t.register_observation("obs-li-1", payload={"raw": "小李：我先走了。"})
    t.register_evidence_set("es-li-1", observation_ids=["obs-li-1"])
    t.register_anchor("anchor-li-solo", evidence_set_ids=["es-li-1"], participant_entity_ids=["小李"])
    t.register_anchor("anchor-shared", participant_entity_ids=["老王", "小李"])
    t.register_entity_link("老王", anchor_ids=["anchor-shared"])
    t.register_entity_link("小李", anchor_ids=["anchor-shared", "anchor-li-solo"])

    # hop 2：发现对等实体小李
    d2 = t.traverse_entity_network("老王", depth=2)
    assert d2.linked_entity_ids == ["小李"]
    assert [a["anchor_id"] for a in d2.anchors] == ["anchor-shared"]
    assert d2.evidence_sets == [] and d2.observations == []

    # hop 3：小李自身的锚点被穿透
    d3 = t.traverse_entity_network("老王", depth=3)
    assert [a["anchor_id"] for a in d3.anchors] == ["anchor-shared", "anchor-li-solo"]
    assert d3.evidence_sets == []

    # hop 4：小李锚点挂载的证据组被穿透
    d4 = t.traverse_entity_network("老王", depth=4)
    assert [e["evidence_set_id"] for e in d4.evidence_sets] == ["es-li-1"]
    assert d4.observations == []

    # hop 5：证据组内的原始观察被穿透
    d5 = t.traverse_entity_network("老王", depth=5)
    assert [o["observation_id"] for o in d5.observations] == ["obs-li-1"]
    assert d5.observations[0]["payload"]["raw"] == "小李：我先走了。"


def test_cycles_and_shared_nodes_are_deduplicated() -> None:
    t = EntityHyperlinkGraphTraverser()
    # A、B 互为对等实体并共享锚点/证据组/观察，构成环。
    t.register_observation("obs-shared", payload={"raw": "共同目击记录"})
    t.register_evidence_set("es-shared", observation_ids=["obs-shared"])
    t.register_anchor(
        "anchor-loop",
        evidence_set_ids=["es-shared", "es-shared"],
        participant_entity_ids=["A", "B", "A"],
    )
    t.register_entity_link("A", aliases=["甲"], anchor_ids=["anchor-loop"])
    t.register_entity_link("B", aliases=["乙"], anchor_ids=["anchor-loop"])

    result = t.traverse_entity_network("甲", depth=6)
    assert result.root_entity_id == "A"
    assert [a["anchor_id"] for a in result.anchors] == ["anchor-loop"]
    assert [e["evidence_set_id"] for e in result.evidence_sets] == ["es-shared"]
    assert [o["observation_id"] for o in result.observations] == ["obs-shared"]
    assert result.linked_entity_ids == ["B"]


def test_forward_referenced_and_missing_links_are_tolerated() -> None:
    t = EntityHyperlinkGraphTraverser()
    # 先登记实体、后登记锚点是合法的（前向引用）。
    t.register_entity_link("老王", anchor_ids=["anchor-late", "anchor-ghost"])
    t.register_anchor("anchor-late", title="迟到登记的锚点")

    result = t.traverse_entity_network("老王", depth=4)
    assert [a["anchor_id"] for a in result.anchors] == ["anchor-late"]


def test_invalid_arguments_are_rejected() -> None:
    t = build_lao_wang_graph()
    with pytest.raises(ValueError):
        t.register_entity_link("  ", aliases=[], anchor_ids=[])
    with pytest.raises(ValueError):
        t.register_entity_link("老王", aliases=["   "], anchor_ids=[])
    with pytest.raises(TypeError):
        t.register_entity_link("老王", aliases=[123], anchor_ids=[])
    with pytest.raises(ValueError):
        t.traverse_entity_network("老王", depth=-1)
    with pytest.raises(TypeError):
        t.traverse_entity_network("老王", depth=True)
    with pytest.raises(TypeError):
        t.traverse_entity_network(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 验收标准 1：深度 4 穿透检索 <= 25ms
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def large_corpus() -> EntityHyperlinkGraphTraverser:
    """400 实体 / 800 锚点 / 2400 证据组 / 9600 观察的大规模语料。

    用于证明检索成本只取决于命中子图，与语料总规模无关
    （废除 LIKE '%xxx%' 全表扫描的核心收益）。
    """

    t = EntityHyperlinkGraphTraverser()
    n_entities = 400
    for i in range(n_entities):
        anchor_ids = []
        for slot in ("self", "shared"):
            aid = f"anchor-{i}-{slot}"
            anchor_ids.append(aid)
            evidence_set_ids = []
            for k in range(3):
                esid = f"{aid}-es-{k}"
                evidence_set_ids.append(esid)
                observation_ids = [f"{esid}-obs-{m}" for m in range(4)]
                for oid in observation_ids:
                    t.register_observation(oid, payload={"raw": f"原始言论 {oid}"})
                t.register_evidence_set(esid, purpose="support", observation_ids=observation_ids)
            participants = [f"ent-{i}", f"ent-{(i + 1) % n_entities}"]
            t.register_anchor(aid, title=f"事件锚点 {aid}", evidence_set_ids=evidence_set_ids, participant_entity_ids=participants)
        t.register_entity_link(
            f"ent-{i}",
            aliases=[f"alias-{i}-a", f"alias-{i}-b"],
            anchor_ids=anchor_ids,
        )
    return t


def test_large_corpus_is_registered(large_corpus: EntityHyperlinkGraphTraverser) -> None:
    stats = large_corpus.stats()
    assert stats == {
        "entities": 400,
        "anchors": 800,
        "evidence_sets": 2400,
        "observations": 9600,
        "alias_index_entries": 400 * 3,
    }


def test_depth4_traversal_within_25ms_budget(
    large_corpus: EntityHyperlinkGraphTraverser,
) -> None:
    t = large_corpus

    # 预热（排除解释器冷启动噪声），随后连续采样 5 次深度 4 穿透。
    t.traverse_entity_network("ent-0", depth=4)
    results = [t.traverse_entity_network("ent-0", depth=4) for _ in range(5)]
    for result in results:
        assert result.traversal_ms <= PERFORMANCE_BUDGET_MS, (
            f"深度 4 穿透耗时 {result.traversal_ms:.3f}ms 超出 25ms 预算"
        )

    # 别名入口的端到端墙钟耗时（含契约构建）同样必须在预算内。
    started = time.perf_counter()
    via_alias = t.traverse_entity_network("alias-17-b", depth=4)
    wall_ms = (time.perf_counter() - started) * 1000.0
    assert wall_ms <= PERFORMANCE_BUDGET_MS
    assert via_alias.root_entity_id == "ent-17"
    assert via_alias.traversal_ms <= PERFORMANCE_BUDGET_MS


def test_depth4_traversal_correctness_on_large_corpus(
    large_corpus: EntityHyperlinkGraphTraverser,
) -> None:
    result = large_corpus.traverse_entity_network("ent-0", depth=4)

    # hop1: ent-0 的 2 锚点；hop2: 6 证据组 + 对等实体 ent-1；
    # hop3: 24 观察 + ent-1 的 2 锚点；hop4: ent-1 锚点的 6 证据组 + 二度对等实体。
    assert [a["anchor_id"] for a in result.anchors] == [
        "anchor-0-self",
        "anchor-0-shared",
        "anchor-1-self",
        "anchor-1-shared",
    ]
    assert len(result.evidence_sets) == 12
    assert len(result.observations) == 24
    assert result.linked_entity_ids == ["ent-1", "ent-2"]
    assert all(o["payload"]["raw"].startswith("原始言论") for o in result.observations)
    assert result.traversal_ms >= 0.0
