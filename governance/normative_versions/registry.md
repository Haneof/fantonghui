# AIOS 规范版本注册表（Normative Versions Registry）

> **用途**：全仓文档的"血统档案"。任何 Issue、代码注释、测试名、审计报告引用的上位规范，必须能在此表中按「编号+哈希」唯一定位。哈希由 `tools/governance/hash_registry.py`（M0-023 交付物）自动刷新；本文件由治理平面签署。
> **刷新日期**：2026-09-15 · G0 签发同期
> **规则**：①一行 = 一份规范的一个版本；②一旦入库的行禁止改写（追加新版本行代替）；③CI 校验任何"已登记文件"的实际哈希若与本表不符即红检。

| 规范编号 | 文件 | 版本 | 哈希 (SHA-256) | 状态 | 上位法 |
|---|---|---|---|---|---|
| CONST-v2.0 | `AIOS宪法2.0.txt` | 2.0 | （历史，补登待治理作业） | ARCHIVED（被 v3.0.1 全面取代） | — |
| CONST-R1 | `AIOS宪法2.0及开发规格修改案_R1.md` | R1 | （历史，补登待治理作业） | ARCHIVED（并入 v3.0.1） | CONST-v2.0 |
| CONST-R2 | `AIOS宪法2.0及开发规格修改案_R2.md` | R2 | （历史，补登待治理作业） | ARCHIVED（并入 v3.0.1） | CONST-R1 |
| CONST-R3 | `AIOS宪法2.0及开发规格修改案_R3.md` | R3 草案 | （历史，补登待治理作业） | SUPERSEDED（其全部内容已并入 v3.0 定稿） | CONST-R2 |
| CONST-v3.0 | `AIOS核心系统宪法v3.0.md` | 3.0 | `4df049fc34482df46fbb75ff8701026403c1ea512f97719269f3a525f21bcef1` | **被 v3.0.1 修订（仍作原文基线保留）** | CONST-R3 |
| **CONST-v3.0.1** | `AIOS核心系统宪法v3.0.md` + `governance/v3.0.1_规范裁决集_ADJ-001-012.md` | 3.0.1 | 宪法基线同上 + 裁决集哈希（本表签发后由工具自动回填） | **CURRENT**（唯一生效宪基） | CONST-v3.0 |
| PLAN-v0.1 | `AIOS Core 系统架构图与开发规划.md` | V0.1 | `9fb1b1cf9c431512f88c514a662b15d40d20c27ef0505f242241edef4050cf71` | **DEPRECATED**（由 PLAN-R4 取代；保留作历史） | CONST-v2.0（过期来源） |
| TASK-R2 | `AIOS_Core_详细开发任务拆分_R2_总工程师版.md` | R2 | `314f94b32a8b119e09e369c971d0e7f887ea295a745c8058f59526c7136bf5cb` | **PARTIALLY DEPRECATED**（按 R4 §3.3 处置表逐条 UPGRADE/REWRITE/DEPRECATE） | CONST-v2.0+R1+R2（过期来源） |
| WB-v0.1 | `AIOS认知工作台功能规格.md` | V0.1 | `c568d2ab41ce1a81bc1324dfaecb5973fd49c55eb9be29cdc4b0b2f6709b4a51` | **DEPRECATED**（由 WB-R4 取代） | 依赖 PLAN-v0.1→过期 |
| TEST-v0.1 | `AIOS虚拟世界测试规范.md` | V0.1 | `a5f90a1b7d966f5a1ca8e7351d9d53e4456354d68163eede1765d192a54506a6` | **DEPRECATED**（由 TEST-R4 取代） | 无宪法版本声明（缺陷） |
| PLAN-R4 | `AIOS_Core_任务规划与开发任务拆分重构方案_R4_独立首席架构师版.md` | R4 提案 | （本文件提交时由工具回填） | **PROPOSED→随 G0 签发转 CURRENT** | CONST-v3.0.1 |
| ADJ-v3.0.1 | `governance/v3.0.1_规范裁决集_ADJ-001-012.md` | 3.0.1 | （本文件提交时由工具回填） | **PROPOSED→随 G0 签发转 CURRENT** | 宪法第 115 条 |
| TRACE-MATRIX | `governance/traceability_matrix.csv` | 3.0.1-seed | （本文件提交时由工具回填） | **PROPOSED→随 G0 签发转 CURRENT** | ADJ-011 稳定键制度 |
| THRESH-BASE | `governance/thresholds/baseline_v1.json` | v1 | （待 M0-031 落地后补登） | REGISTERED-TODO | ADJ-008 |

## 过渡期特别说明（G0 签发后 14 天内）

1. PLAN-v0.1 / WB-v0.1 / TEST-v0.1 三份 DEPRECATED 文档只读保留；任何新 Issue 引用这三份文档的模块表、验收编号或条款号，CI 直红。
2. TASK-R2 在《R4 处置表》（§3.3）尚未逐条标记完成的 Issue 前，保持"部分有效"状态；引用 TASK-R2 任一 Issue 时必须同时声明其 R4 处置类别（KEEP/UPGRADE/REWRITE/SPLIT/DEPRECATE）。
3. CONST-v2.0~R3 系列补登哈希属治理一次性作业（M0-023 附注），不影响 v3.0.1 生效。
4. 任何本表未收录的 README/博客/口头决议，一律不构成工程基准。
