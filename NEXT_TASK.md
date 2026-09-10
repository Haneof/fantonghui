# NEXT TASK · Task 5 复验 → Task 6 收尾 → Curve/Evidence 契约冻结

- 签发：总体架构规划与工程审查 Agent ｜ 2026-09-10 09:45（替代 09-09 版）
- 前置变化：Task 5（Event→World Update）已由云端 Agent 完成并吸收主线（commit eecfe44，stated.py 554 行实装 + 三 schema + T29 验收记录）
- 本单不重做 Task 5，只做复验、收尾与下一层契约冻结

## 任务 A · Task 5 双环境复验（本地 Agent，半天）

1. `git pull` 后在 Windows 跑 `aios/01_os/code/tests/test_s1_t5.py`，记录通过数/失败数/环境/commit
2. WSL2（/opt/aios 同步后）重跑一遍
3. 对照 T29 验收记录十二项逐条打勾
- 禁止：改 stated.py / schemas / 测试文件本身
- 产出：复验记录追加进 T29 文档；Windows+WSL2 全绿 → Task 5 状态置 ACCEPTED

## 任务 B · Task 6 收尾（World Change 广播，1 天）

stated 已产出 world_change（before/after/evidence_events，落库+快照），收尾项：
1. World Change 同步广播到总线主题 `world.change`（帧协议不变，msg 载荷 = canonical world_change.json）
2. `test_s1_t6.py`：广播内容与落库记录逐字段一致；重复事件不产生重复广播（幂等）
3. 下游订阅冒烟：memoryd / attentiond 各加一条订阅日志验证可达（不改其逻辑）
- 允许改：stated.py（仅广播段）、tests/test_s1_t6.py（新增）、T30 任务书
- 禁止：总线帧协议、已验收服务逻辑、schemas 三件套

## 任务 C · Curve/Evidence Runtime 契约冻结（设计文档，不写业务代码）

按 PM 二次评审 + 审查 Agent 补正 + **指挥官架构图（aios/01_os/docs/assets/curve_architecture_v0.png，2026-09-10）**，产出 `aios/01_os/docs/10_CURVE_EVIDENCE_RUNTIME.md`，冻结七项：
1. 曲线主体（entity_id 引用，禁止自带 Identity）
2. 维度类型清单（v1：心率/睡眠/消费/社交频率/深夜指数——全部 SQL 可出；文本情绪维度 v2 另立）
3. 点结构（timestamp/value/source/event_id，未知不填猜测值）
4. 窗口与基线来源（个人基线 = 滚动窗口统计，禁止全局固定值）
5. Evidence 输出结构（curve_id/dimension/window/points/derived/explanation/supporting_events/supporting_world_changes——引用 chg_*，禁止第二套 change 协议）
6. 唯一挂载关系：消费 Canonical Event + World Change，输出只进自己的 Evidence Store
7. 双消费者声明：Wake Policy（证据包）+ AI Runtime（人格状态地图，Sprint 3 上下文装配）
8. 交互节奏参数：平线触发窗口（无波动→主动交互的时长）作为 evolutiond 的 strategy key（可版本化/可回滚/可个性化），设上下限地板与天花板，禁止无界漂移
9. Regret 适用边界：反馈学习只调整社交/节奏类触发，**安全硬规则（EMERGENCY）永久豁免学习**——任何历史反馈不得压低安全唤醒
10. 情境签名规范：Regret 反馈按“曲线情境签名”（哪些维度偏离、方向、社交上下文）记录，同/相似情境才沉默，禁止全局拉黑触发类型；签名置信度低时不得改变行为（对齐 03 Growth schema 的 confidence/rollback_key）
11. 静默巡检 tick：事件驱动架构对“无事件”失明——新增时钟驱动巡检（定时对比状态快照/曲线窗口），“平线超时”作为一等 Wake 候选条件；巡检零模型、固定周期、可与 attentiond 心跳同节拍
12. 维度注册制：曲线架构与数据供给解耦——曲线只消费 Canonical Event，不关心来源（手环/手机/聊天/模拟器）；每个维度声明（来源事件类型/打分方式/基线策略）后注册生效，新数据源=新注册项，禁止为接新数据改曲线内核；曲线验证用模拟真值独立进行，不等硬件
- 红线：曲线值 = INFERRED，永不写 World State 事实槽位；不调用任何模型/网络；不做第二套 Identity/MODE/Goal
- 产出后由 PM 审查冻结，才允许进入 Curve Runtime 编码

