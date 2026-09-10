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

按 PM 二次评审 + 审查 Agent 补正，产出 `aios/01_os/docs/10_CURVE_EVIDENCE_RUNTIME.md`，冻结七项：
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
- 红线：曲线值 = INFERRED，永不写 World State 事实槽位；不调用任何模型/网络；不做第二套 Identity/MODE/Goal
- 产出后由 PM 审查冻结，才允许进入 Curve Runtime 编码

## 完成后下一任务

Sprint 2 正式开工（Dedup → Sliding Window → Clustering → Trend → Baseline → Relevance → Attention → Wake 四级），Curve/Evidence Runtime 作为其中 Evidence 层实现——gate_rules 内核换 canonical 四级命名后挂入，636 题回归测试作为守门。
