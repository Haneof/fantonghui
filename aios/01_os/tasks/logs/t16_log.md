# T16 工作日志（M2 · decisiond 决策系统）

## 2026-09-09 02:53 | 决策代理（subagent）

### 派单
- 任务 T16：实现 `services/decisiond.py`（非对称阈值 + INFERRED≠KNOWN 校验）。
- 契约依据：`tasks/contracts_m2.md §T16`、`tasks/contracts.md §2 §4`。

### 实现内容（services/decisiond.py）
- 标准库 `os / sqlite3 / sys / uuid / pathlib` + `aios_sdk.AIOSService`，UTF-8。
- 订阅 `sys.decision.request`、`evt.normalized`。
- 判定只读 `run/cognitive_tree.db`：`sqlite3.connect("file:...?mode=ro", uri=True)`，
  每次新建并关闭，绝不写；读不到行 / 库表不存在 / 只读异常 → 一律视作引用缺失。
- `decide(req)` 判定顺序严格（契约 §T16）：
  1. cites 任一查无 → `{verdict:"REJECT", reason:"CITATION_MISSING", ids:[...]}`
  2. cites 任一 `epistemic != "KNOWN"` → `{verdict:"REJECT", reason:"INFERRED_AS_KNOWN", ids:[...]}`
  3. `risk_class=="FINANCIAL"` 且 `action in {pay,execute,transfer}` → `{verdict:"REQUIRE_CONFIRM", reason:"FINANCIAL_HIGH_RISK"}`
  4. 否则 → `{verdict:"ACCEPT"}`
- cites 为空列表 → 无引用 → ACCEPT（v0 约定）。
- 回 `evt.query.reply.<req_id>`；`evt.normalized` v0 仅接收。

### 自测结论
- `python -m py_compile services\decisiond.py` → **exit=0 通过**。
- 内联单测 `python services\decisiond.py --selftest`（临时库手工插入 1 条 INFERRED + 1 条 KNOWN）→ **5/5 全绿**：
  - empty cites → ACCEPT
  - CITATION_MISSING（引用 ghost）
  - INFERRED_AS_KNOWN（引用 inf-1）
  - FINANCIAL_HIGH_RISK（KNOWN + FINANCIAL/pay → REQUIRE_CONFIRM）
  - KNOWN SAFETY → ACCEPT
- 只读 URI（mode=ro）读取路径已被单测实际走到并验证。

### 契约符合性
- 判定顺序 1→2→3→4 与契约 §T16 完全一致；reply 主题与载荷字段一致。
- 只读连接、绝不写 cognitive_tree.db（符合「决策代理只读认知树」物理隔离）。
- 文件所有权：仅写 `services/decisiond.py`，未触碰 cognitiond.py / cognitive_tree.db / 其它。

### 遗留
1. 集成验收由指挥官执行 `tests/test_m2.py`（本代理未跑全栈）。
2. 安全护栏约束：本环境拦截「Python destructive file API」（shutil.rmtree / tempfile.mkdtemp 等），
   因此自测的「清理临时库」改为 **SQL 级清空（DELETE FROM）**，未用文件删除 API；
   空表残留文件位于系统临时目录 `%TEMP%\decisiond_selftest_cognitive_tree.db`，可安全忽略/由系统回收。

## 2026-09-09 03:05 | 最高指挥官
- 验收：test_m2.py 全栈实测，T16 相关项全部 PASS
- 结果：**通过 ✅**

> **执行方式**：M2 恢复多代理并行——3 路代理用 DeepSeek V4 Pro（zai/tdpsk_deepseek-v4-pro-202606）并发开发（认知 4m6s / 租约 4m54s / 决策 9m54s），首次协同即通过验收。验收套件 test_m2.py 由指挥官编写（期间修正了测试脚本自身的 2 处 bug：漏 sub 订阅 + makefile 超时读法脆弱），代理代码本体零返工。test_m2.py 8/8 全绿。
