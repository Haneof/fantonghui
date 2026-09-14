# M0 Gate — B8 / B9 红队中断续审与总工程师修复记录

日期：2026-09-14  
角色：`chief-01`  
状态：**PATCH APPLIED / WAITING EXACT CI — NOT FINAL PASS**

## 1. 来源

第三轮 `architect-01` 复审因 Work 额度耗尽未完成云端 `LATEST.md` 更新。截图中已明确留下两项待提交问题：

- B8：跨进程集合序列化可导致同一请求无法重放；
- B9：包含单词 `busy` 的非锁型内部 SQLite 错误会被误判为可重试锁冲突。

治理分支 `LATEST.md` 仍是上一轮审计旧报告，因此不能把截图当成正式 architect verdict，也不能伪造 GPT-6 PASS/BLOCKER 报告。Chief 只把这两项作为可复现红队输入继续独立验证和修复。

## 2. B8 独立复现

Chief 新增 `tests/unit/test_m0_gate_fourth_followup.py`，使用两个不同 `PYTHONHASHSEED` 启动两个独立 Python 进程，提交相同 logical request，其中 OperationRequest.arguments 与 Observation.value 都含 set。

预修复 CI：

- commit: `83a23302ff3c88a409db988059c03e5ec27a7ace`
- run: `34831346707`
- formal: **418 passed / 2 failed / 1 warning**
- B8 失败为第二进程同 key 同 logical request 得到 `IDEMPOTENCY_CONFLICT / request_fingerprint_mismatch`。

根因：Pydantic 将 set JSON 化为 list，但 list 元素顺序受进程 hash seed 影响；持久化 JSON 与后续 fingerprint 没有共享跨进程 deterministic unordered-collection representation。

## 3. B9 独立复现

同一预修复 CI 中，执行：

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

## 5. Gate 状态

本记录不构成 M0 FINAL PASS。

必须：

1. 跑当前 source 的全量 formal + Reference；
2. B8/B9 新复现测试必须从红转绿；
3. 再更新治理请求，明确第三轮 architect 被额度中断，后续有额度时必须从 B8/B9 修复后的候选继续独立复审，而不是沿用旧 LATEST verdict。

M1 与并行核心开发继续暂停。
