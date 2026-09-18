#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIOS 宪法 v3.0 最终整合版 —— 组装与逐字校验工具（PM 治理工件）。

用法：
  python3 scripts/assemble_constitution_v3_final.py          # 重新组装整合版
  python3 scripts/assemble_constitution_v3_final.py --check  # 校验整合版与源文件逐字一致

整合原则：所有源文件正文逐字原样并入（字符级零修改），
以 <!-- BEGIN/END INTEGRATED SECTION --> 标记包裹，标记内记录来源路径、SHA-256 与法律地位。
源文件本身一律不修改、不删除、不移动。
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "docs" / "constitution" / "AIOS_Constitution_v3.0_FINAL_CONSOLIDATED.md"

BEGIN_MARK = "<!-- BEGIN INTEGRATED SECTION: {path} | sha256:{sha} | status:{status} -->"
END_MARK = "<!-- END INTEGRATED SECTION: {path} -->"

# (卷横幅, 法律地位) —— 顺序遵循 governance/normative_versions/registry.md 现行规范栈，与 SOURCES 一一对应
SECTIONS: list[tuple[str, str]] = [
    (
        "# ═══════════ 卷零 · 立国宣言书 ═══════════\n\n"
        "> **法律地位**：宪法第一条《一句话定义》的根本性心智释法（源文件抬头自述）；"
        "在文档层级上居首（沿用历史整合骨架 `AIOS_Constitution_v3.0_FINAL.md` 的优先级列表）。\n",
        "ACTIVE-INTERPRETIVE-BASIS",
    ),
    (
        "# ═══════════ 第一编～第六编 · 主宪法（现行规范栈 Priority 1） ═══════════\n\n"
        "> **法律地位**：ACTIVE · 现行唯一宪法基线。六编三十三章一百一十六条。"
        "所有开发、验收、架构变更均以本部分为准。\n",
        "ACTIVE",
    ),
    (
        "# ═══════════ 第七编 · v3.0.1 规范裁决集 ADJ-001~012（现行规范栈 Priority 2） ═══════════\n\n"
        "> **法律地位**：ACTIVE · 对主宪法歧义/冲突的正式裁决；凡 v3.0 原文与本裁决集冲突处，以本裁决集为准。"
        "其中 ADJ-004 明确 LLM 不拥有直接物理删除权。\n",
        "ACTIVE",
    ),
    (
        "# ═══════════ 第八编 · 修改案 R5：AI 认知执行运行时与驾驶权（现行规范栈 Priority 3） ═══════════\n\n"
        "> **法律地位**：ACTIVE · 主宪法正式增补条款（第八十五条之三）。"
        "确立 World / Search-Recall / AI Cognitive Runtime 三层法统与 AI 系统驾驶权。\n",
        "ACTIVE",
    ),
    (
        "# ═══════════ 第九编 · 修改案 R6：自适应认知策略与阈值主权（现行规范栈 Priority 4） ═══════════\n\n"
        "> **法律地位**：ACTIVE · 主宪法正式增补条款（第八十五条之四，R6 语义）。"
        "区分 Hard Boundary / Engineering Parameter / Cognitive Policy，治理认知阈值与自适应权。\n",
        "ACTIVE",
    ),
    (
        "# ═══════════ 第十编 · 修改案 R4（CANDIDATE · 候选未生效） ═══════════\n\n"
        "> ⚠️ **法律地位**：**CANDIDATE（待批准，未自动生效）**。\n"
        "> 依据 `governance/normative_versions/registry.md` §4：R4 属明确标注“待批准”的候选修改案，"
        "不得仅凭本整合收录即视为现行最高法统；其中已被后续正式法统吸收的语义，以后续正式法统为准。\n"
        "> 本编按原文收录以保持法统沿革完整，供批准程序与历史追溯使用。\n",
        "CANDIDATE",
    ),
    (
        "# ═══════════ 附录一 · 终极认知形态演进路线图 Phase 1~3（NON_NORMATIVE） ═══════════\n\n"
        "> **法律地位**：NON_NORMATIVE · 设计/路线文件，不自动获得最高法效力（宪法目录 README §3）。"
        "可作为工程证据与战略规划，但不能覆盖现行法统。\n",
        "NON_NORMATIVE",
    ),
]

