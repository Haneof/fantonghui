# AIOS 核心系统宪法与法统专区

本目录为 AIOS 系统的最高法律与法统规约中心。

> **现行规范唯一注册入口**：`governance/normative_versions/registry.md`。任何运行时代码、测试、Agent 派工或审计在解释法统优先级时，必须先以该注册表为准，再读取对应正文。
> **最终整合版唯一入口**：[`AIOS_Constitution_v3.0_FINAL.md`](./AIOS_Constitution_v3.0_FINAL.md) —— 2026-09-18 项目经理整合版，零散法统原文逐字聚合，未做任何语义修改。自本文件发布之日起，新 Issue/PR/测试/Agent 派工在引用宪法时应优先引用本最终整合版。

## 0. 最终整合版（2026-09-18）

**[`AIOS_Constitution_v3.0_FINAL.md`](./AIOS_Constitution_v3.0_FINAL.md)** — **AIOS 核心系统宪法 v3.0 最终整合版（FINAL INTEGRATED）**

- **状态**：正式发布 · 唯一宪法基线（逐字整合版）
- **整合来源**：`AIOS核心系统宪法v3.0.md`（主宪法 6编33章116条）+ `v3.0.1_规范裁决集_ADJ-001-012.md`（12项裁决）+ `R5`（AI认知执行运行时与驾驶权）+ `R6`（自适应认知策略与阈值主权）+ `R4`（候选附录）+ `AIOS_THE_AI_OPERATED_SYSTEM_MANIFESTO.md`（宣言）+ `AIOS_Core_终极认知形态演进路线图_Phase1至Phase3.md`（三阶路线）+ `governance/normative_versions/registry.md`
- **行数**：3369 行 / 235KB / 约 3100+ 原文行
- **法律效力**：本文件为全部零散宪法文件的唯一最终整合文本，后续开发、验收、架构变更均以本文件为准；零散旧文件保留于仓库仅作溯源，不再具备独立法统效力
- **结构**：第一部分 主宪法 → 第二部分 v3.0.1 裁决集 → 第三部分 R5 → 第四部分 R6 → 第五部分 R4候选附录 → 第六部分 宣言 → 第七部分 路线图 → 第八部分 法统注册表 → 整合封条

> **使用要求**：自 2026-09-18 起，所有新文档引用宪法必须引用 `AIOS_Constitution_v3.0_FINAL.md` 及其中具体章节/条款稳定键，不得再以零散旧文件作为独立最高依据。

## 1. 现行最高法统（零散来源备查）

> 以下为本次整合前的零散来源，现已被最终整合版全文逐字整合，保留备查：

1. **[`AIOS核心系统宪法v3.0.md`](./AIOS核心系统宪法v3.0.md)**：AIOS 3.0 主宪法与基础原则。
2. **[`v3.0.1_规范裁决集_ADJ-001-012.md`](./v3.0.1_规范裁决集_ADJ-001-012.md)**：对既有条款的正式规范裁决；其中 ADJ-004 明确 LLM 不拥有直接物理删除权，清理意图必须经过引用锁、保留/冻结等确定性门禁后由受控机械执行路径处理。
3. **[`AIOS宪法v3.0修改案_R5_AI认知执行运行时与驾驶权.md`](./AIOS宪法v3.0修改案_R5_AI认知执行运行时与驾驶权.md)**：确立 World / Search-Recall / AI Cognitive Runtime 三层法统，以及 AI 自主 Search / Recall / Follow / Compare / Commit 的系统驾驶权。
4. **[`AIOS宪法v3.0修改案_R6_自适应认知策略与阈值主权.md`](./AIOS宪法v3.0修改案_R6_自适应认知策略与阈值主权.md)**：区分 Hard Boundary、Engineering Parameter、Cognitive Policy；禁止以固定句数、固定关系身份、固定认知阈值或破坏性正则替 AI 完成高阶认知。
5. **[`AIOS_THE_AI_OPERATED_SYSTEM_MANIFESTO.md`](./AIOS_THE_AI_OPERATED_SYSTEM_MANIFESTO.md)**：AIOS 共生心智宣言书，对主宪法第一条的根本性释法。
6. **[`AIOS_Core_终极认知形态演进路线图_Phase1至Phase3.md`](./AIOS_Core_终极认知形态演进路线图_Phase1至Phase3.md)**：Phase 1 确定性离散工程体 -> Phase 2 神经拟态端侧协处理体 -> Phase 3 主动推理自由能生命体的演进规划。
7. 根目录 [`AIOS宪法v3.0修改案_R4.md`](../../AIOS宪法v3.0修改案_R4.md)：R4 候选修改案 9 项，待批准。

当旧设计、旧测试、旧注释与后续正式裁决/增补冲突时，以注册表记录的现行解释与后法为准；不得为了保持历史测试绿灯而恢复已被废止的认知规则。

## 2. 现行解释要点

- **AIOS = AI-Operated System**：确定性程序负责事实底座、工具、事务、审计、安全和资源边界；大模型负责理解、判断、联想、取舍、分寸与是否继续追忆。
- **多维世界不是规则大脑**：World 负责可靠保存；Search/Recall 负责找候选；最终相关性与高阶认知归 AI。
- **删除是受控机械执行，不是 LLM 物理直删**：AI 可以提出清理/删除意图，但不得绕过引用、保留、权限与审计门禁直接修改历史物理事实。
- **历史不可倒写**：后来形成的新认知应通过新 Claim、Reinterpretation、Summary、Experience、Reflection 等向前演进。
- **Cockpit 四段是稳定布局，不是固定思维顺序**。
- **1~3 句、60 字等仅可作为历史风格启发式，不得作为破坏模型语义的硬上限**。
- **认知策略必须可审计、可版本化、可回滚**；硬边界不得因 AI 自适应而被放宽。

## 3. 设计/路线文件（非自动获得最高法效力）

- **[`AIOS_Core_终极认知形态演进路线图_Phase1至Phase3.md`](./AIOS_Core_终极认知形态演进路线图_Phase1至Phase3.md)**：Phase 1 确定性离散工程体 -> Phase 2 神经拟态端侧协处理体 -> Phase 3 主动推理自由能生命体的演进规划。（已被最终整合版第七部分整合）
- R4 及其他明确标注“待批准/待签发”的修改案或设计书，在完成正式批准前属于候选设计依据；其中已被后续正式法统吸收的语义，以后续正式法统为准。

## 4. 历史法统沿革 (`history/`)

- [`history/AIOS宪法2.0.txt`](./history/AIOS宪法2.0.txt)：AIOS 2.0 基础宪法文本。
- [`history/AIOS宪法2.0及开发规格修改案_R1.md`](./history/AIOS宪法2.0及开发规格修改案_R1.md)：R1 修正案。
- [`history/AIOS宪法2.0及开发规格修改案_R2.md`](./history/AIOS宪法2.0及开发规格修改案_R2.md)：R2 修正案。
- [`history/AIOS宪法2.0及开发规格修改案_R3.md`](./history/AIOS宪法2.0及开发规格修改案_R3.md)：R3 修正案。

## 5. 整合凭证

- 最终整合版生成：2026-09-18 235KB 3369行，由项目经理执行零散文件逐字整合
- 备份：`AIOS_Constitution_v3.0_FINAL.backup.*.md` 保留旧 FINAL 占位版
- 校验：建议治理平面对最终整合版计算 sha256 并登记于 registry 下一版
