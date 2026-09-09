# AIOS M3 接口契约（冻结版）· T17-T19

> 上位契约：tasks/contracts.md（总线/SDK 不变）+ contracts_m2.md（认知树/租约已冻结）。
> 三棵树至此补全：人生树（M1 memoryd）+ 认知树（M2 cognitiond）+ 成长树（M3 evolutiond）。

## T17 interactd（交互代理）· 五级介入通道选择

- 订阅：`evt.normalized`、`sys.interact.request`
- 通道等级（最低打扰优先，能低不高）：`VISUAL(0) < HAPTIC(1) < BONE_CONDUCTION(2) < EXECUTE(3)`；另有 `SILENT_WATCH` 表示不介入
- `sys.interact.request` `{req_id, risk_class, priority}` → 按非对称规则选通道：
  - `risk_class=="SAFETY"` → `HAPTIC`（保命至少震动，可跨级）
  - `risk_class=="SOCIAL"` → `priority=="high"` ? `BONE_CONDUCTION` : `VISUAL`（社交默认静默，不打断谈话）
  - `risk_class=="FINANCIAL"` → `HAPTIC`（需用户注意，配合二次确认）
  - 其它 → `VISUAL`
  - 结果发布 `evt.intervention` `{intervention_id, risk_class, channel, priority, ts}`，并回 `evt.query.reply.<req_id>` `{intervention_id, channel}`

## T18 evolutiond（进化代理）· Intervention Regret 对账闭环 + 成长树

- 订阅：`evt.intervention`、`sys.interact.feedback`
- 成长树唯一写者：`run/growth_tree.db`（SQLite WAL，synchronous=NORMAL）：
  ```sql
  CREATE TABLE IF NOT EXISTS growth (
    id TEXT PRIMARY KEY, situation TEXT, ai_judgment TEXT, ai_action TEXT,
    user_feedback TEXT, actual_result TEXT, was_correct INTEGER,
    error_analysis TEXT, lesson TEXT, strategy_update TEXT, confidence REAL, created_at REAL);
  CREATE TABLE IF NOT EXISTS strategy_versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_key TEXT,
    threshold REAL, reason TEXT, created_at REAL, active INTEGER);
  ```
- 阈值模型（内存 + 落库）：按 risk_class 维护介入阈值（0-1，越高越谨慎），初值 SOCIAL=0.5 / FINANCIAL=0.8 / SAFETY=0.1
- `sys.interact.feedback` `{req_id, intervention_id, feedback}`，feedback ∈ accepted/ignored/rejected：
  - accepted → 对应 risk_class 阈值下调 0.05（下限 0.05）
  - rejected → 阈值上调 0.15（上限 0.95）；ignored → 中性（+0.02）
  - 每次变更：写 growth 表 + 新增 strategy_versions 行（active=1，旧行 active=0，可回退）
  - 回 `evt.query.reply.<req_id>` `{risk_class, threshold, was_correct:true/false}`
- `sys.evolve.rollback` `{req_id, strategy_key}` → 回退到上一 active 版本 → 回 `{rolled_back:true, threshold}`

## T19 modelrouterd（路由代理）· 模型路由 + 降级队列

- 订阅：`sys.model.request`、`sys.model.set_offline`、`evt.normalized`
- 路由决策（v0，本地模型为确定性桩，不依赖真实 llama.cpp）：
  - `task_type ∈ {simple_judgment, summarize}` → 本地桩（返回 `local_stub` 结果）
  - `task_type ∈ {complex_reason, deep_chat}` → 云端（v0 无真实 API，返回 `cloud_mock` 结果）
  - 离线模式（收到 `sys.model.set_offline {offline:true}`）→ 所有请求降级：简单任务仍本地，复杂任务进降级队列 `run/model_degrade.json`（append），返回 `{routed:"degraded_queued"}`
- `sys.model.request` `{req_id, task_type, payload}` → 回 `evt.query.reply.<req_id>` `{routed, task_type, result}`
- `sys.model.set_offline` `{offline}` → 回 `{offline}`
- 降级队列：`run/model_degrade.json`（JSON array，每条 {task_type, payload, ts}）

## M3 门禁（tests/test_m3.py，指挥官编写并执行）

1. interactd：SOCIAL 默认 → VISUAL；SOCIAL+high → BONE_CONDUCTION；SAFETY → HAPTIC；FINANCIAL → HAPTIC
2. evolutiond：rejected → SOCIAL 阈值上调；accepted → 下调；rollback → 回退到上一版本；growth_tree.db + strategy_versions 落库
3. modelrouterd：simple→local_stub；complex→cloud_mock；set_offline 后 complex→degraded_queued 且降级队列 append

## 文件所有权

- 交互代理：`services/interactd.py`
- 进化代理：`services/evolutiond.py`
- 路由代理：`services/modelrouterd.py`
- 指挥官：`tests/test_m3.py`
