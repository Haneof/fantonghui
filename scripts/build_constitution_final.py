#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the single unified AIOS v3.0 FINAL constitution.

This script does NOT rewrite the wording of any source document. It only:
  1. strips each source file's own H1 title line and its leading front-matter
     block (the metadata lines + the first horizontal rule),
  2. shifts every markdown heading down by a fixed offset so that the merged
     document has exactly one H1 and a consistent 编 / 章 / 条 hierarchy,
  3. concatenates the bodies under a newly written 法统总纲 + table of contents.

Text inside fenced code blocks is never touched.

Usage:  python3 scripts/build_constitution_final.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONST = REPO / "docs" / "constitution"
OUT = CONST / "AIOS_Constitution_v3.0_FINAL.md"

BUILD_DATE = "2026-09-18"


@dataclass
class Source:
    """One source document to be folded into the final constitution."""

    path: Path
    part_heading: str          # the '## ...' heading this document lives under
    lead: str = ""             # editorial note written above the imported body
    offset: int = 1            # how many levels every heading is pushed down
    drop_front_matter: bool = True
    section: str = ""          # if set, import only this heading's subtree
    body: str = field(default="", init=False)


SOURCES: list[Source] = [
    Source(
        path=CONST / "AIOS_THE_AI_OPERATED_SYSTEM_MANIFESTO.md",
        part_heading="## 第零编：立国宣言（AIOS 究竟是什么）",
        lead=(
            "> **法统地位**：ACTIVE。本编为对第一条《一句话定义》的根本性释法，"
            "原件 `AIOS_THE_AI_OPERATED_SYSTEM_MANIFESTO.md`，逐字并入，未作改写。"
        ),
        offset=1,
    ),
    Source(
        path=CONST / "AIOS核心系统宪法v3.0.md",
        part_heading="",  # 主宪法直接铺开六编，不额外套一层
        lead="",
        offset=1,
    ),
    Source(
        path=CONST / "v3.0.1_规范裁决集_ADJ-001-012.md",
        part_heading="## 第七编：v3.0.1 规范裁决集（ADJ-001~012）",
        lead=(
            "> **法统地位**：ACTIVE。本编为宪法第 115 条二级变更程序下签发的正式裁决文本，"
            "凡与第一编至第六编原文冲突处，以本编为准。原件 `v3.0.1_规范裁决集_ADJ-001-012.md`，"
            "逐字并入，未作改写。"
        ),
        offset=1,
    ),
    Source(
        path=CONST / "AIOS宪法v3.0修改案_R5_AI认知执行运行时与驾驶权.md",
        part_heading="## 第八编：R5 修改案——AI 认知执行运行时与驾驶权",
        lead=(
            "> **法统地位**：ACTIVE（v3.0 正式增补条款）。本编确立 World / Search-Recall / "
            "AI Cognitive Runtime 三层法统与 AI 的系统驾驶权。原件 "
            "`AIOS宪法v3.0修改案_R5_AI认知执行运行时与驾驶权.md`，逐字并入，未作改写。"
        ),
        offset=1,
    ),
    Source(
        path=CONST / "AIOS宪法v3.0修改案_R6_自适应认知策略与阈值主权.md",
        part_heading="## 第九编：R6 修改案——自适应认知策略与阈值主权",
        lead=(
            "> **法统地位**：ACTIVE（v3.0 正式增补条款）。本编确立 Hard Boundary / "
            "Engineering Parameter / Cognitive Policy 三分法与阈值治理。原件 "
            "`AIOS宪法v3.0修改案_R6_自适应认知策略与阈值主权.md`，逐字并入，未作改写。"
        ),
        offset=1,
    ),
    Source(
        path=REPO / "governance" / "normative_versions" / "registry.md",
        part_heading="## 第十编：2026-09-18 Runtime Realignment 裁决",
        lead=(
            "> **法统地位**：ACTIVE。本编为现行规范注册表中登记的最新一轮正式裁决，"
            "在本卷内部冲突裁决顺序中位阶最高。原件 "
            "`governance/normative_versions/registry.md` §6，逐字并入，未作改写。"
        ),
        offset=1,
        drop_front_matter=False,
        section="## 6. 2026-09-18 Runtime Realignment 裁决",
    ),
    Source(
        path=REPO / "AIOS宪法v3.0修改案_R4.md",
        part_heading="## 附录 A：R4 修改案（CANDIDATE，未签核不生效）",
        lead=(
            "> **法统地位**：CANDIDATE。本附录尚待 architect-01 复审与 chief-01 签署，"
            "**在签核前不具备最高法效力**，不得单独作为开发依据；其中已被第七编至第九编吸收的语义，"
            "以已生效正文为准。原件 `AIOS宪法v3.0修改案_R4.md`，逐字并入，未作改写。"
        ),
        offset=1,
    ),
    Source(
        path=CONST / "AIOS_Core_终极认知形态演进路线图_Phase1至Phase3.md",
        part_heading="## 附录 B：终极认知形态演进路线图（NON-NORMATIVE）",
        lead=(
            "> **法统地位**：NON-NORMATIVE。本附录为战略路线与研发计划，"
            "不自动获得最高法效力，不得用以覆盖第零编至第九编的任何条款。原件 "
            "`AIOS_Core_终极认知形态演进路线图_Phase1至Phase3.md`，逐字并入，未作改写。"
        ),
        offset=1,
    ),
]

