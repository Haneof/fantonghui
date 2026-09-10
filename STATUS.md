# AIOS 当前开发状态表（唯一权威）

- 生成：2026-09-10 ｜ 维护者：总体架构规划与工程审查 Agent
- 对照基准：根目录 12 份 Canonical 文档（00-09 + Constitution V1.2-r1）
- 实现基线：`aios/01_os/`（本地 Agent 实装线，130+ 文件）
- 规则：本表是唯一状态源；禁止依据本表重建项目；Task 4 不重做

## 一、运行时对照总表（Canonical 契约 → 实际实现）

| Canonical 运行时/契约 | 实现载体（aios/01_os） | 状态 | 证据 / 缺口 |
|---|---|---|---|
| Event Runtime（去重/排序/窗口聚合/Entity 关联） | hublinkd（持久化队列 829条/秒）+ 总线 | 部分完成 | 持久化✓（kill-9 零丢失实测）；**去重/窗口聚合/聚类未做**（Sprint 2） |
| World Runtime / State Runtime（快照+**Delta**） | stated.py | **未完成（空壳）** | 17 行空壳；Task 4 交付物在 arena 旧分支 core/（骨架），主线无可运行世界状态 |
| Entity / Identity Runtime | entityd.py | **未完成（空壳）** | 17 行空壳；实体数据目前由 memoryd 侧带式覆盖 |
| Memory Runtime（时间轴/多级摘要/索引；事实与推断隔离） | memoryd v3 + cognitiond（INFERRED≠KNOWN） | **已完成** | 六跳摘要金字塔 31,032→1 全通；主题/域索引部分缺（Sprint 后补） |
| Relevance Runtime（score+reason） | tests/gate_rules.py（原型） | 部分完成 | 636 题实测 100%，但**在 tests/ 未接入总线运行时**（Sprint 2 任务） |
| Attention Runtime（score+lease，非 LLM） | attentiond（算力租约 v0） | 部分完成 | 租约发放/回收✓（M2 验收）；relevance/attention 评分函数未接 |
| Wake Runtime（NO_WAKE/MICRO_WAKE/AI_WAKE/EMERGENCY） | modelrouterd 三态路由 + T28 门控设计 | 部分完成 | 三态≈四级（缺 MICRO_WAKE 显式层与 EMERGENCY 旁路）；**Active Watch 未实现**（验收 F） |
| AI Runtime（Wake Session 10 步 / 10 类结构化输出） | cognitiond + decisiond | 部分完成 | 认知/决策链路✓；AI 持久 identity、Cognitive Tree 独立树、10 类输出枚举未成形（Sprint 3） |
| Model Router（模型可换，AI 身份/认知/成长不变） | modelrouterd v2（本地 llama + 云端池） | **已完成** | M3 断网降级验收✓；千题实测四档模型 |
| Capability Runtime（AI→Capability→Permission→Safety→Adapter） | abilityd.py | **未完成（空壳）** | 17 行空壳（Phase 5） |
| Permission/Safety | privacyd（授权状态机✓）+ safetyd | 部分完成 | privacyd M1 验收✓；**safetyd 空壳**，EMERGENCY 硬规则未落地 |
| Interaction Runtime | interactd（五级介入通道✓） | **已完成** | M3 验收：最低打扰选择逻辑 |
| Evolution Runtime（judgment/action/outcome/lesson/可回滚） | evolutiond（strategy_versions 版本链） | **已完成** | M3 Regret 闭环+回退验收✓；outcome 全量回流待接（Phase 7 收尾） |
| MODE 引擎（Relevance 因子） | modemgrd.py | **未完成（空壳）** | 17 行空壳 |
| 设备适配（Simulator/Phone/Wearable） | simulator/simd.py + 数据集（31,399 条/90 天） | 部分完成 | Simulator 回放✓；Phone/Wearable Adapter 未启动（Phase 8/9，按计划靠后） |
| Schema（03 的 Event/Entity/WorldState/Change/Cognition/Growth/Decision JSON） | schemas/*.proto.md + DB 表 | 部分完成 | 语义对齐、字段名不对齐（见冲突 2）；Task 5 起逐步采纳 |

## 二、Canonical 验收测试 A-J 现状

| # | 验收项 | 状态 | 说明 |
|---|---|---|---|
| A | 世界连续性（24h 注入/实体不丢/可回放） | 部分完成 | 数据层 90 天回放✓；缺 stated 实装后的正式验收 |
| B | 过滤压力（10,000 事件，AI 调用 ≤1%） | 未完成 | 千题基准测的是答题能力；漏斗式压力测试未跑 |
| C | 趋势测试（110→120→130→145+无运动） | 未完成 | gate_rules 是单事件模式；序列趋势检测未实现 |
| D | 行为偏离测试（基线偏离） | 未完成 | 需个人基线组件（T28 设计已含，未落地运行时） |
| E | 未知场景不静默丢弃 | 部分完成 | 规则引擎默认 LOCAL 留档✓（设计符合）；未做正式验收 |
| F | Active Watch（AI 布置观察任务） | 未完成 | 全仓库无 Watch 实现——**Canonical 核心机制缺口** |
| G | 三棵树隔离（错误判断不入 Memory 事实） | **已完成** | M2 验收：INFERRED 当 KNOWN 被拒绝 |
| H | 模型切换（Identity/Cognition/Growth 不丢） | 部分完成 | 降级路由✓；缺一次显式"切换后三树完整"验收 |
| I | Action 安全（越权必须被拦） | 未完成 | 依赖 abilityd+safetyd（均空壳） |
| J | 结果回流（Action→Outcome→Evolution） | 部分完成 | evolutiond Regret 环✓；Action 侧源头未接 |

## 三、冲突清单（只标记 + 唯一推荐）

| # | 冲突 | 唯一推荐处理 |
|---|---|---|
| 1 | 仓库布局：06 要求 `aios-core/core/{world,event,...}`；实际主线是 `aios/01_os/`（bus+services）；arena 旧分支另有 core/ 骨架 | **aios/01_os 为唯一实现主线**；canonical 模块名按下表映射到现有服务；旧分支 core/ 留作参考，不并入不删除 |
| 2 | Schema 字段：03 用 `id/timestamp/entities/location_id/raw_ref`；实际总线帧 `{t,topic,msg{ts,source,content,confidence}}` | 传输帧协议**不动**；从 Task 5 起在世界边界采纳 03 JSON 作为载荷规范（schemas/event.json + world_state.json），hublinkd→stated 之间做规范化适配 |
| 3 | Wake 术语：04 四级 vs 现有三态（IGNORE/LOCAL/ESCALATE） | 保留规则引擎内核（T28 实测 100%），对外命名改用 canonical 四级；EMERGENCY 由 safetyd 硬规则旁路（随 Sprint 2 落地） |
| 4 | 宪法双文件：`AIOS_Constitution_V1.2-r1.md`（448 行）与 `AIOS宪法.md`（989 行）并存 | **-r1 为唯一 WHY 权威**（00_START_HERE 明示）；989 行版与 aios/00_宪法 均为历史参考，不修改不删除 |
| 5 | "Task 4 已交付" vs 主线 stated 空壳 | Task 4 交付物=arena 旧分支 core/ 骨架（保留不动）；主线在 **Task 5 内补齐等价可运行能力**（属 T5 载体，不构成重做 Task 4） |

## 四、模块映射表（冲突 1 的唯一官方映射）

| Canonical 模块 | 主线实现 |
|---|---|
| Event Runtime | hublinkd + aios_busd |
| World/State Runtime | stated（Task 5 实装） |
| Entity/Identity Runtime | entityd（后续 Sprint 实装） |
| Memory Runtime | memoryd |
| Relevance/Attention/Wake | gate_rules 原型 → attentiond（Sprint 2 产品化） |
| AI Runtime | cognitiond + decisiond |
| Model Router | modelrouterd |
| Capability/Permission/Safety | abilityd + privacyd + safetyd |
| Interaction | interactd |
| Evolution | evolutiond |
| Adapters | simulator/simd.py |
| MODE | modemgrd |

## 五、阻塞清单

| 项 | 类型 | 影响 |
|---|---|---|
| GitHub git 协议间歇性连接重置 | 运维 | 推送需重试；不影响本地开发 |
| Qwen3.5-4B 与 llama.cpp 0.4.0 兼容性 | 已挂起 | 不阻塞任何 Canonical 任务（用户裁定） |
| 云端子代理通道 | 已绕开 | 千题标准已由指挥官本人全量作答（90.6%） |

## 六、下一个实际开发任务

→ 见根目录 `NEXT_TASK.md`：**Sprint 1 · Task 5 —— Event → World Update**（实装 stated，采纳 03 Schema，含回放确定性验收）

之后顺序：Task 6（World Change Delta）→ Task 7（模拟器规范化对接）→ Sprint 2（去重/窗口/聚类/趋势/基线/Relevance/Attention/Wake 产品化 + Active Watch）→ Sprint 3（AI Identity/Cognitive Tree/Growth Tree/World Access Session/结构化输出）。

## 七、红线重申

1. 不重做 Task 4；2. 不重建架构、不建第二套实现；3. 不批量删除 130+ 文件；4. 不改宪法；5. 未通过 Phase 3/4 验收前不得宣称 AIOS 完成。

---

## 增补（2026-09-10 09:45）：Task 5 已完成并吸收进主线（依据 commit eecfe44，已逐项验证）

| 项 | 状态变更 |
|---|---|
| World/State Runtime（stated.py） | ~~未完成（空壳）~~ → **MAINLINE_INTEGRATED**：554 行实装，11 条确定性映射，world_state.db 四表，幂等/陈旧/非法三重防护，零模型零网络 tripwire；待双环境复验后 ACCEPTED |
| Entity Runtime（entityd.py） | 空壳 → 轻量占位（被引用未登记实体落 UNKNOWN，confidence 0.0，不做身份推断）；Identity 正式能力仍 NOT_STARTED |
| Schema（03 对齐） | 部分完成 → **event.json / world_state.json / world_change.json 三件套落地**（canonical 逐字节副本，测试锁定） |
| Sprint 1 · Task 5 | ✅ 完成（云端 Agent 执行，含 T29 十二项验收记录）；Sprint 1 剩 T6 收尾（world.change 广播）+ T7 规范化对接 |
| 下一任务 | 见 NEXT_TASK.md：Task 5 双环境复验 → Task 6 收尾 → **Curve/Evidence Runtime 契约冻结**（七项：主体/维度/点结构/窗口/基线来源/Evidence 输出/world.change 唯一挂载） |

审查附注：PM 二次评审（已读源码）事实核对通过；其 Curve/Evidence 挂载方案采纳，补一条——曲线存储双消费者（Wake 证据包 + AI Runtime 人格状态地图），Sprint 3 上下文装配依赖后者。