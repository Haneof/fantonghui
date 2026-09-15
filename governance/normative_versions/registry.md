# AIOS 规范版本注册表（Normative Versions Registry）

> **用途**：全仓文档的"血统档案"。任何 Issue、代码注释、测试名、审计报告引用的上位规范，必须能在此表中按「编号+哈希」唯一定位。哈希由 `tools/governance/hash_registry.py`（M0-023 交付物）自动刷新；本文件由治理平面签署。
> **刷新日期**：2026-09-16（含 e7ba42e/19ab6a8 法统目录归一化后的路径迁移） · G0 签发后首日补登（hash_registry.py 落地）
> **规则**：①一行 = 一份规范的一个版本；②一旦入库的行禁止改写（追加新版本行代替）；③CI 校验任何"已登记文件"的实际哈希若与本表不符即红检。

| 规范编号 | 文件 | 版本 | 哈希 (SHA-256) | 状态 | 上位法 |
| --- | --- | --- | --- | --- | --- |
| CONST-v2.0 | `docs/constitution/history/AIOS宪法2.0.txt` | 2.0 | `e74a45f139f2f8afabc5ed03bd369cd89dd666036fd70566be699c2afe21cf95` | ARCHIVED（被 v3.0.1 全面取代） | — |
| CONST-R1 | `docs/constitution/history/AIOS宪法2.0及开发规格修改案_R1.md` | R1 | `51c30801b1897e0afd39bc1a2fd189b0ce2f526a0bc4066ad79d408dc41c53c4` | ARCHIVED（并入 v3.0.1） | CONST-v2.0 |
| CONST-R2 | `docs/constitution/history/AIOS宪法2.0及开发规格修改案_R2.md` | R2 | `4f725189f23a252433ddf7ff8c2a88a1db68cf74d040ca9486efc6980e63f0fe` | ARCHIVED（并入 v3.0.1） | CONST-R1 |
| CONST-R3 | `docs/constitution/history/AIOS宪法2.0及开发规格修改案_R3.md` | R3 草案 | `8f42e59dc95bf9721d109eb90a4dce4ec9659a9675735a54f86f40195ddc2ad5` | SUPERSEDED（其全部内容已并入 v3.0 定稿） | CONST-R2 |
| CONST-v3.0 | `docs/constitution/AIOS核心系统宪法v3.0.md` | 3.0 | `4df049fc34482df46fbb75ff8701026403c1ea512f97719269f3a525f21bcef1` | **被 v3.0.1 修订（仍作原文基线保留）** | CONST-R3 |
| **CONST-v3.0.1** | `docs/constitution/AIOS核心系统宪法v3.0.md` + `docs/constitution/v3.0.1_规范裁决集_ADJ-001-012.md` | 3.0.1 | 同上 + `a75a6db191bbb5c217f005cf4e4cb3feac2b21e6f8b6e7fdd861123953e18c85` | **CURRENT**（唯一生效宪基） | CONST-v3.0 |
| PLAN-v0.1 | `docs/specifications/AIOS Core 系统架构图与开发规划.md` | V0.1 | `9fb1b1cf9c431512f88c514a662b15d40d20c27ef0505f242241edef4050cf71` | **DEPRECATED**（由 PLAN-R4 取代；保留作历史） | CONST-v2.0（过期来源） |
| TASK-R2 | `docs/specifications/AIOS_Core_详细开发任务拆分_R2_总工程师版.md` | R2 | `314f94b32a8b119e09e369c971d0e7f887ea295a745c8058f59526c7136bf5cb` | **PARTIALLY DEPRECATED**（按 R4 §3.3 处置表逐条 UPGRADE/REWRITE/DEPRECATE） | CONST-v2.0+R1+R2（过期来源） |
| WB-v0.1 | `docs/specifications/AIOS认知工作台功能规格.md` | V0.1 | `c568d2ab41ce1a81bc1324dfaecb5973fd49c55eb9be29cdc4b0b2f6709b4a51` | **DEPRECATED**（由 WB-R4 取代） | 依赖 PLAN-v0.1→过期 |
| TEST-v0.1 | `docs/specifications/AIOS虚拟世界测试规范.md` | V0.1 | `a5f90a1b7d966f5a1ca8e7351d9d53e4456354d68163eede1765d192a54506a6` | **DEPRECATED**（由 TEST-R4 取代） | 无宪法版本声明（缺陷） |
| PLAN-R4 | `AIOS_Core_任务规划与开发任务拆分重构方案_R4_独立首席架构师版.md` | R4 提案 | `ab6a45f57a68ef489f2dfe9456684ba4e6e4043d050605d406e107ecd101ed75` | **CURRENT**（G0 已于 2026-09-15 签发） | CONST-v3.0.1 |
| ADJ-v3.0.1 | `docs/constitution/v3.0.1_规范裁决集_ADJ-001-012.md` | 3.0.1 | `a75a6db191bbb5c217f005cf4e4cb3feac2b21e6f8b6e7fdd861123953e18c85` | **CURRENT**（G0 已于 2026-09-15 签发） | 宪法第 115 条 |
| TRACE-MATRIX | `governance/traceability_matrix.csv` | 3.0.1-seed | `146f87c971e9ef59a42fdcc40f9f5f52af483cee235ebb83a46d28d4cb9b2522` | SUPERSEDED（哈希封存；CRLF 行尾形态） | ADJ-011 稳定键制度 |
| TRACE-MATRIX | `governance/traceability_matrix.csv` | 3.0.1-seed-lf | `8983d3e7dc65ff3b028ffa27cb6a643829f7a9624b153394738c897b3d2e1a16` | **CURRENT**（内容与 3.0.1-seed **逐行相同**，仅行尾由 CRLF 归一为 LF —— 主线 19ab6a8 集成时所做；120 个稳定键一字未动。按规则② 追加版本行而非改写旧行） | ADJ-011 稳定键制度 |
| THRESH-BASE | `governance/thresholds/baseline_v1.json` | v1 | `613114c8562e8a64d7e53cfaac41a5c68c59d9f6d0d9991a48dc3167cee39638` | SUPERSEDED（哈希封存；M0-031 契约落地时的 v1 基线） | ADJ-008 |
| THRESH-BASE | `governance/thresholds/baseline_v1.json` | v1.1 | `71b002bd5b355b226befa4a2e61601b21a396adb9064e1d97daf20ef69acfed4` | **REGISTERED**（v1.1：仅迁移裁决集引用路径至 docs/constitution/，参数与 change_protocol 一字未动） | ADJ-008 |
| PLAN-R4-B | `AIOS_Core_任务规划与开发任务拆分重构方案_R4.md` | R4 | `89b2b7844e2ad7a63e3f0c77461e562dfb4dfbba4b99e18acbaaf15fe4aa0292` | SUPERSEDED（哈希封存；活版本见下表 R4.1 行） | CONST-v3.0.1 |
| POLICY-RUNTIME | `governance/runtime_policy.json` | 1.0.0 | `3bf3e8318f5ccaab496bc92b0a887cdfb50fc06dd5304c4f05e3c2ad73ba952b` | SUPERSEDED（哈希封存；活版本见下表 1.2.0 行） | CONST-v3.0.1 |
| POLICY-RUNTIME | `governance/runtime_policy.json` | 1.1.0 | `1bcf22f1de533b02c893b76dcaa6925bc654bc528787b5931f5ee6c953937ba5` | SUPERSEDED（哈希封存；1.1.0=retention_ttl 入法，M1-019 参数表） | CONST-v3.0.1 |
| POLICY-RUNTIME | `governance/runtime_policy.json` | 1.2.0 | `80c02abf9ad0e1be8163712d836bf94456eadd340b958d9f21f06e1764ebfa47` | **CURRENT**（1.2.0=两条工作线的 v1.1.0 合并：ADJ-001~012 全量对齐 + retention_ttl 入法；27 域；宪法→法律→判决之法律层） | CONST-v3.0.1 |
| PLAN-R4-B | `AIOS_Core_任务规划与开发任务拆分重构方案_R4.md` | R4.1 | `db87d2f74d7b9f8a85c077fb60d3843cf9c812df361d31e63ed9f2b37e2ecb58` | **CURRENT**（R4.1：§2.1 增编号对撞警告横幅；THRESH-BASE 与 M1-019 落地后两轮对齐） | CONST-v3.0.1 |

