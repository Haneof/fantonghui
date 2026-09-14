# M0-006 总工程师代码审查

日期：2026-09-14

状态：

PATCH REQUIRED (TEST ONLY)

审查HEAD：

ac83582c4746f84768197da1b460b95b39129a8a

## 已通过并冻结的生产实现

以下生产代码已经通过总工程师直接审查：

src/aios_core/contracts/refs.py
src/aios_core/storage/sqlite_store.py

已通过：

- ObjectRef revision=N pinned
- ObjectRef revision=None floating
- SourceRef版本语义
- extra forbid
- frozen
- exact revision不存在不得fallback
- pending同事务引用
- generic knowledge boundary使用referencing object learned_at
- DB knowledge visibility使用canonical UTC
- pending visibility使用as_utc
- future-hidden与missing统一NOT_FOUND
- M0-005 revision/object_type/atomicity不变量保持
- M0-004时间不变量保持

GitHub Actions：

SUCCESS

Python：

3.12

正式测试：

179 passed

Reference：

15 passed

## 阻塞问题：测试冻结不足

阻塞A：

critical model ref test仅检查字段名存在，没有验证字段annotation确实是ObjectRef。

阻塞B：

R09 future leakage断言存在OR逃逸，可能在泄露future payload时仍然false-green。

阻塞C：

pending reference visibility新增了datetime排序路径，但没有DST fold integration test。

因此：

M0-006 PATCH REQUIRED (TEST ONLY)

生产代码 PASS/FROZEN

M0-007 HOLD

## 裁决

M0-006-R1：

- 补强 critical field annotation test
- 补强 future leak canary
- 新增 DST R16/R17 pending visibility
- 不修改生产代码

M0-007：

HOLD