SOURCES = [
    "docs/constitution/AIOS_THE_AI_OPERATED_SYSTEM_MANIFESTO.md",
    "docs/constitution/AIOS核心系统宪法v3.0.md",
    "docs/constitution/v3.0.1_规范裁决集_ADJ-001-012.md",
    "docs/constitution/AIOS宪法v3.0修改案_R5_AI认知执行运行时与驾驶权.md",
    "docs/constitution/AIOS宪法v3.0修改案_R6_自适应认知策略与阈值主权.md",
    "AIOS宪法v3.0修改案_R4.md",
    "docs/constitution/AIOS_Core_终极认知形态演进路线图_Phase1至Phase3.md",
]

assert len(SECTIONS) == len(SOURCES)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_preamble(sha_map: dict[str, str], sizes: dict[str, tuple[int, int]]) -> str:
    def cell(src: str) -> str:
        lines, nbytes = sizes[src]
        return f"`{sha_map[src][:16]}…` | {lines} 行 / {nbytes:,} B"

    return f"""# AIOS 核心系统宪法 v3.0 · 最终整合版（唯一宪法文件）

**文件编号**：CONST-V3.0-FINAL-CONSOLIDATED
**整合日期**：2026-09-18
**编制人**：AIOS 项目经理（PM，受总指挥部委托整合法统）
**编制依据**：`governance/normative_versions/registry.md` 登记的现行规范栈、`docs/constitution/README.md` 现行法统声明
**文件性质**：**既成法统之整合，非新立法。** 本文件不含任何对源文件条文的改写。

---

## 一、整合声明

本文件是 AIOS 3.0 **全部零散宪法文件的单一整合版**。编制目的：

1. 消除历史版本、修正案、裁决集、宣言书与解释文件之间的认知分裂；
2. 为运行时代码、测试、Agent 派工与审计提供唯一的法统阅读入口；
3. 固定每一份宪法文件的法律地位，避免候选文件被误当作现行最高法。

**整合原则**：

1. **原文逐字保留**：每一编均以 `<!-- BEGIN/END INTEGRATED SECTION -->` 标记包裹源文件全文，逐字复制，零增删改、零重排；标记内记录来源路径、SHA-256 与法律地位，供审计与追溯（可用 `python3 scripts/assemble_constitution_v3_final.py --check` 机器校验逐字一致性）；
2. **源文件保持原样**：所有零散源文件保留在原路径，不修改、不删除、不移动。若本整合版与任一源文件出现偏差，以源文件为准，并应重新执行本脚本重建整合版；
3. **排序即法统序**：各编顺序遵循 `governance/normative_versions/registry.md` 登记的现行规范栈优先级；宣言书作为宪法第一条的存在定义与释法依据列于卷首；候选文件与非规范文件列于卷末并显著标注，不混入现行法统栈；
4. **不做隐性裁决**：源文件之间存在的冲突（含条款编号撞号），本文件仅在“已知编号冲突与待裁决事项”一节列出备忘，正式裁决仍须走宪法第 115 条治理程序，整合者不擅自改写。

## 二、现行规范栈与整合对照表

| 整合编目 | 源文件 | 法律地位 | 版本锚（源文件） |
|---|---|---|---|
| 卷零 · 立国宣言书 | `docs/constitution/AIOS_THE_AI_OPERATED_SYSTEM_MANIFESTO.md` | ACTIVE · 释法依据 | {cell(SOURCES[0])} |
| 第一编～第六编 · 主宪法 | `docs/constitution/AIOS核心系统宪法v3.0.md` | ACTIVE · 规范栈 Priority 1 | {cell(SOURCES[1])} |
| 第七编 · v3.0.1 规范裁决集 | `docs/constitution/v3.0.1_规范裁决集_ADJ-001-012.md` | ACTIVE · 规范栈 Priority 2 | {cell(SOURCES[2])} |
| 第八编 · 修改案 R5 | `docs/constitution/AIOS宪法v3.0修改案_R5_AI认知执行运行时与驾驶权.md` | ACTIVE · 规范栈 Priority 3 | {cell(SOURCES[3])} |
| 第九编 · 修改案 R6 | `docs/constitution/AIOS宪法v3.0修改案_R6_自适应认知策略与阈值主权.md` | ACTIVE · 规范栈 Priority 4 | {cell(SOURCES[4])} |
| 第十编 · 修改案 R4 | `AIOS宪法v3.0修改案_R4.md`（仓库根） | **CANDIDATE**（未自动生效） | {cell(SOURCES[5])} |
| 附录一 · 演进路线图 | `docs/constitution/AIOS_Core_终极认知形态演进路线图_Phase1至Phase3.md` | NON_NORMATIVE（设计文件） | {cell(SOURCES[6])} |

**冲突规则**（照录 `governance/normative_versions/registry.md` §1）：在同一规范层级内，后生效且明确处理同一事项的正式裁决/修改案优先于旧表述；R5/R6 不取消主宪法的数据完整性、安全、权限、历史不可篡改等硬边界。

## 三、解释优先级

**规则阶梯**（照录 `governance/normative_versions/registry.md` §2）：当代码、测试、治理表、注释或旧设计存在冲突时，按以下顺序解释：

```text
现行正式法统正文（上表 ACTIVE 栈）
  > 正式机器可读 policy 中与法统一致的硬边界/工程参数
  > 当前批准的工程规格
  > 历史测试/历史进度表/历史注释
  > 未批准候选设计
```

“测试曾经是绿的”不构成恢复已被后续法统废止行为的理由。

**文档层级**（吸收自历史整合骨架 `AIOS_Constitution_v3.0_FINAL.md`，该骨架已被本文件完全取代）：

1. AIOS_THE_AI_OPERATED_SYSTEM_MANIFESTO（AIOS 存在定义）
2. 统一宪法（本整合版）
3. 架构规范
4. 实现规范
5. 代码

历史版本保留，但不得作为独立开发依据。

## 四、现行解释要点

照录 `docs/constitution/README.md` §2，作为阅读本整合版的总纲：

- **AIOS = AI-Operated System**：确定性程序负责事实底座、工具、事务、审计、安全和资源边界；大模型负责理解、判断、联想、取舍、分寸与是否继续追忆。
- **多维世界不是规则大脑**：World 负责可靠保存；Search/Recall 负责找候选；最终相关性与高阶认知归 AI。
- **删除是受控机械执行，不是 LLM 物理直删**：AI 可以提出清理/删除意图，但不得绕过引用、保留、权限与审计门禁直接修改历史物理事实。
- **历史不可倒写**：后来形成的新认知应通过新 Claim、Reinterpretation、Summary、Experience、Reflection 等向前演进。
- **Cockpit 四段是稳定布局，不是固定思维顺序**。
- **1~3 句、60 字等仅可作为历史风格启发式，不得作为破坏模型语义的硬上限**。
- **认知策略必须可审计、可版本化、可回滚**；硬边界不得因 AI 自适应而被放宽。

## 五、取代与单一入口声明

1. 本文件为 AIOS v3.0 法统的**唯一阅读入口**。历史整合骨架 `docs/constitution/AIOS_Constitution_v3.0_FINAL.md`（法统整理初版，自述“后续继续吸收 R5/R6/ADJ 中属于宪法层的内容”）自本文件签发之日起被**完全吸收并取代**；其规范优先级列表已吸收至本前言“三、解释优先级”。
2. `docs/constitution/history/` 下的 2.0 基础宪法文本与 R1/R2/R3 修改案为 HISTORICAL：已被 v3.0 正式法统吸收的部分通过现行正文继续有效，不再作为独立最高解释入口。
3. 本次整合属**既成法统之汇编**，不改变任何正式文件的生效状态，不构成新立法；按 `registry.md` §5 变更纪律，整合版作为统一入口已在注册表同步登记。
4. 后续任何新的正式修改案/裁决生效时，必须同步并入本整合版并更新 `governance/normative_versions/registry.md`（宪法第 115 条三级变更程序继续适用）。

## 六、已知编号冲突与待裁决事项（PM 备忘 · 不改原文）

1. **“第八十五条之四”编号撞号**：第七编 ADJ-007 的裁决文本新增“第八十五条之四”（「1 秒首字」「零误触」「1~3 句」三语录适用范围），第九编修改案 R6 亦以“第八十五条之四（v3.0 确立）”为条名（自适应认知策略、阈值与规则分层）。二者同属现行法统且编号相同。按第七编 ADJ-011 确立的条款稳定键制度（`C{{章节序}}-{{语义键}}` + 版本哈希），正式引用应使用稳定键；两款的稳定键化与更名留待后续治理裁决，本整合版原文并列保留。
2. **条数口径差异**：主宪法自述“一百一十六条”，与实测条款标题数（含诸“之一”补条）存在差异，第七编 ADJ-011 背景段已指出此现象并确立稳定键制度。本整合版保留原文表述。
3. **R4 生效状态**：第十编修改案 R4 原文状态为“待批准”，按注册表 §4 属 CANDIDATE；其语义若已被后续正式法统（如第七编 ADJ-004/005 对回溯标注与删除治理的裁决）吸收，以后续正式法统为准。

---

**以下为逐字并入的各编正文。**

---

"""


