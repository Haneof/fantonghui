# M0-022R 合并复审签核包（Ratification Package）

> 性质：给 architect-01 / chief-01 的**一次性合并复审材料**。本包不自签、不宣布
> Gate 已开；它把"批准/驳回各自需要什么动作"压缩为单步机械操作，把全部已知
> 偏差与风险**显式摊开**——签核包的诚实度就是它的价值。
>
> **状态注记（2026-09-16 晚）**：签核对象由「单一主线」修正为「V3 总指挥部是否
> 接收 R4 delta」——现实对表与编号冲突裁决见 `上游对表裁决_2026-09-16.md`。
>
> 依据：《AIOS宪法v3.0修改案_R4.md》§附（M0-022 复审改签 M0-022R：v2.0 集 +
> R4 delta + CAM 映射 三合一复审）；设计书 R4 §3.1。

---

## 1. 复审对象全集（三块，缺一不审）

| # | 块 | 工件 | 核验命令 | 最近实测 |
|---|---|------|----------|----------|
| A | v2.0 契约集（418+15 基线） | 既有 `tests/`（22 任务，16 FINAL PASS + 5 REOPENED+PATCHED） | `.venv/bin/python -m pytest tests` | 594 passed / 1 failed（唯一失败=既知环境项 b8，见 §4-R3）|
| B | R4 delta 候选契约 | `contracts/{enums,models,operations,registry,ids}.py` + `schemas/r2/m0_contract_snapshot.json`（gate=`M0-R2+R4-delta-candidate`）+ `tests/unit/test_m0_prime_contracts.py` | 同上 + 快照 diff | 12/12 用例绿；快照与 registry 双向一致 |
| C | CAM 验收矩阵 | `schemas/constitution_acceptance.py`（55 项）+ `tests/architecture/test_cam_coverage.py` | `pytest tests/architecture -q` | 7/7 绿；21 项 contract_frozen 强制挂真实测试文件 |

签核范围**不含** M0-030（runtime_profile 契约，待开工）；**不含** M1 任何表行。

## 2. 批准动作（单步）

1. `schemas/r2/m0_contract_snapshot.json`：`gate_version` 字符串改为
   `M0-R2+R4-delta`（仅此一字串，字段零改动）；
2. `schemas/constitution_acceptance.py`：9 项 R4 提案状态
   `proposed_pending_R4` → `planned`；
3. 台账：M0′ 行改写为"M0-022R 已签核"；M1 Gate 开启公告写入 DEV_LOG。
4. （若 R2 一并批准）按 §7 草案改订设计书 M1-017 相关三处文本并同步 CAM note。

## 3. 驳回动作（同样单步，无残留）

1. `git revert` 契约 delta 提交（`6c3fbaf` 中 contracts/ 与 snapshot 部分）+ 再生成快照回 `M0-R2`；
2. M0′ 行回退；CAM R4 提案 9 项回 `proposed`；
3. **预开工件处置**：commit `20e7733`（存储层 source_class + 检索核）随驳回一并
   revert——它只加列/加投影，不触对象数据，私有构建无迁移遗留（迁移器幂等、
   检索表为可 drop 投影，`drop_projection()` 已就位）。

## 4. 风险登记与偏差摊开（签核人必须逐条画钩）

| # | 事项 | 立场与建议裁决 |
|---|------|----------------|
| R1 | **时序偏差（主动披露）**：M0-023 运行面与 M1-017/018 检索核以"预开工件"先于 Gate 落码（`20e7733`）。 | 属设计书 §1.4"契约先行、执法随后"顺序的**提前**而非违反：未改契约、未动 M1 表行、未接入任何运行路径。裁决项：认可预开工件（推荐，降低 Gate 后关键路径）或要求冻结至 Gate 后。 |
| R2 | **任务书字面偏差（改订草案见 §7）**：M1-017 题名"FTS5 世界检索核"，实现为自持 bigram 倒排核 + FTS5 可替换适配器（本构建实测：unicode61 不分词、trigram 拒 2 字词元，"妈妈"类查询物理不可达）。 | 第 18 条"实现可替换"支持此路线，但**题名需修订**才能销账。裁决项：批准任务文本改订为"世界检索核（FTS5 适配器可选）"，或限期重做。 |
| R3 | b8 跨进程重放在沙箱 py3.11 失败：子进程继承不到 `PYTHONPATH=src`（本包实测带变量即绿）。 | 环境项，非行为回归；CI 3.12.14 基线全绿。建议：conftest 注入环境或接受为沙箱噪音，入既知限制清单。 |
| R4 | 旧库迁移回填策略：`world_commits` 历史行统一显式标记 `ai_cognition` 并审计（拒绝 DEFAULT）。 | 该选择把"历史全是 AI 会话语义"写成了可反驳的审计事实。如签核人认为存在用户直写历史，需在批准前改判定，否则永久污染触发面统计。 |
| R5 | M1-019 编号勘误（上轮口误"唤醒回路"）：唤醒= M2-016/019/021；M1-019 实为 PRUNED tombstone 冷档。 | 无工件影响；DEV_LOG 已勘误。备案即可。 |

## 5. 条款自检（R4 delta 对宪法 v3.0+修改案的逐条对表）

| 条款 | 落点 | 状态 |
|------|------|------|
| R4-02（提交分类+触发豁免） | OperationRequest 双字段互斥校验；`world_commits.source_class`+部分索引；`triggerable_commits_after` 结构性排除 maintenance | 契约✅ 运行面✅(预开工件) M2-002 接入⏳ |
| 36/89（别名不自动合并/共现交集） | resolve-before-intersect + `ambiguous_keywords` 显式返回 + posting-AND 交集 | 内核✅(预开工件) |
| 114（CAM 全映射） | 55/55，21 项强制测试引用，宪法原文实时解析防账本自嗨 | ✅ |
| 110（Issue 规范） | `governance/issues/M0-023..028`（GitHub Issues 关闭，文件为权威载体） | ✅ |
| 33.5/R4-07（归档审计） | M1-019 施工图 + 静态防删守卫先行落码（见 `governance/issues/M1-019_blueprint.md`） | 设计✅ 守卫✅ 冷档实现⏳Gate 后 |
| R4-09（V31 注入拦截） | M4-006 场景包 | ⏳（不在本包范围，防越权承诺） |

## 6. 本包明确不声称的事

- 不声称 M0 Gate 已开、不声称 M1 已开工；
- 不声称 50 万修订 G-M1P 通过（CI 仅降规模 2000 对象冒烟，正式压测 Gate 后跑目标硬件）;
- 不声称 M0-030 交付；不声称 band_v0 冒烟（M2 起强制）。

## 7. R2 裁决附件：M1-017 任务文本改订草案

> 设计书由文档所有者维护，签核人批准后**由批准动作第 4 步代为插入**；本包只出
> 草案不代改。批准 R2 时追加：

- §3.4 表行改订为：`| M1-017 | 世界检索核（自持倒排投影；FTS5 为可替换适配器）+ 共现交集物理计划（禁 payload 扫描） | M1 | M1-012 | R4-02 |`
- §2 对照表 M1-012 行的"内核划入 M1-017"补注：`（实现形态：CJK bigram 倒排为主核——unicode61 不分词/trigram 拒短词元为实测依据；FTS5 适配器按第 18 条保留）`
- T2-G② 的物理计划断言改为：`EXPLAIN QUERY PLAN 断言使用倒排 postings 表或 fts5（二者任一）、不含 SCAN object_revisions`

批准动作第 4 步同步加入 CAM：`R4-02` 条目 note 追加 "search kernel = replaceable-adapter doctrine (M1-017 rev.)"。