FENCE = re.compile(r"^\s{0,3}(```|~~~)")
HEADING = re.compile(r"^(#{1,6})(\s+)(.*)$")


def split_lines_outside_fences(text: str):
    """Yield (line, in_fence) pairs so callers never rewrite fenced content."""
    in_fence = False
    fence_token = ""
    for line in text.splitlines():
        m = FENCE.match(line)
        if m:
            token = m.group(1)
            if not in_fence:
                in_fence, fence_token = True, token
                yield line, True
                continue
            if token == fence_token:
                in_fence, fence_token = False, ""
                yield line, True
                continue
        yield line, in_fence


def strip_front_matter(text: str) -> str:
    """Remove the document's own H1 line and the metadata block before the first '---'."""
    lines = text.splitlines()
    start = 0
    # drop leading H1 (and an immediately following '## ——' subtitle line)
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start < len(lines) and lines[start].startswith("# "):
        start += 1
        if start < len(lines) and lines[start].startswith("## ——"):
            start += 1
    # drop everything up to and including the first horizontal rule, but only if
    # that rule appears early (i.e. it really is the front-matter separator)
    for i in range(start, min(start + 40, len(lines))):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1 :]).strip("\n")
    return "\n".join(lines[start:]).strip("\n")


def extract_section(text: str, heading: str) -> str:
    """Return the body of `heading`'s subtree, with the heading line removed."""
    target = heading.strip()
    level = len(target) - len(target.lstrip("#"))
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == target:
            start = i + 1
            break
    if start is None:
        raise SystemExit(f"section not found: {heading}")
    end = len(lines)
    for j in range(start, len(lines)):
        m = HEADING.match(lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break
    return "\n".join(lines[start:end]).strip("\n")


def shift_headings(text: str, offset: int) -> str:
    out = []
    for line, in_fence in split_lines_outside_fences(text):
        if in_fence:
            out.append(line)
            continue
        m = HEADING.match(line)
        if m:
            level = min(len(m.group(1)) + offset, 6)
            out.append("#" * level + m.group(2) + m.group(3))
        else:
            out.append(line)
    return "\n".join(out)


def slugify(title: str) -> str:
    slug = title.strip().lower()
    slug = re.sub(r"[^\w\u4e00-\u9fff\- ]+", "", slug)
    slug = slug.replace(" ", "-")
    return slug


def build_toc(body: str, max_level: int = 3) -> str:
    seen: dict[str, int] = {}
    rows = []
    for line, in_fence in split_lines_outside_fences(body):
        if in_fence:
            continue
        m = HEADING.match(line)
        if not m:
            continue
        level = len(m.group(1))
        if level < 2 or level > max_level:
            continue
        title = m.group(3).strip()
        slug = slugify(title)
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        anchor = slug if n == 0 else f"{slug}-{n}"
        rows.append(f"{'  ' * (level - 2)}- [{title}](#{anchor})")
    return "\n".join(rows)


def main() -> None:
    chunks: list[str] = []

    for src in SOURCES:
        raw = src.path.read_text(encoding="utf-8")
        if src.section:
            body = extract_section(raw, src.section)
        elif src.drop_front_matter:
            body = strip_front_matter(raw)
        else:
            body = raw
        body = shift_headings(body, src.offset)
        piece = []
        if src.part_heading:
            piece.append(src.part_heading)
            piece.append("")
        if src.lead:
            piece.append(src.lead)
            piece.append("")
        piece.append(body.strip("\n"))
        chunks.append("\n".join(piece).strip("\n"))

    merged_body = "\n\n---\n\n".join(chunks)

    header = f"""# AIOS 核心系统宪法 v3.0 · 终极统一版（FINAL）

> **文件编号**：AIOS-CONST-V3.0-FINAL
> **状态**：ACTIVE —— AIOS Core 项目唯一宪法基线与唯一阅读入口
> **编纂日期**：{BUILD_DATE}
> **编纂方式**：机械合卷（`scripts/build_constitution_final.py`）。本文件由下列现行法统文件**逐字整合**而成，
> 仅重排标题层级与编次，**未改写、未删减、未新增任何条款正文**。
> **法律效力**：本文件与各原件内容等同；原件保留归档，供溯源与哈希校验，不再作为独立开发依据分别解读。

---

## 编纂总纲（本编为新增导读，不创设新条款）

### 一、为什么要有这一卷

AIOS v3.0 的法统此前分散在一份主宪法、一份立国宣言、一份规范裁决集、两份正式增补修改案、
一份候选修改案与一份路线图中。开发者、审计者与 Agent 必须同时读齐七份文件才能得到完整法意，
任何一份被漏读都会直接造成认知分裂与违宪实现。本卷把它们合为**一份可从头读到尾的完整宪法**。

### 二、本卷的组成与法统层级

| 编次 | 来源原件 | 法统地位 | 说明 |
|---|---|---|---|
| 第零编 | `AIOS_THE_AI_OPERATED_SYSTEM_MANIFESTO.md` | ACTIVE | 立国宣言，对第一条的根本释法 |
| 第一编~第六编 | `AIOS核心系统宪法v3.0.md` | ACTIVE | 主宪法本体，六编三十三章一百一十六条 |
| 第七编 | `v3.0.1_规范裁决集_ADJ-001-012.md` | ACTIVE | 12 项正式裁决，冲突时优先于主宪法原文 |
| 第八编 | `AIOS宪法v3.0修改案_R5_...md` | ACTIVE | AI Cognitive Runtime 与系统驾驶权 |
| 第九编 | `AIOS宪法v3.0修改案_R6_...md` | ACTIVE | 自适应认知策略与阈值主权 |
| 第十编 | `governance/normative_versions/registry.md` §6 | ACTIVE | 2026-09-18 Runtime Realignment 裁决 |
| 附录 A | `AIOS宪法v3.0修改案_R4.md` | CANDIDATE | 待签核，**当前不生效** |
| 附录 B | `AIOS_Core_终极认知形态演进路线图_...md` | NON-NORMATIVE | 战略路线，不具最高法效力 |

### 三、冲突裁决顺序（本卷内部）

```text
第十编（2026-09-18 Runtime Realignment 裁决）
  > 第八编 / 第九编（R5、R6 正式增补）
  > 第七编（v3.0.1 规范裁决集）
  > 第一编~第六编（主宪法原文）
  > 第零编（立国宣言，用于释法而非推翻具体契约）
  > 附录 A（候选，签核前无效）
  > 附录 B（非规范）
```

同一层级内，后生效且明确处理同一事项的文本优先于旧表述。
R5 / R6 / ADJ 不取消主宪法关于数据完整性、安全、权限与历史不可篡改的任何硬边界。
**“测试曾经是绿的”不构成恢复已被后续法统废止行为的理由。**

### 四、与既有治理工件的关系

1. `governance/normative_versions/registry.md` 仍为现行规范的注册入口；本卷是其登记的正文合卷。
2. 条款引用一律遵循第七编 ADJ-011 的**稳定键**制度（`C{{章节序}}-{{语义键}}` + 版本哈希），裸条号仅作友好别名。
3. 本卷不替代 `governance/tunable_parameters.md` 与 `governance/runtime_policy.json`；
   属于认知策略的参数按第九编补齐 `mutable_by_ai`、Evidence、Version 与 Rollback 语义。
4. 历史沿革（AIOS 宪法 2.0 与 R1/R2/R3）为 `HISTORICAL`，见 `history/` 目录，已被本卷吸收者以本卷为准。

### 五、修改纪律

本卷的任何实质性修改必须遵循第六编第一百一十五条的三级变更制度；
涉及 ADJ-001、ADJ-004 的实质变更必须重走全量 G0 合议并重新签发。
合卷本身不得被用作夹带修改的通道——**如需修法，先修原件，再重新执行合卷脚本。**

---

## 目录

{{TOC}}

---
"""

    toc = build_toc(header.replace("{TOC}", "") + "\n" + merged_body)
    document = header.replace("{TOC}", toc) + "\n" + merged_body + "\n"

    # 第十编 is injected from the governance registry ruling section.
    OUT.write_text(document, encoding="utf-8")
    print(f"wrote {OUT} ({len(document)} chars)")


if __name__ == "__main__":
    main()
