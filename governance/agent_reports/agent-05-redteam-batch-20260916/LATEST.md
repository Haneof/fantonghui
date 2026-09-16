# agent-05 独立红队验收批次报告（2026-09-16）

**批次代号**：`agent-05-redteam-batch-20260916`
**分支**：`arena/01a0a700-fantonghui`（会话锁定分支；工单要求的 `arena/agent-XX-*` 分支因会话锁无法使用，此映射提请总师知悉）
**基线**：`7785aed`（M1-018 增量硬化合流点），全仓 **651 passed**
**验收结果**：全仓 **704 passed**（651 基线 + 53 新增红队测试），零失败、零跳过

---

## 0. 执行原则（总师指令）

- 四个工单**逐个跑完**，各自独立提交并推送；
- **不要覆盖任何版本**：所有交付物均为**新增文件**（独立命名），
  既有实现（`world/retrospective_annotation.py`、`cockpit/pipeline.py`、
  `wake/dispatcher.py`、`ingest/multimodal_edge.py`）与既有门禁测试
  （`test_m1_018_retrospective_annotation.py`、`test_m2_009r_cockpit_budget.py`、
  `test_v22_acute_cardiac_fall_safety.py`、`test_m1_001r_high_entropy_audio.py`）**一行未动**；
- **独立起名**：新增模块 `v22_hardware_first.py`，四个红队测试文件
  `*_independent_redteam.py` / `*_adv_independent_redteam.py`；
- 严禁低幼化样例：全部测试数据采用工单指定的高熵场景
  （商业对赌反转、职场降薪/调岗/竞业危机、03:15 心血管+晕厥跌倒、85dB 车间+24 人跨国圆桌）。

---

## 1. M1-018 独立红队验收层（14 项）

**文件**：`tests/unit/test_m1_018_independent_redteam.py`
**复核对象**：M1-018 老王案（`world/retrospective_annotation.py`，含 `b0c540a` 与本分支 `7785aed` 增量硬化）

| 对抗口径 | 结论 |
|---|---|
| 倒写历史强校验：`learned_at < target_time_end` / `recorded_at < learned_at` | ✅ 违宪拒绝（ValueError），双规则独立生效 |
| 双时间戳均缺省 → 共享同一 now 锚点（`learned_at == recorded_at`，与真实时钟 ±5min 同源） | ✅ |
| 图层零提前泄露：知识时刻早于获知时刻严格不可见，获知瞬间可见 | ✅ |
| naive 事实/锚点按 UTC 契约归一化（无注记路径） | ✅ |
| naive 切片锚点 × aware 注记 overlap 路径 | ⚠️ **已知缺口留档**（见 §4-2），不改既有版本 |
| 跨账本实例哈希确定性（480 条同事实 → 同 SHA-256 矩阵 + 同总指纹） | ✅ |
| Unicode/嵌套载荷规范哈希稳定（key 序、ensure_ascii、分隔符） | ✅ |
| 非 JSON / 非 dict 载荷 fail-closed | ✅ |
| 级联动态图：失效后新增下游**不**被回溯标记；重复失效幂等；二跳节点不受污染 | ✅ |
| `max_hops != 1` fail-closed（含 0 / 2 / 负数） | ✅ |
| 万级独立复测：2,000 事实 + 3,211 节点 5 层网络，单跳失效恰 10 个一级节点、深度严格 1、重算 0 次 | ✅ |

**M1-018 工单复核说明**：本工单已以 `b0c540a` 交付（本会话早前提交），
`8f21987`（并行会话版本）亦保留于历史；按总师指令本批次**只做独立红队复核、不重新交付、不覆盖任何版本**。

## 2. M2-009R 独立红队验收层（11 项）

**文件**：`tests/unit/test_m2_009r_independent_redteam.py`
**复核对象**：M2-009R 高密危机防爆（`cockpit/pipeline.py`）

