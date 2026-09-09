# T18 日志 · evolutiond（进化系统：Intervention Regret 对账闭环 + 成长树唯一写者）

- 时间：2026-09-09（M3 冲刺）
- 代理：进化代理（subagent）
- 产物：`code/services/evolutiond.py`（唯一名下文件）

## 完成内容

1. **成长树唯一写者**：`run/growth_tree.db`，SQLite WAL + `synchronous=NORMAL`，建表
   `growth` 与 `strategy_versions`，schema 严格按契约 §T18 逐列对齐（含 `idx_sv_key` 索引）。
2. **订阅**：`evt.intervention` / `sys.interact.feedback` / `sys.evolve.rollback`。
3. **阈值模型**：内存 `_state["thresholds"]` + strategy_versions 落库，按 risk_class 维护，
   初值 SOCIAL=0.5 / FINANCIAL=0.8 / SAFETY=0.1；未知类兜底 0.5。
4. **反馈对账**（`sys.interact.feedback {req_id, intervention_id, feedback}`）：
   - accepted → -0.05（下限 0.05）；rejected → +0.15（上限 0.95）；ignored → 中性 +0.02
   - 每次变更写 growth 一条 + strategy_versions 新行（active=1，旧 active=0）
   - 回 `evt.query.reply.<req_id>` `{risk_class, threshold, was_correct}`
   - risk_class 从 `evt.intervention` 缓存 mapping（`intervention_id -> meta`）解析，
     附「最近一次介入」兜底；缓存超 1000 条丢弃最旧一半防膨胀。
5. **回退**（`sys.evolve.rollback {req_id, strategy_key}`）：strategy_key=risk_class，
   当前 active 行转 0、最近一条 inactive 行转 1，回 `{rolled_back:true, threshold}`；
   无上一版本 → `rolled_back:false` + 当前阈值。
6. **重启恢复**：启动时 `seed_and_load` 补齐初值版本并从 DB active 行恢复内存阈值，
   保证内存与落库一致。

## 自测结论

- `python -m py_compile services\evolutiond.py` ✅ 通过
- 内联单测 `python services\evolutiond.py --selftest` ✅ 15/15 全过：
  - rejected 上调（0.5→0.65）、accepted 下调（0.65→0.60）
  - rollback 回退到上一 active 版本（0.65）、内存阈值同步
  - strategy_versions 行数增长（每次变更 +1）
  - growth 对账行数 = 2（rejected + accepted）
  - 阈值边界：rejected 上限 0.95 / accepted 下限 0.05
  - 无版本 rollback 不翻车（rolled_back=false）
- 测完已清理：临时库仅 SQL 级清空（DELETE），未调用文件删除 API，不污染项目 `run/`。

## 契约符合性

- 仅标准库（json/os/sqlite3/sys/time/uuid）+ aios_sdk + sqlite3 ✅
- UTF-8 编码 ✅；只写 evolutiond.py，未触碰其它名下文件 ✅
- 三棵树物理隔离：本服务只写 growth_tree.db ✅
- 未跑全栈（集成验收由指挥官 test_m3.py 执行）✅

## 遗留

- `confidence` 列 v0 以「介入后新阈值」作谨慎度/置信度代理，语义粗放，待 M 后续细化。
- `ignored` 的 was_correct 约定为 false（仅 accepted 为 true），属 v0 设计选择。
- rollback 只动 strategy_versions（不写 growth），与契约一致，但回退轨迹不落 growth。

## 2026-09-09 03:20 | 最高指挥官
- 验收：test_m3.py 全栈实测，T18 相关项全部 PASS
- 结果：**通过 ✅**

> **执行方式**：DeepSeek V4 Pro 三路代理并发（交互 1m07s / 进化 4m09s / 路由 3m05s），首次交付即通过验收，零返工。test_m3.py 5/5 全绿。
