# agent-05 latest report（M1-018 超集并存线 · epistemic_world_lens）

agent_id: agent-05
role: M1-018 Implementation Engineer（认知反向传播语义图层 / 首席架构部高阶工单）
task: M1-018 高阶实战版（王建国 Pre-A 对赌合伙案 · 司法冻结查封 · 双时间透镜 + 单跳隔离）
status: SUPERSET DELIVERED / PYTEST 100% GREEN

branch: arena/01a0a700-fantonghui
note_branch: 本会话受平台约束固定于 arena/01a0a700-fantonghui；工单文面要求的新分支无法由本会话
  创建/推送，全部成果落在上述固定分支（fast-forward，无 force-push）。
base: origin/arena/01a0a700-fantonghui @ 7785aed（= origin 远端头）

## 一、并存裁定（老大亲裁三条）

1. **契约基线：SUPERSET（超集）** —— 保留本线已实现的引擎，同时补齐升级版工单（origin/aios-2.0
   @ 6047b7b）的契约面与重负载门禁；
2. **冲突处置：COEXIST（并存）** —— 战队已合入基线 `world/retrospective_annotation.py`
   （b0c540a → 7785aed）及其 25 项测试**一字未改**；本线全部落盘到新路径：
   - 实现：`src/aios_core/world/epistemic_world_lens.py`
   - 单测：`tests/unit/test_m1_018_epistemic_world_lens.py`
   - 报告：本文件（`LATEST.md` 保持基线版本原样）
3. **集成基线：** 以 `origin/arena/01a0a700-fantonghui` 头为基，fast-forward 推送。

包级导出（`world/__init__.py`）为**纯增量**：27 个非冲突符号并入 `__all__`；三个同名符号
（`RetrospectiveAnnotation` / `BiTemporalEpistemicLens` / `SingleHopCascadeIsolator`）
**继续以基线为准**，既有调用方零感知；需要本线实现时显式
`from aios_core.world.epistemic_world_lens import ...`。

## 二、四大硬门禁（升级版工单 §3）在本线的实证

- **门禁 1【历史事实绝对不可变】**：`test_ra26_ten_thousand_high_density_facts_keep_every_single_sha256`
  造 730 天内 10,000 条高密度事实（每 105 分钟一条），挂载司法查封回溯注记后
  **逐条比对 SHA-256：10,000/10,000 字节级一致**，另附全量聚合指纹（aggregate digest）一致、
  `verify_history_integrity().checked_facts == 10_000`、`tampered == ()`、
  `recompute_audit()` 三项恒零。本线哈希口径 = **真实落库 payload 字节**的 SHA-256
  （与 C02 SQLite `object_revisions.payload_json` 逐字节同构），不是活对象内存快照。
- **门禁 2【只在今天打标签】**：`RetrospectiveAnnotation` 规范字段名采用升级版工单命名
  （`valid_time_start` / `valid_time_end` / `source_evidence_ref` / `confidence` / `recorded_at`），
  `learned_at = recorded_at = T_now`，`valid_time_range = [T0, T_now]`；
  排序校验拒绝倒写历史（`learned_at >= valid_time_end`、`recorded_at >= learned_at`）。
  一号工单命名（`target_time_*` / `source_statement_ref`）以 `AliasChoices` 双向接受，
  并以只读属性同值暴露 → **两版工单读法都成立，指纹相同**（`test_ra23`）。
- **门禁 3【双时间透镜对撞】**：`test_ra24` 走
  `BiTemporalEpistemicLens(raw_store, annotation_store).query_entity_state(...)`，
  产物为强类型 `HistoricalEpistemicSlice`（骨架字段 `entity_id / query_time / as_of_cutoff /
  raw_observations / active_annotations / effective_interpretation` 全部保留，
  本线增补 `view_kind` 与 `raw_observation_digests` 让哈希门禁在查询产物上自证）：
  `as_of_cutoff = T0+100 天` → `active_annotations == []`、`view_kind == "AS_OF"`、
  序列化全文不含 `司法冻结查封确认欺诈` 与法院文书号（**零泄露**）；
  `as_of_cutoff = None` → `view_kind == "CURRENT"`、恰好一层叠加、
  `effective_interpretation` 渲染警示，而 `raw_observation_digests` 与 AS_OF 视图**逐条相同**。