| 门禁 | 对抗口径 | 结论 |
|---|---|---|
| 单看板 ≤1500 token | 200 轮深滚动全程逐轮断言 | ✅ 每轮 `token_count ≤ 1500` |
| 6 轮易变窗口无损 | 100 次调用 = 200 轮（用户+老友）；窗口恰 6 / 归档 194 / 总量 200 | ✅ 全量 = 归档 + 窗口，round_id 无重无漏 |
| 争议点证据链 | 10 条关键争议点跨窗口驱逐全程有序无损 | ✅ |
| 组装 P95 ≤15ms | 200 次组装实测 P95 | ✅ 远低于红线 |
| 20k 字巨型轮 | 第 25/60 轮注入 20,000 字碎片 | ✅ 全部看板 ≤1500 token，峰值 <100ms |
| BrevityGuard 说教拦截 | 5 句模式规避说教 → 结构截断 + `TOO_MANY_SENTENCES`；2 句说教被剥离；长 3 句 ≤120 字硬切 | ✅ |
| 空回复兜底 | `""` → 宪法兜底句（1~3 句约束成立、非空、留审计痕） | ✅ |
| 纯标点输入 | "…………" → 结构约束成立（1~3 句）但信息量为零 | ⚠️ **已知弱点留档**（见 §4-3） |
| 提示词字节级确定性 | 同状态 + 显式 `occurred_at` → 两次组装 prompt 逐字节一致 | ✅（须显式 `occurred_at`，`process_round` 缺省走 `_utc_now`） |
| 冻结模型 | `ConversationRound` frozen，字段改写失败 | ✅ |
| execute() 调度入口 | P2 唤醒 → `COCKPIT_ASSEMBLED`，prompt ≤1500 | ✅ |

## 3. M0-023-V22 独立红队验收层（11 项）+ 失败安全入口（纯增量模块）

**文件**：`tests/unit/test_v22_independent_redteam.py` + **新增** `src/aios_core/wake/v22_hardware_first.py`
**复核对象**：M0-023-V22 跨模态心血管突发（`wake/dispatcher.py` V1 主链，未触碰）

| 对抗口径 | 结论 |
|---|---|
| V1 主链畸形 P0 行为留档 | 硬件脉冲**先发出**（SOS 不静音），随后收据阶段 `AttributeError` —— 审计回执丢失（见 §4-1） |
| `safe_dispatch_v22` 畸形 P0 降级路径 | ✅ 端到端 ≤50ms；`SAFETY_BYPASS_EXECUTED_DEGRADED`；`audit.hazard_type=None`（不伪造险情类型） |
| `hazard_type` 属性缺失 | ✅ 同样降级，`vital_snapshot` 透传脉冲 |
| 脉冲失败回执诚实性 | ✅ `hardware_action_dispatched=False`（含审计回执内），绝不假报成功 |
| 良构 P0 委托 V1 | ✅ 行为与审计队列语义不变，回执 FIFO（`rcpt_safe_*` 序） |
| 复合体征快照逐字节透传 | ✅ 03:15 时钟 / pvc_run 4 / 165bpm / 5.2G 三轴 / deep_sleep 上下文，脉冲 payload 逐字节一致 |
| 100 次 P0 突发 | ✅ 全部 ≤50ms（实测最差 <20ms 留档） |
| 5ms 慢脉冲（蜂窝抖动） | ✅ 端到端仍 ≤50ms |
| 非 P0 隔离 | ✅ 零脉冲 / 零队列 / 看板恰好 1 次 |
| 非 P0 无 context | ✅ fail-closed（ValueError） |
| 脉冲调用点单点化 | ✅ 新入口经 `dispatcher` 模块命名空间延迟绑定，与 V1 主链同一调用点（升级/spy 对两路径同时生效） |

**设计声明**：`v22_hardware_first.py` 是独立命名的纯增量模块 ——
不修改 `dispatcher.py` 一行；良构 P0 直接委托 V1；畸形 P0 才走失败安全降级路径；
非 P0 语义与 V1 一致（无 context 时 fail-closed）。

## 4. 红队审计发现（3 项，均留档测试，未改既有版本）

1. **V22 畸形 P0 审计回执丢失**（严重度：中 —— 人先被救，法律责任溯源受损）
   V1 主链 `dispatch_wake_event` 对畸形 `safety_bypass` 在脉冲发出后、构造收据时抛
   `AttributeError`。调用方拿到裸异常而非可审计结果。
   **处置**：新增 `safe_dispatch_v22` 兜底入口（降级可审计回执），V1 保持原样。
   生产侧后续可将调度入口切换至 `safe_dispatch_v22`（良构路径零行为差异）。
