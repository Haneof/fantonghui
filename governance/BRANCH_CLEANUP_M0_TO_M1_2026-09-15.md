# M0 → M1 分支清理与基线裁决

日期：2026-09-15
角色：Chief Engineer / Integrator

## 1. 正式主线

GitHub 默认分支 `aios-2.0` 已从旧的 `3c7fcf328ae0a4c7b60c89c96161b7f65d16ae58` 对齐到 M0 FINAL PASS exact SHA：

`f2107656d404bb9cac526f71175cbfc1fbbb91cb`

旧默认分支头已经建立历史锚点：

`archive/pre-m0-default-20260915`

旧默认分支相对 M0 基线的两个独有提交只是一次独立审计证据误放后又移除，最终 tree 无净文件差异，因此不应阻止 M0 正式成为默认主线。

从本文件生效起：

- `aios-2.0` 是唯一 M1 开发基线。
- 所有 M1 工作分支必须从当时经 Chief 确认的 `aios-2.0` HEAD 创建。
- 禁止从任何旧 `arena/*`、`review/*`、`audit/*` 分支继续开发 M1。
- M0 冻结基线仍记录为 `f2107656d404bb9cac526f71175cbfc1fbbb91cb`，后续 M1 提交不会改变该历史 Gate 结论。

## 2. PR 状态

清理时仓库没有 open PR。M0 历史 PR 均已关闭/归档，不存在等待合并的 M0 工作。

## 3. 可删除的纯开发/重复分支

以下分支已经被 `aios-2.0@f2107656...` 完全吸收，或只是指向已经被主线取代的 candidate，没有继续作为开发基线的价值：

- `arena/01a09bc6-fantonghui`（HEAD 与主线同为 `f2107656...`）
- `arena/integrator-x8-x10-repair-20260915`（HEAD 与主线同为 `f2107656...`）
- `arena/integrator-typedref-replay-20260914`（`b6588bda...` 是主线祖先）
- `arena/integrator-x5-x7-repair-20260914`（`b9b5921c...` 是主线祖先）
- `arena/chief-b9b-boundary-adjudication-20260915`（`f3e2fcfd...` 是主线祖先）
- `review/independent-quality-b9b5921c-20260914`（重复 candidate ref）
- `review/independent-quality-b9b5921c-frozen`（重复 candidate ref）
- `review/independent-quality-b9b5921c-frozen-r1`（重复 candidate ref）
- `review/m0-independent-quality-b6588bda-20260914`（重复 candidate ref）

这些分支不再承担任何 M1 职责。

## 4. 必须保留的治理/证据分支

当前保留：

- `governance/aios-control-plane`：宪法/R1/R2、任务母表、Gate、进度与 Chief 裁决。
- `constitution/v1.4-r0`：历史宪法基线。
- `archive/pre-m0-default-20260915`：默认分支切换前的历史锚点。
- `arena/verify-f210-frozen488-20260915`：在 `f210...` 之上唯一增加冻结 394 + independent 94 回归测试文件，是 1046 收敛的直接可回放载体。
- `audit/architect-01-b6588bd-frozen-20260914`：包含独立冻结方案、SHA256、collect-only、执行记录、报告与原始 red-team suite，不能在证据迁移前删除。
- `review/independent-quality-b9b5921c-r1`：包含独立 94-probe robustness suite、报告、环境和运行日志，在证据迁移前保留。

## 5. 暂停/待二次清点的历史分支

其余旧 `arena/*`、旧 Pydantic 实验、旧 verify/auditor 分支以及随机 agent 工作分支全部进入 **QUARANTINED / DO NOT DEVELOP** 状态。它们不得作为 M1 基线，也不得合并到主线。只有在确认其中没有主线/治理分支之外的唯一证据后才物理删除。

## 6. 物理删除限制

当前 GitHub 连接支持分支读取、创建和移动 ref，但没有 delete-ref / delete-branch 动作；执行环境中的 GitHub CLI 也未授权。因此本轮不能安全地远程删除 branch ref。

这不是开发阻塞：逻辑清理已经完成，M1 基线被唯一化。后续一旦获得 delete-ref 能力，只按本文件的删除清单操作，不重新裁决代码语义。

## 7. M1 分支规则

- feature branch 必须以 `m1/` 开头。
- 每个 branch 只对应一个冻结 Issue 或同一 Issue 的独立测试工作流。
- 一个 Issue 未通过 Chief Gate，不解锁依赖它的后续 Issue。
- 并行只发生在任务母表依赖图允许的位置。
- 所有 PR base 必须是 `aios-2.0`。
- 不允许从旧 M0 candidate branch cherry-pick 未经 Chief 明确复核的提交。