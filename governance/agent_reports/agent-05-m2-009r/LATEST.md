# M2-009R latest report (session arena/01a0a700-fantonghui)

agent_id: agent-05 (本会话)
role: Cockpit Pipeline Engineer (C03 单看板)
task: M2-009R 高密危机防爆——Single-Shot 单看板 1500 Token 封套
status: PATCH COMPLETE / WAITING CHIEF ENGINEER SANDBOX ACCEPTANCE

branch: arena/01a0a700-fantonghui (会话固定分支，请总工做分支重映射)

production_files_changed:
  - src/aios_core/cockpit/pipeline.py (新增：CockpitPipeline / RollingRoundWindow / ConversationState / ConversationRound / BrevityGuard / BrevityVerdict / SingleShotCockpit / RoundResult / estimate_tokens / SINGLE_SHOT_TOKEN_BUDGET=1500 / ACTIVITY_WINDOW_SIZE=6)
  - src/aios_core/cockpit/__init__.py (新增包导出)
test_files_added:
  - tests/unit/test_m2_009r_cockpit_budget.py (11 项验收断言)

scenario_compliance (严禁低幼化):
  - 50 轮深夜对抗全语料为职业危机实战碎片：恶意降薪 40%、强制调岗 P8→P6、
    竞业协议索赔 300 万、期权行权条件被改、仲裁举证、壳公司章、录音证据链等
  - 9 条关键争议点证据锚跨 50 轮分布（降薪原文/社保基数/竞业范围/补偿缺失/仲裁受理/绩效S/索赔口径/期权回购价/证据锁定）

four_gates_compliance:
  - 门禁1 1500 Token 绝对物理截断：50 轮全流程 token_count <= 1500（逐轮断言 + 独立复算）；
    单轮注入 2 万字级超长文本仍被硬切达标（physically_truncated=True）；
    SingleShotCockpit 模型校验器结构化兜底（token_count > budget 直接 ValidationError）
  - 门禁2 无损滚动：活动窗口恒 6 轮；100 轮全量 = 94 归档 + 6 活动，round_id 序列完整；
    用户 50 条碎片逐字保留；9 条争议点证据含已淘汰轮次全链路无损且顺序与发生序严格一致
  - 门禁3 反爹味 BrevityGuard：长篇五点心理疏导注入 → 强制截断 + PREACH_PATTERN 拦截，
    说教内容全部剥离（1~3 句、<=120 字符、无"积极心态/心理疏导/为您推荐"残留）；
    纯说教回落到合宪兜底句；5 句闲聊截断至 3 句；自然老友线零误伤（intercepted=False）
  - 门禁4 组装延迟：50 轮压测 P95 = 0.126ms（限制 15ms，118x 余量），单次 max = 0.148ms；
    组装只消费活动窗口 + 预聚合证据摘要（O(窗口) 与全量上下文解耦）

tests_run: PYTHONPATH=src python -m pytest
test_result: 本任务 11/11 通过；全量回归全绿（提交前验证）
notes:
  - estimate_tokens 为确定性上界估算（CJK 字符=1 token，ASCII 词=1 token，宁可高估）
  - 说教序号模式要求"第X[，,：:]"标点伴随，避免"第一句"类正常表述误伤
