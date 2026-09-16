"""CAM —— 宪法验收矩阵（Constitutional Acceptance Matrix）。

唯一账本：《AIOS核心系统宪法v3.0》第 114 条全部 46 项验收 + R4 修改案新增 9 项 = 55 项，
每项映射到 [宪法条款, 模块编号(C01-C15, 以 R4 设计书为唯一账本), 里程碑, 状态, 测试]。

CI 闸门：tests/architecture/test_cam_coverage.py
  - 任何宪法验收项缺失映射 = 红灯；
  - status=contract_frozen 的条目，其 tests 路径必须真实存在；
  - R4-* 在修改案批准前保持 proposed_pending_R4。

status 枚举：
  contract_frozen     M0 已冻结该行为所需契约并有单元测试（运行面待后续里程碑）
  planned             契约已/将冻结，行为验收在指定里程碑出口测
  proposed_pending_R4 验收项本身随 R4 修改案待批准
"""

CAM_VERSION = "1.0.0"
CAM_DATE = "2026-09-16"
LEDGER_MODULES = frozenset(f"C{i:02d}" for i in range(1, 16))

CONSTITUTION_ACCEPTANCE: list[dict] = [
    # ---------- 原宪法验收（A 系列，第 114 条） ----------
    {"id": "A01", "title": "用户世界和 AI 世界共享时间轴", "articles": [16, 17, 30],
     "module": ["C02"], "milestone": "M0", "status": "contract_frozen",
     "tests": ["tests/unit/test_time.py", "tests/unit/test_world_object_revision.py"]},
    {"id": "A02", "title": "多维世界可挂载不同数据形态", "articles": [18, 19],
     "module": ["C03"], "milestone": "M0", "status": "contract_frozen",
     "tests": ["tests/unit/test_dimensions.py", "tests/unit/test_dimension_membership_persistence.py"]},
    {"id": "A03", "title": "事件由大模型判断而非底层生成", "articles": [46],
     "module": ["C06", "C09"], "milestone": "M2", "status": "contract_frozen",
     "tests": ["tests/unit/test_event_anchor.py", "tests/unit/test_observation.py"]},
    {"id": "A04", "title": "事件是锚点，引用而非复制", "articles": [47, 18],
     "module": ["C06", "C02"], "milestone": "M1", "status": "contract_frozen",
     "tests": ["tests/unit/test_event_anchor.py", "tests/unit/test_refs.py"]},
    {"id": "A05", "title": "高层认知可向下追溯到原始证据", "articles": [65, 27],
     "module": ["C07", "C11"], "milestone": "M3", "status": "contract_frozen",
     "tests": ["tests/unit/test_dependency.py"]},
    {"id": "A06", "title": "世界搜索可用", "articles": [89, 95, 96],
     "module": ["C11"], "milestone": "M1", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m1_gate_search.py (M1-017, G-M1P)"},
    {"id": "A07", "title": "时间缩放可用", "articles": [87, 88],
     "module": ["C11"], "milestone": "M1", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m1_time_lens.py (M1-010; EMPTY_LAYER 语义见 R4-04)"},
    {"id": "A08", "title": "AI 操作可回放", "articles": [66, 86],
     "module": ["C02", "C10"], "milestone": "M2", "status": "contract_frozen",
     "tests": ["tests/unit/test_operations.py"]},
    {"id": "A09", "title": "任务系统可用", "articles": [60, 61, 62],
     "module": ["C08"], "milestone": "M2", "status": "contract_frozen",
     "tests": ["tests/unit/test_state_machines.py", "tests/unit/test_state_machines_m021.py"]},
    {"id": "A10", "title": "触发器不做语义判断", "articles": [77, 79],
     "module": ["C09"], "milestone": "M2", "status": "contract_frozen",
     "tests": ["tests/unit/test_observation.py"]},

    # ---------- R1 验收 ----------
    {"id": "R1-01", "title": "AI 可以跳过无必要工作项仍正确完成任务", "articles": [86],
     "module": ["C10"], "milestone": "M2", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m2_skip_workitems.py (M2-012)"},
    {"id": "R1-02", "title": "连续无认知增量的会话不产生占位反思", "articles": [86],
     "module": ["C10", "C06"], "milestone": "M2", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m2_no_placeholder.py (M2-013)"},
    {"id": "R1-03", "title": "合法维度能够自主登记不依赖固定价值分类", "articles": [72, 76],
     "module": ["C03"], "milestone": "M0", "status": "contract_frozen",
     "tests": ["tests/unit/test_dimension_lifecycle.py"]},
    {"id": "R1-04", "title": "无效引用、重复提交和资源超限得到明确处理", "articles": [76],
     "module": ["C02", "C03"], "milestone": "M0", "status": "contract_frozen",
     "tests": ["tests/unit/test_reference_validation_m019.py", "tests/unit/test_store.py"]},
    {"id": "R1-05", "title": "低频但关联长期承诺的维度不会被误清理", "articles": [75],
     "module": ["C03"], "milestone": "M3", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m3_dim_retention.py (M3-007)"},
    {"id": "R1-06", "title": "同关键词持续出现时唤醒可合并新证据仍能进入", "articles": [82],
     "module": ["C09"], "milestone": "M2", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m2_wake_merge.py (M2-003)"},
    {"id": "R1-07", "title": "AI 写入认知或修改策略不产生无限自我唤醒", "articles": [64, 82],
     "module": ["C07", "C09"], "milestone": "M3", "status": "contract_frozen",
     "tests": ["tests/unit/test_dependency.py"],
     "planned": "运行面扩展: M2-016/MAINTENANCE 豁免后升级为全链路回归 (R4-05)"},
    {"id": "R1-08", "title": "暂停或冷却均有期限、证据记录与解除条件", "articles": [82],
     "module": ["C09"], "milestone": "M2", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m2_cooldown_expiry.py (M2-003)"},
    {"id": "R1-09", "title": "无用户提问 AI 能自主发现帮助机会并完成跟进", "articles": [4, 14],
     "module": ["C09", "C10", "C08"], "milestone": "M2", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m2_proactive_loop.py (M2-015)"},
    {"id": "R1-10", "title": "模型中断后恢复不重复行动不丢失未完成任务", "articles": [86],
     "module": ["C13", "C10"], "milestone": "M2", "status": "contract_frozen",
     "tests": ["tests/unit/test_store.py", "tests/unit/test_active_system_contracts.py"],
     "planned": "运行面: M2-008/011 (checkpoint 续办)"},
    {"id": "R1-11", "title": "第一轮报告不把未验证能力计作成果", "articles": [113],
     "module": ["C14"], "milestone": "M4", "status": "planned",
     "tests": [], "planned": "报告审查规则 (M4b); CAM 自身即机器执行面"},

    # ---------- R2 专项验收 ----------
    {"id": "R2-01", "title": "高频基础数据不会逐条唤醒", "articles": [34, 79],
     "module": ["C09"], "milestone": "M2", "status": "contract_frozen",
     "tests": ["tests/unit/test_observation.py"],
     "planned": "运行面: M2-002 + V21b 风暴回归 (R4-05)"},
    {"id": "R2-02", "title": "用户说过 ≠ 现实事实", "articles": [38, 41],
     "module": ["C06"], "milestone": "M1", "status": "contract_frozen",
     "tests": ["tests/unit/test_claim.py"]},
    {"id": "R2-03", "title": "证据集合可复核（STALE+重审）", "articles": [42, 44],
     "module": ["C06"], "milestone": "M1", "status": "contract_frozen",
     "tests": ["tests/unit/test_evidence_set.py"],
     "planned": "运行面: M3-002"},
    {"id": "R2-04", "title": "区间证据不漂移（可重建切片）", "articles": [43],
     "module": ["C06"], "milestone": "M1", "status": "contract_frozen",
     "tests": ["tests/unit/test_evidence_set.py"]},
    {"id": "R2-05", "title": "派生维度可追溯且随输入失效标复核", "articles": [24, 65],
     "module": ["C03", "C07"], "milestone": "M3", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m3_derivation_trace.py (M3-008)"},
    {"id": "R2-06", "title": "候选维度不等于正式活跃", "articles": [73, 74],
     "module": ["C03"], "milestone": "M0", "status": "contract_frozen",
     "tests": ["tests/unit/test_dimension_lifecycle.py"]},
    {"id": "R2-07", "title": "低频高价值维度不会误清理", "articles": [75],
     "module": ["C03", "C05"], "milestone": "M3", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m3_lowfreq_keep.py (M3-007)"},
    {"id": "R2-08", "title": "Goal 与 Task 分离", "articles": [54, 56],
     "module": ["C06", "C08"], "milestone": "M1", "status": "contract_frozen",
     "tests": ["tests/unit/test_goal.py"]},
    {"id": "R2-09", "title": "推断目标与明确目标分离", "articles": [55, 58],
     "module": ["C06"], "milestone": "M1", "status": "contract_frozen",
     "tests": ["tests/unit/test_goal_reviewability.py", "tests/unit/test_goal.py"]},
    {"id": "R2-10", "title": "Event 生命周期可回放（版本链）", "articles": [48],
     "module": ["C06"], "milestone": "M1", "status": "contract_frozen",
     "tests": ["tests/unit/test_event_anchor.py", "tests/unit/test_event_anchor_legacy_evidence_ref.py"]},
    {"id": "R2-11", "title": "事件修正精确波及下游", "articles": [49],
     "module": ["C07"], "milestone": "M3", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m3_propagation.py (M3-001 重写 + M3-012)"},
    {"id": "R2-12", "title": "最小多尺度总结闭环", "articles": [28],
     "module": ["C05"], "milestone": "M3", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m3_summary_chain.py (M3-004/005, 契约 M0-024)"},
    {"id": "R2-13", "title": "总结不覆盖原始历史", "articles": [25, 93],
     "module": ["C02", "C05"], "milestone": "M0", "status": "contract_frozen",
     "tests": ["tests/unit/test_world_object_revision.py", "tests/unit/test_world_revision_atomicity.py"]},
    {"id": "R2-14", "title": "AI 可跳过总结层直接下钻", "articles": [27, 91],
     "module": ["C11", "C10"], "milestone": "M3", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m3_direct_drill.py (M3-005)"},
    {"id": "R2-15", "title": "认知修正不会自激无限循环", "articles": [64, 82],
     "module": ["C07", "C09"], "milestone": "M3", "status": "contract_frozen",
     "tests": ["tests/unit/test_dependency.py"],
     "planned": "运行面: M3-012 传播预算 + R4-05 V21b"},

    # ---------- R3 验收 ----------
    {"id": "R3-01", "title": "黑盒零做题（无问卷/画像 UI）", "articles": [6],
     "module": ["C15"], "milestone": "M4", "status": "planned",
     "tests": [], "planned": "界面审查 + 116 条违宪扫描 (M4b)"},
    {"id": "R3-02", "title": "事实自然纠偏（无确认框重构）", "articles": [7],
     "module": ["C06", "C10"], "milestone": "M4", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m4_implicit_fix.py (M4-001)"},
    {"id": "R3-03", "title": "预测证伪闭环", "articles": [50, 51, 53],
     "module": ["C06", "C08"], "milestone": "M3", "status": "planned",
     "tests": [], "planned": "契约冻结 M0-025; 闭环测试 M3-012 后 (PredictionCheckTask)"},
    {"id": "R3-04", "title": "总结无损下钻", "articles": [27],
     "module": ["C05", "C11"], "milestone": "M3", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m3_lossy_drill.py (M3-005)"},
    {"id": "R3-05", "title": "相变与章节归档", "articles": [29],
     "module": ["C05"], "milestone": "M4", "status": "planned",
     "tests": [], "planned": "契约冻结 M0-024; V35 场景判分 (M4-001)"},
    {"id": "R3-06", "title": "反谄媚硬骨气", "articles": [9, 15],
     "module": ["C10", "C14"], "milestone": "M4", "status": "planned",
     "tests": [], "planned": "荒谬事实注入场景 (M4b 盲测)"},
    {"id": "R3-07", "title": "分寸自适应（被拒后降频）", "articles": [10, 80, 97],
     "module": ["C09", "C12"], "milestone": "M4", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m4_rapport_cooling.py (M4-001)"},

    # ---------- v3.0 新增验收 ----------
    {"id": "V3-01", "title": "沟通风格进化", "articles": [12, 69],
     "module": ["C06", "C12"], "milestone": "M4", "status": "planned",
     "tests": [], "planned": "契约冻结 M0-026; 风格漂移评分 (M4b)"},
    {"id": "V3-02", "title": "关系节奏触发", "articles": [80],
     "module": ["C09", "C08"], "milestone": "M2", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m2_heartbeat_gate.py (M2-019)"},
    {"id": "V3-03", "title": "上下文精准组装（切片相关性）", "articles": [85],
     "module": ["C10", "C11"], "milestone": "M2", "status": "planned",
     "tests": [], "planned": "tests/integration/test_m2_manifest_relevance.py (M2-009 重写)"},

    # ---------- R4 修改案新增验收（proposed_pending_R4） ----------
    {"id": "R4-01", "title": "首字延迟预算 p95<=1.0s (V34 链路)", "articles": [85],
     "module": ["C10", "C11", "C13"], "milestone": "M4", "status": "proposed_pending_R4",
     "tests": [], "planned": "tests/perf/test_m4_first_token_budget.py (M4-005)"},
    {"id": "R4-02", "title": "共现检索 p95<=50ms@50万修订; 三点位一致", "articles": [89],
     "module": ["C11"], "milestone": "M1", "status": "proposed_pending_R4",
     "tests": [], "planned": "tests/perf/test_g_m1p_scale.py (G-M1P); EXPLAIN 无 payload 扫描断言"},
    {"id": "R4-03", "title": "调度零浪费: 评估 O(命中), 路径 LLM 调用=0, 重放幂等", "articles": [86, 79],
     "module": ["C08"], "milestone": "M2", "status": "proposed_pending_R4",
     "tests": [], "planned": "tests/integration/test_m2_scheduler_storm.py (M2-016/017/019)"},
    {"id": "R4-04", "title": "心智四步序回放断言 (mirror→rapport→posture→world)", "articles": [84],
     "module": ["C10", "C14"], "milestone": "M2", "status": "proposed_pending_R4",
     "tests": [], "planned": "tests/integration/test_m2_four_step_trace.py (M2-020)"},
    {"id": "R4-05", "title": "V21b 风暴回归: 放大比<=1; 维护写 0 Wake; 越权必败", "articles": [64, 79, 82],
     "module": ["C09", "C02"], "milestone": "M2", "status": "proposed_pending_R4",
     "tests": [], "planned": "tests/integration/test_m2_gate_storm.py (M0-023 + M2-GATE)"},
    {"id": "R4-06", "title": "双视图确定性分叉; 标注不改目标 revision; 半径=O(引用)", "articles": [31, 93],
     "module": ["C06", "C02"], "milestone": "M3", "status": "proposed_pending_R4",
     "tests": [], "planned": "tests/integration/test_m3_reinterpretation_views.py (M0-027 + M3-013)"},
    {"id": "R4-07", "title": "归档审计: 无非三条件物理删除; PRUNED 可解析", "articles": [33, 116],
     "module": ["C02", "C01"], "milestone": "M1", "status": "proposed_pending_R4",
     "tests": [], "planned": "tests/integration/test_m1_prune_audit.py (M1-019)"},
    {"id": "R4-08", "title": "影子双世界: 清洗组效用 >= 全留组 - eps 且存储下降", "articles": [33, 111],
     "module": ["C14"], "milestone": "M4", "status": "proposed_pending_R4",
     "tests": [], "planned": "tests/experiment/test_m3_shadow_worlds.py (M3-014)"},
    {"id": "R4-09", "title": "注入防线: 第三方 REPORTED 不升 FACT 不动作", "articles": [19, 38],
     "module": ["C06"], "milestone": "M4", "status": "proposed_pending_R4",
     "tests": [], "planned": "tests/experiment/test_v31_injection.py (M4-006)"},
]


def charter_ids() -> set[str]:
    """已被宪法第 114 条正文覆盖的验收项 id（不含 R4 新增）。"""
    return {e["id"] for e in CONSTITUTION_ACCEPTANCE if not e["id"].startswith("R4-")}


def r4_proposed_ids() -> set[str]:
    return {e["id"] for e in CONSTITUTION_ACCEPTANCE if e["id"].startswith("R4-")}
