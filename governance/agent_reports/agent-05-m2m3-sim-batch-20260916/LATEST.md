# agent-05 M2/M3/SIM 实现批次报告（独立命名并存线，2026-09-16）

**批次代号**：`agent-05-m2m3-sim-batch-20260916`
**分支**：`arena/01a0a700-fantonghui`（会话锁定分支；四个工单要求的目标分支
`arena/agent-dispatch-m2-005r` / `arena/agent-wake-m2-001` / `arena/agent-cognition-m3-001r` /
`arena/agent-sim-engine` 因会话锁无法使用，映射提请总师知悉）
**验收结果**：全仓 **849 passed**，零失败、零跳过

## 0. 并行交付与零覆盖处置（本批次关键事件）

四个工单推进期间，并行会话已将同工单的规范实现先行合流至共享分支：
`9df301e`（M2-005R）/ `276473f`（M2-001）/ `4fbe772`（M3-001R）/
`cce3816`（SIM-001），并另交付 M1-018 超集并存线 `8d921ae`
（`world/epistemic_world_lens.py`，2,196 行 + 1,677 行测试）。

并行版本占用了工单指定的规范模块路径。依总师"不要覆盖任何别的文件"铁律
与仓库既定并存先例（`retrospective_annotation_agent05`、`epistemic_world_lens`），
本批次全部交付物转为**独立命名并存线**（`*_agent05`）：

| 工单 | 规范实现（并行会话，一行未动） | 本批次并存线（新增） |
|---|---|---|
| M2-005R | `scheduler/conditional_engine.py` | `scheduler/conditional_engine_agent05.py` |
| M2-001 | `wake/cooldown_queue.py` | `wake/cooldown_queue_agent05.py` |
| M3-001R | `dimensions/evolution_guard.py` | `dimensions/evolution_guard_agent05.py` |
| SIM-001 | `simulation/headless_life_driver.py` + `governance/runtime_policy.json` | `simulation/headless_life_driver_agent05.py` + `simulation/cjk_trigram_index.py` |

配套验收测试同步独立命名（`tests/unit/*_agent05.py`、
`tests/simulation/test_30day_headless_life_simulation_agent05.py`），
与规范实现的验收测试并存、互不依赖。
`governance/runtime_policy.json` 沿用并行会话版本（`monthly_token_budget: 2554000`
与工单口径一致），本批次 SIM 驱动直接读取该规范文件核验封套，未另立口径。
**本批次未修改、未覆盖任何既有或并行版本文件。**

## 1. M2-005R 条件驱动双轨引擎并存线（21 项全绿）

| 门禁 | 达成口径 |
|---|---|
| DORMANT Token 严格 0 | 200 任务场景：195 休眠任务渲染片段严格空串、`estimate_tokens == 0`、任务 id 零泄漏 |
| Level-1 机械快轨 | 时间绝对到期 / 地理围栏 300m 边界 / 晚间心率连续 3 天阈值（`evening_heart_rate_bpm` 独立口径防运动峰值污染）/ 合取条件；200 任务扫描实测 <1ms、LLM 严格 0 |
| Level-2 机会式捎带 | 必须携带用户主动 `wake_ref`（空则 fail-closed）；场景不匹配不成熟；无自主唤醒入口（防退化审计） |
| 非法跃迁 100% 拦截 | DORMANT→RUNNING/COMPLETED、READY→COMPLETED、RUNNING→READY、COMPLETED→任意全部抛 `IllegalStateTransitionError` |

## 2. M2-001 唤醒去重合并队列并存线（17 项全绿）