def build() -> None:
    sha_map: dict[str, str] = {}
    sizes: dict[str, tuple[int, int]] = {}
    parts: list[str] = []
    for src in SOURCES:
        p = REPO_ROOT / src
        raw = p.read_bytes()
        sha_map[src] = hashlib.sha256(raw).hexdigest()
        sizes[src] = (raw.count(b"\n") + (0 if raw.endswith(b"\n") else 1), len(raw))

    parts.append(build_preamble(sha_map, sizes))

    for (banner, status), src in zip(SECTIONS, SOURCES):
        p = REPO_ROOT / src
        text = p.read_text(encoding="utf-8")
        parts.append("\n---\n\n")
        parts.append(banner)
        parts.append("\n")
        parts.append(BEGIN_MARK.format(path=src, sha=sha_map[src], status=status))
        parts.append("\n")
        parts.append(text)
        if not text.endswith("\n"):
            parts.append("\n")
        parts.append(END_MARK.format(path=src))
        parts.append("\n")

    parts.append(
        """
---

# 编后记 · 版本记录

| 日期 | 动作 | 说明 |
|---|---|---|
| 2026-09-18 | 首次整合 | 将宣言书、主宪法、v3.0.1 ADJ 裁决集、修改案 R5、修改案 R6、修改案 R4（候选）与演进路线图（附录）逐字并入单一文件；源文件零修改 |

**后续修订纪律**：新正式修改案/裁决生效后，并入本文件对应编目、更新本版本记录，并按 `governance/normative_versions/registry.md` §5 同步注册表与 `governance/runtime_policy.json` 的 `constitution_baseline`。

> **本整合版作为 AIOS Core 项目的唯一宪法文件入口。一切开发、验收、架构变更、Agent 派工与审计，以本文件登记的现行规范栈为准。**
"""
    )

    OUTPUT.write_text("".join(parts), encoding="utf-8")
    total_lines = "".join(parts).count("\n")
    print(f"[assemble] wrote {OUTPUT.relative_to(REPO_ROOT)} ({OUTPUT.stat().st_size:,} bytes, ~{total_lines} lines)")
    for src in SOURCES:
        print(f"  - {src}  sha256={sha_map[src][:16]}…")