## 架构图增补（2026-09-10，指挥官手绘曲线域全景图 → 待并入契约）

图与已冻结 12 条的对齐：阈值基线触发⑴✓ / 保护系统直触⑨✓ / 全曲线正常 3-5h 主动触发⑪✓ / 用户主动发起（第四触发源，无需学习）✓ / 数据清洗 hub=规范化路径⑫✓ / 时间缩放钻取=AI 上下文装配✓。

**图中新增、待并入契约的机制（契约签署时逐条裁决）：**
- **A1 心里曲线 / 内心数据入口**：不靠外部数据，靠与用户主动/被动交流持续收集材料，反哺更新其它曲线（外部测不到的心理压力，通过对话得知后按时间地点更新情绪/位置曲线）。约束：source=conversation 标记，全部 INFERRED，永不写事实槽位；这是对话作为一类传感器的正式化
- **A2 维度生命周期**：AI 根据用户情况主动生成可挂载维度；所有维度带热值，久未更新降级停维护。约束：热值衰减必须有**时间锚定豁免**（生日/纪念日一年只活跃一次，热值衰减会误杀最重要的提醒）；AI 生成维度走注册审批（evolutiond 可回滚），防维度爆炸
- **A3 跨曲线索引**：关键词超链接（当前世界出现关键词 → 串联 AI 记忆曲线/人生曲线/关系曲线的全部相关记录，快速理解因果）+ 事件锚点（AI 摘要事件打标签，标签进超链接记录）。定位：这就是 02 §4 Memory Runtime"多维索引"的实现载体
- **A4 Wake 加载顺序语义**：AI 进入先查自己记忆树最后状态（自我认知/对用户态度先行），再由维度曲线决定看待用户记忆的方式——"这个顺序不能乱"。并入 05 Wake Session 序列，作为硬约束
- **A5 二级 AI 分身**（后置，Sprint 3+ 预留）：英语教练/娱乐/社交/RPG 等分身共享同一认知底座，各自建各自记忆曲线。约束：persona = identity + 专属曲线视图，依赖 Identity Runtime（entityd）先实装
- **A6 UI 专区**：屏保/一级 UI（AI 形象）/二级 UI（分身列表）——归 Interaction Runtime（Phase 6），不与曲线域耦合，此处仅作产品愿景记录

## PM 讨论采纳裁决（2026-09-10，指挥官×PM 记忆专题讨论，经审查 Agent 核定）

1. **记忆哲学定稿**：废除“压缩”措辞——记忆是全量语义保留 + 多维索引 + 多层观察（Summary Dimension 为观察视图之一）；金字塔机制不变（实现本就是全保留+溯源），仅文档措辞更新
2. **三记忆维度**：User Life Memory / AI Self Memory / **AI Attitude（对用户关系模型，独立第三维）**——宪法三树隔离不变量不变，Memory Fabric/三条记忆维度为三棵树的实现视图组织，映射写入规格文档
3. **AI 进入世界 7 步协议**：Identity → Attitude → Memory Links → User World → World State → Cognition → Think；结尾 Self Memory / Attitude 更新——并入 05 Wake Session 契约（与 A4 合并）
4. **Anchor Index / Semantic Link / Event Anchor**：列为 Memory Runtime 多维索引的实现载体，Sprint 2-3 实现
5. **漏斗数字定稿**：30万信号→几万语义事件→几百 World Change→几十候选→几个真唤醒
6. **治理红线**：升级现有 00-09 为 v0.2 并入上述机制，**禁止另起平行文档集**；讨论记录去重后归档 Git（§62）
7. **停止概念讨论**：进入规格落地（本文件任务 A/B/C 即首批执行单）

## 完成后下一任务

Sprint 2 正式开工（Dedup → Sliding Window → Clustering → Trend → Baseline → Relevance → Attention → Wake 四级），Curve/Evidence Runtime 作为其中 Evidence 层实现——gate_rules 内核换 canonical 四级命名后挂入，636 题回归测试作为守门。