| 门禁 | 达成口径 |
|---|---|
| 合并窗口 | 250 条 50Hz 脉冲（5s）→ 1 条批次事件（`downstream_wakes`：两波 = 2 次，严禁 500 次）；窗口边界自动关窗；去重统计（100 重复值 unique=1） |
| 冷却硬防护 | 15min 基线 / 被抑制 +5min / 封顶 30min / 确认回落 15min，恒在区间；P0 完全绕过冷却 |
| DEEP_SLEEP 闸 | 一般通知/复盘/任务提醒全部挂起，一般马达振动严格 0；P0 经 `wake.dispatcher` 既有脉冲通道（调用时解析，与 V1 同一调用点）直穿 |
| 无损延递 | 第一安全窗口保序、分组聚合、一条不丢（120 挂起 → 120 延递实测） |

## 3. M3-001R 维度衍生三重门限并存线（19 项全绿）

| 门禁 | 达成口径 |
|---|---|
| 门限一 | 单域 3 天拒 / 双域 2 天拒 / 双域 3 天入池 / 空证据拒 |
| 门限二 | 7/10=0.70 边界恰好达标 → ACTIVE；60% → EXPIRED；零预测 → EXPIRED；100% 准确率无解释力 → EXPIRED |
| 门限三 + 熔断 | 每日反思配额严格 1 次；恶意"反思是否要反思" → 第 2 层递归物理切断（留痕审计） |
| 全局硬顶 | 33 候选：第 33 个晋升时最弱活跃被 ARCHIVED，活跃恰 32；40 候选：32 活跃 + 8 归档，硬顶零击穿 |

## 4. SIM-001 无界面人生仿真器并存线（11 项全绿，30 天跑批 0.64s）

| 门禁 | 达成口径（30 天实测） |
|---|---|
| 720h 高熵时间流 | 昼夜节律逐块校验（深睡 02~05 / 浅睡 00,01,06,23）；120 场真实工作会议；85dB 车间高噪；连续 3 晚 21:00 HR 97~101（老王违约压力）；唯一 03:15 P0；流发生器双跑逐位确定 |
| 完整技术链 | C01：210 图全粉碎（188 收留/22 拒，滞留 0）+ 声纹 24 人 72 切片；C06（`cjk_trigram_index` 自持实现）：123 文档，对赌+回购 **121** 命中、老王+违约 **122** 命中；C02：154 事实哈希封存 + 完整性验证；C04：24 次危机对话装配逐次 ≤1500（峰值 449）；C05：裁定回溯注记零提前泄露 + 当前可见 + 单跳级联恰 4 节点、深层不受污染、重算 0 次；叠加 M2-005R（106 Level-1 + 1 Level-2，三旗舰任务闭环）+ M2-001（18 万脉冲 → 720 批次、P0 直穿 1 次、静默 120/解冻 120）+ M3-001R（1 ACTIVE / 1 EXPIRED / 1 熔断） |
| 0 死锁与内存平稳 | 死锁看门狗 0 次；峰值 RSS **33.9MB** ≤ 128MB；VmRSS 首尾差 ≤ 20MB；原始二进制图片滞留严格 0 |
| 月度 Token 封套 | **8,540** tokens 严格 ≤ 规范 `runtime_policy.json` 的 **2,554,000** 月度预算 |

长时程：180 天（4320h）冒烟 0 死锁 / RSS 平稳 / 事件不重复触发；确定性双跑
（账本指纹 / Token 总量 / 事实数逐位一致）。

**定位声明**：`cjk_trigram_index.py` 为仿真驱动的自持 C06 求交实现
（CJK 二元/三元倒排 + 多词求交），与并行会话规范 SIM-001 内建的
`InvertedIntersectionIndex` 并存，互不依赖、不占用对方路径。

## 5. 提交谱系（并存线 5 提交）

M2-005R → M2-001 → M3-001R → SIM-001 → 治理登记（本提交），
全部叠加于并行会话谱系 `4451e38` → `8d921ae`/`9df301e`/`276473f`/`4fbe772`/`cce3816` 之上。

**回归证据**：`PYTHONPATH=src python -m pytest` → **849 passed**（沙箱实测，2026-09-16）。