- **门禁 4【单跳隔离深度防爆】**：`test_ra25` 构建 5 层依赖拓扑
  （1 级 10 / 2 级 200 / 3 级 1000 / 4 级 2000 / 5 级 4000，共 7,210 个下游节点），
  `invalidate_downstream_single_hop(...)` 严格只标记 **10 个 1 级节点**；
  审计报告 `traversal_depth_reached == 1`、`graph_queries == 1`、`llm_recompute_triggered == 0`、
  `second_hop_expanded is False`，间谍回调零调用；**绊线图**（任何 2 级邻接查询即 `AssertionError`）
  实证遍历次数物理为 1；`max_hops=2` 直接抛 `OverlayCascadeForbidden`（拒绝无界级联）；
  只读诊断可看清被压制的 200 个 2 级节点但**不打 stale、不重算**（深度上限 `MAX_DIAGNOSTIC_DEPTH`）。
  审计报告模型本身被 `Field(ge=1, le=1)` / `le=0` / `Literal[False]` 锁死：
  **该契约根本无法表达“发生过级联递归”**（`test_ra25` 四条 `ValidationError` 断言）。

## 三、给首席的仲裁留档（本线相对基线的可熔铸点）

1. **双线一致性已实证**：`test_ra27_both_implementation_lines_agree_on_all_four_hard_gates`
   用同一份王建国案情境同时驱动两条线，四大门禁给出**同一答案**（历史哈希全绿、当时零图层、
   今天恰一层、单跳严格 10 节点/深度 1/重算 0）。熔铸时不必二选一，行为已对齐。
2. **切片语义差异（唯一实质分歧）**：基线为累积切片 `(-∞, target_time]`；本线默认
   `slice_mode="instant"`（精确时间点/区间命中）。本线已内建
   `slice_mode="cumulative"` 复现基线语义（`test_ra24` / `test_ra26` / `test_ra27` 均以此对撞），
   故**分歧已收敛为可选参数**，默认值由首席裁定即可。
3. **契约互操作零成本**：`coerce_annotation()` 直接吃基线 `RetrospectiveAnnotation`
   实例 / 映射 / 世界对象；`to_sibling_annotation()` 反向投影回基线契约（只投影对方声明过的字段）。
   两条线可共用同一份认知账本。
4. **错误分类法**：本线走 `aios_core.errors.AIOSProtocolError + ErrorCode`
   （与 C02 存储底座同族），基线为 `ValueError` 家族 —— 保留原分歧待裁。
5. **时区策略**：本线按 `contracts.time.require_aware` fail-closed 拒绝 naive，
   基线 naive 静默按 UTC 归一 —— 保留原分歧待裁。
6. **查询返回形态**：本线同时提供强类型视图（`EpistemicSliceView` /
   `HistoricalEpistemicSlice`）与一号工单原文的 `Dict[str, Any]`
   （`query_historical_slice`），基线只有强类型 —— 本线为超集。

## 四、运行证据

```
PYTHONPATH=src .venv/bin/python -m pytest tests/     # Python 3.11.2 / pytest 8.4.2 / pydantic 2.13.5
→ 678 passed（651 仓库既有 + 27 本线；0 failed / 0 error / 全仓满堂绿）
```

- 本线单测：27 项（ra01–ra27），单文件耗时 ≈ 6.7s（含 10,000 条事实哈希全量复核）。
- 本线 10,000 事实重负载实测：登记 1.46s / 完整性复核 0.93s / 挂载注记 0.82s /
  二次复核 0.79s / 切片查询 0.012s。
- ruff（仓库未配置 ruff，默认规则集）：本线两文件仅 20 条风格类提示
  （UP017/UP037/DTZ001/SIM103/FURB162），**零 F 级（正确性）告警**；
  同期基线两文件为 35 条同类提示，风格与仓库现状一致，未做无谓改写。

## 五、宪法遵从声明（第九十三条 / 老王案）

只在今天这个时间节点打标签；两年前原始事实（聊天记录、心率体征、合伙事件）**从未 UPDATE /
DELETE**，原始 SHA-256 永久不变；新认知以**今日追加的外挂图层**指回过去的时间切片；
双时间透镜在历史 cutoff 下**原样复现当时的信任世界**（不泄露今日认知），在当下视图动态渲染
“后来发现欺诈”的警示；**严禁任何级联递归重算历史**——严格单跳、报告契约物理锁死、
大模型重算触发次数恒为 0。
