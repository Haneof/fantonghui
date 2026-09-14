# M0 Gate — B8 / B9 红队中断续审与总工程师修复记录

日期：2026-09-14  
角色：`chief-01`  
状态：**PATCH GREEN / WAITING INDEPENDENT ARCHITECT CONTINUATION — NOT FINAL PASS**

## 1. 来源

第三轮 `architect-01` 复审因 Work 额度耗尽未完成云端 `LATEST.md` 更新。截图中明确留下两项待提交问题：

- B8：跨进程集合序列化可导致同一请求无法重放；
- B9：包含单词 `busy` 的非锁型内部 SQLite 错误会被误判为可重试锁冲突。

治理分支 `LATEST.md` 仍是上一轮审计旧报告，因此不能把截图当成正式 architect verdict，也不能伪造 GPT-6 PASS/BLOCKER 报告。Chief 只把这两项作为可复现红队输入继续独立验证和修复。

## 2. B8 独立复现

Chief 新增 `tests/unit/test_m0_gate_fourth_followup.py`，使用两个不同 `PYTHONHASHSEED` 启动两个独立 Python 进程，提交相同 logical request，其中 OperationRequest.arguments 与 Observation.value 都含 set。

预修复 CI：

- commit: `83a23302ff3c88a409db988059c03e5ec27a7ace`
- run: `34831346707`
- job: `103935164027`
- formal: **418 passed / 2 failed / 1 warning**
- B8 失败为第二进程同 key 同 logical request 得到 `IDEMPOTENCY_CONFLICT / request_fingerprint_mismatch`。

根因：Pydantic 将 set JSON 化为 list，但 list 元素顺序受进程 hash seed 影响；持久化 JSON 与后续 fingerprint 没有共享跨进程 deterministic unordered-collection representation。

## 3. B9 独立复现

同一预修复 CI 中执行：

`SELECT * FROM busy_missing_internal_table`

SQLite 返回普通 `OperationalError`，错误文本包含 `busy` 只是因为表名包含 busy。旧分类器使用字符串包含判断：

`"locked" in message or "busy" in message`

因此错误地映射为：

`VERSION_CONFLICT / storage_busy`

而不是 `STORAGE_FAILURE / sqlite_operational_error`。

## 4. 修复

B8：

- 新增 deterministic durable JSON canonicalization；
- ordered list/tuple 保持顺序；
- set/frozenset 先递归 canonicalize，再按 canonical JSON 排序；
- OperationRequest arguments 持久化与 fingerprint 共用同一 canonical representation；
- WorldObject durable payload 与 fingerprint 共用同一 canonical representation；
- 避免 Python hash randomization 改变 exact retry identity。

B9：

- 不再用错误字符串包含 `busy/locked` 判断锁冲突；
- 使用 `sqlite_errorcode` 的 SQLite base result code；
- 只有 `SQLITE_BUSY` / `SQLITE_LOCKED` 映射 `VERSION_CONFLICT / storage_busy`；
- 其它 OperationalError 继续映射 `STORAGE_FAILURE`。

语义 repair commit：

`659157b849a0dbaad241c3e316dcd98eb7c72df7`

## 5. 修复后验证

修复后的生产 source + 本记录归档 HEAD：

`d180091c73be63bcce680748048ef731316f848b`

Exact CI：

- run `34831608087`
- job `103935994524`
- Ubuntu 24.04.5
- CPython 3.12.14
- pytest 8.4.2
- formal：**420 passed, 1 known warning**
- Reference：**15 passed**
- conclusion：**SUCCESS**

关键事实：原先两个失败的 `test_m0_gate_fourth_followup.py` 现均通过；全量 M0 回归及四个 Gate fixture、schema snapshot、Reference suite 同时保持绿色。

## 6. Gate 状态

**NOT FINAL PASS。**

第三轮 architect 的云端正式报告没有完成，不能由 chief-01 冒充 GPT-6 补签。

后续有 architect-01 额度时，必须从 B8/B9 修复后的 semantic candidate `659157b...`（或仅文档领先的等价 archive HEAD）继续独立复审，并重新审查 B6/B7/B5/R4 + B8/B9 + 全局 M0 regression。

在独立架构复审给出可接受 verdict 且 chief-01 最终签 Gate 前：

- M0 不恢复 22/22 FINAL PASS；
- M1 不开始；
- 并行核心开发不启用。