> **多版本行的阅读规则（2026-09-16 起）**：同一 `规范编号` + 同一 `文件路径` 可以有多行，
> 一行 = 一个版本（规则①）。`hash_registry.py --check` 采用**位置语义**：
> 只有该组**表内最后一行**参与漂移比对，更早的行视为 archived —— 其历史哈希永久封存、
> 绝不改写（规则②），也绝不与当前文件比对。archived 行记录的是
> 「该版本曾以此哈希签署」这一不可变事实，而非「文件现在仍是这个内容」。
>
> **POLICY-RUNTIME 曾出现版本号对撞**：两条工作线在互不知情的情况下各自产出了一个
> 「1.1.0」（一个把 retention_ttl 入法，一个做 ADJ-001~012 全量对齐），内容不同、
> 版本号相同。合并后的工件升为 **1.2.0**，使任何一个版本号都不同时指代两份不同内容 ——
> 这正是注册表存在的理由。两条 1.1.0 中已提交的那条按规则②原样封存，
> 未提交的那条不占版本号（其内容已并入 1.2.0，过程记录在 git 与对齐报告 §9）。

## 过渡期特别说明（G0 签发后 14 天内）

1. PLAN-v0.1 / WB-v0.1 / TEST-v0.1 三份 DEPRECATED 文档只读保留；任何新 Issue 引用这三份文档的模块表、验收编号或条款号，CI 直红。
2. TASK-R2 在《R4 处置表》（§3.3）尚未逐条标记完成的 Issue 前，保持"部分有效"状态；引用 TASK-R2 任一 Issue 时必须同时声明其 R4 处置类别（KEEP/UPGRADE/REWRITE/SPLIT/DEPRECATE）。
3. CONST-v2.0~R3 系列补登哈希属治理一次性作业（M0-023 附注），不影响 v3.0.1 生效。
4. 任何本表未收录的 README/博客/口头决议，一律不构成工程基准。
