# M0-011 REVIEW PACKET

日期：2026-09-14

## 任务

DimensionDefinition / DimensionMembership / DimensionDerivation 三层契约。

## 基线与冻结

- 起始工作 HEAD：`a06ac1a5b634c852a5252373795a3727f7a4ba02`
- 语义实现冻结：`295d2a162f8814c9479d7281bd5988ccd2d8b6f5`
- 正式结论：FINAL PASS

## 权威依据

任务书 M0-011 要求：
- Definition / Membership / Derivation 分离；
- Definition 定义 name/description/data_shape/lifecycle/update_method；
- Membership 引用 dimension 和 member；
- Derivation 引用 output dimension + input refs + evidence + applicable scope/time + confidence/counterexamples；
- 一个对象允许多个 Membership；
- Derivation 输入可以是维度、事件、Claim、Summary、EvidenceSet；
- data_shape 不得被压成 curve/vector-only；
- 原始 Observation 不得复制成每个维度的私有数据；
- 高层维度可以向下追溯输入。

R2 额外固定 DimensionLifecycle：
`CANDIDATE/TRIAL/ACTIVE/LOW_ACTIVITY/DORMANT/MERGED/SPLIT/REVISED/REJECTED/REACTIVATED`。

## 生产改动

### contracts/models.py

仅对三层契约中的两类边增加持久化历史约束：

- DimensionMembership.dimension_ref pinned
- DimensionMembership.member_ref pinned
- DimensionMembership.basis_refs pinned
- DimensionDerivation.output_dimension_ref pinned
- DimensionDerivation.input_refs pinned
- DimensionDerivation.evidence_set_refs pinned
- DimensionDerivation.counterexample_refs pinned

不修改全局 ObjectRef 的 floating 能力。

### contracts/enums.py

DimensionLifecycle 从旧 scaffold：

`CANDIDATE/TRIAL/ACTIVE/LOW_ACTIVITY/DORMANT/REJECTED/RETIRED`

修正为 R2 exact：

`CANDIDATE/TRIAL/ACTIVE/LOW_ACTIVITY/DORMANT/MERGED/SPLIT/REVISED/REJECTED/REACTIVATED`

仓库搜索无 `DimensionLifecycle.RETIRED` 使用。

### CI

`.github/workflows/ci.yml` 增加 Reference contract suite：

`PYTHONPATH=aios_core_r2_reference/src python -m pytest aios_core_r2_reference/tests -v`

从此 Reference 15 进入每次 GitHub Actions core build。

## 新增测试

### tests/unit/test_dimensions.py

13 项：
- D01 exact 三层 schema
- D02 非 curve-only data_shape
- D03 一个 member 可对应多个 Membership model
- D04 Membership pinned refs
- D05 Derivation input_refs 非空
- D06 学习能力 → 数学/英语/编程下钻
- D07 heterogeneous ObjectRef inputs，不是 numeric vector
- D08 Derivation provenance pinned
- D09 raw Observation 不复制
- D10 三层对象 SQLite round-trip
- D11 Membership post-validation mutation 被 durable boundary 拦截
- D12 Derivation post-validation mutation 被 durable boundary 拦截
- D13 confidence 0..1

### tests/unit/test_dimension_lifecycle.py

精确冻结 R2 lifecycle names + values。

### tests/unit/test_dimension_membership_persistence.py

使用真实已提交 Observation + 两个真实 DimensionDefinition，持久化两个 Membership，证明同一 object 可同时挂载两个维度，且不会被覆盖/合并。

## 对抗验证矩阵

A. data_shape 只允许 curve/vector → D02 失败。
B. member 唯一化/禁止多 Membership → persistence test 失败。
C. input_refs 改为 list[float] → D01/D07 失败。
D. 允许空 input_refs → D05 失败。
E. floating Membership refs → D04/D11 失败。
F. floating Derivation refs → D08/D12 失败。
G. 复制 Observation.value → D09 失败。
H. lifecycle 漏 MERGED/SPLIT/REVISED/REACTIVATED 或恢复 RETIRED → lifecycle exact test 失败。

## Exact-head CI

语义冻结 HEAD：`295d2a162f8814c9479d7281bd5988ccd2d8b6f5`
Run：`34805946078`
Job：`103857745942`

- Python 3.12.14
- pytest 8.4.2
- formal: 268 passed, 1 expected adversarial warning
- Reference: 15 passed

## Scope audit

从 `a06ac1a...` 至 `295d2a...` 仅：
- `.github/workflows/ci.yml`
- `src/aios_core/contracts/enums.py`
- `src/aios_core/contracts/models.py`
- `tests/unit/test_dimension_lifecycle.py`
- `tests/unit/test_dimension_membership_persistence.py`
- `tests/unit/test_dimensions.py`

无 storage/refs/base/time 生产修改。

## 未解决问题

NONE for M0-011 scope.

后续 services / lifecycle transition / derivation trace service 不属于本任务。