def check() -> int:
    """校验整合版中每个 INTEGRATED SECTION 与源文件逐字一致。"""
    doc = OUTPUT.read_text(encoding="utf-8")
    failures = 0
    for (banner, status), src in zip(SECTIONS, SOURCES):
        begin = BEGIN_MARK.split("{")[0]  # "<!-- BEGIN INTEGRATED SECTION: "
        start_marker = f"<!-- BEGIN INTEGRATED SECTION: {src} | "
        end_marker = END_MARK.format(path=src)
        i = doc.find(start_marker)
        j = doc.find("\n", i)
        k = doc.find(end_marker)
        if i < 0 or j < 0 or k < 0:
            print(f"[check] MISSING section for {src}")
            failures += 1
            continue
        # 头部声明的哈希
        head = doc[i:j]
        declared_sha = head.split("sha256:", 1)[1].split(" ", 1)[0]
        # 区块正文：标记行换行之后、结束标记之前。
        # 组装规则：正文 = 源文件字节（逐字）；仅当源文件末尾无换行时补一个换行作分隔。
        body = doc[j + 1 : k]
        body_bytes = body.encode("utf-8")
        src_bytes = (REPO_ROOT / src).read_bytes()
        expected = src_bytes if src_bytes.endswith(b"\n") else src_bytes + b"\n"
        if body_bytes != expected:
            print(f"[check] MISMATCH {src}: integrated {len(body_bytes)}B vs source {len(src_bytes)}B")
            failures += 1
            continue
        actual_sha = hashlib.sha256(src_bytes).hexdigest()
        if declared_sha != actual_sha:
            print(f"[check] SHA DRIFT {src}: declared {declared_sha[:16]}… actual {actual_sha[:16]}…")
            failures += 1
            continue
        print(f"[check] OK  {src} ({len(src_bytes):,}B, sha256={actual_sha[:16]}…)")
    return failures


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(check())
    build()