2. **M1-018 naive 切片锚点 × aware 注记 overlap 崩溃**（严重度：低 —— 边缘调用口径）
   `BiTemporalEpistemicLens.query_historical_slice` 在 `_ranges_overlap` 比较前
   未归一化切片边界（事实侧/视图侧均归一化，唯 overlap 路径漏归一化）→ `TypeError`。
   **处置**：留档于红队层 `test_known_gap_naive_slice_anchor_vs_aware_annotation`，
   **提请总师裁定**是否在下个增量版本做 2 行归一化硬化（本批次不改既有版本）。
3. **BrevityGuard 纯标点输入**（严重度：低 —— 结构门禁不受影响）
   "…………" 被计为 1~3 句"标点句"，信息量为零。1~3 句硬约束仍成立。
   **处置**：留档 `test_punctuation_only_reply_audit`，信息量兜底列为增强候选。

## 5. M1-001R-ADV 独立红队验收层（17 项）

**文件**：`tests/unit/test_m1_001r_adv_independent_redteam.py`
**复核对象**：M1-001R-ADV 高熵工业/商务（`ingest/multimodal_edge.py`）

| 门禁 | 对抗口径 | 结论 |
|---|---|---|
| 画质分 <0.4 物理粉碎 | 2,000 张垃圾图（1~4KB）+ 500 张合格图：purge 释放字节精确等于垃圾总量，残留严格 0 | ✅ |
| RawByteSink 契约 | 未知 id purge → 0；重复 purge → 0（幂等）；重复 sink → `ValueError`（单写）；空 id → 拒绝 | ✅ |
| 3,000 张粉碎线性缩放 | ≤30ms 预算（5ms×500 张口径 ×6 线性放大） | ✅ |
| 画质 0.4 边界 | 0.3999 拒 / 0.4 收（`evaluate_and_clean_image` 全链路，`raw_image_bytes_retained=False`） | ✅ |
| 昏暗崩塌 | `luma<40` → 总分 ×0.3 → 0.207 < 0.4 拒 | ✅ |
| 显式分优先 | `quality_score` 显式传入绕过传感器合成 | ✅ |
| 24 人 LSH 纯净 | 24 声源 × 30 交织切片 = 720 条，`assign_slice` 100% 归位 | ✅ |
| 类内/类间汉明间隙 | 同人切片最大类内距离 < 任意两参考签名最小类间距离 | ✅ |
| 同人重现 | 核心伙伴再出现（σ=0.03）→ top-1 正确且汉明 ≤3 | ✅ |
| 未知第 25 人 | 陌生人 top-1 距离 > 类内噪声水平 → **异常可检测**（`assign_slice` 无距离阈值会误归位，需 `candidate_search` 距离裕度识别，留档为生产接线建议） | ✅ |
| 签名形态 | 128 位 LSH 签名非退化（0 < 置位数 < 128） | ✅ |
| 注册契约 | 非 128 维拒绝；重复注册拒绝；未知 id 查询 KeyError | ✅ |
| TTL 整点边界 | 179d23h59m59s 仍活跃；**恰满 180 天瞬间**严格墓碑（`>=` 边界） | ✅ |
| 错峰到期 | 5 个不同接触日声纹各自在"接触日+180d"瞬间单独到期 | ✅ |
| 360 天工单规模 | 15 未绑定背景人声全部墓碑；8 名绑定核心商务伙伴永驻热表 | ✅ |
| 墓碑复活 | 第 200 天再次接触 → 回热表；从复活时刻重新计 180 天（第 380 天再次墓碑） | ✅ |
| 绑定豁免 | 绑定伙伴 360 天无接触也不墓碑 | ✅ |

---

## 6. 提交与谱系

- 提交 1：`test(world): M1-018 独立红队验收层…`
- 提交 2：`test(cockpit): M2-009R 独立红队验收层…`
- 提交 3：`feat(wake): M0-023-V22 失败安全入口 v22_hardware_first + 独立红队验收（纯增量，不覆盖 V1 主链）`
- 提交 4：`test(ingest): M1-001R-ADV 独立红队验收层…`
- 提交 5（治理）：本报告 + `docs/specifications/TASK_PROGRESS_V3.md` 第三节登记

既有版本 `b0c540a` / `8f21987` / `29d115f` / `db40aa0` / `0f097c4` 全部保留于历史，未被覆盖。

**回归证据**：`PYTHONPATH=src python -m pytest` → **704 passed**（沙箱实测，2026-09-16）。
