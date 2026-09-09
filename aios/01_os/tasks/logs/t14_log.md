# T14 工作日志 · cognitiond 认知系统（认知树唯一写者）· 认知代理

## 2026-09-09 02:53 | 认知代理
- 做了：实现 `services/cognitiond.py`（Python 3.13 标准库 sqlite3 + aios_sdk）。认知树 `run/cognitive_tree.db`（ROOT=code 根），WAL + synchronous=NORMAL；schema 严格按 contracts_m2.md §认知树存储（cognition 表 id/kind/conclusion/confidence/evidence/status/epistemic/created_at/updated_at，confidence/evidence/epistemic 等字段 NOT NULL）。订阅 evt.normalized、sys.cognition.assert、sys.query.cognition。assert 校验（confidence∈[0,1] 数字、epistemic∈五状态、evidence 列表）非法回 `{status:"rejected",reason}`，合法 uuid4 落库回 `{id,status:"stored",confidence,epistemic}`；query 按 q.epistemic 过滤、evidence JSON 字符串还原为列表；evt.normalized v0 仅接收不推导。服务启动打日志；主入口 `if __name__=="__main__"` 守卫以支持内联自测。
- 自测：`python -m py_compile` 通过（exit 0）。内联代码（不连总线）直接调用建表+insert+query：journal_mode=wal；插入 INFERRED+KNOWN 两条均可查回，confidence/evidence/epistemic 字段非空且 evidence 还原为列表；epistemic 过滤命中正确；5 类非法输入（confidence 越界/非数字、epistemic 非法、evidence 非列表、kind 缺失）全部 rejected，合法边界（confidence=0.0/UNKNOWN）通过。自测全部通过。
- 遗留：**自测残留未清理**——`run/cognitive_tree.db`（含 -wal/-shm，内有两行自测数据：1 条 INFERRED 的 HYPOTHESIS + 1 条 KNOWN 的 BELIEF）与临时脚本 `.openclaw/tmp/t14_selftest.py` 因文件删除命令触发安全护栏审批超时被拒，本轮未清理。残留对门禁「认知树文件存在」与「assert 落库字段校验」无影响，但 test_m2.py 若有精确计数断言需注意；待指挥官手动清理或授权后我再清理。

> 诚实原则：文件删除（`Remove-Item`）被 AutoClaw Safety Guard 以 `File delete command` 高风险拦截（APPROVAL_TIMEOUT_DENIED），未以替代命令/工具绕过，如实记录。

## 2026-09-09 03:05 | 最高指挥官
- 验收：test_m2.py 全栈实测，T14 相关项全部 PASS
- 结果：**通过 ✅**

> **执行方式**：M2 恢复多代理并行——3 路代理用 DeepSeek V4 Pro（zai/tdpsk_deepseek-v4-pro-202606）并发开发（认知 4m6s / 租约 4m54s / 决策 9m54s），首次协同即通过验收。验收套件 test_m2.py 由指挥官编写（期间修正了测试脚本自身的 2 处 bug：漏 sub 订阅 + makefile 超时读法脆弱），代理代码本体零返工。test_m2.py 8/8 全绿。
