# 新机制发明与新工具提议（ToolProposal）

> 交付物 3/3 · 老大约法三章：总结机制、发明工具 · 2026-09-16
> 交付形态：**两个已纯代码实现并入库**（TP-001 / TP-002，含 ToolProposal
> 契约实例与专项测试）+ 一个已立项设计的后续工具（TP-003）。

---

## 1. 机制总结（本次盲测沉淀的三条通用机制）

### 机制一：「守恒账目」——有损压缩必须有不变量作保

阶段一的教训升华：波形轻量化（50Hz→宏观状态）天然有损，但**有损
不等于失守**——只要公开一条可断言的守恒不变量（每个样本要么进均值
通道、要么进尖峰通道，coverage ≡ 1.0），有损压缩就变成可审计的
确定性变换而非数据黑洞。该机制已泛化为 TP-001 的核心契约。

### 机制二：「虚拟投影」——视图是旗标不是拷贝

阶段五双透镜的老王案验证：10 万记录 + 500 总结 + 2 条推翻注解的
世界里，AsKnown/Annotated 两套视图若各自物化，就要复制 20 万载荷；
把"被推翻/带注记"降维成**倒排旗标集**，查询期虚拟叠加，构建成本
只随注解数增长（实测构建扫描量 2 == 注解数），一致性由集合代数
保证（visible(annotated) = visible(as_known) − overturned）。

### 机制三：「对抗 Oracle」——真值卷宗与管线物理隔离

自编自答的根治不是"更小心地写断言"，而是把出题权交给独立组件：
生成器封存卷宗（种子确定性、通道独立），管线对卷宗盲测，裁决在
两者交界处进行。本批压测中该机制当场抓获 4 个真实缺陷
（声纹碎裂/词典漏配/链式聚簇/O(n²) purge）——mock 永远抓不到这些。

---

## 2. TP-001 自适应时序压缩算子（已实现）

**代码**：`src/aios_core/tools/adaptive_compressor.py`
**契约实例**：`tool_proposal_of_compressor()`（六字段齐全）
**测试**：`tests/bench/test_stage_engines.py::test_tp001_adaptive_compressor_conservation`

```python
comp = AdaptiveTemporalCompressor(window_size=50, spike_sigma=3.0)
result = comp.compress(values)      # 5,000 点心率/IMU 序列
result.coverage        # == 1.0 样本守恒（无静默丢点）
result.spike_values    # 全部 >3σ 极值独立保全
result.ratio           # 实测 6~43× 压缩比
```

- **能力缺口**：边缘层各流各写一套窗口聚合，尖峰判定口径不一、
  无守恒审计面。
- **预期收益（实测）**：合成序列压缩比 43.5×，均值通道失真 <1%，
  极值 100% 进尖峰通道；直接支撑铁律4"原始波形不直写、突变独立
  成 Observation"的机械化。
- **验证方案**：coverage==1.0 不变量 + 尖峰全召回 + 均值偏差 <1%
  三断言已入库，随全仓回归持续把关。

## 3. TP-002 双透镜虚拟索引投影器（已实现）

**代码**：`src/aios_core/tools/dual_lens_index.py`
**契约实例**：`tool_proposal_of_dual_lens()`
**测试**：`tests/bench/test_stage_engines.py::test_tp002_dual_lens_virtual_index`

```python
idx = DualLensVirtualIndexProjector(
    record_subjects={...2 万条...},        # record_id -> subject
    annotations=[{"record_id": "r19999", "kind": "overturn"}, ...])
idx.build_scan_count                       # == 3（O(注解) 构建，与记录量解耦）
idx.view("partner_zhou", lens="annotated") # 零拷贝：id + 推翻旗标集
idx.consistency_report()                   # {"consistent": True, ...}
```

- **能力缺口**：双透镜视图逐条遍历注解链现算，10 万级历史每次查询
  重放链条；SingleHopCascadeIsolator 只给 stale 标记不给视图物。
- **预期收益（实测）**：2 万记录 + 3 注解场景构建扫描量 3 次
  （对比物化 4 万次拷贝，↓4 个数量级）；全马阶段5 与隔离器交叉
  验证一致性 100%。
- **验证方案**：visible 差集==overturn 集、⊇关系闭合、构建扫描量
  ==注解数，三项断言已入库。

## 4. TP-003 倒排共现拓扑索引（已立项设计，下一批实现）

压测暴露的头号 I/O 热点（34 万记录单查 942ms）的对症工具：

```
机理：查询期把多关键词 AND 下推到既有 _by_keyword 倒排层——
      1) 各关键词取倒排链（已在库内，零新增存储）
      2) 取最小链起步，逐链求集合交集（K 个关键词 → K-1 次交集）
      3) 仅对交集做正文共现复核（残余集合通常 <100 条）
复杂度：O(Σ|倒排链|) vs 现路径 C 的 O(N)
预期：34 万库 942ms → <5ms（188×）；千万库 28s → <200ms
风险与对策：高频词（"日常"）倒排链过长 → 词表 IDF 分层，
      骨架词不进共现索引首层
验证方案：与现路径 C 在全马库上做 200 查询双跑一致性
      （hit_ids 完全相等）+ 延迟对比入压测报告
```

实现落点：`MultidimensionalSearchEngine` 新增第四条路径
`INVERTED_COOCCURRENCE`（不动既有三路径语义），以 OperationExperience
蒸馏机制自动接管为黄金路径——检索体系自我进化的闭环。

## 5. 工具与契约的落地清单

| 项 | 状态 | 位置 | 回归锚点 |
|---|---|---|---|
| TP-001 实现 + 契约 + 测试 | ✅ 已入库 | `tools/adaptive_compressor.py` | `test_tp001_...` |
| TP-002 实现 + 契约 + 测试 | ✅ 已入库 | `tools/dual_lens_index.py` | `test_tp002_...` |
| TP-003 设计 + 验证方案 | 📋 立项 | 本报告 §4 | 双跑一致性（下批） |
| 机制一/二/三 | ✅ 已实证 | bench 全链 | 全马 817 绿 |
